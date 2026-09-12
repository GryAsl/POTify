"""Settings persistence and configuration management for POTify."""

import json
from pathlib import Path
from typing import Any

from potify.constants import (
    AUTO_POT_MODES,
    AUTO_POT_NEXT,
    DEFAULT_HEIGHT,
    DEFAULT_SCALE_PERCENTAGE,
    DEFAULT_WIDTH,
    EXISTING_ACTIONS,
    EXISTING_OVERWRITE,
    FILTER_NEAREST,
    FIT_MODE_FIT,
    FIT_MODES,
    METHOD_FIXED,
    OUTPUT_FORMATS,
    RESIZE_FILTERS,
    SIZING_METHODS,
)
from potify.models import ConversionConfig

CONFIG_DIR = Path.home() / ".potify"
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "last_input_folder": "",
    "last_output_folder": "",
    "resize_method": METHOD_FIXED,
    "target_width": DEFAULT_WIDTH,
    "target_height": DEFAULT_HEIGHT,
    "scale_percentage": DEFAULT_SCALE_PERCENTAGE,
    "output_format": "PNG",
    "filter_name": FILTER_NEAREST,
    "existing_action": EXISTING_OVERWRITE,
    "fit_mode": FIT_MODE_FIT,
    "auto_pot": False,
    "auto_pot_mode": AUTO_POT_NEXT,
    "include_subfolders": True,
    "delete_source": False,
}


def load_settings(config_path: Path = CONFIG_FILE) -> dict[str, Any]:
    """Load persisted settings from JSON, safely falling back to defaults if corrupted or missing."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        if not config_path.is_file():
            return settings

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            # Validate and sanitize known fields
            if data.get("resize_method") in SIZING_METHODS:
                settings["resize_method"] = data["resize_method"]
            if isinstance(data.get("target_width"), int) and data["target_width"] > 0:
                settings["target_width"] = data["target_width"]
            if isinstance(data.get("target_height"), int) and data["target_height"] > 0:
                settings["target_height"] = data["target_height"]
            if isinstance(data.get("scale_percentage"), (int, float)) and data["scale_percentage"] > 0:
                settings["scale_percentage"] = int(data["scale_percentage"])
            if data.get("output_format") in OUTPUT_FORMATS:
                settings["output_format"] = data["output_format"]
            if data.get("filter_name") in RESIZE_FILTERS:
                settings["filter_name"] = data["filter_name"]
            if data.get("existing_action") in EXISTING_ACTIONS:
                settings["existing_action"] = data["existing_action"]
            if data.get("fit_mode") in FIT_MODES:
                settings["fit_mode"] = data["fit_mode"]
            if isinstance(data.get("auto_pot"), bool):
                settings["auto_pot"] = data["auto_pot"]
            if data.get("auto_pot_mode") in AUTO_POT_MODES:
                settings["auto_pot_mode"] = data["auto_pot_mode"]
            if isinstance(data.get("include_subfolders"), bool):
                settings["include_subfolders"] = data["include_subfolders"]
            if isinstance(data.get("delete_source"), bool):
                settings["delete_source"] = data["delete_source"]

            # Paths
            if isinstance(data.get("last_input_folder"), str):
                settings["last_input_folder"] = data["last_input_folder"]
            if isinstance(data.get("last_output_folder"), str):
                settings["last_output_folder"] = data["last_output_folder"]

    except Exception:
        # If file is invalid/corrupt, fallback to defaults safely
        pass

    return settings


def save_settings(settings: dict[str, Any], config_path: Path = CONFIG_FILE) -> None:
    """Save user configuration settings to local JSON file."""
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        # Non-fatal if filesystem prevents writing config
        pass


def config_from_settings(settings: dict[str, Any]) -> ConversionConfig:
    """Instantiate a ConversionConfig dataclass from stored dictionary values."""
    input_str = settings.get("last_input_folder", "")
    output_str = settings.get("last_output_folder", "")

    input_dir = Path(input_str) if input_str else None
    output_dir = Path(output_str) if output_str else None

    return ConversionConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        include_subfolders=settings.get("include_subfolders", True),
        delete_source=settings.get("delete_source", False),
        resize_method=settings.get("resize_method", METHOD_FIXED),
        target_width=settings.get("target_width", DEFAULT_WIDTH),
        target_height=settings.get("target_height", DEFAULT_HEIGHT),
        scale_percentage=settings.get("scale_percentage", DEFAULT_SCALE_PERCENTAGE),
        fit_mode=settings.get("fit_mode", FIT_MODE_FIT),
        auto_pot=settings.get("auto_pot", False),
        auto_pot_mode=settings.get("auto_pot_mode", AUTO_POT_NEXT),
        filter_name=settings.get("filter_name", FILTER_NEAREST),
        output_format=settings.get("output_format", "PNG"),
        existing_action=settings.get("existing_action", EXISTING_OVERWRITE),
    )
