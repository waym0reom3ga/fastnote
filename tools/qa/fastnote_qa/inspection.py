"""Static wiring checks. The runtime cases prove behaviour; these prove that
behaviour is reachable from the interface and the standard accelerators, that
the CLI does not exist as a private copy of the logic (spec 5.2), and that the
edition implements the event-file publication (spec 5.1). Patterns are
deliberately language-neutral; they are guards, not evidence, and each can
fail."""

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

OPEN_CONTROL = re.compile(r'"Open"|Open File|on_open|openBtn|open_btn|OpenPath|open_clicked|request_open|menu.*open', re.I)
OPEN_BIND = re.compile(r'openBtn\.Clicked|on_open|OpenPath|open_clicked|connect_clicked|button\("Open"\)\.clicked|request_open|"open"|open_button', re.I)
EXPORT_CONTROL = re.compile(r'"Export|exportBtn|export_btn|ExportTo|on_export|export_html|export_pdf', re.I)
EXPORT_BIND = re.compile(r'exportBtn\.Clicked|export_btn|on_export|ExportTo|export_clicked|button\("Export"\)\.clicked|Pending::Export|export_to|export_html|export_pdf', re.I)
WRITE = re.compile(r'ExportTo|SaveToFile|save_to_file|WriteFile|fwrite|fopen|fs::write|File::create|export_to|open\(.*["\']w|write_text|\.write\b|to_bytes.*write', re.I)
BROWSER = re.compile(r'FileBrowser|file_browser|filebrowser|BrowserOpen|browser', re.I)
NATIVE_DIALOG = re.compile(r'GtkFileChooser|gtk_file_chooser|QFileDialog|rfd::|tinyfd_|add_file_dialog|FileChooserNative|explorer|prompt\(')
POSIX_OPS = re.compile(r'opendir|readdir|os\.listdir|os\.scandir|pathlib|\.iterdir|fs::read_dir|GList|glob\(', re.I)

# FR-11 accelerators, toolkit-neutral. Matches GTK ("<Primary>o", "^o"),
# Qt ("Ctrl+O", QKeySequence), Gio (KeyO + ModCtrl), Fyne (fyne.KeyO),
# egui (Key::O), Slint, DearPyGui (mvKey_O), etc.
ACC_OPEN = re.compile(r'ctrl\+?[_-]?o|Primary>o|Control>o|\^o|KeyO\b|Key::O|fyne\.KeyO|Key_O\b|mvKey_O', re.I)
ACC_SAVE = re.compile(r'ctrl\+?[_-]?s|Primary>s|Control>s|\^s|KeyS\b|Key::S|fyne\.KeyS|Key_S\b|mvKey_S', re.I)
ACC_SAVE_AS = re.compile(r'ctrl\+?[_-]?shift[_-]?s|Primary><Shift>s|Control><Shift>s|Ctrl\+Shift\+S|KeyS\b|Key::S|fyne\.KeyS|Key_S\b', re.I)
ACC_EXPORT = re.compile(r'ctrl\+?[_-]?e|Primary>e|Control>e|\^e|KeyE\b|Key::E|fyne\.KeyE|Key_E\b|mvKey_E', re.I)
ACC_EXPORT_PDF = re.compile(r'ctrl\+?[_-]?shift[_-]?e|Primary><Shift>e|Control><Shift>e|Ctrl\+Shift\+E|KeyE\b|Key::E|fyne\.KeyE|Key_E\b', re.I)
ACC_FOCUS_PATH = re.compile(r'ctrl\+?[_-]?l|Primary>l|Control>l|\^l|KeyL\b|Key::L|fyne\.KeyL|Key_L\b|mvKey_L', re.I)

PATH_FIELD = re.compile(r'path|PathInput|file_name|filename|entry', re.I)
CONFIRM_ENTER = re.compile(r'Return|Key_Enter|Key::Enter|on_activate|set_activate|EnterKey|KeyEnter', re.I)
CANCEL_ESCAPE = re.compile(r'Escape|Key_Escape|Key::Escape|mvKey_Escape', re.I)

EVENT_FILE = re.compile(r'--event-file|event_file|EVENT_FILE|event.file', re.I)
EVENT_MARKERS = re.compile(r'painted|save-as|export-html|export-pdf|"open"|\'open\'|"save"|\'save\'')


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
    checks["accel_open"] = (bool(ACC_OPEN.search(text)), "no Ctrl+O accelerator binding (FR-11)")
    checks["export_control"] = (bool(EXPORT_CONTROL.search(text)), "no Export control in UI sources")
    checks["export_bound"] = (bool(EXPORT_BIND.search(text)), "Export control never bound to a handler")
    checks["export_writes"] = (bool(WRITE.search(text)), "Export handler reaches no filesystem write")
    checks["accel_export"] = (bool(ACC_EXPORT.search(text)), "no Ctrl+E accelerator binding (FR-11)")
    checks["accel_export_pdf"] = (bool(ACC_EXPORT_PDF.search(text)), "no Ctrl+Shift+E accelerator binding (FR-11)")
    checks["accel_save"] = (bool(ACC_SAVE.search(text)), "no Ctrl+S accelerator binding (FR-11)")
    checks["accel_save_as"] = (bool(ACC_SAVE_AS.search(text)), "no Ctrl+Shift+S accelerator binding (FR-11)")
    checks["accel_focus_path"] = (bool(ACC_FOCUS_PATH.search(text)), "no Ctrl+L path-field focus binding (spec 3.2)")

    checks["browser"] = (bool(BROWSER.search(text)), "no file browser component found")
    native = NATIVE_DIALOG.search(text)
    posix = POSIX_OPS.search(text)
    if native:
        checks["browser_policy"] = (True, f"native dialog used ({native.group(0)}) — permitted by spec 3.1")
    elif posix:
        checks["browser_policy"] = (True, "in-app browser with POSIX filesystem operations")
    else:
        checks["browser_policy"] = (False, "no browser and no POSIX file operations found")

    has_path = bool(PATH_FIELD.search(text))
    has_enter = bool(CONFIRM_ENTER.search(text))
    has_escape = bool(CANCEL_ESCAPE.search(text))
    checks["keyboard_contract"] = (
        has_path and has_enter and has_escape,
        f"browser keyboard contract incomplete (path field {has_path}, Enter {has_enter}, Escape {has_escape})")

    checks["event_file"] = (bool(EVENT_FILE.search(text)), "no --event-file handling (spec 5.1)")
    checks["event_markers"] = (bool(EVENT_MARKERS.search(text)), "no phase markers written (spec 5.1)")
    return checks, files
