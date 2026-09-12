"""Core batch image converter engine for POTify.

Provides filesystem discovery, subfolder mapping, conflict resolution,
safe format conversion, verified deletion, and cancellation semantics.
Completely independent of the GUI framework.
"""

import os
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError

from potify.constants import (
    EXISTING_OVERWRITE,
    EXISTING_RENAME,
    EXISTING_SKIP,
    METHOD_PERCENTAGE,
    SUPPORTED_EXTENSIONS,
)
from potify.image_utils import (
    calculate_auto_pot,
    calculate_percentage_dimensions,
    get_pil_resampling,
    prepare_for_export,
    resize_image,
    resolve_output_format_info,
)
from potify.models import BatchResult, ConversionConfig, FileResult

ProgressCallback = Callable[[int, int, str, FileResult], None]


def discover_images(
    input_dir: Path,
    include_subfolders: bool = True,
    output_dir: Optional[Path] = None,
) -> list[Path]:
    """Scan and return all supported image files in input_dir.

    If include_subfolders is True, recursively scans nested directories.
    If output_dir is nested under input_dir, excludes the output subtree so
    generated files are never rescanned.
    If output_dir is an ancestor of input_dir, scans input_dir normally.
    """
    if not input_dir or not input_dir.is_dir():
        return []

    images: list[Path] = []
    resolved_input = input_dir.resolve()
    resolved_output = output_dir.resolve() if output_dir else None

    # Check if output is strictly nested inside input
    output_is_nested_under_input = False
    if resolved_output and resolved_output != resolved_input:
        try:
            resolved_output.relative_to(resolved_input)
            output_is_nested_under_input = True
        except ValueError:
            output_is_nested_under_input = False

    if include_subfolders:
        for root, dirs, files in os.walk(input_dir):
            root_path = Path(root).resolve()

            # If output is nested under input, exclude the output subtree
            if output_is_nested_under_input and resolved_output:
                if root_path == resolved_output:
                    dirs.clear()
                    continue
                # Exclude output dir from dirs to traverse
                dirs[:] = [
                    d for d in dirs
                    if (root_path / d).resolve() != resolved_output
                ]

            for filename in files:
                file_path = Path(root) / filename
                if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    images.append(file_path)
    else:
        for item in input_dir.iterdir():
            if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
                images.append(item)

    images.sort(key=lambda p: str(p).lower())
    return images


def resolve_destination_path(
    source_path: Path,
    input_dir: Path,
    output_dir: Path,
    include_subfolders: bool,
    target_ext: str,
    existing_action: str,
) -> tuple[Path, bool]:
    """Calculate output path preserving subfolders and handling filename conflicts.

    Returns: (resolved_dest_path, should_skip)
    """
    if include_subfolders:
        try:
            rel_parent = source_path.relative_to(input_dir).parent
            dest_dir = output_dir / rel_parent
        except ValueError:
            dest_dir = output_dir
    else:
        dest_dir = output_dir

    base_stem = source_path.stem
    target_filename = f"{base_stem}{target_ext}"
    dest_path = dest_dir / target_filename

    if not dest_path.exists():
        return (dest_path, False)

    # Destination already exists; apply conflict strategy
    if existing_action == EXISTING_SKIP:
        return (dest_path, True)
    elif existing_action == EXISTING_OVERWRITE:
        return (dest_path, False)
    elif existing_action == EXISTING_RENAME:
        counter = 1
        while True:
            candidate = dest_dir / f"{base_stem}_{counter}{target_ext}"
            if not candidate.exists():
                return (candidate, False)
            counter += 1

    return (dest_path, False)


