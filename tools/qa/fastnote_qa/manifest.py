"""Edition manifest. One record per edition:

    name: (dir, build_command, binary_path, window_title, event)

event is whether the edition's binary already accepts --event-file (spec 5.1)
and publishes phase markers. It gates the GUI-driving cases A03-A09 and A13:
until an edition is reworked to the keyboard-first protocol, those cases
report PARTIAL rather than pretend to drive the GUI.

The binary is always launched with --event-file <path>. There is no control
map, no --notes-dir, no other flag: exactly --version and --event-file are
permitted by the specification.
"""

ROOT = None  # set by suite.py before use
import sys
from pathlib import Path
if ROOT is None:
    ROOT = Path(__file__).resolve().parent.parent.parent.parent

EDITIONS = {
    "go_gio":    ("fastnote_go_gio_ed",    "make",                  "fastnote-gio",        "FastNote", False),
    "go_fyne":   ("fastnote_go_fyne_ed",   "make",                  "fastnotes",           "FastNote", True),
    "go_gtk4":   ("fastnote_go_gtk4_ed",   "make",                  "fastnote-gtk4",       "FastNote", True),
    "go_wails3": ("fastnote_go_wails3_ed", "wails3 build",          "bin/fastnote-wails3", "FastNote", True),
    "c_gtk4":    ("fastnote_c_gtk4_ed",    "make",                  "fastnote_c_gtk4",     "FastNote", True),
    "c_nuklear": ("fastnote_c_nuklear_ed", "make",                  "fastnote_c_nuklear",  "FastNote", True),
    "c_raygui":  ("fastnote_c_raygui_ed",  "make",                  "fastnote_c_raygui",   "FastNote", True),
    "rust_gtk4": ("fastnote_rust_gtk4_ed", "cargo build --release", "target/release/fastnote-rust-gtk4", "FastNote", True),
    "rust_egui": ("fastnote_rust_egui_ed", "cargo build --release", "target/release/fastnote-rust-egui", "FastNote", True),
    "rust_slint":("fastnote_rust_slint_ed","cargo build --release", "target/release/fastnote-rust-slint", "FastNote", True),
    "python_gtk4":("fastnote_python_gtk4_ed", "make", "fastnote_python_gtk4",     "FastNote", True),
    "python_pyqt6":("fastnote_python_pyqt6_ed", "make", "fastnote_python_pyqt6",   "FastNote", True),
    "python_pyside6":("fastnote_python_pyside6_ed", "make", "fastnote_python_pyside6","FastNote", True),
    "python_dearpygui":("fastnote_python_dearpygui_ed", "make", "fastnote_python_dearpygui", "FastNote", True),
}

# Per-edition GUI event suite command (a14 sabotage validation). The suite
# drives the edition's real widget tree through the toolkit's own input API.
SUITES = {
    "go_gio":    "go test -count=1 -run TestUI .",
    "go_fyne":   "go test -count=1 -run TestUI .",
    "go_gtk4":   "go test -count=1 -run TestUI .",
    "go_wails3": "",
    "c_gtk4":    "make test-ui",
    "c_nuklear": "make test-ui",
    "c_raygui":  "make test-ui",
    "rust_gtk4": "cargo test --release --test ui_click",
    "rust_egui": "cargo test --release --test ui_click",
    "rust_slint":"cargo test --release --test ui_click",
    "python_gtk4":     "python3 -m pytest tests/test_ui_click.py -q",
    "python_pyqt6":    "python3 -m pytest tests/test_ui_click.py -q",
    "python_pyside6":  "python3 -m pytest tests/test_ui_click.py -q",
    "python_dearpygui":"./.venv/bin/python -m pytest tests/test_ui_click.py -q",
}


def all_names():
    return list(EDITIONS)


def entry(name):
    d, build, binary, title, event = EDITIONS[name]
    return {
        "name": name,
        "dir": d,
        "path": ROOT / "editions" / d,
        "build": build,
        "binary": binary,
        "bin_path": ROOT / "editions" / d / binary,
        "title": title,
        "event": event,
        "suite": SUITES.get(name, ""),
    }
