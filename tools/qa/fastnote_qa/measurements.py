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
import threading
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


# ── RAM sampling ───────────────────────────────────────────────────────

class RamSampler:
    """Background thread that polls /proc/[pid]/status for VmRSS every
    interval_ms. Tracks peak_kb during each named 'arc' (operation window).

    Usage:
        sampler = RamSampler(pid)
        sampler.start()
        # ... do operation ...
        peak = sampler.peak_kb()
        sampler.stop()
    """

    def __init__(self, pid, interval_ms=10):
        self.pid = pid
        self.interval = interval_ms / 1000.0
        self._stop_event = threading.Event()
        self._thread = None
        self._samples = []       # (timestamp, rss_kb)
        self._peak_kb = 0
        self._arcs = {}          # name -> peak_kb during that arc

    def _read_vm_rss(self, pid):
        """Read VmRSS in KB from /proc/[pid]/status (whole process tree)."""
        total = 0
        pids = [pid]
        try:
            for child_path in Path(f"/proc/{pid}/task").rglob("children"):
                for c in child_path.read_text().split():
                    try:
                        pids.append(int(c))
                    except ValueError:
                        pass
        except (FileNotFoundError, PermissionError):
            pass

        for p in set(pids):
            try:
                text = Path(f"/proc/{p}/status").read_text()
                for line in text.splitlines():
                    if line.startswith("VmRSS:"):
                        total += int(line.split()[1])
                        break
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        return total

    def _poll(self):
        while not self._stop_event.is_set():
            try:
                rss = self._read_vm_rss(self.pid)
                if rss > 0:
                    self._samples.append((time.monotonic(), rss))
                    if rss > self._peak_kb:
                        self._peak_kb = rss
            except (FileNotFoundError, ProcessLookupError):
                pass
            self._stop_event.wait(self.interval)

    def start(self):
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def peak_kb(self):
        """Peak VmRSS across the entire sampling window."""
        return self._peak_kb

    def peak_between(self, t0, t1):
        """Peak VmRSS between two monotonic timestamps."""
        peak = 0
        for ts, rss in self._samples:
            if t0 <= ts <= t1 and rss > peak:
                peak = rss
        return peak

    def mark_arc_start(self, name):
        """Begin a named measurement arc."""
        self._arcs[name] = {"start": time.monotonic(), "peak": 0}

    def mark_arc_end(self, name):
        """End a named measurement arc. Returns peak KB during that arc."""
        if name not in self._arcs:
            return 0
        arc = self._arcs[name]
        t0, t1 = arc["start"], time.monotonic()
        peak = self.peak_between(t0, t1)
        arc["end"] = t1
        arc["peak"] = peak
        return peak

    def get_arc_peak(self, name):
        """Get the peak KB for a completed arc."""
        arc = self._arcs.get(name)
        return arc["peak"] if arc else 0


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


