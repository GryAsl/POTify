"""Data models and value objects for POTify."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from potify.constants import (
    AUTO_POT_NEXT,
    DEFAULT_HEIGHT,
    DEFAULT_MATTE_COLOR,
    DEFAULT_SCALE_PERCENTAGE,
    DEFAULT_WIDTH,
    EXISTING_OVERWRITE,
    FILTER_NEAREST,
    FIT_MODE_FIT,
    METHOD_FIXED,
)


@dataclass
class ConversionConfig:
    """Complete specification for a batch conversion run."""

    input_dir: Optional[Path] = None
    output_dir: Optional[Path] = None
    include_subfolders: bool = True
    delete_source: bool = False

    resize_method: str = METHOD_FIXED  # "Fixed Resolution" or "Percentage Scale"
    target_width: int = DEFAULT_WIDTH
    target_height: int = DEFAULT_HEIGHT
    scale_percentage: int = DEFAULT_SCALE_PERCENTAGE

    fit_mode: str = FIT_MODE_FIT  # "Fit", "Fill", "Stretch"
    auto_pot: bool = False
    auto_pot_mode: str = AUTO_POT_NEXT  # "Next POT" or "Nearest POT"

    filter_name: str = FILTER_NEAREST  # "Nearest Neighbor", "Bilinear", etc.
    output_format: str = "PNG"  # "Same as Source", "PNG", "JPG", etc.
    existing_action: str = EXISTING_OVERWRITE  # "Overwrite", "Skip", "Rename"

    matte_color: tuple[int, int, int] = DEFAULT_MATTE_COLOR


@dataclass
class FileResult:
    """Telemetry outcome for an individual asset conversion."""

    source_path: Path
    dest_path: Optional[Path] = None
    status: str = "pending"  # "converted", "skipped", "failed"
    error_message: Optional[str] = None
    source_dims: tuple[int, int] = (0, 0)
    dest_dims: tuple[int, int] = (0, 0)
    deleted_source: bool = False


@dataclass
class BatchResult:
    """Overall summary statistics and telemetry for a batch conversion."""

    total_discovered: int = 0
    converted: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: bool = False
    file_results: list[FileResult] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.converted + self.skipped + self.failed

    @property
    def errors(self) -> list[FileResult]:
        return [r for r in self.file_results if r.status == "failed"]
