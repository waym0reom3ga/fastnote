#!/usr/bin/env python3
"""FastNote report aggregator.

Reads test_config.txt from each edition, collects metrics, produces
a combined report (Markdown + CSV).

Usage:
  python3 tools/report_aggregate.py              # all editions
  python3 tools/report_aggregate.py --edition c_gtk4
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDITIONS_DIR = ROOT / "editions"
OUT_DIR = ROOT / "tools" / "tmp" / "qa"
MEASUREMENTS_JSON = OUT_DIR / "results.json"

sys.path.insert(0, str(ROOT / "tools" / "qa"))
from fastnote_qa.manifest import EDITIONS


def parse_config(edition_dir):
    """Parse test_config.txt into structured data."""
    config_path = edition_dir / "test_config.txt"
    if not config_path.exists():
        return None

    config = {"tests": []}
    current_test = None

    for line in config_path.read_text().splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("test:"):
            current_test = {"name": line.split(":", 1)[1].strip(), "params": {}}
            config["tests"].append(current_test)
        elif line.startswith("  ") and current_test:
            key, _, val = line.strip().partition(":")
            current_test["params"][key.strip()] = val.strip()

    return config


def get_binary_size(name, edition_dir, config):
    """Calculate binary + dynamic library sizes."""
    d, build, binary, title, event = EDITIONS[name]
    binpath = edition_dir / binary

    if not binpath.exists():
        return {"binary_bytes": 0, "lib_bytes": 0, "total_bytes": 0, "error": "binary missing"}

    binary_bytes = binpath.stat().st_size

    # Get dynamic lib sizes from config
    lib_bytes = 0
    lib_details = []
    binary_test = next((t for t in config["tests"] if t["name"] == "binary_size"), None)
    if binary_test:
        libs_str = binary_test["params"].get("libs", "none")
        if libs_str != "none":
            libs = [l.strip() for l in libs_str.split(",") if l.strip()]
            for lib in libs:
                lib_path = find_lib(lib)
                if lib_path:
                    size = lib_path.stat().st_size
                    lib_bytes += size
                    lib_details.append({"name": lib, "path": str(lib_path), "bytes": size})

    return {
        "binary_bytes": binary_bytes,
        "lib_bytes": lib_bytes,
        "total_bytes": binary_bytes + lib_bytes,
        "lib_details": lib_details,
    }


def find_lib(name):
    """Find a shared library in standard paths."""
    paths = ["/usr/lib", "/usr/lib64", "/lib", "/lib64"]
    for d in paths:
        p = Path(d) / name
        if p.exists():
            return p
    # Try ldconfig
    try:
        r = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if name in line and "=>" in line:
                path = line.split("=>")[1].strip()
                if Path(path).exists():
                    return Path(path)
    except:
        pass
    return None


def fmt_size(b):
    if b == 0:
        return "N/A"
    if b >= 1048576:
        return f"{b / 1048576:.1f} MB"
    return f"{b / 1024:.0f} KB"


def generate_report(results):
    """Generate Markdown report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# FastNote Measurement Report",
        f"",
        f"Generated: {now}",
        "",
        "## Binary Size (binary + specified dynamic libraries)",
        "",
        "| Edition | Binary | Libs | Total | Notes |",
        "|---------|--------|------|-------|-------|",
    ]

    for r in sorted(results, key=lambda x: x["total_bytes"], reverse=True):
        notes = r.get("notes", "")
        if len(notes) > 60:
            notes = notes[:57] + "..."
        lines.append(
            f"| {r['name']} | {fmt_size(r['binary_bytes'])} | "
            f"{fmt_size(r['lib_bytes'])} | **{fmt_size(r['total_bytes'])}** | {notes} |"
        )

    # Timing and RAM section (if measurement data exists)
    measurements = load_measurements()
    if measurements:
        lines += [
            "",
            "## Performance Measurements",
            "",
            "Measured via keyboard-driven operations with --event-file markers.",
            "RAM = peak VmRSS sampled every10ms during each operation arc.",
            "",
            "| Edition | Startup | Startup RAM | Open | Open RAM | Save | Save RAM | Export HTML | Export PDF | Close | Close RAM |",
            "|---------|---------|-------------|------|----------|------|----------|-------------|------------|-------|-----------|",
        ]

        for name in sorted(measurements.keys()):
            m = measurements[name]
            startup = _fmt_ms(m.get("startup_ms"))
            startup_ram = _fmt_ram(m.get("startup_ram_kb"))
            open_t = _fmt_ms(m.get("open_ms"))
            open_ram = _fmt_ram(m.get("open_ram_kb"))
            save_t = _fmt_ms(m.get("save_ms"))
            save_ram = _fmt_ram(m.get("save_ram_kb"))
            html_t = _fmt_ms(m.get("export_html_ms"))
            pdf_t = _fmt_ms(m.get("export_pdf_ms"))
            close_t = _fmt_ms(m.get("close_ms"))
            close_ram = _fmt_ram(m.get("close_ram_kb"))

            lines.append(
                f"| {name} | {startup} | {startup_ram} | {open_t} | {open_ram} | "
                f"{save_t} | {save_ram} | {html_t} | {pdf_t} | {close_t} | {close_ram} |"
            )

    lines += [
        "",
        "## Edition Details",
        "",
    ]

    for r in sorted(results, key=lambda x: x["total_bytes"], reverse=True):
        lines.append(f"### {r['name']}")
        lines.append("")
        if r.get("error"):
            lines.append(f"**Error:** {r['error']}")
            lines.append("")
            continue

        lines.append(f"- Binary: `{r['binary_path']}` ({fmt_size(r['binary_bytes'])})")
        if r.get("lib_details"):
            lines.append(f"- Dynamic libraries ({len(r['lib_details'])}):")
            for lib in r["lib_details"]:
                lines.append(f"  - `{lib['name']}` ({fmt_size(lib['bytes'])})")
        elif r.get("libs_spec") == "none":
            lines.append("- Dynamic libraries: self-contained (only libc/libm/libgcc)")
        lines.append(f"- **Total footprint: {fmt_size(r['total_bytes'])}**")

        # Config notes
        config = r.get("config")
        if config:
            for test in config["tests"]:
                notes = test["params"].get("notes", "")
                if notes:
                    lines.append(f"- {test['name']}: {notes}")

        # Measurement data
        m = measurements.get(r["name"])
        if m and not m.get("error"):
            lines.append("")
            lines.append("**Performance:**")
            if m.get("startup_ms"):
                s = m["startup_ms"]
                lines.append(f"- Startup: {s.get('median', 'N/A')} ms (peak RAM: {_fmt_ram(m.get('startup_ram_kb'))})")
            for op, label in [("open_ms", "Open"), ("save_ms", "Save"),
                              ("export_html_ms", "Export HTML"), ("export_pdf_ms", "Export PDF")]:
                if m.get(op):
                    v = m[op]
                    ram_key = f"{op.replace('_ms', '_ram_kb')}"
                    lines.append(f"- {label}: {v.get('median', 'N/A')} ms (peak RAM: {_fmt_ram(m.get(ram_key))})")
            if m.get("edit_ms"):
                v = m["edit_ms"]
                lines.append(f"- Edit (keystroke→render): {v.get('median', 'N/A')} ms")
            if m.get("close_ms"):
                v = m["close_ms"]
                lines.append(f"- Close (→PID gone): {v.get('median', 'N/A')} ms (peak RAM: {_fmt_ram(m.get('close_ram_kb'))})")

        lines.append("")

    return "\n".join(lines)


