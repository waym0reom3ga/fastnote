"""Measurement: binary size, startup, peak RSS, and operation latencies.

Nothing is timed inside the application. Every operation is driven through the
real keyboard (the FR-11 accelerators and the browser keyboard contract) and
the clock runs until the edition publishes the corresponding completion marker
in its --event-file (spec 5.1). The instrument is validated against fnsynth's
known delays before any edition is measured; a mismatch stops the run."""

import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from . import x11

MIN_SAMPLES = 5

LATENCY_MARKERS = {
    "open_ms": ("ctrl+o", "open"),
    "save_ms": ("ctrl+s", "save"),
    "export_html_ms": ("ctrl+e", "export-html"),
    "export_pdf_ms": ("ctrl+shift+e", "export-pdf"),
}


class GateError(Exception):
    pass


def _summarise(samples):
    vals = [v for v in samples if v is not None]
    lost = len(samples) - len(vals)
    if len(vals) < MIN_SAMPLES:
        return {"insufficient": True, "n": len(vals), "lost": lost, "wanted": len(samples)}
    return {
        "n": len(vals),
        "min": round(min(vals), 1),
        "median": round(statistics.median(vals), 1),
        "max": round(max(vals), 1),
        "stdev": round(statistics.stdev(vals), 1) if len(vals) > 1 else 0.0,
        "lost": lost,
    }


def _existing_windows(title):
    return set(x11.window_ids(title))


