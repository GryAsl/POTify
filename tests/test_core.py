"""Compact critical tests for POTify core image processing, conversion pipeline, and safety."""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from potify.constants import (
    AUTO_POT_NEAREST,
    AUTO_POT_NEXT,
    EXISTING_OVERWRITE,
    EXISTING_RENAME,
    EXISTING_SKIP,
    FILTER_LANCZOS,
    FIT_MODE_FILL,
    FIT_MODE_FIT,
    FIT_MODE_STRETCH,
    METHOD_FIXED,
)
from potify.converter import (
    convert_batch,
    convert_single_image,
    discover_images,
    resolve_destination_path,
)
from potify.image_utils import (
    calculate_auto_pot,
    calculate_percentage_dimensions,
    prepare_for_export,
    resize_image,
)
from potify.models import ConversionConfig


# 1) Headless end-to-end conversion smoke across representative input/output and nested folder preservation
def test_headless_end_to_end_smoke(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    # Representative assets: root PNG with alpha, nested JPG in subfolder, nested WebP
    Image.new("RGBA", (300, 180), (255, 100, 50, 128)).save(in_dir / "sprite.png")
    sub_dir = in_dir / "world" / "tiles"
    sub_dir.mkdir(parents=True)
    Image.new("RGB", (640, 480), (80, 160, 40)).save(sub_dir / "grass.jpg")
    ui_dir = in_dir / "ui"
    ui_dir.mkdir()
    Image.new("RGBA", (150, 150), (200, 200, 255, 200)).save(ui_dir / "badge.webp")

    config = ConversionConfig(
        input_dir=in_dir,
        output_dir=out_dir,
        include_subfolders=True,
        resize_method=METHOD_FIXED,
        target_width=512,
        target_height=256,
        fit_mode=FIT_MODE_FIT,
        filter_name=FILTER_LANCZOS,
        output_format="WebP",
    )

    batch_res = convert_batch(config)
    assert batch_res.total_discovered == 3
    assert batch_res.converted == 3
    assert batch_res.failed == 0

    # Verify nested folder structure and dimensions preserved
    out_sprite = out_dir / "sprite.webp"
    out_grass = out_dir / "world" / "tiles" / "grass.webp"
    out_badge = out_dir / "ui" / "badge.webp"
    assert out_sprite.is_file() and out_grass.is_file() and out_badge.is_file()

    with Image.open(out_sprite) as im:
        assert im.size == (512, 256)
        assert im.format == "WEBP"


# 2) Core resize math in one compact parametrized test: percentage minimum 1px, fixed Fit/Fill/Stretch, Next/Nearest POT
@pytest.mark.parametrize("category", ["scaling_and_pot", "fixed_fit_modes"])
def test_core_resize_math(category: str) -> None:
    if category == "scaling_and_pot":
        assert calculate_percentage_dimensions(256, 256, 50) == (128, 128)
        assert calculate_percentage_dimensions(1, 1, 1) == (1, 1)  # Minimum 1px guarantee
        assert calculate_auto_pot(300, 180, mode=AUTO_POT_NEXT) == (512, 256)
        assert calculate_auto_pot(300, 180, mode=AUTO_POT_NEAREST) == (256, 128)
    elif category == "fixed_fit_modes":
        resample = Image.Resampling.NEAREST
        src = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
        # Stretch
        stretched = resize_image(src, (256, 128), METHOD_FIXED, fit_mode=FIT_MODE_STRETCH, resample_filter=resample)
        assert stretched.size == (256, 128)
        # Fit with transparent padding
        fitted = resize_image(src, (200, 200), METHOD_FIXED, fit_mode=FIT_MODE_FIT, resample_filter=resample, target_has_alpha=True)
        assert fitted.size == (200, 200) and fitted.getpixel((0, 0))[3] == 0
        # Fill with centered crop
        filled = resize_image(src, (100, 100), METHOD_FIXED, fit_mode=FIT_MODE_FILL, resample_filter=resample)
        assert filled.size == (100, 100)


# 3) Alpha image safely converts to JPG/RGB and extension/format agree
def test_alpha_safely_converts_to_jpg_and_formats_agree(tmp_path: Path) -> None:
    rgba_img = Image.new("RGBA", (64, 64), (255, 0, 0, 128))

    # Test export preparation flattening to RGB
    export_img, kwargs = prepare_for_export(rgba_img, pil_format="JPEG", matte_color=(0, 0, 0))
    assert export_img.mode == "RGB"
    assert export_img.size == (64, 64)
    assert kwargs.get("quality") == 95

    # PNG / WebP alpha preservation
    png_exp, _ = prepare_for_export(rgba_img, pil_format="PNG")
    assert png_exp.mode == "RGBA"
    webp_exp, _ = prepare_for_export(rgba_img, pil_format="WEBP")
    assert webp_exp.mode == "RGBA"

    # End-to-end file export to ensure format and extension match
    src_file = tmp_path / "trans.png"
    dest_jpg = tmp_path / "trans.jpg"
    rgba_img.save(src_file)

    cfg = ConversionConfig(
        input_dir=tmp_path,
        output_dir=tmp_path,
        resize_method=METHOD_FIXED,
        target_width=64,
        target_height=64,
        output_format="JPG",
    )
    res = convert_single_image(src_file, dest_jpg, cfg)
    assert res.status == "converted"
    with Image.open(dest_jpg) as im:
        assert im.format == "JPEG"
        assert im.mode == "RGB"


# 4) Conflict handling (skip/rename/overwrite) in one coherent test
def test_conflict_handling(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    src = in_dir / "icon.png"
    src.touch()
    existing_dest = out_dir / "icon.webp"
    existing_dest.touch()

    # Overwrite strategy
    dest_ow, skip_ow = resolve_destination_path(
        src, in_dir, out_dir, True, ".webp", EXISTING_OVERWRITE
    )
    assert dest_ow == existing_dest
    assert skip_ow is False

    # Skip strategy
    dest_sk, skip_sk = resolve_destination_path(
        src, in_dir, out_dir, True, ".webp", EXISTING_SKIP
    )
    assert dest_sk == existing_dest
    assert skip_sk is True

    # Rename strategy
    dest_rn, skip_rn = resolve_destination_path(
        src, in_dir, out_dir, True, ".webp", EXISTING_RENAME
    )
    assert dest_rn == out_dir / "icon_1.webp"
    assert skip_rn is False


# 5) Directory safety: identical input/output rejection and nested output not rescanned
def test_directory_safety(tmp_path: Path) -> None:
    in_dir = tmp_path / "data"
    in_dir.mkdir()

    # Identical input and output rejection
    cfg = ConversionConfig(input_dir=in_dir, output_dir=in_dir)
    with pytest.raises(ValueError, match="identical"):
        convert_batch(cfg)

    # Nested output not rescanned
    nested_out = in_dir / "converted_cache"
    nested_out.mkdir()
    (in_dir / "image.png").touch()
    (nested_out / "cached.png").touch()

    discovered = discover_images(in_dir, include_subfolders=True, output_dir=nested_out)
    assert len(discovered) == 1
    assert discovered[0].name == "image.png"


# 6) Transactional failure safety: failed save/replace preserves source and existing destination and cleans temp output
def test_transactional_failure_safety(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    src = in_dir / "photo.png"
    dest = out_dir / "photo.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(src)

    orig_dest_content = b"EXISTING_ORIGINAL_DESTINATION"
    dest.write_bytes(orig_dest_content)

    def failing_save(*args: Any, **kwargs: Any) -> None:
        raise OSError("Simulated disk write error")

    monkeypatch.setattr(Image.Image, "save", failing_save)

    cfg = ConversionConfig(input_dir=in_dir, output_dir=out_dir, delete_source=True)
    res = convert_single_image(src, dest, cfg)

    assert res.status == "failed"
    assert src.is_file()  # Source preserved
    assert dest.read_bytes() == orig_dest_content  # Existing destination uncorrupted
    assert len(list(out_dir.glob(".tmp_*"))) == 0  # Temp files cleaned up


# 7) Delete-after-success deletes only successfully converted sources, never failed ones
def test_delete_after_success(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    good_src = in_dir / "valid.png"
    Image.new("RGB", (32, 32), (255, 0, 0)).save(good_src)

    bad_src = in_dir / "corrupted.png"
    bad_src.write_text("invalid binary payload")

    cfg = ConversionConfig(
        input_dir=in_dir,
        output_dir=out_dir,
        delete_source=True,
        output_format="PNG",
    )
    res = convert_batch(cfg)
    assert res.converted == 1
    assert res.failed == 1

    assert not good_src.exists()  # Successfully converted source safely deleted
    assert bad_src.exists()  # Failed source untouched
