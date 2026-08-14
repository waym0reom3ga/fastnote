"""Measurement: binary size, startup, peak RSS, and interaction latencies.

Nothing is timed inside the application. Input is delivered through XTEST and
the clock runs until the observable witness (pixels, window title, file on
disk) changes. The instrument is validated against fnsynth's known delays
before any edition is measured; a mismatch stops the run."""

import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from . import x11

MIN_SAMPLES = 5


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
    """Launch to first painted frame (ready-file), median of reps after a
    discarded cold first launch."""
    from .gui import GuiSession
    title = title or entry["title"]
    d = entry["path"]
    binpath = d / entry["binary"]

    work = workroot / f"{entry['name']}-startup"
    if work.exists():
        shutil.rmtree(work)
    (work / "notes").mkdir(parents=True)
    doc = work / "notes" / "doc.md"
    doc.write_text("# Doc\n\nstartup\n")

    samples = []
    for i in range(reps + 1):
        before = _existing_windows(title)
        t0 = time.perf_counter()
        session = GuiSession(entry, work, work / "notes").start()
        try:
            session.wait_window(timeout=20)
            deadline = time.time() + 30
            ready = work / "ready"
            while not ready.exists() and time.time() < deadline:
                time.sleep(0.002)
            elapsed = (time.perf_counter() - t0) * 1000 if ready.exists() else None
        finally:
            session.stop()
        _wait_gone(title, before)
        if i > 0:
            samples.append(elapsed)
    return _summarise(samples)
