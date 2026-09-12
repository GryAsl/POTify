========================================================================
POTify - Resize & Convert Your Images
Version 1.0.0 (Windows 64-bit Portable Distribution)
========================================================================

QUICK START
-----------
1. If you extracted this from a ZIP archive, ensure the entire 'POTify'
   folder was extracted.
2. Double-click 'POTify.exe' to launch the graphical user interface.
3. No Python installation, runtime environment, or external dependencies
   are required.

PACKAGE CONTENTS
----------------
- POTify.exe    : Main standalone application executable.
- _internal/    : Bundled Python runtime, libraries, CustomTkinter themes,
                  and Tcl/Tk drag-and-drop binaries.
- assets/       : High-resolution application branding icons.
- README.txt    : Quick-start and troubleshooting documentation.

FEATURES
--------
- Power-of-Two (POT) batch resizing (Fixed or Percentage modes).
- Auto POT rounding (Nearest or Next power of two).
- Aspect ratio modes: Fit (letterbox), Fill (crop), and Stretch.
- Supported image formats: PNG, JPG, WebP, BMP, TGA.
- Alpha channel preservation and intelligent JPG matte flattening.
- Recursive directory tree preservation.
- Thread-safe non-blocking batch conversion with instant cancellation.
- Dark purple theme with modern rounded card aesthetics.

COMMAND-LINE INTERFACE (CLI)
----------------------------
You can also invoke POTify from Command Prompt or PowerShell:
  POTify.exe --help        Show usage options
  POTify.exe --version     Display application version
  POTify.exe --smoke-test  Execute automated headless UI lifecycle check

SETTINGS PERSISTENCE
--------------------
User preferences and last-used paths are automatically saved to:
  %USERPROFILE%\.potify\settings.json

TROUBLESHOOTING
---------------
- Drag and drop: Dragging folders directly into Input or Output fields is supported.
  If running under elevated Administrator privileges or restricted shell
  environments, Windows may block drag-and-drop messages across integrity
  levels; use the built-in 'Browse' buttons instead.
- Windows SmartScreen: This build is currently unsigned. Each rebuilt unsigned
  EXE has a new file hash and must establish reputation again. For public
  distribution, publish through the Microsoft Store or sign every release with
  the same trusted RSA Authenticode identity. A self-signed certificate does not
  solve public SmartScreen reputation.
- If Windows file Properties shows an 'Unblock' checkbox, it only removes the
  internet Zone.Identifier (the same operation as PowerShell Unblock-File). It
  does not create publisher reputation. Smart App Control has no per-app bypass;
  POTify does not disable or weaken Windows security settings.

========================================================================
Developed with Python, CustomTkinter, and Pillow.
Copyright (c) 2026 POTify Team. MIT License.
========================================================================