def load_measurements():
    """Load measurement data from results.json (produced by suite.py --measure)."""
    if not MEASUREMENTS_JSON.exists():
        return {}
    try:
        data = json.loads(MEASUREMENTS_JSON.read_text())
        results = {}
        for r in data.get("results", []):
            if "error" not in r:
                results[r["edition"]] = r
        return results
    except:
        return {}


def _fmt_ms(data):
    """Format timing data (dict with 'median' key) to string."""
    if not data or not isinstance(data, dict):
        return "N/A"
    if data.get("insufficient"):
        return "N/A"
    med = data.get("median")
    if med is None:
        return "N/A"
    return f"{med:.0f} ms"


def _fmt_ram(data):
    """Format RAM data (dict with 'peak_kb' key) to string."""
    if not data or not isinstance(data, dict):
        return "N/A"
    peak = data.get("peak_kb", 0)
    if peak == 0:
        return "N/A"
    if peak >= 1024:
        return f"{peak / 1024:.0f} MB"
    return f"{peak} KB"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--edition", action="append", default=[])
    args = ap.parse_args()

    if args.edition:
        names = args.edition
    else:
        names = sorted(EDITIONS.keys())

    results = []
    for name in names:
        if name not in EDITIONS:
            print(f"unknown edition: {name}", file=sys.stderr)
            continue

        d = EDITIONS[name][0]
        edition_dir = EDITIONS_DIR / d
        config = parse_config(edition_dir)

        if not config:
            print(f"  SKIP {name}: no test_config.txt")
            continue

        binary_test = next((t for t in config["tests"] if t["name"] == "binary_size"), None)
        if not binary_test:
            print(f"  SKIP {name}: no binary_size test in config")
            continue

        size_data = get_binary_size(name, edition_dir, config)
        notes = binary_test["params"].get("notes", "")

        result = {
            "name": name,
            "binary_path": str(edition_dir / EDITIONS[name][2]),
            "binary_bytes": size_data["binary_bytes"],
            "lib_bytes": size_data["lib_bytes"],
            "total_bytes": size_data["total_bytes"],
            "lib_details": size_data.get("lib_details", []),
            "libs_spec": binary_test["params"].get("libs", "none"),
            "notes": notes,
            "config": config,
        }
        results.append(result)

        sz = fmt_size(size_data["total_bytes"])
        libs = len(size_data.get("lib_details", []))
        print(f"  {name:<18} {sz:>10}  ({libs} libs)")

    # Generate report
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    md = generate_report(results)
    md_path = OUT_DIR / "measurement_report.md"
    md_path.write_text(md)
    print(f"\n  Markdown: {md_path}")

    # CSV
    csv_path = OUT_DIR / "measurement_report.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["edition", "binary_bytes", "lib_bytes", "total_bytes", "total_human", "notes"])
        for r in sorted(results, key=lambda x: x["total_bytes"], reverse=True):
            w.writerow([r["name"], r["binary_bytes"], r["lib_bytes"],
                        r["total_bytes"], fmt_size(r["total_bytes"]), r["notes"]])
    print(f"  CSV:      {csv_path}")

    # Summary
    print(f"\n  {len(results)} editions measured")
    if results:
        biggest = max(results, key=lambda x: x["total_bytes"])
        smallest = min(results, key=lambda x: x["total_bytes"])
        print(f"  Largest:  {biggest['name']} ({fmt_size(biggest['total_bytes'])})")
        print(f"  Smallest: {smallest['name']} ({fmt_size(smallest['total_bytes'])})")


if __name__ == "__main__":
    main()
