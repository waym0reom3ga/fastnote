"""X11 driver layer. Everything here talks to the real display: window
discovery, geometry, real input (xdotool / XTEST via fnprobe), and the pixel
probe. Native Wayland windows are out of scope by design; editions run as X
clients under the user's compositor."""

import os
import re
import subprocess
import time

PROBE = None
SYNTH = None


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def display_ok():
    return bool(os.environ.get("DISPLAY"))


def window_ids(title_substr):
    out = sh(["xdotool", "search", "--name", title_substr]).stdout
    return [w for w in out.split() if w]


def window_name(wid):
    r = sh(["xdotool", "getwindowname", wid])
    return r.stdout.strip() if r.returncode == 0 else ""


def window_geometry(wid):
    r = sh(["xdotool", "getwindowgeometry", wid])
    if r.returncode != 0:
        return None
    m = re.search(r"Geometry:\s*(\d+)x(\d+)", r.stdout)
    return (int(m.group(1)), int(m.group(2))) if m else None


def find_window(title_substr, exclude=(), min_side=200, timeout=25.0):
    """First viewable window whose name contains title_substr and is bigger
    than a token size (toolkit helper windows are 1x1 and would swallow the
    click)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for wid in window_ids(title_substr):
            if wid in exclude:
                continue
            g = window_geometry(wid)
            if g and g[0] >= min_side and g[1] >= min_side:
                return wid
        time.sleep(0.05)
    return None


def activate(wid):
    sh(["xdotool", "windowactivate", "--sync", wid])


def click_at(wid, x, y):
    sh(["xdotool", "mousemove", "--window", wid, str(x), str(y), "click", "1"])


def type_text(text, delay_ms=40):
    sh(["xdotool", "type", "--delay", str(delay_ms), text])


def key(keysym):
    sh(["xdotool", "key", keysym])


def close_window(wid):
    sh(["xdotool", "windowclose", wid])


def _probe(wid, args, settle=300, timeout_ms=4000):
    if not PROBE or not PROBE.exists():
        return None
    r = sh([str(PROBE), "--window", wid, "--settle", str(settle),
            "--timeout", str(timeout_ms)] + args)
    if r.returncode != 0:
        return None
    parts = r.stdout.strip().split("\t")
    if len(parts) < 2 or parts[1] == "timeout":
        return None
    return float(parts[1]), int(parts[2])


def probe_click(wid, x, y, settle=300, timeout_ms=4000):
    """Timed real click. Returns (latency_ms, changed_px) or None on timeout."""
    r = _probe(wid, ["click", str(x), str(y)], settle, timeout_ms)
    return r


def probe_key(wid, keysym, settle=300, timeout_ms=4000):
    return _probe(wid, ["key", keysym], settle, timeout_ms)


def probe_baseline(wid, settle=120):
    """How many sampled bytes change with no input at all. Zero means the
    window is still and timings can be trusted."""
    if not PROBE or not PROBE.exists():
        return None
    r = sh([str(PROBE), "--window", wid, "--settle", str(settle), "baseline"])
    if r.returncode != 0:
        return None
    parts = r.stdout.strip().split("\t")
    return int(parts[2]) if len(parts) >= 3 else None


def window_settled(wid, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if probe_baseline(wid, settle=120) == 0:
            return True
        time.sleep(0.05)
    return False
