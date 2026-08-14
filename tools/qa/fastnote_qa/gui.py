"""GUI session driver. Launches the edition's real binary with --event-file,
waits for its real window, and performs real input through the keyboard. No
headless mode is ever used; if the edition cannot show a window, the case
fails.

The edition publishes phase completions by appending one line per marker to
the event file (spec 5.1). The harness waits for a marker before asserting on
disk state or timing an operation. All user-facing actions are driven with the
standard accelerators (spec FR-11) and the browser keyboard contract (spec
3.2): Ctrl+O open, Ctrl+L focus path, type path, Enter confirm, Escape cancel,
Ctrl+S save, Ctrl+Shift+S save-as, Ctrl+E export HTML, Ctrl+Shift+E export
PDF. No coordinates, no control maps.
"""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from . import x11

EVENT_PAINTED = "painted"
EVENT_OPEN = "open"
EVENT_SAVE = "save"
EVENT_SAVE_AS = "save-as"
EVENT_EXPORT_HTML = "export-html"
EVENT_EXPORT_PDF = "export-pdf"

# Canonical accelerators (spec FR-11).
ACCEL_OPEN = "ctrl+o"
ACCEL_SAVE = "ctrl+s"
ACCEL_SAVE_AS = "ctrl+shift+s"
ACCEL_EXPORT_HTML = "ctrl+e"
ACCEL_EXPORT_PDF = "ctrl+shift+e"
ACCEL_FOCUS_PATH = "ctrl+l"
ACCEL_CONFIRM = "Return"
ACCEL_CANCEL = "Escape"


class GuiSession:
    def __init__(self, entry, work, notes_dir):
        self.entry = entry
        self.work = Path(work)
        self.notes_dir = notes_dir
        self.proc = None
        self.wid = None
        self.events = None        # Path; set when event_file is requested
        self.ready = self.work / "ready"

    # -- lifecycle ---------------------------------------------------------

    def start(self, event_file=False, ready_timeout=30.0):
        d = Path(self.entry["path"])
        env = dict(os.environ)
        env["FASTNOTE_CONFIG_DIR"] = str(self.work / "cfg")
        cmd = [str(d / self.entry["binary"])]
        if event_file:
            self.events = self.work / "events.txt"
            cmd += ["--event-file", str(self.events)]
        self.proc = subprocess.Popen(cmd, cwd=d, env=env, start_new_session=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return self

    def stop(self, wait=8.0):
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        if self.proc:
            try:
                self.proc.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                self.proc.wait(timeout=5)
        if self.proc and self.proc.stdout:
            out = self.proc.stdout.read().decode("utf-8", errors="replace")
            return out
        return ""

    def close_via_wm(self, wait=8.0):
        """Request a real WM close (WM_DELETE_WINDOW)."""
        if self.wid:
            x11.close_window(self.wid)
        if self.proc:
            try:
                self.proc.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                return False
            return True
        return False

    # -- waits -------------------------------------------------------------

    def wait_window(self, timeout=25.0):
        self.wid = x11.find_window(self.entry["title"], timeout=timeout)
        return self.wid is not None

    def wait_event(self, marker, timeout=20.0):
        """Wait until the edition has appended the phase marker to its event
        file. The file itself may not exist yet (it is created by the app);
        this polls for both. Returns True when seen, False on timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.events is not None and self.events.exists():
                try:
                    text = self.events.read_text()
                except OSError:
                    text = ""
                if any(line.strip() == marker for line in text.splitlines()):
                    return True
            time.sleep(0.05)
        return False

    def wait_ready(self, timeout=20.0):
        """First painted frame, signalled by the 'painted' marker."""
        return self.wait_event(EVENT_PAINTED, timeout)

    def wait_title_contains(self, substr, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if substr in x11.window_name(self.wid):
                return True
            time.sleep(0.05)
        return False

    def wait_file(self, path, min_size=1, stable_interval=0.15, timeout=15.0):
        """File exists and its size has not changed across two polls."""
        path = Path(path)
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            if path.exists() and path.stat().st_size >= min_size:
                cur = path.stat().st_size
                if last == cur:
                    return True
                last = cur
            time.sleep(stable_interval)
        return False

    # -- keyboard-driven actions -------------------------------------------

    def focus(self):
        """Make the main window the X input-focus window."""
        if self.wid:
            x11.focus(self.wid)
            time.sleep(0.2)

    def press(self, accel, settle=0.3, refocus=False):
        """Press a canonical accelerator. refocus first establishes X input
        focus on the main window (needed for the first key of a sequence);
        once a modal browser/dialog is open it owns the keyboard, so later
        keys in the sequence must not re-focus the main window."""
        if refocus:
            self.focus()
        x11.key(accel)
        if settle:
            time.sleep(settle)

    def type(self, text, refocus=False, delay_ms=40):
        if refocus:
            self.focus()
        x11.type_text(text, delay_ms)

    def open_path(self, path, settle=0.3):
        """The full open gesture: focus, Ctrl+O, Ctrl+L, type the path, Enter."""
        self.press(ACCEL_OPEN, settle=settle, refocus=True)
        self.press(ACCEL_FOCUS_PATH, settle=settle)
        self.type(str(path))
        time.sleep(settle)
        self.press(ACCEL_CONFIRM, settle=0)
