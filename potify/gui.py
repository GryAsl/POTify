"""CustomTkinter GUI implementation for POTify.

Matches the visual reference specification: dark purple palette, rounded bordered cards,
drag & drop with graceful browse fallback, dynamic drop hint collapse, responsive sizing method
controls, real-time telemetry, and safe threaded execution.
"""

import queue
import threading
import time
from pathlib import Path
from tkinter import messagebox
from typing import Any, Optional

import customtkinter as ctk
from PIL import Image

from potify.assets import ICON_ICO_PATH, create_folder_outline_icon, ensure_icon_assets
from potify.config import (
    CONFIG_FILE,
    DEFAULT_SETTINGS,
    config_from_settings,
    load_settings,
    save_settings,
)
from potify.constants import (
    AUTO_POT_MODES,
    AUTO_POT_NEXT,
    COLOR_ACCENT_PURPLE,
    COLOR_BG_BACKDROP,
    COLOR_BG_MAIN,
    COLOR_BTN_BROWSE_BG,
    COLOR_BTN_BROWSE_BORDER,
    COLOR_BTN_BROWSE_HOVER,
    COLOR_BTN_BROWSE_TEXT,
    COLOR_BTN_CANCEL,
    COLOR_BTN_CANCEL_HOVER,
    COLOR_BTN_CONVERT,
    COLOR_BTN_CONVERT_HOVER,
    COLOR_CARD_BORDER,
    COLOR_CARD_FOLDERS,
    COLOR_CARD_INFO,
    COLOR_CARD_SETTINGS,
    COLOR_CHECKBOX_CHECKED,
    COLOR_INPUT_BG,
    COLOR_INPUT_BORDER,
    COLOR_PROGRESS_FILL,
    COLOR_PROGRESS_TRACK,
    COLOR_TEXT_DISABLED,
    COLOR_TEXT_ERROR,
    COLOR_TEXT_LIGHT,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PLACEHOLDER,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT_SUCCESS,
    COLOR_TEXT_WHITE,
    DEFAULT_HEIGHT,
    DEFAULT_SCALE_PERCENTAGE,
    DEFAULT_WIDTH,
    EXISTING_ACTIONS,
    EXISTING_OVERWRITE,
    FILTER_NEAREST,
    FIT_MODE_FIT,
    FIT_MODES,
    METHOD_FIXED,
    METHOD_PERCENTAGE,
    OUTPUT_FORMATS,
    PERCENTAGE_PRESETS,
    POT_PRESETS,
    RESIZE_FILTERS,
    SIZING_METHODS,
    SUPPORTED_EXTENSIONS,
)
from potify.converter import convert_batch, discover_images
from potify.models import BatchResult, ConversionConfig, FileResult

HAS_DND_MODULE = False
try:
    import tkinterdnd2

    HAS_DND_MODULE = True
except Exception:
    pass

if HAS_DND_MODULE:

    class BaseWindow(ctk.CTk, tkinterdnd2.TkinterDnD.DnDWrapper):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.dnd_available = False
            try:
                self.TkdndVersion = tkinterdnd2.TkinterDnD._require(self)
                self.dnd_available = True
            except Exception:
                self.dnd_available = False

else:

    class BaseWindow(ctk.CTk):  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.dnd_available = False


