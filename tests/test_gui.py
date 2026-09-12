"""Compact critical tests for POTify GUI layout, structural simplification, and 120 Hz responsiveness."""

from typing import Any
import pytest
import customtkinter as ctk

from potify.gui import POTifyApp
from potify.models import BatchResult


@pytest.fixture(scope="module")
def app() -> Any:
    potify_app = POTifyApp()
    potify_app.update()
    yield potify_app
    try:
        super(POTifyApp, potify_app).destroy()
    except Exception:
        pass


def test_gui_structural_layout(app: POTifyApp) -> None:
    """Verify simplified non-scrolling layout, exact generalized title, absence of bloat widgets, and screen fit."""
    # 1. Native window title
    assert app.title() == "POTify - Resize & convert your images"

    # 2. Main container is fixed CTkFrame, not CTkScrollableFrame
    assert isinstance(app.main_container, ctk.CTkFrame)
    assert not isinstance(app.main_container, ctk.CTkScrollableFrame)

    # 3. No header, logo, or dropzone widgets
    assert not hasattr(app, "header_frame")
    assert not hasattr(app, "logo_img")
    assert not hasattr(app, "dropzone_frame")
    assert not hasattr(app, "conversion_summary_lbl")
    assert not hasattr(app, "telemetry_sub_lbl")

    # 4. Info card contains only header and supported image count
    assert hasattr(app, "telemetry_main_lbl")
    info_labels = [
        c.cget("text")
        for c in app.info_card.winfo_children()
        if isinstance(c, ctk.CTkLabel)
    ]
    assert not any("Transparency" in str(txt) for txt in info_labels)

    # 5. Browse controls use a real centered image instead of a baseline-shifted emoji.
    assert app.input_browse_btn.cget("text") == "Browse"
    assert app.output_browse_btn.cget("text") == "Browse"
    assert "📁" not in app.input_browse_btn.cget("text")
    assert app.input_browse_btn.cget("image") is app.browse_folder_icon
    assert app.output_browse_btn.cget("image") is app.browse_folder_icon
    assert app.input_browse_btn.winfo_width() == app.output_browse_btn.winfo_width()
    assert app.input_browse_btn.winfo_height() == app.output_browse_btn.winfo_height()
    icon_label = app.input_browse_btn._image_label
    text_label = app.input_browse_btn._text_label
    icon_center_y = icon_label.winfo_y() + icon_label.winfo_height() / 2
    text_center_y = text_label.winfo_y() + text_label.winfo_height() / 2
    button_center_y = app.input_browse_btn.winfo_height() / 2
    assert abs(icon_center_y - text_center_y) <= 1.0
    assert abs(icon_center_y - button_center_y) <= 1.0
    assert abs(text_center_y - button_center_y) <= 1.0

    # 6. Action controls share one compact row and Convert does not span the window.
    action_widgets = (
        app.convert_btn,
        app.progress_bar,
        app.progress_text_lbl,
        app.metrics_lbl,
    )
    assert all(widget.grid_info()["row"] == 0 for widget in action_widgets)
    assert app.convert_btn.winfo_width() < app.action_container.winfo_width() / 3
    assert app.action_container.winfo_reqheight() <= app.convert_btn.winfo_height() + 8

    # 7. Content fits within initialized window without scrolling or clipping
    app.update_idletasks()
    assert app.main_container.winfo_reqheight() <= app.winfo_height()
    assert getattr(app, "_min_width", 0) <= 780
    assert getattr(app, "_min_height", 0) <= 600


def test_gui_responsiveness_and_dispatch(app: POTifyApp, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 120 Hz scheduling constants, coalesced single-slot progress mailbox, bounded ticks, and prompt terminal flush."""
    # 1. Nominal interval <= 8.333ms (~120 Hz)
    assert app.MIN_PROGRESS_INTERVAL_SEC <= (1.0 / 120.0) + 1e-9
    assert app.BUSY_POLL_INTERVAL_MS <= 8
    assert app.MAX_TICK_TIME_SEC < 0.008333

    while not app.event_queue.empty():
        app.event_queue.get_nowait()
    app.clear_progress()
    app._last_progress_render_time = 0.0

    # 2. Single-slot mailbox: bursts coalesce and do not build unbounded queue
    for i in range(1, 301):
        app.publish_progress((i, 300, f"frame_{i}.png", None))
    assert app.event_queue.qsize() == 0  # Mailbox bypassed event_queue

    app._process_event_queue()
    assert app.current_filename == "frame_300.png"

    # 3. Bounded tick processing for queued non-progress events
    for i in range(1, 101):
        app.event_queue.put(("progress", (i, 100, f"q_{i}.png", None)))
    app._last_progress_render_time = 0.0
    app._process_event_queue()
    assert app.event_queue.qsize() == (100 - app.MAX_EVENTS_PER_TICK)

    while not app.event_queue.empty():
        app.event_queue.get_nowait()
    app.clear_progress()

    # 4. Terminal events flush latest progress promptly before state transition
    app.is_converting = True
    app.publish_progress((50, 50, "last.png", None))
    batch_res = BatchResult(total_discovered=50, converted=50)
    app.event_queue.put(("finished", batch_res))
    app._process_event_queue()

    assert app.is_converting is False
    assert app.progress_text_lbl.cget("text") == "Complete"
    assert app.metrics_lbl.cget("text") == "50 converted    0 skipped    0 failed"
