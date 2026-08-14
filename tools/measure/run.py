#!/usr/bin/env python3
"""FastNote measurement harness.

Measures each edition the way a user experiences it: a real binary, a real window on a real
display, real input events delivered through XTEST, and the wall-clock interval until the
screen actually changes.

What is measured
----------------
  binary size    bytes of the built artifact
  startup        process launch to the window's first painted frame
  peak RSS       kernel high-water mark of resident memory (VmHWM), not a sample
  open latency   click Open   -> file browser appears
  export latency click Export -> destination browser appears
  edit latency   keystroke    -> glyph on screen
  save latency   Ctrl+S       -> screen acknowledges

Nothing is timed inside the application. An in-process timer stops when the handler
returns, which is before layout, compositing and presentation; that number flatters every
toolkit, and flatters hardest the ones that defer the most work.

Control coordinates
-------------------
Buttons are not clicked at guessed coordinates. Each edition publishes the rectangles its
own toolkit laid out (--control-map), and the harness clicks those. Guessed coordinates
were tried first and mostly missed, which produces a timeout if you are lucky and a hit on
the wrong control if you are not.

Instrument overhead
-------------------
Click-to-pixel includes the whole display pipeline: X dispatch, the toolkit's response, and
the wait for the next scanout. On a 60 Hz screen that floor is around 20 ms. It is measured
rather than assumed -- fnsynth repaints after a known delay and fnprobe is checked against
it -- and reported alongside the results instead of being silently subtracted, because the
user waits through it too. The 'app' column shows the edition's own share.
"""

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MEASURE = ROOT / "tools" / "measure"
PROBE = MEASURE / "fnprobe"
SYNTH = MEASURE / "fnsynth"
WORK = ROOT / "tools" / "tmp" / "measure"

# dir, binary, window-title pattern, control-map flag style
EDITIONS = {
    "go_gio":  ("fastnote_go_gio_ed",  "fastnote-gio", "FastNote", "flag"),
    "go_fyne": ("fastnote_go_fyne_ed", "fastnotes",    "FastNote", "flag"),
    "c_gtk4":  ("fastnote_c_gtk4_ed",  "fastnote",     "FastNotes", "env"),
    "rust_gtk4": ("fastnote_rust_gtk4_ed",
                  "target/release/fastnote-gtk4", "FastNotes", "env"),
    "rust_egui": ("fastnote_rust_egui_ed",
                  "target/release/fastnote-egui", "FastNotes", "env"),
}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def existing_windows(title):
    return set(sh(["xdotool", "search", "--name", title]).stdout.split())


