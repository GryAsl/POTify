"""Constants, theme design tokens, and configuration options for POTify."""

from typing import Final

# Supported image formats
SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tga",
)

OUTPUT_FORMATS: Final[list[str]] = [
    "Same as Source",
    "PNG",
    "JPG",
    "WebP",
    "BMP",
    "TGA",
]

FORMAT_TO_EXT_AND_PIL: Final[dict[str, tuple[str, str]]] = {
    "PNG": (".png", "PNG"),
    "JPG": (".jpg", "JPEG"),
    "WebP": (".webp", "WEBP"),
    "BMP": (".bmp", "BMP"),
    "TGA": (".tga", "TGA"),
}

# Alpha capability per format
FORMATS_WITH_ALPHA: Final[set[str]] = {"PNG", "WEBP", "TGA"}

# Sizing methods
METHOD_FIXED: Final[str] = "Fixed Resolution"
METHOD_PERCENTAGE: Final[str] = "Percentage Scale"
SIZING_METHODS: Final[list[str]] = [METHOD_FIXED, METHOD_PERCENTAGE]

# Aspect / Fit modes
FIT_MODE_FIT: Final[str] = "Fit"
FIT_MODE_FILL: Final[str] = "Fill"
FIT_MODE_STRETCH: Final[str] = "Stretch"
FIT_MODES: Final[list[str]] = [FIT_MODE_FIT, FIT_MODE_FILL, FIT_MODE_STRETCH]

# Resize Filters
FILTER_NEAREST: Final[str] = "Nearest Neighbor"
FILTER_BILINEAR: Final[str] = "Bilinear"
FILTER_BICUBIC: Final[str] = "Bicubic"
FILTER_LANCZOS: Final[str] = "Lanczos"
RESIZE_FILTERS: Final[list[str]] = [
    FILTER_NEAREST,
    FILTER_BILINEAR,
    FILTER_BICUBIC,
    FILTER_LANCZOS,
]

# Existing file handling
EXISTING_OVERWRITE: Final[str] = "Overwrite"
EXISTING_SKIP: Final[str] = "Skip"
EXISTING_RENAME: Final[str] = "Rename"
EXISTING_ACTIONS: Final[list[str]] = [
    EXISTING_OVERWRITE,
    EXISTING_SKIP,
    EXISTING_RENAME,
]

# Auto POT Modes
AUTO_POT_NEXT: Final[str] = "Next POT"
AUTO_POT_NEAREST: Final[str] = "Nearest POT"
AUTO_POT_MODES: Final[list[str]] = [AUTO_POT_NEXT, AUTO_POT_NEAREST]

# Common Power of Two presets
POT_PRESETS: Final[list[int]] = [16, 32, 64, 128, 256, 512, 1024, 2048, 4096]

# Scale Percentage presets
PERCENTAGE_PRESETS: Final[list[str]] = ["25%", "50%", "75%", "100%", "200%"]

# Default Values
DEFAULT_WIDTH: Final[int] = 256
DEFAULT_HEIGHT: Final[int] = 256
DEFAULT_SCALE_PERCENTAGE: Final[int] = 50
DEFAULT_MATTE_COLOR: Final[tuple[int, int, int]] = (0, 0, 0)

# Theme & Palette Tokens (from visual audit transcript)
COLOR_BG_BACKDROP: Final[str] = "#1b0e2e"
COLOR_BG_MAIN: Final[str] = "#160e24"
COLOR_CARD_FOLDERS: Final[str] = "#150e22"
COLOR_CARD_SETTINGS: Final[str] = "#161023"
COLOR_CARD_INFO: Final[str] = "#171123"
COLOR_CARD_BORDER: Final[str] = "#2b1f47"

COLOR_INPUT_BG: Final[str] = "#140e20"
COLOR_INPUT_BORDER: Final[str] = "#2a203e"
COLOR_INPUT_BORDER_HOVER: Final[str] = "#5e2e80"
COLOR_INPUT_BORDER_FOCUSED: Final[str] = "#a855f7"

COLOR_BTN_BROWSE_BG: Final[str] = "#181026"
COLOR_BTN_BROWSE_BORDER: Final[str] = "#3d2d5c"
COLOR_BTN_BROWSE_TEXT: Final[str] = "#ba7adb"
COLOR_BTN_BROWSE_HOVER: Final[str] = "#241838"

COLOR_DROPZONE_BORDER: Final[str] = "#69308a"
COLOR_DROPZONE_BG: Final[str] = "#181028"
COLOR_DROPZONE_TEXT: Final[str] = "#ba7adb"
COLOR_DROPZONE_HOVER_BG: Final[str] = "#23163a"

COLOR_ACCENT_PURPLE: Final[str] = "#a855f7"
COLOR_ACCENT_GLOW: Final[str] = "#8a3ded"
COLOR_CHECKBOX_CHECKED: Final[str] = "#9d4edd"

COLOR_BTN_CONVERT: Final[str] = "#9a46f4"
COLOR_BTN_CONVERT_HOVER: Final[str] = "#ac68f4"
COLOR_BTN_CANCEL: Final[str] = "#d9383a"
COLOR_BTN_CANCEL_HOVER: Final[str] = "#eb4d4f"

COLOR_PROGRESS_TRACK: Final[str] = "#231d36"
COLOR_PROGRESS_FILL: Final[str] = "#9a46f4"

COLOR_TEXT_WHITE: Final[str] = "#ffffff"
COLOR_TEXT_LIGHT: Final[str] = "#ede9f6"
COLOR_TEXT_MUTED: Final[str] = "#9d93b3"
COLOR_TEXT_SECONDARY: Final[str] = "#867e9b"
COLOR_TEXT_PLACEHOLDER: Final[str] = "#5f5773"
COLOR_TEXT_DISABLED: Final[str] = "#4d465f"
COLOR_TEXT_SUCCESS: Final[str] = "#4ade80"
COLOR_TEXT_WARNING: Final[str] = "#fbbf24"
COLOR_TEXT_ERROR: Final[str] = "#f87171"
