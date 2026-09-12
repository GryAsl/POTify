import sys
from pathlib import Path

from PIL import Image, ImageDraw


def _resolve_assets_dir() -> Path:
    """Resolve the directory containing application assets.

    Supports development source tree, PyInstaller onedir/onefile runtime
    environments (via sys._MEIPASS), and external assets folder next to the executable.
    """
    if getattr(sys, "frozen", False):
        # 1. Bundled internal assets directory (PyInstaller sys._MEIPASS)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = Path(meipass) / "assets"
            if cand.exists():
                return cand

        # 2. Assets directory adjacent to the executable
        exe_dir = Path(sys.executable).resolve().parent
        cand = exe_dir / "assets"
        if cand.exists():
            return cand

        # Fallback to sys._MEIPASS / "assets" or exe_dir / "assets"
        return Path(meipass) / "assets" if meipass else cand

    # Running from source
    return Path(__file__).resolve().parent.parent / "assets"


ASSETS_DIR = _resolve_assets_dir()
ICON_PNG_PATH = ASSETS_DIR / "icon.png"
ICON_ICO_PATH = ASSETS_DIR / "icon.ico"


def create_folder_outline_icon(
    size: int = 64,
    color: tuple[int, int, int, int] = (199, 104, 255, 255),
) -> Image.Image:
    """Return a centered, antialiased folder-outline icon for CTk buttons.

    The drawing uses a square transparent canvas with symmetric vertical padding.
    Rendering it as an image avoids the platform-dependent baseline of emoji glyphs.
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = size / 64.0

    def pt(x: int, y: int) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    stroke = max(2, round(5 * scale))
    # Visible bounds are y=15..49, centered around the canvas midpoint.
    outline = [pt(9, 23), pt(9, 18), pt(25, 18), pt(31, 24), pt(55, 24)]
    draw.line(outline, fill=color, width=stroke, joint="curve")
    draw.rounded_rectangle(
        (*pt(9, 23), *pt(55, 49)),
        radius=max(2, round(3 * scale)),
        outline=color,
        width=stroke,
    )
    return image


def ensure_icon_assets() -> Path:
    """Ensure POTify branding icon assets exist, generating them programmatically if missing.

    Renders a 3-layer isometric diamond / rhombus stack with vibrant violet/purple gradient.
    """
    if ICON_PNG_PATH.is_file() and ICON_ICO_PATH.is_file():
        return ICON_PNG_PATH

    try:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # Draw high-res isometric logo (256x256)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center_x = size // 2
    rhombus_w = 90
    rhombus_h = 42

    # 3-layer isometric rhombus stack: bottom (#6b28d4), middle (#8a3dee), top (#b860f8)
    layers = [
        (170, (107, 40, 212, 255), (78, 26, 160, 255)),   # Bottom layer
        (130, (138, 61, 238, 255), (105, 38, 195, 255)),  # Middle layer
        (90,  (184, 96, 248, 255), (145, 60, 210, 255)),  # Top layer
    ]

    for center_y, fill_col, border_col in layers:
        points = [
            (center_x, center_y - rhombus_h),
            (center_x + rhombus_w, center_y),
            (center_x, center_y + rhombus_h),
            (center_x - rhombus_w, center_y),
        ]
        draw.polygon(points, fill=fill_col, outline=border_col, width=3)

    # Save PNG
    img.save(ICON_PNG_PATH, format="PNG")

    # Save multi-size ICO
    try:
        ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ICON_ICO_PATH, format="ICO", sizes=ico_sizes)
    except Exception:
        pass

    return ICON_PNG_PATH
