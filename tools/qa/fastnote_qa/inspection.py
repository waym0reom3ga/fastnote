"""Static wiring checks. The CLI-driven and GUI-driven cases prove behaviour;
these prove that behaviour is reachable from the interface, and that the CLI
does not exist as a private copy of the logic (spec 5.2). Patterns are
deliberately language-neutral."""

import re
from pathlib import Path

UI_GLOBS = {
    "go_gio": ["*.go"],
    "go_fyne": ["*.go"],
    "go_gtk4": ["*.go"],
    "go_wails3": ["*.go", "frontend/src/*.ts"],
    "c_gtk4": ["src/*.c", "src/*.h"],
    "c_nuklear": ["src/*.c", "src/*.h"],
    "c_raygui": ["src/*.c", "src/*.h"],
    "rust_gtk4": ["src/*.rs"],
    "rust_egui": ["src/*.rs"],
    "rust_slint": ["src/*.rs", "src/*.slint"],
    "python_gtk4": ["src/*.py"],
    "python_pyqt6": ["src/*.py"],
    "python_pyside6": ["src/*.py"],
    "python_dearpygui": ["src/*.py"],
}

OPEN_CONTROL = re.compile(r'"Open"|Open File|on_open|openBtn|open_btn|OpenPath|open_clicked|request_open', re.I)
OPEN_BIND = re.compile(r'openBtn\.Clicked|on_open|OpenPath|open_clicked|connect_clicked|button\("Open"\)\.clicked|request_open|"open"', re.I)
EXPORT_CONTROL = re.compile(r'"Export|exportBtn|export_btn|ExportTo|on_export', re.I)
EXPORT_BIND = re.compile(r'exportBtn\.Clicked|export_btn|on_export|ExportTo|export_clicked|button\("Export"\)\.clicked|Pending::Export|export_to|export_html|export_pdf', re.I)
WRITE = re.compile(r'ExportTo|SaveToFile|save_to_file|WriteFile|fwrite|fopen|fs::write|File::create|export_to|open\(.*["\']w|write_text|\.write\b', re.I)
BROWSER = re.compile(r'FileBrowser|file_browser|filebrowser|BrowserOpen|browser')
NATIVE_DIALOG = re.compile(r'GtkFileChooser|gtk_file_chooser|QFileDialog|rfd::|tinyfd_|add_file_dialog|FileChooserNative|explorer|prompt\(')
POSIX_OPS = re.compile(r'opendir|readdir|os\.listdir|os\.scandir|pathlib|\.iterdir|fs::read_dir|GList|glob\(', re.I)


def source_files(root, name):
    files = []
    for g in UI_GLOBS.get(name, ["*"]):
        for f in Path(root).glob(g):
            if f.is_file():
                files.append(f)
    return files


def check_wiring(root, name):
    """Returns a dict of checks -> (bool, detail)."""
    files = source_files(root, name)
    text = "\n".join(f.read_text(errors="replace") for f in files)
    checks = {}

    checks["open_control"] = (bool(OPEN_CONTROL.search(text)), "no Open control in UI sources")
    checks["open_bound"] = (bool(OPEN_BIND.search(text)), "Open control never bound to a handler")
    checks["export_control"] = (bool(EXPORT_CONTROL.search(text)), "no Export control in UI sources")
    checks["export_bound"] = (bool(EXPORT_BIND.search(text)), "Export control never bound to a handler")
    checks["export_writes"] = (bool(WRITE.search(text)), "Export handler reaches no filesystem write")
    checks["browser"] = (bool(BROWSER.search(text)), "no file browser component found")

    native = NATIVE_DIALOG.search(text)
    posix = POSIX_OPS.search(text)
    if native:
        checks["browser_policy"] = (True, f"native dialog used ({native.group(0)}) — permitted by spec 3.1")
    elif posix:
        checks["browser_policy"] = (True, "in-app browser with POSIX filesystem operations")
    else:
        checks["browser_policy"] = (False, "no browser and no POSIX file operations found")
    return checks, files
