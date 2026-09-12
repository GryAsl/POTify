"""Image mathematics, Power-of-Two algorithms, resizing, and format conversion utilities."""

import math
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from potify.constants import (
    AUTO_POT_NEAREST,
    AUTO_POT_NEXT,
    DEFAULT_MATTE_COLOR,
    FILTER_BICUBIC,
    FILTER_BILINEAR,
    FILTER_LANCZOS,
    FILTER_NEAREST,
    FIT_MODE_FILL,
    FIT_MODE_FIT,
    FIT_MODE_STRETCH,
    FORMAT_TO_EXT_AND_PIL,
    FORMATS_WITH_ALPHA,
    METHOD_PERCENTAGE,
    SUPPORTED_EXTENSIONS,
)


def is_power_of_two(n: int) -> bool:
    """Return True if n is a positive power of two."""
    return n > 0 and (n & (n - 1)) == 0


def next_power_of_two(n: int) -> int:
    """Return the next power of two greater than or equal to n.

    Guaranteed to return at least 1.
    """
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def nearest_power_of_two(n: int) -> int:
    """Return the power of two closest to n.

    Guaranteed to return at least 1.
    """
    if n <= 1:
        return 1
    bit_len = n.bit_length()
    low = 1 << (bit_len - 1)
    high = low << 1
    if (n - low) < (high - n):
        return low
    return high


def calculate_auto_pot(
    width: int, height: int, mode: str = AUTO_POT_NEXT
) -> tuple[int, int]:
    """Calculate independent Power-of-Two dimensions for rectangular or square assets."""
    if mode == AUTO_POT_NEAREST:
        return (nearest_power_of_two(width), nearest_power_of_two(height))
    return (next_power_of_two(width), next_power_of_two(height))


def calculate_percentage_dimensions(
    orig_w: int, orig_h: int, percentage: float
) -> tuple[int, int]:
    """Calculate target dimensions given a percentage scale, bounded to at least 1px."""
    pct = max(0.01, float(percentage))
    new_w = max(1, round(orig_w * (pct / 100.0)))
    new_h = max(1, round(orig_h * (pct / 100.0)))
    return (new_w, new_h)


def get_pil_resampling(filter_name: str) -> Image.Resampling:
    """Map UI filter names to Pillow resampling filters."""
    mapping = {
        FILTER_NEAREST: Image.Resampling.NEAREST,
        FILTER_BILINEAR: Image.Resampling.BILINEAR,
        FILTER_BICUBIC: Image.Resampling.BICUBIC,
        FILTER_LANCZOS: Image.Resampling.LANCZOS,
    }
    return mapping.get(filter_name, Image.Resampling.NEAREST)


def resolve_output_format_info(
    source_path: Path, output_format_choice: str
) -> tuple[str, str, bool]:
    """Determine target file extension, PIL format name, and alpha support.

    Returns: (extension with dot, pil_format_string, supports_alpha)
    """
    if output_format_choice == "Same as Source":
        ext = source_path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            return (".jpg", "JPEG", False)
        elif ext == ".png":
            return (".png", "PNG", True)
        elif ext == ".webp":
            return (".webp", "WEBP", True)
        elif ext == ".bmp":
            return (".bmp", "BMP", False)
        elif ext == ".tga":
            return (".tga", "TGA", True)
        else:
            # Fallback to PNG
            return (".png", "PNG", True)

    ext, pil_fmt = FORMAT_TO_EXT_AND_PIL.get(
        output_format_choice, (".png", "PNG")
    )
    supports_alpha = pil_fmt in FORMATS_WITH_ALPHA
    return (ext, pil_fmt, supports_alpha)