def _summarise_ram(samples):
    """Summarise peak RAM samples (KB). Returns median peak."""
    vals = [v for v in samples if v is not None and v > 0]
    if not vals:
        return {"peak_kb": 0}
    return {
        "peak_kb": max(vals),
        "median_peak_kb": round(statistics.median(vals)),
        "min_peak_kb": min(vals),
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
    reps after a discarded cold first launch. Also measures peak RAM during
    the startup arc."""
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
    ram_samples = []
    for i in range(reps + 1):
        before = _existing_windows(title)
        t0 = time.perf_counter()
        session = GuiSession(entry, work, work / "notes").start(event_file=True)
        sampler = RamSampler(session.proc.pid)
        sampler.start()
        try:
            session.wait_window(timeout=20)
            ready = session.wait_ready(timeout=30)
            elapsed = (time.perf_counter() - t0) * 1000 if ready else None
            peak = sampler.peak_kb()
        finally:
            sampler.stop()
            session.stop()
        _wait_gone(title, before)
        if i > 0:
            samples.append(elapsed)
            ram_samples.append(peak)
    return _summarise(samples), _summarise_ram(ram_samples)


def _timed(trigger, marker, sess, timeout=20.0):
    """Time a single operation: run trigger(), then wait for the marker.
    Returns elapsed ms, or None if the marker never arrived."""
    t0 = time.perf_counter()
    trigger()
    if sess.wait_event(marker, timeout=timeout):
        return (time.perf_counter() - t0) * 1000
    return None


def _timed_with_ram(trigger, marker, sampler, arc_name, sess, timeout=20.0):
    """Time a single operation and track peak RAM during the arc.
    Returns (elapsed_ms, peak_ram_kb) or (None, 0) on timeout."""
    sampler.mark_arc_start(arc_name)
    t0 = time.perf_counter()
    trigger()
    if sess.wait_event(marker, timeout=timeout):
        elapsed = (time.perf_counter() - t0) * 1000
        peak = sampler.mark_arc_end(arc_name)
        return elapsed, peak
    sampler.mark_arc_end(arc_name)
    return None, 0


def measure_close(sess, sampler, timeout=10.0):
    """Measure time from close command to PID truly gone.
    Returns (close_ms, peak_ram_kb_during_close)."""
    pid = sess.proc.pid
    sampler.mark_arc_start("close")
    t0 = time.perf_counter()

    # Send WM close
    if sess.wid:
        x11.close_window(sess.wid)

    # Wait for PID to disappear
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)  # Check if PID exists
        except ProcessLookupError:
            # PID gone
            elapsed = (time.perf_counter() - t0) * 1000
            peak = sampler.mark_arc_end("close")
            return elapsed, peak
        time.sleep(0.02)

    sampler.mark_arc_end("close")
    return None, 0


def measure_latencies(entry, workroot, reps=5):
    """One live session: open a far document, then time open / save /
    export-html / export-pdf / edit operations through the keyboard and the
    completion markers. Tracks peak RAM per operation and measures close time."""
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
    sampler = RamSampler(sess.proc.pid)
    sampler.start()
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

        open_results = [_timed_with_ram(open_rep, "open", sampler, f"open_{i}", sess)
                        for i in range(reps)]

        # Save: dirty the document first (a keystroke into the editor), then
        # Ctrl+S. The keystroke lands wherever focus is; after an open the
        # editor should own it.
        save_results = []
        for i in range(reps):
            x11.type_text("a")
            time.sleep(0.3)
            x11.window_settled(sess.wid)
            save_results.append(
                _timed_with_ram(lambda: sess.press("ctrl+s", settle=0),
                                "save", sampler, f"save_{i}", sess))

        def export_rep(path):
            def go():
                sess.press("ctrl+e" if path.suffix == ".html" else "ctrl+shift+e",
                           settle=0.2)
                sess.press("ctrl+l", settle=0.2)
                x11.type_text(str(path))
                time.sleep(0.2)
                sess.press("Return", settle=0)
            return go

        html_results = [_timed_with_ram(export_rep(out_html), "export-html",
                                        sampler, f"html_{i}", sess)
                        for i in range(reps)]
        pdf_results = [_timed_with_ram(export_rep(out_pdf), "export-pdf",
                                       sampler, f"pdf_{i}", sess)
                       for i in range(reps)]

        # Extract timing and RAM from combined results
        open_s = [r[0] for r in open_results]
        open_ram = [r[1] for r in open_results if r[1] > 0]
        save_s = [r[0] for r in save_results]
        save_ram = [r[1] for r in save_results if r[1] > 0]
        html_s = [r[0] for r in html_results]
        html_ram = [r[1] for r in html_results if r[1] > 0]
        pdf_s = [r[0] for r in pdf_results]
        pdf_ram = [r[1] for r in pdf_results if r[1] > 0]

        out["open_ms"] = _summarise(open_s)
        out["open_ram_kb"] = _summarise_ram(open_ram)
        out["save_ms"] = _summarise(save_s)
        out["save_ram_kb"] = _summarise_ram(save_ram)
        out["export_html_ms"] = _summarise(html_s)
        out["export_html_ram_kb"] = _summarise_ram(html_ram)
        out["export_pdf_ms"] = _summarise(pdf_s)
        out["export_pdf_ram_kb"] = _summarise_ram(pdf_ram)

        # Interaction latency through the pixel probe (keystroke -> glyph).
        try:
            r = x11.probe_key(sess.wid, "x", settle=250)
        except Exception:
            r = None
        if r:
            edit_results = [(x11.probe_key(sess.wid, "x", settle=250)[0], 0)
                            for _ in range(reps)]
            out["edit_ms"] = _summarise([r[0] for r in edit_results])

        # Overall peak RSS (entire session)
        out["rss"] = peak_rss_kb(sess.proc.pid)
        out["window"] = f"{sess.wid}"
    finally:
        # Measure close time: send close, wait for PID to vanish
        close_ms, close_ram = measure_close(sess, sampler, timeout=10.0)
        out["close_ms"] = {"median": round(close_ms, 1)} if close_ms else {"insufficient": True}
        out["close_ram_kb"] = {"peak_kb": close_ram} if close_ram else {"peak_kb": 0}
        sampler.stop()
        sess.stop()
    return out


def measure_edition(entry, workroot, reps=5):
    """Everything measured for one edition, in one dict."""
    out = measure_basics(entry)
    binpath = entry["bin_path"]
    if not binpath.exists():
        out["error"] = f"no binary at {entry['binary']}; build it first"
        return out
    startup_time, startup_ram = measure_startup(entry, workroot, reps)
    out["startup_ms"] = startup_time
    out["startup_ram_kb"] = startup_ram
    lat = measure_latencies(entry, workroot, reps)
    if "error" in lat:
        out["error"] = lat["error"]
        return out
    for k in ("open_ms", "open_ram_kb", "save_ms", "save_ram_kb",
              "export_html_ms", "export_html_ram_kb",
              "export_pdf_ms", "export_pdf_ram_kb",
              "edit_ms", "close_ms", "close_ram_kb", "rss", "window"):
        if k in lat:
            out[k] = lat[k]
    return out