def _wait_gone(title, before, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not (_existing_windows(title) - before):
            return True
        time.sleep(0.05)
    return False


def _click_latency(wid):
    r = x11.probe_click(wid, 200, 150, settle=250)
    return r[0] if r else None


def calibrate(reps=25):
    """Floor: latency measured against a target that repaints immediately."""
    if not x11.SYNTH or not x11.SYNTH.exists():
        return None
    before = _existing_windows("fnsynth")
    proc = subprocess.Popen([str(x11.SYNTH), "0"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wid = x11.find_window("fnsynth", exclude=before, timeout=10)
        if not wid:
            return None
        time.sleep(0.6)
        return _summarise([_click_latency(wid) for _ in range(reps)])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        _wait_gone("fnsynth", before)


def verify_probe(floor, reps=6):
    """Point the probe at targets with known delays and read it back."""
    if not x11.SYNTH or not x11.SYNTH.exists():
        return None
    checks = []
    for truth in (50, 150):
        before = _existing_windows("fnsynth")
        proc = subprocess.Popen([str(x11.SYNTH), str(truth)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wid = x11.find_window("fnsynth", exclude=before, timeout=10)
            if not wid:
                continue
            time.sleep(0.6)
            got = _summarise([_click_latency(wid) for _ in range(reps)])
            if got and not got.get("insufficient"):
                checks.append({"truth_ms": truth, "measured_median": got["median"],
                               "overhead": round(got["median"] - truth, 1)})
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            _wait_gone("fnsynth", before)
    return checks


def run_gate():
    """Calibrate and verify. Returns (floor, checks). Raises GateError when
    the instrument does not reproduce known delays within tolerance."""
    floor = calibrate()
    if not floor:
        raise GateError("calibration target (fnsynth) produced no measurement")
    if floor.get("insufficient"):
        raise GateError(f"calibration insufficient: only {floor['n']}/{floor['wanted']} samples")
    checks = verify_probe(floor) or []
    if len(checks) < 2:
        raise GateError("verification against known delays produced no measurements")
    for c in checks:
        err = abs(c["overhead"] - floor["median"])
        if err > 8.0:
            raise GateError(
                f"probe cannot reproduce a known delay: truth {c['truth_ms']} ms measured "
                f"{c['measured_median']} ms, overhead {c['overhead']:.1f} ms, "
                f"floor {floor['median']} ms (delta {err:.1f} ms > 8 ms)")
    return floor, checks


def peak_rss_kb(pid):
    """VmHWM (kernel high-water mark) of the whole process tree, split into
    anon (own) and file (shared library) resident bytes."""
    def descendants(pid):
        out = [pid]
        try:
            tasks = Path(f"/proc/{pid}/task").iterdir()
        except (FileNotFoundError, PermissionError):
            return out
        for task in tasks:
            try:
                for child in (task / "children").read_text().split():
                    out.extend(descendants(int(child)))
            except (FileNotFoundError, PermissionError, ValueError):
                continue
        return out

    peak = anon = filed = 0
    found = False
    for p in set(descendants(pid)):
        try:
            text = Path(f"/proc/{p}/status").read_text()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        for line in text.splitlines():
            if line.startswith("VmHWM:"):
                peak += int(line.split()[1]); found = True
            elif line.startswith("RssAnon:"):
                anon += int(line.split()[1])
            elif line.startswith("RssFile:"):
                filed += int(line.split()[1])
    return {"peak_kb": peak, "anon_kb": anon, "file_kb": filed} if found else None


def measure_basics(entry):
    out = {"edition": entry["name"]}
    binpath = entry["bin_path"]
    if binpath.exists():
        out["binary_size_bytes"] = binpath.stat().st_size
    else:
        out["binary_size_bytes"] = None
    return out


def measure_startup(entry, workroot, reps=5, title=None):
    """Launch to the first painted frame (the 'painted' marker), median of
    reps after a discarded cold first launch."""
    from .gui import GuiSession
    title = title or entry["title"]
    d = entry["path"]
    binpath = d / entry["binary"]

    work = workroot / f"{entry['name']}-startup"
    if work.exists():
        shutil.rmtree(work)
    (work / "notes").mkdir(parents=True)
    (work / "notes" / "doc.md").write_text("# Doc\n\nstartup\n")

    samples = []
    for i in range(reps + 1):
        before = _existing_windows(title)
        t0 = time.perf_counter()
        session = GuiSession(entry, work, work / "notes").start(event_file=True)
        try:
            session.wait_window(timeout=20)
            ready = session.wait_ready(timeout=30)
            elapsed = (time.perf_counter() - t0) * 1000 if ready else None
        finally:
            session.stop()
        _wait_gone(title, before)
        if i > 0:
            samples.append(elapsed)
    return _summarise(samples)


def _timed(trigger, marker, sess, timeout=20.0):
    """Time a single operation: run trigger(), then wait for the marker.
    Returns elapsed ms, or None if the marker never arrived."""
    t0 = time.perf_counter()
    trigger()
    if sess.wait_event(marker, timeout=timeout):
        return (time.perf_counter() - t0) * 1000
    return None


def measure_latencies(entry, workroot, reps=5):
    """One live session: open a far document, then time open / save /
    export-html / export-pdf operations through the keyboard and the
    completion markers."""
    from .gui import GuiSession, EVENT_OPEN
    d = entry["path"]
    binpath = d / entry["binary"]

    work = workroot / entry["name"]
    if work.exists():
        shutil.rmtree(work)
    (work / "notes").mkdir(parents=True)
    doc = work / "notes" / "doc.md"
    doc.write_text("# Doc\n\nmeasure\n")
    far = work / "far.md"
    far.write_text("# Far\n\ncontent\n")
    out_html = work / "out.html"
    out_pdf = work / "out.pdf"

    sess = GuiSession(entry, work, work / "notes").start(event_file=True)
    out = {}
    try:
        if not sess.wait_window(timeout=25) or not sess.wait_ready(timeout=30):
            out["error"] = "no window or no painted marker"
            return out
        sess.wid = x11.find_window(entry["title"], timeout=5)
        time.sleep(0.8)

        # Open once to have a document, then time a second open (same file).
        sess.open_path(far)
        if not sess.wait_event(EVENT_OPEN, timeout=20):
            out["error"] = "could not open the seed document"
            return out

        def open_rep():
            sess.open_path(far, settle=0.2)

        open_s = [_timed(open_rep, "open", sess) for _ in range(reps)]

        # Save: dirty the document first (a keystroke into the editor), then
        # Ctrl+S. The keystroke lands wherever focus is; after an open the
        # editor should own it.
        save_s = []
        for _ in range(reps):
            x11.type_text("a")
            time.sleep(0.3)
            x11.window_settled(sess.wid)
            save_s.append(_timed(lambda: sess.press("ctrl+s", settle=0),
                                 "save", sess))

        def export_rep(path):
            def go():
                sess.press("ctrl+e" if path.suffix == ".html" else "ctrl+shift+e",
                           settle=0.2)
                sess.press("ctrl+l", settle=0.2)
                x11.type_text(str(path))
                time.sleep(0.2)
                sess.press("Return", settle=0)
            return go

        html_s = [_timed(export_rep(out_html), "export-html", sess) for _ in range(reps)]
        pdf_s = [_timed(export_rep(out_pdf), "export-pdf", sess) for _ in range(reps)]

        out["open_ms"] = _summarise(open_s)
        out["save_ms"] = _summarise(save_s)
        out["export_html_ms"] = _summarise(html_s)
        out["export_pdf_ms"] = _summarise(pdf_s)

        # Interaction latency through the pixel probe (keystroke -> glyph).
        ed = None
        try:
            r = x11.probe_key(sess.wid, "x", settle=250)
        except Exception:
            r = None
        if r:
            out["edit_ms"] = _summarise([x11.probe_key(sess.wid, "x", settle=250)[0]
                                         for _ in range(reps)])
        out["rss"] = peak_rss_kb(sess.proc.pid)
        out["window"] = f"{sess.wid}"
    finally:
        sess.stop()
    return out


def measure_edition(entry, workroot, reps=5):
    """Everything measured for one edition, in one dict."""
    out = measure_basics(entry)
    binpath = entry["bin_path"]
    if not binpath.exists():
        out["error"] = f"no binary at {entry['binary']}; build it first"
        return out
    out["startup_ms"] = measure_startup(entry, workroot, reps)
    lat = measure_latencies(entry, workroot, reps)
    if "error" in lat:
        out["error"] = lat["error"]
        return out
    for k in ("open_ms", "save_ms", "export_html_ms", "export_pdf_ms",
              "edit_ms", "rss", "window"):
        if k in lat:
            out[k] = lat[k]
    return out