def resize_image(
    image: Image.Image,
    target_size: tuple[int, int],
    method: str,
    fit_mode: str,
    resample_filter: Image.Resampling,
    matte_color: tuple[int, int, int] = DEFAULT_MATTE_COLOR,
    target_has_alpha: bool = True,
) -> Image.Image:
    """Resize image according to sizing method, fit mode, and target size.

    Handles Fit, Fill, Stretch, and Percentage modes correctly with transparency
    or matte background preservation.
    """
    target_w, target_h = max(1, target_size[0]), max(1, target_size[1])
    orig_w, orig_h = image.size

    # Fast path: if dimensions match exactly
    if orig_w == target_w and orig_h == target_h:
        return image.copy()

    # In Percentage mode or Stretch mode, resize directly to target dimensions
    if method == METHOD_PERCENTAGE or fit_mode == FIT_MODE_STRETCH:
        return image.resize((target_w, target_h), resample=resample_filter)

    if fit_mode == FIT_MODE_FIT:
        # Scale to fit completely inside target bounding box
        scale = min(target_w / orig_w, target_h / orig_h)
        scaled_w = max(1, round(orig_w * scale))
        scaled_h = max(1, round(orig_h * scale))
        scaled_img = image.resize((scaled_w, scaled_h), resample=resample_filter)

        # Center inside target bounding canvas
        pos_x = (target_w - scaled_w) // 2
        pos_y = (target_h - scaled_h) // 2

        if target_has_alpha:
            canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            if scaled_img.mode != "RGBA":
                scaled_img_rgba = scaled_img.convert("RGBA")
            else:
                scaled_img_rgba = scaled_img
            canvas.paste(scaled_img_rgba, (pos_x, pos_y), mask=scaled_img_rgba.split()[3])
            return canvas
        else:
            canvas = Image.new("RGB", (target_w, target_h), matte_color)
            if scaled_img.mode in ("RGBA", "LA", "PA"):
                rgba = scaled_img.convert("RGBA")
                canvas.paste(rgba, (pos_x, pos_y), mask=rgba.split()[3])
            else:
                canvas.paste(scaled_img.convert("RGB"), (pos_x, pos_y))
            return canvas

    elif fit_mode == FIT_MODE_FILL:
        # Scale to cover target bounding box, cropping excess from center
        scale = max(target_w / orig_w, target_h / orig_h)
        scaled_w = max(1, round(orig_w * scale))
        scaled_h = max(1, round(orig_h * scale))
        scaled_img = image.resize((scaled_w, scaled_h), resample=resample_filter)

        crop_x = (scaled_w - target_w) // 2
        crop_y = (scaled_h - target_h) // 2
        return scaled_img.crop(
            (crop_x, crop_y, crop_x + target_w, crop_y + target_h)
        )

    # Fallback to standard resize
    return image.resize((target_w, target_h), resample=resample_filter)


def prepare_for_export(
    image: Image.Image,
    pil_format: str,
    matte_color: tuple[int, int, int] = DEFAULT_MATTE_COLOR,
) -> tuple[Image.Image, dict[str, Any]]:
    """Prepare PIL image for saving to specified format.

    Ensures alpha flattening for JPEG/BMP and optimal save kwargs.
    Returns: (export_image, save_kwargs)
    """
    save_kwargs: dict[str, Any] = {}

    if pil_format == "JPEG":
        save_kwargs["quality"] = 95
        save_kwargs["optimize"] = True

        # Flatten any transparency safely
        has_transparency = (
            image.mode in ("RGBA", "LA", "PA")
            or (image.mode == "P" and "transparency" in image.info)
        )
        if has_transparency:
            rgba = image.convert("RGBA")
            bg = Image.new("RGB", rgba.size, matte_color)
            bg.paste(rgba, (0, 0), mask=rgba.split()[3])
            return bg, save_kwargs
        elif image.mode != "RGB":
            return image.convert("RGB"), save_kwargs
        return image, save_kwargs

    elif pil_format == "BMP":
        # Standard BMP: flatten alpha to RGB to avoid compatibility issues
        if image.mode in ("RGBA", "LA", "PA") or (
            image.mode == "P" and "transparency" in image.info
        ):
            rgba = image.convert("RGBA")
            bg = Image.new("RGB", rgba.size, matte_color)
            bg.paste(rgba, (0, 0), mask=rgba.split()[3])
            return bg, save_kwargs
        elif image.mode != "RGB":
            return image.convert("RGB"), save_kwargs
        return image, save_kwargs

    elif pil_format == "WEBP":
        save_kwargs["quality"] = 95
        save_kwargs["method"] = 6
        if image.mode in ("RGBA", "LA", "PA"):
            return image.convert("RGBA"), save_kwargs
        elif image.mode not in ("RGB", "RGBA", "L"):
            return image.convert("RGBA"), save_kwargs
        return image, save_kwargs

    elif pil_format == "PNG":
        save_kwargs["optimize"] = True
        save_kwargs["compress_level"] = 6
        if image.mode in ("RGBA", "LA", "PA"):
            return image.convert("RGBA"), save_kwargs
        elif image.mode not in ("RGB", "RGBA", "L", "1"):
            return image.convert("RGBA"), save_kwargs
        return image, save_kwargs

    elif pil_format == "TGA":
        if image.mode in ("RGBA", "LA", "PA"):
            return image.convert("RGBA"), save_kwargs
        elif image.mode not in ("RGB", "RGBA", "L"):
            return image.convert("RGB"), save_kwargs
        return image, save_kwargs

    return image, save_kwargs