def convert_single_image(
    source_path: Path, dest_path: Path, config: ConversionConfig
) -> FileResult:
    """Convert and resize an individual image asset according to config specifications."""
    result = FileResult(source_path=source_path, dest_path=dest_path)

    try:
        with Image.open(source_path) as img:
            orig_w, orig_h = img.size
            result.source_dims = (orig_w, orig_h)

            # Determine target dimensions
            if config.resize_method == METHOD_PERCENTAGE:
                target_w, target_h = calculate_percentage_dimensions(
                    orig_w, orig_h, config.scale_percentage
                )
            else:
                if config.auto_pot:
                    target_w, target_h = calculate_auto_pot(
                        orig_w, orig_h, config.auto_pot_mode
                    )
                else:
                    target_w = max(1, config.target_width)
                    target_h = max(1, config.target_height)

            result.dest_dims = (target_w, target_h)

            # Determine format & alpha capability
            target_ext, pil_fmt, supports_alpha = resolve_output_format_info(
                source_path, config.output_format
            )

            # Resample & resize
            resample_filter = get_pil_resampling(config.filter_name)
            resized_img = resize_image(
                image=img,
                target_size=(target_w, target_h),
                method=config.resize_method,
                fit_mode=config.fit_mode,
                resample_filter=resample_filter,
                matte_color=config.matte_color,
                target_has_alpha=supports_alpha,
            )

            # Format preparation (handles JPEG flattening, webp options, etc.)
            export_img, save_kwargs = prepare_for_export(
                image=resized_img,
                pil_format=pil_fmt,
                matte_color=config.matte_color,
            )

            # Ensure parent output directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic transactional write via sibling temporary file
            temp_file = dest_path.parent / f".tmp_{uuid.uuid4().hex}_{dest_path.name}"
            try:
                export_img.save(temp_file, format=pil_fmt, **save_kwargs)
                export_img.close()
                if resized_img is not img:
                    resized_img.close()

                # Verify written temp file before replacing
                if not temp_file.is_file() or temp_file.stat().st_size == 0:
                    raise OSError(f"Generated temporary file {temp_file} is missing or empty.")

                # Atomic replacement
                os.replace(temp_file, dest_path)
            except Exception:
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass
                raise

        # Verify output integrity
        if not dest_path.is_file() or dest_path.stat().st_size == 0:
            raise OSError(f"Generated output file {dest_path} is missing or empty.")

        result.status = "converted"

    except (UnidentifiedImageError, OSError, Exception) as exc:
        result.status = "failed"
        result.error_message = f"{type(exc).__name__}: {exc}"

    return result


def convert_batch(
    config: ConversionConfig,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
) -> BatchResult:
    """Execute batch image conversion with progress tracking, error isolation, and safe deletion."""
    if not config.input_dir or not config.input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {config.input_dir}")
    if not config.output_dir:
        raise ValueError("Output directory must be specified.")

    # Prevent in-place corruption: reject identical input and output directories unconditionally
    if config.input_dir.resolve() == config.output_dir.resolve():
        raise ValueError(
            "Input and output directories cannot be identical. Please select a separate output directory."
        )

    # Scan files
    images = discover_images(
        config.input_dir,
        include_subfolders=config.include_subfolders,
        output_dir=config.output_dir,
    )

    batch_result = BatchResult(total_discovered=len(images))

    if not images:
        return batch_result

    total_count = len(images)

    for idx, source_file in enumerate(images, start=1):
        if cancel_event and cancel_event.is_set():
            batch_result.cancelled = True
            break

        # Resolve target extension
        target_ext, _, _ = resolve_output_format_info(
            source_file, config.output_format
        )

        dest_file, should_skip = resolve_destination_path(
            source_path=source_file,
            input_dir=config.input_dir,
            output_dir=config.output_dir,
            include_subfolders=config.include_subfolders,
            target_ext=target_ext,
            existing_action=config.existing_action,
        )

        if should_skip:
            file_res = FileResult(
                source_path=source_file,
                dest_path=dest_file,
                status="skipped",
            )
            batch_result.skipped += 1
            batch_result.file_results.append(file_res)
            if progress_callback:
                progress_callback(idx, total_count, source_file.name, file_res)
            continue

        # Convert
        file_res = convert_single_image(source_file, dest_file, config)

        if file_res.status == "converted":
            batch_result.converted += 1

            # Verified safe source deletion
            if config.delete_source:
                try:
                    # Strict verification checklist:
                    # 1. Output file exists on disk
                    # 2. Output file size > 0 bytes
                    # 3. Source file and destination file are not the same path
                    # 4. Conversion was strictly successful
                    src_resolved = source_file.resolve()
                    dst_resolved = dest_file.resolve()
                    if (
                        src_resolved != dst_resolved
                        and dest_file.is_file()
                        and dest_file.stat().st_size > 0
                    ):
                        source_file.unlink()
                        file_res.deleted_source = True
                except Exception as del_err:
                    # Do not mark conversion as failed if delete failed, but note warning
                    file_res.error_message = f"Converted, but source deletion failed: {del_err}"
        else:
            batch_result.failed += 1

        batch_result.file_results.append(file_res)

        if progress_callback:
            progress_callback(idx, total_count, source_file.name, file_res)

    return batch_result
