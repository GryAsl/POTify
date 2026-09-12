"""POTify - Main executable entry point."""

import sys
from pathlib import Path

# Ensure package directory is in sys.path when executed directly
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from potify import __version__
from potify.gui import POTifyApp


def _attach_console_if_cli() -> None:
    """Attach to parent console if invoked with CLI arguments in windowed mode."""
    if sys.platform == "win32" and len(sys.argv) > 1:
        try:
            import ctypes

            # ATTACH_PARENT_PROCESS = -1
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        except Exception:
            pass

    if sys.stdout is None:
        import os

        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        import os

        sys.stderr = open(os.devnull, "w")


def main() -> None:
    """Launch POTify graphical user interface."""
    _attach_console_if_cli()

    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--version", "-v"):
            print(f"POTify v{__version__}")
            sys.stdout.flush()
            sys.exit(0)
        elif arg in ("--help", "-h"):
            print("POTify - Resize & convert your images.")
            print("Usage: POTify.exe [options]")
            print("\nOptions:")
            print("  --version, -v      Show version information and exit")
            print("  --help, -h         Show this help message and exit")
            print("  --smoke-test       Instantiate GUI, process event ticks, destroy cleanly, and exit")
            sys.stdout.flush()
            sys.exit(0)
        elif arg == "--smoke-test":
            print("POTify: starting noninteractive UI smoke test...")
            app = POTifyApp()
            app.update_idletasks()
            app.update()
            for _ in range(5):
                app.update_idletasks()
                app.update()
            app.destroy()
            print("POTify: GUI smoke test passed cleanly.")
            sys.stdout.flush()
            sys.exit(0)

    app = POTifyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