class POTifyApp(BaseWindow):
    """Main desktop application window for POTify."""

    def __init__(self) -> None:
        super().__init__()

        # Ensure branding assets
        ensure_icon_assets()

        # Appearance & theme setup
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("POTify - Resize & convert your images")

        # Screen-aware initial & minimum geometry
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        init_w = min(800, max(760, screen_w - 40))
        init_h = min(560, max(520, screen_h - 80))
        self.geometry(f"{init_w}x{init_h}")
        self.minsize(740, 520)
        self.configure(fg_color=COLOR_BG_MAIN)

        # A real image keeps the folder mark optically centered. Emoji glyphs sit
        # on the font baseline and appeared lower than the adjacent Browse text.
        browse_icon = create_folder_outline_icon()
        self.browse_folder_icon = ctk.CTkImage(
            light_image=browse_icon,
            dark_image=browse_icon,
            size=(16, 16),
        )

        if ICON_ICO_PATH.is_file():
            try:
                self.iconbitmap(str(ICON_ICO_PATH))
            except Exception:
                pass

        # Load persisted settings
        self.settings: dict[str, Any] = load_settings()

        # State tracking
        self.is_converting = False
        self.cancel_event: Optional[threading.Event] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.event_queue: queue.Queue = queue.Queue()
        self.last_batch_result: Optional[BatchResult] = None
        self.scanned_images_count = 0
        self._scan_timer: Optional[str] = None
        self.pot_preset_buttons: list[ctk.CTkButton] = []

        # Dispatcher constants & state tracking (~120 Hz responsiveness)
        self.MAX_EVENTS_PER_TICK = 32
        self.MAX_TICK_TIME_SEC = 0.005  # ~5ms limit, comfortably below 8.333ms frame budget
        self.MIN_PROGRESS_INTERVAL_SEC = 1.0 / 120.0  # <= 8.333ms (~120 Hz nominal frame interval)
        self.IDLE_POLL_INTERVAL_MS = 100
        self.BUSY_POLL_INTERVAL_MS = 8  # ~8ms busy scheduling interval

        self._queue_timer: Optional[str] = None
        self._last_progress_render_time: float = 0.0
        self._progress_lock = threading.Lock()
        self._latest_progress: Optional[tuple[Any, ...]] = None
        self._has_new_progress: bool = False
        self._progress_render_count: int = 0
        self.current_filename: str = ""

        self._scan_generation: int = 0
        self._active_scan_params: Optional[tuple[str, bool]] = None
        self._last_completed_scan_params: Optional[tuple[str, bool]] = None

        # Build GUI Components
        self._build_ui()

        # Register Drag and Drop handlers directly on entries if available
        self._setup_drag_and_drop()

        # Restore UI state from settings
        self._apply_settings_to_ui()

        # Poll event queue with adaptive scheduler
        self._schedule_prompt_queue_tick()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def publish_progress(self, progress_data: tuple[Any, ...]) -> None:
        """Thread-safe latest-progress mailbox (single-slot).

        Worker progress callbacks publish/replace the newest progress state
        here rather than enqueueing every progress event into the FIFO event_queue.
        """
        with self._progress_lock:
            self._latest_progress = progress_data
            self._has_new_progress = True

    def clear_progress(self) -> None:
        """Reset latest progress mailbox."""
        with self._progress_lock:
            self._latest_progress = None
            self._has_new_progress = False

    # -------------------------------------------------------------------------
    # UI Building
    # -------------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Construct the entire visual hierarchy with a compact non-scrolling container."""
        self.main_container = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_MAIN,
            corner_radius=0,
        )
        self.main_container.pack(fill="both", expand=True, padx=14, pady=6)

        self._build_folders_card(self.main_container)
        self._build_settings_card(self.main_container)
        self._build_info_card(self.main_container)
        self._build_action_card(self.main_container)

    def _build_folders_card(self, parent: ctk.CTkFrame) -> None:
        """Folders panel for input and output directories."""
        self.folders_card = ctk.CTkFrame(
            parent,
            fg_color=COLOR_CARD_FOLDERS,
            border_color=COLOR_CARD_BORDER,
            border_width=1,
            corner_radius=10,
        )
        self.folders_card.pack(fill="x", pady=3, padx=2)

        card_inner = ctk.CTkFrame(self.folders_card, fg_color="transparent")
        card_inner.pack(fill="x", padx=12, pady=6)

        # Card Title
        title_row = ctk.CTkFrame(card_inner, fg_color="transparent")
        title_row.pack(fill="x", pady=(0, 4))

        title_icon = ctk.CTkLabel(
            title_row,
            text="📁",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_ACCENT_PURPLE,
        )
        title_icon.pack(side="left", padx=(0, 6))

        title_lbl = ctk.CTkLabel(
            title_row,
            text="Folders",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COLOR_TEXT_WHITE,
        )
        title_lbl.pack(side="left")

        # Input Folder Row
        in_row = ctk.CTkFrame(card_inner, fg_color="transparent")
        in_row.pack(fill="x", pady=2)

        in_lbl = ctk.CTkLabel(
            in_row,
            text="Input Folder",
            width=105,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_LIGHT,
        )
        in_lbl.pack(side="left")

        self.input_entry = ctk.CTkEntry(
            in_row,
            placeholder_text="No folder selected...",
            placeholder_text_color=COLOR_TEXT_PLACEHOLDER,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            text_color=COLOR_TEXT_WHITE,
            corner_radius=6,
            height=30,
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.input_entry.bind("<KeyRelease>", lambda e: self._on_input_folder_typed())
        self.input_entry.bind("<FocusOut>", lambda e: self._on_input_folder_committed())
        self.input_entry.bind("<Return>", lambda e: self._on_input_folder_committed(force=True))

        self.input_browse_btn = ctk.CTkButton(
            in_row,
            text="Browse",
            image=self.browse_folder_icon,
            compound="left",
            anchor="center",
            border_spacing=3,
            width=90,
            height=30,
            fg_color=COLOR_BTN_BROWSE_BG,
            hover_color=COLOR_BTN_BROWSE_HOVER,
            border_color=COLOR_BTN_BROWSE_BORDER,
            border_width=1,
            text_color=COLOR_BTN_BROWSE_TEXT,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self._browse_input_folder,
        )
        self.input_browse_btn.pack(side="right")

        # Output Folder Row
        out_row = ctk.CTkFrame(card_inner, fg_color="transparent")
        out_row.pack(fill="x", pady=2)

        out_lbl = ctk.CTkLabel(
            out_row,
            text="Output Folder",
            width=105,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_LIGHT,
        )
        out_lbl.pack(side="left")

        self.output_entry = ctk.CTkEntry(
            out_row,
            placeholder_text="No folder selected...",
            placeholder_text_color=COLOR_TEXT_PLACEHOLDER,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            text_color=COLOR_TEXT_WHITE,
            corner_radius=6,
            height=30,
        )
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.output_entry.bind("<KeyRelease>", lambda e: self._on_output_folder_typed())
        self.output_entry.bind("<FocusOut>", lambda e: self._on_output_folder_committed())
        self.output_entry.bind("<Return>", lambda e: self._on_output_folder_committed())

        self.output_browse_btn = ctk.CTkButton(
            out_row,
            text="Browse",
            image=self.browse_folder_icon,
            compound="left",
            anchor="center",
            border_spacing=3,
            width=90,
            height=30,
            fg_color=COLOR_BTN_BROWSE_BG,
            hover_color=COLOR_BTN_BROWSE_HOVER,
            border_color=COLOR_BTN_BROWSE_BORDER,
            border_width=1,
            text_color=COLOR_BTN_BROWSE_TEXT,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self._browse_output_folder,
        )
        self.output_browse_btn.pack(side="right")

    def _build_settings_card(self, parent: ctk.CTkFrame) -> None:
        """Settings panel with split two-column layout."""
        self.settings_card = ctk.CTkFrame(
            parent,
            fg_color=COLOR_CARD_SETTINGS,
            border_color=COLOR_CARD_BORDER,
            border_width=1,
            corner_radius=10,
        )
        self.settings_card.pack(fill="x", pady=3, padx=2)

        card_inner = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        card_inner.pack(fill="x", padx=12, pady=6)

        # Title
        title_row = ctk.CTkFrame(card_inner, fg_color="transparent")
        title_row.pack(fill="x", pady=(0, 4))

        title_icon = ctk.CTkLabel(
            title_row,
            text="⚙",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_ACCENT_PURPLE,
        )
        title_icon.pack(side="left", padx=(0, 6))

        title_lbl = ctk.CTkLabel(
            title_row,
            text="Settings",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COLOR_TEXT_WHITE,
        )
        title_lbl.pack(side="left")

        # Split 2 Columns
        cols_frame = ctk.CTkFrame(card_inner, fg_color="transparent")
        cols_frame.pack(fill="x")
        cols_frame.grid_columnconfigure(0, weight=1)
        cols_frame.grid_columnconfigure(1, weight=1)

        # ---------------- LEFT COLUMN: Sizing Method ----------------
        left_col = ctk.CTkFrame(cols_frame, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        method_header = ctk.CTkFrame(left_col, fg_color="transparent")
        method_header.pack(fill="x", pady=(0, 3))

        method_lbl = ctk.CTkLabel(
            method_header,
            text="Resize Method",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_TEXT_WHITE,
        )
        method_lbl.pack(side="left")

        # Radio selection: Fixed vs Percentage
        self.method_var = ctk.StringVar(value=METHOD_FIXED)

        radio_frame = ctk.CTkFrame(left_col, fg_color="transparent")
        radio_frame.pack(fill="x", pady=2)

        self.radio_fixed = ctk.CTkRadioButton(
            radio_frame,
            text="Fixed Resolution",
            variable=self.method_var,
            value=METHOD_FIXED,
            fg_color=COLOR_ACCENT_PURPLE,
            border_color="#4a3e62",
            hover_color=COLOR_CHECKBOX_CHECKED,
            text_color=COLOR_TEXT_LIGHT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._on_method_changed,
        )
        self.radio_fixed.pack(side="left", padx=(0, 12))

        self.radio_percentage = ctk.CTkRadioButton(
            radio_frame,
            text="Percentage Scale",
            variable=self.method_var,
            value=METHOD_PERCENTAGE,
            fg_color=COLOR_ACCENT_PURPLE,
            border_color="#4a3e62",
            hover_color=COLOR_CHECKBOX_CHECKED,
            text_color=COLOR_TEXT_LIGHT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._on_method_changed,
        )
        self.radio_percentage.pack(side="left")

        # Fixed Dimensions Controls
        self.fixed_box = ctk.CTkFrame(
            left_col,
            fg_color="#140e22",
            corner_radius=6,
            border_color="#2b1f47",
            border_width=1,
        )
        self.fixed_box.pack(fill="x", pady=(4, 2), padx=2)

        dim_row = ctk.CTkFrame(self.fixed_box, fg_color="transparent")
        dim_row.pack(fill="x", padx=8, pady=4)

        # Width
        w_frame = ctk.CTkFrame(dim_row, fg_color="transparent")
        w_frame.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.lbl_width = ctk.CTkLabel(
            w_frame,
            text="Width",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED,
        )
        self.lbl_width.pack(anchor="w")

        self.width_entry = ctk.CTkEntry(
            w_frame,
            placeholder_text="256",
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            text_color=COLOR_TEXT_WHITE,
            height=28,
            corner_radius=6,
        )
        self.width_entry.pack(fill="x", pady=(1, 0))
        self.width_entry.insert(0, str(DEFAULT_WIDTH))
        self.width_entry.bind("<FocusOut>", lambda e: self._on_dimension_committed())
        self.width_entry.bind("<Return>", lambda e: self._on_dimension_committed())

        # Height
        h_frame = ctk.CTkFrame(dim_row, fg_color="transparent")
        h_frame.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.lbl_height = ctk.CTkLabel(
            h_frame,
            text="Height",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED,
        )
        self.lbl_height.pack(anchor="w")

        self.height_entry = ctk.CTkEntry(
            h_frame,
            placeholder_text="256",
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            text_color=COLOR_TEXT_WHITE,
            height=28,
            corner_radius=6,
        )
        self.height_entry.pack(fill="x", pady=(1, 0))
        self.height_entry.insert(0, str(DEFAULT_HEIGHT))
        self.height_entry.bind("<FocusOut>", lambda e: self._on_dimension_committed())
        self.height_entry.bind("<Return>", lambda e: self._on_dimension_committed())

        # Quick POT Presets row
        preset_row = ctk.CTkFrame(self.fixed_box, fg_color="transparent")
        preset_row.pack(fill="x", padx=8, pady=(0, 4))

        pot_lbl = ctk.CTkLabel(
            preset_row,
            text="POT Presets:",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR_TEXT_SECONDARY,
        )
        pot_lbl.pack(side="left", padx=(0, 4))

        self.pot_preset_buttons = []
        for pot_val in [128, 256, 512, 1024, 2048]:
            btn = ctk.CTkButton(
                preset_row,
                text=str(pot_val),
                width=38,
                height=22,
                fg_color="#1a1228",
                hover_color="#2b1f47",
                border_color="#3e2f5d",
                border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=COLOR_TEXT_LIGHT,
                corner_radius=4,
                command=lambda v=pot_val: self._set_pot_dimensions(v, v),
            )
            btn.pack(side="left", padx=1)
            self.pot_preset_buttons.append(btn)

        # Percentage Controls
        self.percentage_box = ctk.CTkFrame(
            left_col,
            fg_color="#140e22",
            corner_radius=6,
            border_color="#2b1f47",
            border_width=1,
        )
        self.percentage_box.pack(fill="x", pady=(4, 2), padx=2)

        pct_inner = ctk.CTkFrame(self.percentage_box, fg_color="transparent")
        pct_inner.pack(fill="x", padx=8, pady=4)

        self.lbl_scale = ctk.CTkLabel(
            pct_inner,
            text="Scale Percentage",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_LIGHT,
        )
        self.lbl_scale.pack(anchor="w")

        self.scale_menu = ctk.CTkComboBox(
            pct_inner,
            values=PERCENTAGE_PRESETS,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            text_color=COLOR_TEXT_WHITE,
            button_color=COLOR_BTN_BROWSE_BG,
            button_hover_color=COLOR_BTN_BROWSE_HOVER,
            dropdown_fg_color="#1a1228",
            dropdown_text_color=COLOR_TEXT_WHITE,
            corner_radius=6,
            height=28,
            command=lambda v: self._on_dropdown_changed(),
        )
        self.scale_menu.set(f"{DEFAULT_SCALE_PERCENTAGE}%")
        self.scale_menu.pack(fill="x", pady=(1, 3))

        self.helper_note_lbl = ctk.CTkLabel(
            pct_inner,
            text="Images will scale proportionally\n(e.g. 256×256 → 128×128)",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR_TEXT_SECONDARY,
            justify="left",
            anchor="w",
        )
        self.helper_note_lbl.pack(anchor="w")

        # ---------------- RIGHT COLUMN: Parameters & Checkboxes ----------------
        right_col = ctk.CTkFrame(cols_frame, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # Output Format
        fmt_row = ctk.CTkFrame(right_col, fg_color="transparent")
        fmt_row.pack(fill="x", pady=1.5)

        fmt_lbl = ctk.CTkLabel(
            fmt_row,
            text="Output Format",
            width=100,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_LIGHT,
        )
        fmt_lbl.pack(side="left")

        self.format_menu = ctk.CTkOptionMenu(
            fmt_row,
            values=OUTPUT_FORMATS,
            fg_color=COLOR_INPUT_BG,
            button_color=COLOR_BTN_BROWSE_BG,
            button_hover_color=COLOR_BTN_BROWSE_HOVER,
            text_color=COLOR_TEXT_WHITE,
            dropdown_fg_color="#1a1228",
            dropdown_text_color=COLOR_TEXT_WHITE,
            corner_radius=6,
            height=26,
            command=lambda v: self._on_dropdown_changed(),
        )
        self.format_menu.set("PNG")
        self.format_menu.pack(side="right", fill="x", expand=True)

        # Filter
        flt_row = ctk.CTkFrame(right_col, fg_color="transparent")
        flt_row.pack(fill="x", pady=1.5)

        flt_lbl = ctk.CTkLabel(
            flt_row,
            text="Filter",
            width=100,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_LIGHT,
        )
        flt_lbl.pack(side="left")

        self.filter_menu = ctk.CTkOptionMenu(
            flt_row,
            values=RESIZE_FILTERS,
            fg_color=COLOR_INPUT_BG,
            button_color=COLOR_BTN_BROWSE_BG,
            button_hover_color=COLOR_BTN_BROWSE_HOVER,
            text_color=COLOR_TEXT_WHITE,
            dropdown_fg_color="#1a1228",
            dropdown_text_color=COLOR_TEXT_WHITE,
            corner_radius=6,
            height=26,
            command=lambda v: self._on_dropdown_changed(),
        )
        self.filter_menu.set(FILTER_NEAREST)
        self.filter_menu.pack(side="right", fill="x", expand=True)

        # Existing Files
        ex_row = ctk.CTkFrame(right_col, fg_color="transparent")
        ex_row.pack(fill="x", pady=1.5)

        ex_lbl = ctk.CTkLabel(
            ex_row,
            text="Existing Files",
            width=100,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_LIGHT,
        )
        ex_lbl.pack(side="left")

        self.existing_menu = ctk.CTkOptionMenu(
            ex_row,
            values=EXISTING_ACTIONS,
            fg_color=COLOR_INPUT_BG,
            button_color=COLOR_BTN_BROWSE_BG,
            button_hover_color=COLOR_BTN_BROWSE_HOVER,
            text_color=COLOR_TEXT_WHITE,
            dropdown_fg_color="#1a1228",
            dropdown_text_color=COLOR_TEXT_WHITE,
            corner_radius=6,
            height=26,
            command=lambda v: self._on_dropdown_changed(),
        )
        self.existing_menu.set(EXISTING_OVERWRITE)
        self.existing_menu.pack(side="right", fill="x", expand=True)

        # Fit Mode (Disabled/Hidden in Percentage Scale)
        self.fit_row = ctk.CTkFrame(right_col, fg_color="transparent")
        self.fit_row.pack(fill="x", pady=1.5)

        self.fit_lbl = ctk.CTkLabel(
            self.fit_row,
            text="Fit Mode",
            width=100,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_LIGHT,
        )
        self.fit_lbl.pack(side="left")

        self.fit_menu = ctk.CTkOptionMenu(
            self.fit_row,
            values=FIT_MODES,
            fg_color=COLOR_INPUT_BG,
            button_color=COLOR_BTN_BROWSE_BG,
            button_hover_color=COLOR_BTN_BROWSE_HOVER,
            text_color=COLOR_TEXT_WHITE,
            dropdown_fg_color="#1a1228",
            dropdown_text_color=COLOR_TEXT_WHITE,
            corner_radius=6,
            height=26,
            command=lambda v: self._on_dropdown_changed(),
        )
        self.fit_menu.set(FIT_MODE_FIT)
        self.fit_menu.pack(side="right", fill="x", expand=True)

        # Auto POT Row
        auto_pot_row = ctk.CTkFrame(right_col, fg_color="transparent")
        auto_pot_row.pack(fill="x", pady=1.5)

        self.auto_pot_var = ctk.BooleanVar(value=False)
        self.auto_pot_chk = ctk.CTkCheckBox(
            auto_pot_row,
            text="Auto POT ⓘ",
            variable=self.auto_pot_var,
            fg_color=COLOR_ACCENT_PURPLE,
            hover_color=COLOR_CHECKBOX_CHECKED,
            border_color="#4a3e62",
            text_color=COLOR_TEXT_LIGHT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=4,
            command=self._on_auto_pot_toggled,
        )
        self.auto_pot_chk.pack(side="left")

        self.auto_pot_mode_menu = ctk.CTkOptionMenu(
            auto_pot_row,
            values=AUTO_POT_MODES,
            width=110,
            height=24,
            fg_color=COLOR_INPUT_BG,
            button_color=COLOR_BTN_BROWSE_BG,
            button_hover_color=COLOR_BTN_BROWSE_HOVER,
            text_color=COLOR_TEXT_WHITE,
            dropdown_fg_color="#1a1228",
            dropdown_text_color=COLOR_TEXT_WHITE,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            command=lambda v: self._on_auto_pot_mode_changed(),
        )
        self.auto_pot_mode_menu.set(AUTO_POT_NEXT)
        self.auto_pot_mode_menu.pack(side="right")

        # General Checkboxes
        chk_frame = ctk.CTkFrame(right_col, fg_color="transparent")
        chk_frame.pack(fill="x", pady=(3, 0))

        self.subfolders_var = ctk.BooleanVar(value=True)
        self.subfolders_chk = ctk.CTkCheckBox(
            chk_frame,
            text="Include subfolders",
            variable=self.subfolders_var,
            fg_color=COLOR_ACCENT_PURPLE,
            hover_color=COLOR_CHECKBOX_CHECKED,
            border_color="#4a3e62",
            text_color=COLOR_TEXT_LIGHT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=4,
            command=self._on_subfolders_toggled,
        )
        self.subfolders_chk.pack(anchor="w", pady=1)

        self.delete_source_var = ctk.BooleanVar(value=False)
        self.delete_source_chk = ctk.CTkCheckBox(
            chk_frame,
            text="Delete source images after successful conversion",
            variable=self.delete_source_var,
            fg_color=COLOR_ACCENT_PURPLE,
            hover_color=COLOR_CHECKBOX_CHECKED,
            border_color="#4a3e62",
            text_color=COLOR_TEXT_LIGHT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=4,
            command=self._on_delete_source_toggled,
        )
        self.delete_source_chk.pack(anchor="w", pady=1)

    def _build_info_card(self, parent: ctk.CTkFrame) -> None:
        """Info card providing asset count telemetry."""
        self.info_card = ctk.CTkFrame(
            parent,
            fg_color=COLOR_CARD_INFO,
            border_color=COLOR_CARD_BORDER,
            border_width=1,
            corner_radius=10,
        )
        self.info_card.pack(fill="x", pady=3, padx=2)

        card_inner = ctk.CTkFrame(self.info_card, fg_color="transparent")
        card_inner.pack(fill="x", padx=12, pady=5)

        title_row = ctk.CTkFrame(card_inner, fg_color="transparent")
        title_row.pack(fill="x", pady=(0, 2))

        title_icon = ctk.CTkLabel(
            title_row,
            text="ⓘ",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_ACCENT_PURPLE,
        )
        title_icon.pack(side="left", padx=(0, 6))

        title_lbl = ctk.CTkLabel(
            title_row,
            text="Info",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COLOR_TEXT_WHITE,
        )
        title_lbl.pack(side="left")

        self.telemetry_main_lbl = ctk.CTkLabel(
            card_inner,
            text="0 supported images found",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_TEXT_WHITE,
            anchor="w",
        )
        self.telemetry_main_lbl.pack(anchor="w")

    def _build_action_card(self, parent: ctk.CTkFrame) -> None:
        """Compact single-row action area with progress and telemetry."""
        self.action_container = ctk.CTkFrame(parent, fg_color="transparent")
        self.action_container.pack(fill="x", pady=(3, 1), padx=2)
        self.action_container.grid_columnconfigure(1, weight=1, minsize=110)

        # Primary Convert / Cancel Button
        self.convert_btn = ctk.CTkButton(
            self.action_container,
            text="▶  Convert",
            width=126,
            height=34,
            fg_color=COLOR_BTN_CONVERT,
            hover_color=COLOR_BTN_CONVERT_HOVER,
            corner_radius=7,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_TEXT_WHITE,
            command=self._on_convert_clicked,
        )
        self.convert_btn.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(
            self.action_container,
            height=12,
            corner_radius=6,
            fg_color=COLOR_PROGRESS_TRACK,
            progress_color=COLOR_PROGRESS_FILL,
        )
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=0, column=1, sticky="ew")

        self.progress_text_lbl = ctk.CTkLabel(
            self.action_container,
            text="Ready",
            width=118,
            anchor="center",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLOR_TEXT_LIGHT,
        )
        self.progress_text_lbl.grid(row=0, column=2, padx=(8, 6))

        self.metrics_lbl = ctk.CTkLabel(
            self.action_container,
            text="0 converted    0 skipped    0 failed",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR_TEXT_MUTED,
            anchor="e",
        )
        self.metrics_lbl.grid(row=0, column=3, sticky="e")

        # View error details button (hidden until failures exist)
        self.view_errors_btn = ctk.CTkButton(
            self.action_container,
            text="View Errors",
            width=76,
            height=24,
            fg_color="#3d1d28",
            hover_color="#5d2638",
            border_color="#7a2a3e",
            border_width=1,
            text_color=COLOR_TEXT_ERROR,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6,
            command=self._show_error_details_modal,
        )
        self.view_errors_btn.grid(row=0, column=4, padx=(6, 0))
        self.view_errors_btn.grid_remove()

    # -------------------------------------------------------------------------
    # Drag and Drop Integration
    # -------------------------------------------------------------------------
    def _setup_drag_and_drop(self) -> None:
        """Register DnD targets directly on entry fields if tkinterdnd2 is available and supported."""
        if not getattr(self, "dnd_available", False):
            return

        try:
            # Register root window and entry targets directly
            self.drop_target_register(tkinterdnd2.DND_FILES)
            self.dnd_bind("<<Drop>>", self._handle_window_drop)

            self.input_entry.drop_target_register(tkinterdnd2.DND_FILES)
            self.input_entry.dnd_bind("<<Drop>>", self._handle_input_drop)

            self.output_entry.drop_target_register(tkinterdnd2.DND_FILES)
            self.output_entry.dnd_bind("<<Drop>>", self._handle_output_drop)
        except Exception:
            pass

    def _parse_dnd_path(self, raw_data: str) -> Optional[Path]:
        """Extract valid directory Path from dropped data string."""
        try:
            paths = self.tk.splitlist(raw_data)
            if not paths:
                return None
            target = Path(paths[0])
            if target.is_dir():
                return target
            elif target.is_file():
                return target.parent
        except Exception:
            pass
        return None

    def _handle_input_drop(self, event: Any) -> None:
        path = self._parse_dnd_path(event.data)
        if path:
            self._set_input_folder(path)

    def _handle_output_drop(self, event: Any) -> None:
        path = self._parse_dnd_path(event.data)
        if path:
            self._set_output_folder(path)

    def _handle_window_drop(self, event: Any) -> None:
        """Intelligent folder assignment per specification:

        - If Input is empty -> set Input.
        - If Input exists but Output is empty -> set Output.
        - If both exist -> update Input or leave Output.
        """
        path = self._parse_dnd_path(event.data)
        if not path:
            return

        in_text = self.input_entry.get().strip()
        out_text = self.output_entry.get().strip()

        if not in_text:
            self._set_input_folder(path)
        elif not out_text:
            self._set_output_folder(path)
        else:
            self._set_input_folder(path)

    # -------------------------------------------------------------------------
    # Settings & Dynamic GUI Reactivity
    # -------------------------------------------------------------------------
    def _apply_settings_to_ui(self) -> None:
        """Populate GUI widgets from loaded settings dictionary."""
        s = self.settings

        # Folders
        if s.get("last_input_folder"):
            in_p = Path(s["last_input_folder"])
            if in_p.is_dir():
                self.input_entry.delete(0, "end")
                self.input_entry.insert(0, str(in_p))

        if s.get("last_output_folder"):
            out_p = Path(s["last_output_folder"])
            if out_p.is_dir():
                self.output_entry.delete(0, "end")
                self.output_entry.insert(0, str(out_p))

        # Method
        method = s.get("resize_method", METHOD_FIXED)
        self.method_var.set(method)

        # Width / Height
        self.width_entry.delete(0, "end")
        self.width_entry.insert(0, str(s.get("target_width", DEFAULT_WIDTH)))
        self.height_entry.delete(0, "end")
        self.height_entry.insert(0, str(s.get("target_height", DEFAULT_HEIGHT)))

        # Percentage
        pct = s.get("scale_percentage", DEFAULT_SCALE_PERCENTAGE)
        self.scale_menu.set(f"{pct}%")

        # Right column
        self.format_menu.set(s.get("output_format", "PNG"))
        self.filter_menu.set(s.get("filter_name", FILTER_NEAREST))
        self.existing_menu.set(s.get("existing_action", EXISTING_OVERWRITE))
        self.fit_menu.set(s.get("fit_mode", FIT_MODE_FIT))

        self.auto_pot_var.set(s.get("auto_pot", False))
        self.auto_pot_mode_menu.set(s.get("auto_pot_mode", AUTO_POT_NEXT))
        self.subfolders_var.set(s.get("include_subfolders", True))
        self.delete_source_var.set(s.get("delete_source", False))

        self._update_method_ui_state()
        self._scan_input_folder()

    def _save_active_settings(self) -> None:
        """Extract UI state and persist to settings file."""
        try:
            w = int(self.width_entry.get().strip() or DEFAULT_WIDTH)
        except ValueError:
            w = DEFAULT_WIDTH

        try:
            h = int(self.height_entry.get().strip() or DEFAULT_HEIGHT)
        except ValueError:
            h = DEFAULT_HEIGHT

        scale_str = self.scale_menu.get().replace("%", "").strip()
        try:
            scale_val = int(scale_str) if scale_str else DEFAULT_SCALE_PERCENTAGE
        except ValueError:
            scale_val = DEFAULT_SCALE_PERCENTAGE

        self.settings.update(
            {
                "last_input_folder": self.input_entry.get().strip(),
                "last_output_folder": self.output_entry.get().strip(),
                "resize_method": self.method_var.get(),
                "target_width": w,
                "target_height": h,
                "scale_percentage": scale_val,
                "output_format": self.format_menu.get(),
                "filter_name": self.filter_menu.get(),
                "existing_action": self.existing_menu.get(),
                "fit_mode": self.fit_menu.get(),
                "auto_pot": self.auto_pot_var.get(),
                "auto_pot_mode": self.auto_pot_mode_menu.get(),
                "include_subfolders": self.subfolders_var.get(),
                "delete_source": self.delete_source_var.get(),
            }
        )
        save_settings(self.settings)

    def _on_method_changed(self) -> None:
        """Handle Sizing Method radio toggle."""
        self._update_method_ui_state()
        self._save_active_settings()

    def _on_auto_pot_toggled(self) -> None:
        """Handle Auto POT checkbox toggle."""
        self._update_method_ui_state()
        self._save_active_settings()

    def _on_auto_pot_mode_changed(self) -> None:
        """Handle Auto POT strategy change."""
        self._save_active_settings()

    def _on_dropdown_changed(self) -> None:
        """Handle dropdown option selection."""
        self._save_active_settings()

    def _update_method_ui_state(self) -> None:
        """Enable/disable controls according to selected Resize Method and Auto POT."""
        method = self.method_var.get()

        if method == METHOD_PERCENTAGE:
            # Percentage Mode: Enable scale dropdown, disable fixed / fit / auto_pot / auto_pot_mode
            self.width_entry.configure(
                state="disabled", text_color=COLOR_TEXT_DISABLED
            )
            self.height_entry.configure(
                state="disabled", text_color=COLOR_TEXT_DISABLED
            )
            self.lbl_width.configure(text_color=COLOR_TEXT_DISABLED)
            self.lbl_height.configure(text_color=COLOR_TEXT_DISABLED)
            for btn in self.pot_preset_buttons:
                btn.configure(state="disabled", text_color=COLOR_TEXT_DISABLED)

            self.scale_menu.configure(state="normal")
            self.lbl_scale.configure(text_color=COLOR_TEXT_LIGHT)
            self.helper_note_lbl.configure(text_color=COLOR_TEXT_SECONDARY)

            self.fit_menu.configure(state="disabled")
            self.fit_lbl.configure(text_color=COLOR_TEXT_DISABLED)
            self.auto_pot_chk.configure(state="disabled")
            self.auto_pot_mode_menu.configure(state="disabled")

        else:
            # Fixed Resolution Mode:
            self.scale_menu.configure(state="disabled")
            self.lbl_scale.configure(text_color=COLOR_TEXT_DISABLED)
            self.helper_note_lbl.configure(text_color=COLOR_TEXT_DISABLED)

            self.fit_menu.configure(state="normal")
            self.fit_lbl.configure(text_color=COLOR_TEXT_LIGHT)
            self.auto_pot_chk.configure(state="normal")

            # Check if Auto POT is enabled
            auto_pot_enabled = self.auto_pot_var.get()
            if auto_pot_enabled:
                self.auto_pot_mode_menu.configure(state="normal")
                # When Auto POT is enabled, visually disable width/height controls and labels
                self.width_entry.configure(
                    state="disabled", text_color=COLOR_TEXT_DISABLED
                )
                self.height_entry.configure(
                    state="disabled", text_color=COLOR_TEXT_DISABLED
                )
                self.lbl_width.configure(text_color=COLOR_TEXT_DISABLED)
                self.lbl_height.configure(text_color=COLOR_TEXT_DISABLED)
                for btn in self.pot_preset_buttons:
                    btn.configure(state="disabled", text_color=COLOR_TEXT_DISABLED)
            else:
                self.auto_pot_mode_menu.configure(state="disabled")
                # Restore width/height controls and labels
                self.width_entry.configure(state="normal", text_color=COLOR_TEXT_WHITE)
                self.height_entry.configure(state="normal", text_color=COLOR_TEXT_WHITE)
                self.lbl_width.configure(text_color=COLOR_TEXT_LIGHT)
                self.lbl_height.configure(text_color=COLOR_TEXT_LIGHT)
                for btn in self.pot_preset_buttons:
                    btn.configure(state="normal", text_color=COLOR_TEXT_LIGHT)

    def _set_pot_dimensions(self, w: int, h: int) -> None:
        """Set width and height inputs to predetermined POT value."""
        if self.method_var.get() != METHOD_FIXED:
            self.method_var.set(METHOD_FIXED)
            self._update_method_ui_state()

        self.width_entry.delete(0, "end")
        self.width_entry.insert(0, str(w))
        self.height_entry.delete(0, "end")
        self.height_entry.insert(0, str(h))
        self._save_active_settings()

    def _on_dimension_committed(self) -> None:
        """Validate dimension inputs on focus loss / Enter key and persist."""
        try:
            w = max(1, int(self.width_entry.get().strip()))
        except ValueError:
            w = DEFAULT_WIDTH
        self.width_entry.delete(0, "end")
        self.width_entry.insert(0, str(w))

        try:
            h = max(1, int(self.height_entry.get().strip()))
        except ValueError:
            h = DEFAULT_HEIGHT
        self.height_entry.delete(0, "end")
        self.height_entry.insert(0, str(h))

        self._save_active_settings()

    def _on_subfolders_toggled(self) -> None:
        self._save_active_settings()
        self._scan_input_folder(force=True)

    def _on_delete_source_toggled(self) -> None:
        if self.delete_source_var.get():
            in_dir = self.input_entry.get().strip()
            out_dir = self.output_entry.get().strip()
            if in_dir and out_dir and Path(in_dir).resolve() == Path(out_dir).resolve():
                self._show_info_dialog(
                    "Invalid Configuration",
                    "Input and Output directories are identical.\n'Delete source images' cannot be enabled to prevent data loss.",
                )
                self.delete_source_var.set(False)
                return
        self._save_active_settings()

    def _on_input_folder_typed(self) -> None:
        """Handle typing in input folder entry with debounced scan."""
        self._check_identical_folders_telemetry()
        if self._scan_timer is not None:
            try:
                self.after_cancel(self._scan_timer)
            except Exception:
                pass
        self._scan_timer = self.after(350, self._scan_input_folder)

    def _on_input_folder_committed(self, force: bool = False) -> None:
        """Handle committed change in input folder entry on focus out or Enter key."""
        if self._scan_timer is not None:
            try:
                self.after_cancel(self._scan_timer)
            except Exception:
                pass
            self._scan_timer = None
        self._check_identical_folders_telemetry()
        self._save_active_settings()
        self._scan_input_folder(force=force)

    def _on_output_folder_typed(self) -> None:
        """Handle typing in output folder entry without rescanning input."""
        self._check_identical_folders_telemetry()

    def _on_output_folder_committed(self) -> None:
        """Handle committed change in output folder entry without rescanning input."""
        self._check_identical_folders_telemetry()
        self._save_active_settings()

    def _check_identical_folders_telemetry(self) -> None:
        """Update telemetry message immediately if folders are identical, without disk I/O."""
        in_str = self.input_entry.get().strip()
        out_str = self.output_entry.get().strip()
        if in_str and out_str and in_str.lower() == out_str.lower():
            self.telemetry_main_lbl.configure(
                text="Input and Output folders cannot be identical"
            )
        elif in_str:
            self.telemetry_main_lbl.configure(
                text=f"{self.scanned_images_count} supported images found"
            )

    def _on_folder_entry_typed(self) -> None:
        """Backward-compatible handler for folder typing."""
        self._on_input_folder_typed()

    def _on_folder_entry_committed(self) -> None:
        """Backward-compatible handler for folder commit."""
        self._on_input_folder_committed()

    # -------------------------------------------------------------------------
    # Browsing & Discovery
    # -------------------------------------------------------------------------
    def _browse_input_folder(self) -> None:
        initial = self.input_entry.get().strip()
        selected = ctk.filedialog.askdirectory(
            title="Select Input Folder Containing Images",
            initialdir=initial if Path(initial).is_dir() else None,
        )
        if selected:
            self._set_input_folder(Path(selected))

    def _browse_output_folder(self) -> None:
        initial = self.output_entry.get().strip()
        selected = ctk.filedialog.askdirectory(
            title="Select Output Folder for Converted Images",
            initialdir=initial if Path(initial).is_dir() else None,
        )
        if selected:
            self._set_output_folder(Path(selected))

    def _set_input_folder(self, path: Path) -> None:
        self.input_entry.delete(0, "end")
        self.input_entry.insert(0, str(path))
        self._on_input_folder_committed(force=True)

    def _set_output_folder(self, path: Path) -> None:
        self.output_entry.delete(0, "end")
        self.output_entry.insert(0, str(path))
        self._on_output_folder_committed()

    def _scan_input_folder(self, force: bool = False) -> None:
        """Scan input directory asynchronously using generation tokens to reject stale results."""
        in_path_str = self.input_entry.get().strip()
        if not in_path_str:
            self.scanned_images_count = 0
            self.telemetry_main_lbl.configure(text="0 supported images found")
            self._active_scan_params = None
            self._last_completed_scan_params = None
            return

        out_str = self.output_entry.get().strip()

        # Check identical folder edge case on main thread without blocking disk I/O
        if out_str and in_path_str.strip().lower() == out_str.strip().lower():
            self.scanned_images_count = 0
            self.telemetry_main_lbl.configure(
                text="Input and Output folders cannot be identical"
            )
            self._active_scan_params = None
            return

        include_sub = self.subfolders_var.get()
        scan_params = (in_path_str, include_sub)

        # 1. Avoid simultaneous duplicate scans for the same input and options
        if not force and self._active_scan_params == scan_params:
            return

        # 2. Avoid redundant scans if already scanned with identical input and options
        if not force and self._last_completed_scan_params == scan_params:
            return

        self._scan_generation += 1
        current_token = self._scan_generation
        self._active_scan_params = scan_params

        # Immediate main-thread visual feedback before any background I/O
        self.telemetry_main_lbl.configure(text="Scanning folder...")

        in_path = Path(in_path_str)
        out_path = Path(out_str) if out_str else None

        def scan_worker(token: int, target_in: Path, target_out: Optional[Path], subfolders: bool, params: tuple[str, bool]) -> None:
            try:
                if not target_in.is_dir():
                    self.event_queue.put(("scanned", (token, "not_found")))
                    return

                if target_out and target_in.resolve() == target_out.resolve():
                    self.event_queue.put(("scanned", (token, "identical")))
                    return

                found = discover_images(
                    input_dir=target_in,
                    include_subfolders=subfolders,
                    output_dir=target_out,
                )
                self.event_queue.put(("scanned", (token, len(found))))
            except Exception:
                self.event_queue.put(("scanned", (token, 0)))
            finally:
                if self._active_scan_params == params:
                    self._active_scan_params = None

        threading.Thread(
            target=scan_worker,
            args=(current_token, in_path, out_path, include_sub, scan_params),
            daemon=True,
        ).start()

    # -------------------------------------------------------------------------
    # Conversion Pipeline
    # -------------------------------------------------------------------------
    def _on_convert_clicked(self) -> None:
        """Trigger conversion start or handle cancellation request."""
        if self.is_converting:
            # Request cancellation
            if self.cancel_event:
                self.cancel_event.set()
                self.convert_btn.configure(text="Cancelling...", state="disabled")
            return

        # Validation checks
        in_str = self.input_entry.get().strip()
        out_str = self.output_entry.get().strip()

        if not in_str or not Path(in_str).is_dir():
            self._show_info_dialog(
                "Missing Input", "Please select a valid input folder containing images."
            )
            return

        if not out_str:
            self._show_info_dialog(
                "Missing Output", "Please select or specify an output folder."
            )
            return

        in_dir = Path(in_str).resolve()
        out_dir = Path(out_str).resolve()

        # Reject identical input/output directories before discovery/conversion
        if in_dir == out_dir:
            self._show_info_dialog(
                "Invalid Directory Selection",
                "Input and Output folders cannot be the same directory.\nPlease choose a separate output directory to avoid corrupting or overwriting your source images.",
            )
            return

        if self.delete_source_var.get():
            # Destructive confirmation
            confirm = messagebox.askyesno(
                "Confirm Source Deletion",
                "You have enabled 'Delete source images after successful conversion'.\n\n"
                "Converted original files will be permanently deleted after output verification.\n"
                "Are you sure you want to proceed?",
            )
            if not confirm:
                return

        # Compile conversion configuration
        try:
            w = int(self.width_entry.get().strip() or DEFAULT_WIDTH)
        except ValueError:
            w = DEFAULT_WIDTH

        try:
            h = int(self.height_entry.get().strip() or DEFAULT_HEIGHT)
        except ValueError:
            h = DEFAULT_HEIGHT

        scale_str = self.scale_menu.get().replace("%", "").strip()
        try:
            scale_val = int(scale_str) if scale_str else DEFAULT_SCALE_PERCENTAGE
        except ValueError:
            scale_val = DEFAULT_SCALE_PERCENTAGE

        config = ConversionConfig(
            input_dir=in_dir,
            output_dir=out_dir,
            include_subfolders=self.subfolders_var.get(),
            delete_source=self.delete_source_var.get(),
            resize_method=self.method_var.get(),
            target_width=w,
            target_height=h,
            scale_percentage=scale_val,
            fit_mode=self.fit_menu.get(),
            auto_pot=self.auto_pot_var.get(),
            auto_pot_mode=self.auto_pot_mode_menu.get(),
            filter_name=self.filter_menu.get(),
            output_format=self.format_menu.get(),
            existing_action=self.existing_menu.get(),
        )

        # Setup runtime state
        self.is_converting = True
        self.cancel_event = threading.Event()
        self.convert_btn.configure(
            text="⏹  Cancel",
            fg_color=COLOR_BTN_CANCEL,
            hover_color=COLOR_BTN_CANCEL_HOVER,
            state="normal",
        )
        self.progress_bar.set(0.0)
        self.progress_text_lbl.configure(text="Starting...")
        self.metrics_lbl.configure(text="0 converted    0 skipped    0 failed")
        self.view_errors_btn.grid_remove()

        # Promptly wake queue dispatcher for active conversion
        self.clear_progress()
        self._schedule_prompt_queue_tick()

        # Launch background worker
        def worker() -> None:
            def progress_cb(
                cur: int, total: int, filename: str, res: FileResult
            ) -> None:
                self.publish_progress((cur, total, filename, res))

            try:
                batch_res = convert_batch(
                    config=config,
                    progress_callback=progress_cb,
                    cancel_event=self.cancel_event,
                )
                self.event_queue.put(("finished", batch_res))
            except Exception as e:
                self.event_queue.put(("error", str(e)))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    # -------------------------------------------------------------------------
    # Event Queue Processing (Main Thread Dispatch)
    # -------------------------------------------------------------------------
    def _schedule_prompt_queue_tick(self) -> None:
        """Promptly schedule the queue dispatcher for active work."""
        if self._queue_timer is not None:
            try:
                self.after_cancel(self._queue_timer)
            except Exception:
                pass
            self._queue_timer = None
        self._queue_timer = self.after_idle(self._process_event_queue)

    def _apply_progress(self, progress_data: tuple[Any, ...]) -> None:
        """Render single progress update to UI widgets."""
        if len(progress_data) == 4:
            cur, total, filename, res = progress_data
        elif len(progress_data) == 3:
            cur, total, filename = progress_data
            res = None
        elif len(progress_data) >= 2:
            cur, total = progress_data[0], progress_data[1]
            filename = ""
            res = None
        else:
            return

        self.current_filename = filename
        ratio = cur / max(1, total)
        self.progress_bar.set(ratio)
        self.progress_text_lbl.configure(text=f"Converting... {cur} / {total}")
        self._progress_render_count += 1

    def _handle_scanned_result(self, result: Any) -> None:
        """Handle resolved folder scan telemetry on the main thread."""
        if result == "not_found":
            self.scanned_images_count = 0
            self.telemetry_main_lbl.configure(text="Input folder does not exist")
        elif result == "identical":
            self.scanned_images_count = 0
            self.telemetry_main_lbl.configure(
                text="Input and Output folders cannot be identical"
            )
        elif isinstance(result, int):
            self.scanned_images_count = result
            self.telemetry_main_lbl.configure(
                text=f"{result} supported images found"
            )
        elif isinstance(result, str):
            self.telemetry_main_lbl.configure(text=result)
        else:
            self.scanned_images_count = 0
            self.telemetry_main_lbl.configure(text="0 supported images found")

    def _process_event_queue(self) -> None:
        """Bounded, time-sliced event dispatcher with single-slot progress coalescing and ~120 Hz scheduling."""
        start_time = time.perf_counter()
        events_processed = 0

        latest_scanned: Optional[tuple[int, Any]] = None
        terminal_event: Optional[tuple[str, Any]] = None
        has_more_in_queue = False

        while events_processed < self.MAX_EVENTS_PER_TICK:
            if (time.perf_counter() - start_time) >= self.MAX_TICK_TIME_SEC:
                has_more_in_queue = True
                break

            try:
                msg = self.event_queue.get_nowait()
            except queue.Empty:
                break

            events_processed += 1
            msg_type = msg[0]
            payload = msg[1] if len(msg) > 1 else None

            if msg_type == "scanned":
                if isinstance(payload, tuple) and len(payload) >= 2:
                    token, res = payload[0], payload[1]
                    if token == self._scan_generation:
                        latest_scanned = (token, res)
                elif isinstance(payload, int):
                    latest_scanned = (self._scan_generation, payload)

            elif msg_type == "progress":
                self.publish_progress(payload)

            elif msg_type == "finished":
                terminal_event = ("finished", payload)
                break

            elif msg_type == "error":
                terminal_event = ("error", payload)
                break

        if not self.event_queue.empty():
            has_more_in_queue = True

        # 1. Apply latest scanned result
        if latest_scanned is not None:
            token, result = latest_scanned
            self._handle_scanned_result(result)

        # 2. Progress update handling from single-slot mailbox
        now = time.perf_counter()
        prog_to_render = None

        with self._progress_lock:
            if terminal_event is not None:
                # Terminal events (finished/error/cancel) must remain lossless and flush latest progress first
                if self._latest_progress is not None and self._has_new_progress:
                    prog_to_render = self._latest_progress
                    self._has_new_progress = False
            elif self._has_new_progress and self._latest_progress is not None:
                # 120 Hz nominal frame interval check or complete ratio
                if (now - self._last_progress_render_time) >= self.MIN_PROGRESS_INTERVAL_SEC:
                    prog_to_render = self._latest_progress
                    self._has_new_progress = False
                elif len(self._latest_progress) >= 2 and self._latest_progress[0] >= self._latest_progress[1]:
                    prog_to_render = self._latest_progress
                    self._has_new_progress = False

        if prog_to_render is not None:
            self._apply_progress(prog_to_render)
            self._last_progress_render_time = now

        # 3. Apply terminal state
        if terminal_event is not None:
            term_type, term_payload = terminal_event
            if term_type == "finished":
                self._on_conversion_finished(term_payload)
            elif term_type == "error":
                self._on_conversion_error(term_payload)

        # 4. Adaptive scheduling
        if self._queue_timer is not None:
            try:
                self.after_cancel(self._queue_timer)
            except Exception:
                pass
            self._queue_timer = None

        with self._progress_lock:
            pending_progress = self._has_new_progress

        if has_more_in_queue:
            self._queue_timer = self.after_idle(self._process_event_queue)
        elif self.is_converting:
            self._queue_timer = self.after(self.BUSY_POLL_INTERVAL_MS, self._process_event_queue)
        elif pending_progress:
            self._queue_timer = self.after(self.BUSY_POLL_INTERVAL_MS, self._process_event_queue)
        else:
            self._queue_timer = self.after(self.IDLE_POLL_INTERVAL_MS, self._process_event_queue)

    def _on_conversion_finished(self, batch_res: BatchResult) -> None:
        """Handle normal or cancelled conversion completion."""
        self.is_converting = False
        self.last_batch_result = batch_res
        self.current_filename = ""

        self.convert_btn.configure(
            text="▶  Convert",
            fg_color=COLOR_BTN_CONVERT,
            hover_color=COLOR_BTN_CONVERT_HOVER,
            state="normal",
        )

        if batch_res.cancelled:
            self.progress_text_lbl.configure(text="Cancelled")
        else:
            self.progress_bar.set(1.0)
            self.progress_text_lbl.configure(text="Complete")

        self.metrics_lbl.configure(
            text=f"{batch_res.converted} converted    {batch_res.skipped} skipped    {batch_res.failed} failed"
        )

        if batch_res.failed > 0:
            self.view_errors_btn.grid()

        # Re-scan in case source deletion occurred
        self._scan_input_folder(force=True)

    def _on_conversion_error(self, err_msg: str) -> None:
        """Handle fatal pipeline failure."""
        self.is_converting = False
        self.current_filename = ""
        self.convert_btn.configure(
            text="▶  Convert",
            fg_color=COLOR_BTN_CONVERT,
            hover_color=COLOR_BTN_CONVERT_HOVER,
            state="normal",
        )
        self.progress_text_lbl.configure(text="Error")
        self._show_info_dialog("Conversion Error", f"Batch conversion failed: {err_msg}")

    # -------------------------------------------------------------------------
    # Dialogs & Modals
    # -------------------------------------------------------------------------
    def _show_info_dialog(self, title: str, message: str) -> None:
        """Display clean modal info dialog."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("440x220")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=COLOR_BG_BACKDROP)

        frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD_INFO, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        msg_lbl = ctk.CTkLabel(
            frame,
            text=message,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLOR_TEXT_LIGHT,
            wraplength=380,
            justify="center",
        )
        msg_lbl.pack(expand=True, padx=12, pady=(16, 8))

        ok_btn = ctk.CTkButton(
            frame,
            text="OK",
            width=90,
            height=32,
            fg_color=COLOR_BTN_CONVERT,
            hover_color=COLOR_BTN_CONVERT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=dialog.destroy,
        )
        ok_btn.pack(pady=(0, 16))

    def _show_error_details_modal(self) -> None:
        """Open detailed error inspector for troubleshooting failed images."""
        if not self.last_batch_result or not self.last_batch_result.errors:
            return

        modal = ctk.CTkToplevel(self)
        modal.title("Failed Image Details")
        modal.geometry("640x440")
        modal.minsize(500, 300)
        modal.transient(self)
        modal.grab_set()
        modal.configure(fg_color=COLOR_BG_BACKDROP)

        inner = ctk.CTkFrame(modal, fg_color=COLOR_CARD_SETTINGS, corner_radius=12)
        inner.pack(fill="both", expand=True, padx=16, pady=16)

        title_lbl = ctk.CTkLabel(
            inner,
            text=f"Encountered {len(self.last_batch_result.errors)} File Errors",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=COLOR_TEXT_ERROR,
        )
        title_lbl.pack(anchor="w", padx=16, pady=(12, 6))

        scroll = ctk.CTkScrollableFrame(inner, fg_color=COLOR_INPUT_BG, corner_radius=8)
        scroll.pack(fill="both", expand=True, padx=16, pady=8)

        for err_res in self.last_batch_result.errors:
            row = ctk.CTkFrame(scroll, fg_color="#1e1428", corner_radius=6)
            row.pack(fill="x", pady=4, padx=4)

            name_lbl = ctk.CTkLabel(
                row,
                text=err_res.source_path.name,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=COLOR_TEXT_WHITE,
                anchor="w",
            )
            name_lbl.pack(anchor="w", padx=8, pady=(4, 2))

            msg = err_res.error_message or "Unknown failure"
            err_lbl = ctk.CTkLabel(
                row,
                text=msg,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=COLOR_TEXT_SECONDARY,
                anchor="w",
                justify="left",
                wraplength=520,
            )
            err_lbl.pack(anchor="w", padx=8, pady=(0, 4))

        close_btn = ctk.CTkButton(
            inner,
            text="Close",
            width=100,
            height=32,
            fg_color="#3d2d5c",
            hover_color="#523d7a",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=modal.destroy,
        )
        close_btn.pack(pady=10)

    # -------------------------------------------------------------------------
    # Safe Exit Handling
    # -------------------------------------------------------------------------
    def _on_close(self) -> None:
        """Handle window close safely, waiting for background thread if active."""
        if self.is_converting:
            confirm = messagebox.askyesno(
                "Conversion in Progress",
                "A batch conversion is currently running.\nDo you want to cancel and exit?",
            )
            if not confirm:
                return

            if self.cancel_event:
                self.cancel_event.set()

        if self._queue_timer is not None:
            try:
                self.after_cancel(self._queue_timer)
            except Exception:
                pass
            self._queue_timer = None

        if self._scan_timer is not None:
            try:
                self.after_cancel(self._scan_timer)
            except Exception:
                pass
            self._scan_timer = None

        self._save_active_settings()
        self.destroy()

    def destroy(self) -> None:
        """Safely destroy window, cancelling any active poll or scan timers."""
        if hasattr(self, "_queue_timer") and self._queue_timer is not None:
            try:
                self.after_cancel(self._queue_timer)
            except Exception:
                pass
            self._queue_timer = None
        if hasattr(self, "_scan_timer") and self._scan_timer is not None:
            try:
                self.after_cancel(self._scan_timer)
            except Exception:
                pass
            self._scan_timer = None
        super().destroy()
