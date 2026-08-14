#!/usr/bin/env python3
"""FastNote QA/QC suite.

The only test authority. Every verdict comes from the edition's real binary,
its real window on the real display, real OS-level input, and real files on
disk. No headless mode is used anywhere; per-edition test suites are not
consulted.

Usage:
  suite.py --edition go_gio --case a01,a02       one edition, selected cases
  suite.py --all                                  every edition, every case
  suite.py --edition go_gio --measure             calibration gate + metrics
  suite.py --calibrate                            instrument validation only
  suite.py --all --junit tools/tmp/qa/junit.xml

Exit status: 0 all pass, 1 any fail, 2 usage/environment error,
3 instrument gate failed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastnote_qa import core, manifest, measurements, results, x11
from cases.cases import all_cases

WORK = ROOT / "tools" / "tmp" / "qa"
EVIDENCE = WORK / "evidence"
DB = WORK / "results.db"
BUILD_LOG = WORK / "build"

TIMEOUTS = {"build": 600, "case": 120}


def build_edition(entry, force):
    logdir = BUILD_LOG / entry["name"]
    logdir.mkdir(parents=True, exist_ok=True)
    build_cmd = entry["build"]
    if not force and entry["bin_path"].exists():
        (logdir / "build.log").write_text("binary already present; skipped build\n")
        return True, "already built"
    if build_cmd == "true":
        (logdir / "build.log").write_text("launcher edition; nothing to build\n")
        return True, "launcher, nothing to build"
    try:
        r = subprocess.run(["bash", "-lc", build_cmd], cwd=entry["path"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=TIMEOUTS["build"])
    except subprocess.TimeoutExpired as e:
        (logdir / "build.log").write_text("build timed out")
        return False, "build timed out"
    (logdir / "build.log").write_text(r.stdout[-4000:])
    if r.returncode != 0:
        return False, f"build failed ({build_cmd}) — see tools/tmp/qa/build/{entry['name']}/build.log"
    if not entry["bin_path"].exists():
        return False, f"build succeeded but no artifact at {entry['binary']}"
    return True, "built"


def print_case(id_, r):
    mark = {"PASS": "\033[32mPASS\033[0m", "FAIL": "\033[31mFAIL\033[0m",
            "SKIP": "\033[33mSKIP\033[0m", "PARTIAL": "\033[33mPART\033[0m"}[r.status]
    print(f"  {mark}  {id_.upper():5s} {r.detail[:110]}")


def run_edition(args, name, store, case_filter):
    entry = manifest.entry(name)
    build_ok, build_note = build_edition(entry, args.build)
    store.begin_run(name, build_note if not build_ok else "")
    print(f"\033[1m=== {name} ===\033[0m ({build_note})")

    display_ok = x11.display_ok()
    instrumented = entry["event"]
    runner = core.Runner(all_cases(), WORK / "work", EVIDENCE, store)
    rows = runner.run_edition(entry, display_ok, instrumented, build_ok,
                              BUILD_LOG / name, case_filter)
    verdict = {"PASS": 0, "FAIL": 0, "SKIP": 0, "PARTIAL": 0}
    for case_id, r in rows:
        print_case(case_id, r)
        verdict[r.status] += 1
    print(f"  -- {verdict['PASS']} pass, {verdict['FAIL']} fail, "
          f"{verdict['SKIP']} skip, {verdict['PARTIAL']} partial")
    return verdict["FAIL"] == 0 and verdict["PARTIAL"] == 0


def measure(args, names):
    print("\033[1mCalibration gate\033[0m")
    try:
        floor, checks = measurements.run_gate()
    except measurements.GateError as e:
        print(f"\033[31mGATE FAILED: {e}\033[0m")
        return 3
    print(f"  floor: {floor['median']:.0f} ms (n={floor['n']})")
    for c in checks:
        print(f"  truth {c['truth_ms']} ms -> measured {c['measured_median']:.1f} ms "
              f"(overhead {c['overhead']:+.1f} ms)")

    results = []
    ok = True
    for name in names:
        entry = manifest.entry(name)
        print(f"\033[1mmeasuring {name}\033[0m")
        if not entry["event"]:
            print(f"  SKIP: edition does not publish --event-file yet")
            continue
        r = measurements.measure_edition(entry, WORK / "measure", args.reps)
        results.append(r)
        if "error" in r:
            print(f"  ERROR: {r['error']}")
            ok = False
            continue
        _print_measured(r)
    if not results:
        print("no editions measured (none publish --event-file yet)")
        return 1

    payload = {"floor": floor, "verification": checks, "results": results}
    out = WORK / "results.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nraw: {out}")
    return 0 if ok else 1


def _print_measured(r):
    size = r["binary_size_bytes"]
    sz = f"{size/1048576:.1f} MB" if size >= 1048576 else f"{size/1024:.0f} KB"
    su = r.get("startup_ms") or {}
    startup = f"{su['median']:.0f} ms" if su.get("median") is not None else "n/a"
    rss = r.get("rss") or {}
    own = f"{rss.get('anon_kb', 0)/1024:.0f} MB" if rss else "n/a"
    peak = f"{rss.get('peak_kb', 0)/1024:.0f} MB" if rss else "n/a"
    lat = []
    for k in ("open_ms", "save_ms", "export_html_ms", "export_pdf_ms", "edit_ms"):
        v = r.get(k) or {}
        lat.append(f"{k[:-3]}={v.get('median', 'n/a')} ms")
    print(f"  binary {sz} | startup {startup} | RSS own {own} | peak {peak}")
    print(f"  " + "  ".join(lat))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edition", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--case", default="")
    ap.add_argument("--build", action="store_true", help="force rebuild even if binary exists")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--junit", type=Path)
    args = ap.parse_args()

    if args.edition and not args.all:
        names = args.edition
    else:
        names = manifest.all_names()
    for n in names:
        if n not in manifest.EDITIONS:
            print(f"unknown edition {n}", file=sys.stderr)
            return 2

    case_filter = {c.strip() for c in args.case.split(",") if c.strip()} or None

    manifest.ROOT = ROOT
    x11.PROBE = ROOT / "tools" / "measure" / "fnprobe"
    x11.SYNTH = ROOT / "tools" / "measure" / "fnsynth"
    WORK.mkdir(parents=True, exist_ok=True)

    if args.calibrate:
        try:
            floor, checks = measurements.run_gate()
        except measurements.GateError as e:
            print(f"\033[31mGATE FAILED: {e}\033[0m")
            return 3
        print(f"floor: {floor['median']:.0f} ms (n={floor['n']})")
        for c in checks:
            print(f"truth {c['truth_ms']} ms -> measured {c['measured_median']:.1f} ms")
        return 0

    if args.measure:
        return measure(args, names)

    if not x11.display_ok() and case_filter and case_filter <= {"a02"}:
        pass
    if not x11.display_ok():
        print("\033[33mnote: no DISPLAY — GUI cases will be skipped or partial; "
              "a02 (--version) still runs\033[0m", file=sys.stderr)

    store = results.Store(DB)
    exit_code = 0
    for name in names:
        if not run_edition(args, name, store, case_filter):
            exit_code = 1

    rows = store.latest_rows()
    if rows:
        md = results.report_markdown(rows)
        (WORK / "report.md").write_text(md)
        print(f"\nreport: {WORK / 'report.md'}")
        if args.junit:
            import xml.etree.ElementTree as ET
            root = ET.Element("testsuites")
            for edition, case_id, status, detail, seconds in rows:
                el = ET.SubElement(root, "testcase",
                                   name=f"{edition}.{case_id}",
                                   classname=edition, time=f"{seconds:.3f}")
                if status != "PASS":
                    ET.SubElement(el, "failure", message=status).text = detail
            tree = ET.ElementTree(root)
            args.junit.parent.mkdir(parents=True, exist_ok=True)
            tree.write(args.junit, encoding="utf-8", xml_declaration=True)
            print(f"junit: {args.junit}")
    print("\nexit ", "0" if exit_code == 0 else "1")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())