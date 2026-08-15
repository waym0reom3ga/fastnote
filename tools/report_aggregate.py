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
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDITIONS_DIR = ROOT / "editions"
OUT_DIR = ROOT / "tools" / "tmp" / "qa"

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

        lines.append("")

    return "\n".join(lines)


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
