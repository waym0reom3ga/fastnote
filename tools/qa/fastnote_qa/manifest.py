"""Edition manifest. One record per edition:

    name: (dir, build_command, binary_path, window_title, instrumentation)

instrumentation is how the edition publishes its control map and ready file:
    "flag"  -- --control-map <path> --ready-file <path> command-line flags
    "env"   -- FASTNOTE_CONTROL_MAP / FASTNOTE_READY_FILE environment variables
    "none"  -- not instrumented yet; GUI-driving cases are partial until repaired
"""

ROOT = None  # set by suite.py before use
import sys
from pathlib import Path
if ROOT is None:
    ROOT = Path(__file__).resolve().parent.parent.parent.parent

EDITIONS = {
    "go_gio":   ("fastnote_go_gio_ed",    "make",                    "fastnote-gio",       "FastNote", "flag"),
    "go_fyne":  ("fastnote_go_fyne_ed",   "make",                    "fastnotes",          "FastNote", "flag"),
    "go_gtk4":  ("fastnote_go_gtk4_ed",   "make",                    "fastnote-gtk4",      "FastNote", "flag"),
    "go_wails3":("fastnote_go_wails3_ed", "wails3 build",            "bin/fastnote-wails3","FastNote", "none"),
    "c_gtk4":   ("fastnote_c_gtk4_ed",    "make",                    "fastnote-c-gtk4",    "FastNote", "none"),
    "c_nuklear":("fastnote_c_nuklear_ed", "make",                    "fastnote",           "FastNote", "none"),
    "c_raygui": ("fastnote_c_raygui_ed",  "make",                    "fastnote-c-raygui",  "FastNote", "none"),
    "rust_gtk4":("fastnote_rust_gtk4_ed", "cargo build --release",   "target/release/fastnote-rust-gtk4", "FastNote", "none"),
    "rust_egui":("fastnote_rust_egui_ed", "cargo build --release",   "target/release/fastnote-egui", "FastNote", "none"),
    "rust_slint":("fastnote_rust_slint_ed","cargo build --release",  "target/release/fastnote-slint","FastNote", "none"),
    "python_gtk4":("fastnote_python_gtk4_ed", "true", "run.sh",      "FastNote", "none"),
    "python_pyqt6":("fastnote_python_pyqt6_ed", "true", "run.sh",    "FastNote", "none"),
    "python_pyside6":("fastnote_python_pyside6_ed", "true", "run.sh","FastNote", "none"),
    "python_dearpygui":("fastnote_python_dearpygui_ed", "true", "run.sh", "FastNote", "none"),
}


def all_names():
    return list(EDITIONS)


def entry(name):
    d, build, binary, title, inst = EDITIONS[name]
    return {
        "name": name,
        "dir": d,
        "path": ROOT / "editions" / d,
        "build": build,
        "binary": binary,
        "bin_path": ROOT / "editions" / d / binary,
        "title": title,
        "instrumentation": inst,
    }
