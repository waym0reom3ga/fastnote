"""GUI session driver. Launches the edition's real binary, waits for its real
window, reads its published control map, and performs real input. No headless
mode is ever used; if the edition cannot show a window, the case fails."""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from . import x11

LABEL_ALIASES = {
    "open": ["Open"],
    "save": ["Save"],
    "save_as": ["SaveAs", "Save As"],
    "export_html": ["Export", "ExportHTML", "Export Html", "Export HTML"],
    "export_pdf": ["ExportPdf", "Export PDF"],
    "theme": ["Theme"],
    "editor": ["editor"],
    "path": ["path", "PathInput"],
    "ok": ["ok", "Ok", "OK", "confirm"],
    "cancel": ["cancel", "Cancel"],
    "up": ["up", "Up", ".."],
}


class GuiSession:
    def __init__(self, entry, work, notes_dir):
        self.entry = entry
        self.work = Path(work)
        self.notes_dir = notes_dir
        self.proc = None
        self.wid = None
        self.controls = {}
        self.map_style = entry["instrumentation"]
        self.ready = self.work / "ready"
        self.map_path = self.work / "controls.tsv"

    # -- lifecycle ---------------------------------------------------------

    def start(self, ready_timeout=30.0):
        d = Path(self.entry["path"])
        env = dict(os.environ)
        env["FASTNOTE_CONFIG_DIR"] = str(self.work / "cfg")
        if self.map_style == "flag":
            cmd = [str(d / self.entry["binary"]), "--notes-dir", str(self.notes_dir),
                   "--control-map", str(self.map_path), "--ready-file", str(self.ready)]
        elif self.map_style == "env":
            env["FASTNOTE_CONTROL_MAP"] = str(self.map_path)
            env["FASTNOTE_READY_FILE"] = str(self.ready)
            cmd = [str(d / self.entry["binary"]), "--notes-dir", str(self.notes_dir)]
        else:
            cmd = [str(d / self.entry["binary"]), "--notes-dir", str(self.notes_dir)]
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

    def wait_ready(self, timeout=20.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.ready.exists():
                return True
            time.sleep(0.05)
        return False

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

    # -- control map -------------------------------------------------------

    def load_control_map(self):
        self.controls = {}
        if not self.map_path.exists():
            return False
        for line in self.map_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 5:
                continue
            try:
                self.controls[parts[0]] = tuple(int(v) for v in parts[1:])
            except ValueError:
                continue
        return bool(self.controls)

    def rect(self, canonical):
        """Resolve a canonical control name against the published map."""
        for alias in LABEL_ALIASES.get(canonical, [canonical]):
            if alias in self.controls:
                return self.controls[alias]
        return None

    def has(self, canonical):
        return self.rect(canonical) is not None

    def click_point(self, canonical):
        rect = self.rect(canonical)
        if not rect:
            return None
        x, y, w, h = rect
        if w <= 200:
            return x + w // 2, y + h // 2
        return x + 12, y + min(h // 2, 16)

    def click(self, canonical, settle=True):
        pt = self.click_point(canonical)
        if not pt:
            return False
        if settle:
            x11.window_settled(self.wid)
        x11.click_at(self.wid, pt[0], pt[1])
        return True