def find_window(title, exclude, timeout=25.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for wid in sh(["xdotool", "search", "--name", title]).stdout.split():
            if wid not in exclude:
                if "Geometry" in sh(["xdotool", "getwindowgeometry", wid]).stdout:
                    return wid
        time.sleep(0.03)
    return None


def geometry(wid):
    m = re.search(r"Geometry:\s*(\d+)x(\d+)",
                  sh(["xdotool", "getwindowgeometry", wid]).stdout)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _descendants(pid):
    """Every process in the tree rooted at pid, including pid itself."""
    out = [pid]
    try:
        kids = Path(f"/proc/{pid}/task").iterdir()
    except (FileNotFoundError, PermissionError):
        return out
    for task in kids:
        try:
            for child in (task / "children").read_text().split():
                out.extend(_descendants(int(child)))
        except (FileNotFoundError, PermissionError, ValueError):
            continue
    return out


def peak_rss_kb(pid):
    """Resident memory of the process tree, split into private and shared.

    Three figures, because one hides too much:

      peak   VmHWM, the kernel's own high-water mark -- a true peak, not a poll.
      anon   RssAnon: heap, stack, and anything else this program allocated.
      file   RssFile: pages backed by mapped files, overwhelmingly shared library text.

    The split matters for this comparison. A GTK port reports ~213 MB resident, of which
    ~183 MB is GTK and its dependencies mapped in and shared with every other GTK process
    on the machine; its own footprint is ~29 MB. A statically linked Go binary carries
    almost all of its resident set as anon. Quoting only the total makes the dynamically
    linked ports look profligate and the static ones frugal, when the truth is closer to
    the reverse.

    The whole tree is summed because a port that forks a helper -- or re-execs itself, as
    the Python launchers do through run.sh -- leaves the launched pid holding nothing.
    """
    peak = anon = filed = 0
    found = False
    for p in set(_descendants(pid)):
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
    if not found:
        return None
    return {"peak_kb": peak, "anon_kb": anon, "file_kb": filed}


def read_control_map(path):
    """Parse the rectangles the edition published. Labels may contain spaces, so the file
    is tab-separated and split on tabs only."""
    controls = {}
    if not path.exists():
        return controls
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        label, x, y, w, h = parts
        try:
            controls[label] = (int(x), int(y), int(w), int(h))
        except ValueError:
            continue
    return controls


def click_point(rect):
    """A point safely inside a control.

    The centre is used where the rectangle is small enough to trust. Gio reports origins
    accurately but extents only approximately, so for wide rectangles a point near the
    origin is safer -- it is inside the control on every toolkit measured.
    """
    x, y, w, h = rect
    if w <= 200:
        return x + w // 2, y + h // 2
    return x + 12, y + min(h // 2, 16)


def probe(wid, *args, settle=300, timeout=4000):
    r = sh([str(PROBE), "--window", wid, "--settle", str(settle),
            "--timeout", str(timeout), *[str(a) for a in args]])
    if r.returncode != 0:
        return None
    parts = r.stdout.strip().split("\t")
    if len(parts) < 2 or parts[1] == "timeout":
        return None
    return float(parts[1])


# A median computed from one or two surviving samples is not a median. Below this many,
# the figure is withheld rather than printed with a footnote nobody reads.
MIN_SAMPLES = 5


def summarise(samples):
    vals = [v for v in samples if v is not None]
    lost = len(samples) - len(vals)
    if len(vals) < MIN_SAMPLES:
        # Reported as a refusal, not as a number: the earlier harness printed "11 ms"
        # from a single surviving sample out of seven.
        return {"insufficient": True, "n": len(vals), "lost": lost,
                "wanted": max(MIN_SAMPLES, len(samples))}
    return {"n": len(vals), "min": round(min(vals), 1),
            "median": round(statistics.median(vals), 1),
            "max": round(max(vals), 1),
            "stdev": round(statistics.stdev(vals), 1) if len(vals) > 1 else 0.0,
            "lost": lost}


def calibrate(reps=25):
    """Point the probe at a target that repaints immediately, to find the floor."""
    if not SYNTH.exists():
        return None
    before = existing_windows("fnsynth")
    proc = subprocess.Popen([str(SYNTH), "0"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wid = find_window("fnsynth", before, timeout=10)
        if not wid:
            return None
        # The target must be settled and frontmost before timing, and a gap is needed
        # between clicks: fnsynth is single-threaded, so a click arriving while it is
        # still repainting is answered late and the sample is meaningless.
        time.sleep(0.6)
        return summarise([probe(wid, "click", 200, 150, settle=250) for _ in range(reps)])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def verify_probe(floor, reps=6):
    """Check the probe tracks a known delay. A latency tool that has never been pointed at
    a known quantity is a number generator."""
    if not SYNTH.exists():
        return None
    checks = []
    for truth in (50, 150):
        before = existing_windows("fnsynth")
        proc = subprocess.Popen([str(SYNTH), str(truth)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wid = find_window("fnsynth", before, timeout=10)
            if not wid:
                continue
            time.sleep(0.6)
            got = summarise([probe(wid, "click", 200, 150, settle=250)
                             for _ in range(reps)])
            if got:
                checks.append({"truth_ms": truth, "measured_median": got["median"],
                               "overhead": round(got["median"] - truth, 1)})
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            # Wait for the window to disappear. Otherwise the next iteration's
            # find_window can return this one, and the probe then measures a dead
            # window that never changes -- or worse, a stale one that does.
            for _ in range(100):
                if not existing_windows("fnsynth") - before:
                    break
                time.sleep(0.05)
    return checks


def measure_startup(name, reps=5):
    """Time launch to first painted frame, repeatedly.

    A single sample is not a measurement: across three runs of one edition this varied
    from 605 ms to 957 ms, and reporting the last one as the figure would have been
    reporting noise. Cold-cache effects make the first launch slower than the rest, so
    it is discarded rather than averaged in.
    """
    dirname, binary, title, mapstyle = EDITIONS[name]
    d = ROOT / "editions" / dirname
    binpath = d / binary

    work = WORK / f"{name}-startup"
    if work.exists():
        shutil.rmtree(work)
    (work / "notes").mkdir(parents=True)
    shutil.copy(ROOT / "docs" / "testdata" / "template.md", work / "notes" / "doc.md")
    doc = work / "notes" / "doc.md"

    samples = []
    for i in range(reps + 1):
        ready = work / f"ready{i}"
        env = dict(os.environ)
        env["FASTNOTE_CONFIG_DIR"] = str(work / "cfg")
        cmd = [str(binpath), "--notes-dir", str(work / "notes"), "--open", str(doc)]
        if mapstyle == "flag":
            cmd += ["--ready-file", str(ready)]
        else:
            env["FASTNOTE_READY_FILE"] = str(ready)

        before = existing_windows(title)
        t0 = time.perf_counter()
        proc = subprocess.Popen(cmd, cwd=d, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while not ready.exists() and time.time() < deadline:
            time.sleep(0.001)
        elapsed = (time.perf_counter() - t0) * 1000 if ready.exists() else None

        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=5)
        # Let the window actually go, so the next launch is not racing its teardown.
        for _ in range(100):
            if not existing_windows(title) - before:
                break
            time.sleep(0.05)

        # The first launch pays for cold page cache; it is not what a user sees twice.
        if i > 0:
            samples.append(elapsed)
    return summarise(samples)


def measure(name, reps):
    dirname, binary, title, mapstyle = EDITIONS[name]
    d = ROOT / "editions" / dirname
    binpath = d / binary
    out = {"edition": name}

    if not binpath.exists():
        out["error"] = f"no binary at {binary}; build it first"
        return out
    out["binary_size_bytes"] = binpath.stat().st_size

    work = WORK / name
    if work.exists():
        shutil.rmtree(work)
    (work / "notes").mkdir(parents=True)
    shutil.copy(ROOT / "docs" / "testdata" / "template.md", work / "notes" / "doc.md")
    doc = work / "notes" / "doc.md"
    cmap = work / "controls.tsv"
    ready = work / "ready"

    env = dict(os.environ)
    env["FASTNOTE_CONFIG_DIR"] = str(work / "cfg")

    cmd = [str(binpath), "--notes-dir", str(work / "notes"), "--open", str(doc)]
    if mapstyle == "flag":
        cmd += ["--control-map", str(cmap), "--ready-file", str(ready)]
    else:
        env["FASTNOTE_CONTROL_MAP"] = str(cmap)
        env["FASTNOTE_READY_FILE"] = str(ready)

    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, cwd=d, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wid = find_window(title, existing_windows(title), timeout=25)
        if not wid:
            out["error"] = "no window appeared"
            return out

        deadline = time.time() + 25
        while not ready.exists() and time.time() < deadline:
            time.sleep(0.002)
        if not ready.exists():
            out["error"] = "window never reported a painted frame"
            return out

        out["startup_first_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        w, h = geometry(wid)
        out["window"] = f"{w}x{h}"

        controls = read_control_map(cmap)
        out["controls_found"] = len(controls)
        if not controls:
            out["error"] = "edition published no control map"
            return out

        time.sleep(0.8)

        # A still window is a precondition: anything animating on its own would be timed
        # instead of the response to input.
        r = sh([str(PROBE), "--window", wid, "--settle", "400", "baseline"])
        out["baseline_px"] = int(r.stdout.strip().split("\t")[2]) if r.returncode == 0 else -1

        def screen_settled(timeout=2.0):
            """Wait until the window stops changing on its own.

            Timing a click while a previous transition is still painting measures the
            transition. The probe's own baseline mode reports whether anything moved
            between two captures, so it is used as the settling test.
            """
            deadline = time.time() + timeout
            while time.time() < deadline:
                r = sh([str(PROBE), "--window", wid, "--settle", "120", "baseline"])
                if r.returncode == 0 and r.stdout.strip().split("\t")[2] == "0":
                    return True
                time.sleep(0.05)
            return False

        def click_control(label, n):
            """Time n clicks on one control, restoring the starting screen between them.

            The previous version pressed Escape and hoped. When the modal did not
            actually close, later repetitions clicked a screen that was not the one
            assumed, the pixels never changed, and the sample was lost -- which is why
            six of seven samples vanished and the median came from the survivor.
            Each repetition now verifies it is back at the starting screen first, and
            says so when it cannot get there.
            """
            rect = controls.get(label)
            if not rect:
                return None
            x, y = click_point(rect)

            samples = []
            for _ in range(n):
                if not screen_settled():
                    samples.append(None)
                    continue
                samples.append(probe(wid, "click", x, y, settle=250))

                # Dismiss whatever opened and confirm it actually went away, rather than
                # assuming Escape was honoured.
                for _ in range(3):
                    sh(["xdotool", "key", "--window", wid, "Escape"])
                    time.sleep(0.25)
                    if screen_settled(timeout=1.0):
                        break
            return summarise(samples)

        out["open_ms"] = click_control("Open", reps)
        out["export_ms"] = click_control("Export", reps)

        # Typing: click into the editor pane first so keystrokes land there.
        ed = controls.get("editor")
        if ed:
            ex, ey = click_point(ed)
            sh(["xdotool", "mousemove", "--window", wid, str(ex), str(ey), "click", "1"])
            time.sleep(0.4)
            out["edit_ms"] = summarise(
                [probe(wid, "key", "x", settle=250) for _ in range(reps)])

            # Saving is only observable when there is something to save: on a clean
            # document Ctrl+S changes nothing on screen, the probe correctly reports no
            # pixel change, and every sample was discarded -- which is why this figure
            # was missing entirely. Each repetition dirties the document first and
            # confirms the dirty marker appeared before timing the save.
            save = []
            for _ in range(reps):
                if not screen_settled():
                    save.append(None)
                    continue
                # A keystroke into the editor; the title gains its dirty marker.
                dirtied = probe(wid, "key", "a", settle=200)
                if dirtied is None:
                    save.append(None)
                    continue
                time.sleep(0.2)
                save.append(probe(wid, "key", "ctrl+s", settle=200))
                time.sleep(0.2)
            out["save_ms"] = summarise(save)

        out["rss"] = peak_rss_kb(proc.pid)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    return out


def report(results, floor, checks):
    fl = floor["median"] if floor else 0.0

    print("\n" + "=" * 82)
    print("FastNote measured results")
    print("=" * 82)
    print("Real binaries, real windows, real input, real pixels.\n")

    print(f"{'edition':<10} {'binary':>10} {'startup':>14} "
          f"{'RSS own':>9} {'RSS shared':>11} {'RSS peak':>9}")
    print("-" * 82)
    for r in results:
        if "error" in r:
            print(f"{r['edition']:<10} ERROR: {r['error']}")
            continue
        b = r["binary_size_bytes"]
        size = f"{b/1048576:.1f} MB" if b >= 1048576 else f"{b/1024:.0f} KB"

        su = r.get("startup_ms")
        if not su:
            startup = "not measured"
        elif su.get("insufficient"):
            startup = f"only {su['n']}"
        else:
            startup = f"{su['median']:.0f}ms +/-{su.get('stdev', 0):.0f}"

        m = r.get("rss") or {}
        own = f"{m['anon_kb']/1024:.0f} MB" if m else "n/a"
        shared = f"{m['file_kb']/1024:.0f} MB" if m else "n/a"
        peak = f"{m['peak_kb']/1024:.0f} MB" if m else "n/a"
        print(f"{r['edition']:<10} {size:>10} {startup:>14} "
              f"{own:>9} {shared:>11} {peak:>9}")

    print("\n  RSS own    = RssAnon: heap and stack, this program's own memory.")
    print("  RSS shared = RssFile: mapped libraries, shared with every other process")
    print("               using them. A GTK port's is mostly GTK, already resident.")
    print("  startup    = launch to first painted frame, median of 5 after a warm-up.")

    print(f"\nInteraction latency: input event to pixel change, median of n samples.")
    print(f"Instrument floor: {fl:.0f} ms (60 Hz frame interval dominates).")
    print(f"'app' = median minus floor, the edition's own share.\n")

    print(f"{'edition':<10} {'open':>17} {'edit':>17} {'save':>17} {'export':>17}")
    print("-" * 82)
    for r in results:
        if "error" in r:
            continue
        cells = []
        for k in ("open_ms", "edit_ms", "save_ms", "export_ms"):
            v = r.get(k)
            if not v:
                cells.append("not measured")
            elif v.get("insufficient"):
                cells.append(f"only {v['n']}/{v['wanted']}")
            else:
                cells.append(f"{v['median']:.0f} (app {max(0.0, v['median']-fl):.0f})")
        print(f"{r['edition']:<10} " + " ".join(f"{c:>17}" for c in cells))

    if checks:
        print("\nProbe verification against known delays:")
        for c in checks:
            print(f"  target {c['truth_ms']:>4} ms -> measured {c['measured_median']:>6.1f} ms"
                  f"  (overhead {c['overhead']:+.1f} ms)")

    for r in results:
        if r.get("baseline_px", 0) > 0:
            print(f"\nnote: {r['edition']}'s window was not still before timing "
                  f"({r['baseline_px']} sampled bytes changing unprompted); its latencies "
                  f"may include that motion.")
        for k in ("open_ms", "edit_ms", "save_ms", "export_ms"):
            v = r.get(k)
            if not v:
                continue
            if v.get("insufficient"):
                print(f"note: {r['edition']} {k}: withheld -- only {v['n']} usable "
                      f"samples, {v['lost']} saw no pixel change. A median of "
                      f"{v['n']} is not a measurement.")
            elif v.get("lost"):
                print(f"note: {r['edition']} {k}: {v['lost']} of "
                      f"{v['n']+v['lost']} samples discarded (no pixel change in time).")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("editions", nargs="*", choices=list(EDITIONS) + [], default=None)
    ap.add_argument("--reps", type=int, default=7)
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--i-know-it-grabs-input", action="store_true",
                    help="required: the run injects real input and takes over the machine")
    args = ap.parse_args()

    if not PROBE.exists():
        print(f"error: {PROBE} not built. Run: make -C measure", file=sys.stderr)
        return 2
    if not os.environ.get("DISPLAY"):
        print("error: no DISPLAY; these measurements need a real screen.", file=sys.stderr)
        return 2

    # This harness injects real pointer and keyboard events through XTEST. They go to
    # whatever is focused, so a run takes over the machine for its duration and will type
    # into another window if focus moves. That is disruptive enough to require saying so.
    if not args.i_know_it_grabs_input:
        print(
            "This measures real windows by injecting real input: it will take over the\n"
            "pointer and keyboard for the duration, and stray keystrokes can land in\n"
            "other windows if focus changes. Do not use the machine while it runs.\n\n"
            "Re-run with --i-know-it-grabs-input to proceed.",
            file=sys.stderr,
        )
        return 2

    WORK.mkdir(parents=True, exist_ok=True)

    floor = calibrate()
    if args.calibrate:
        print("instrument floor (zero-delay target):", floor)
        print("verification:", verify_probe(floor))
        return 0

    wanted = args.editions or list(EDITIONS)
    results = []
    for name in EDITIONS:
        if name in wanted:
            print(f"measuring {name} ...", file=sys.stderr, flush=True)
            r = measure(name, args.reps)
            if "error" not in r:
                print(f"  startup x{5} ...", file=sys.stderr, flush=True)
                r["startup_ms"] = measure_startup(name)
            results.append(r)

    checks = verify_probe(floor)
    report(results, floor, checks)

    if args.json:
        args.json.write_text(json.dumps(
            {"floor": floor, "verification": checks, "results": results}, indent=2))
        print(f"\nraw: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
