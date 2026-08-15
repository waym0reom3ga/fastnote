#!/usr/bin/env python3
"""Generate the FastNote comparative tableau (HTML).

Combines two real sources of evidence:
  1. the capability matrix  — each edition's most recent QA run, from the
     SQLite history at tools/tmp/qa/results.db (which edition passes which
     of A01..A14, i.e. which FR);
  2. the measured metrics    — tools/tmp/qa/results.json from
     `suite.py --measure` (binary size, startup, RSS, operation latencies).

Per specification 6.2, performance figures for an edition that fails any of
A01..A11 are published with an incompleteness marker; the tableau leads with
the capability matrix, never a test-count percentage.

Usage:
  python3 tools/qa/suite.py --all --measure   # produce the inputs
  python3 tools/measure/gen_report.py          # render docs/benchmark-report.html
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS = ROOT / "tools" / "tmp" / "qa" / "results.json"
DB = ROOT / "tools" / "tmp" / "qa" / "results.db"
OUT = ROOT / "docs" / "benchmark-report.html"

CASE_ORDER = ["a01", "a02", "a03", "a04", "a05", "a06", "a07", "a08",
              "a09", "a10", "a11", "a12", "a13", "a14"]

LABELS = {
    "go_gio": "Go/Gio", "go_fyne": "Go/Fyne", "go_gtk4": "Go/GTK4",
    "go_wails3": "Go/Wails3", "c_gtk4": "C/GTK4", "c_nuklear": "C/Nuklear",
    "c_raygui": "C/RayGUI", "rust_gtk4": "Rust/GTK4", "rust_egui": "Rust/egui",
    "rust_slint": "Rust/Slint", "python_gtk4": "Python/GTK4",
    "python_pyqt6": "Python/PyQt6", "python_pyside6": "Python/PySide6",
    "python_dearpygui": "Python/DearPyGUI",
}
LANG = {
    "go_gio": "Go", "go_fyne": "Go", "go_gtk4": "Go", "go_wails3": "Go",
    "c_gtk4": "C", "c_nuklear": "C", "c_raygui": "C",
    "rust_gtk4": "Rust", "rust_egui": "Rust", "rust_slint": "Rust",
    "python_gtk4": "Python", "python_pyqt6": "Python", "python_pyside6": "Python",
    "python_dearpygui": "Python",
}

C = {
    "binary": "#22d3ee", "startup": "#22d3ee", "open": "#34d399",
    "save": "#fbbf24", "export_html": "#fb7185", "export_pdf": "#a78bfa",
    "edit": "#38bdf8", "rss_own": "#38bdf8", "rss_file": "#94a3b8",
    "rss_peak": "#fb923c",
}

STATUS_CLASS = {"PASS": "b-g", "FAIL": "b-r", "PARTIAL": "b-a", "SKIP": "b-s"}


def load():
    if not RESULTS.exists():
        print(f"error: {RESULTS} missing. Run `suite.py --all --measure` first.",
              file=sys.stderr)
        sys.exit(2)
    data = json.loads(RESULTS.read_text())
    results = [r for r in data["results"] if "error" not in r]
    errored = [r["edition"] for r in data["results"] if "error" in r]
    floor = data["floor"]
    checks = data.get("verification", [])

    matrix = {}
    if DB.exists():
        conn = sqlite3.connect(DB)
        rows = conn.execute("""
            SELECT res.edition, res.case_id, res.status
            FROM result res
            WHERE res.id IN (
                SELECT MAX(r2.id) FROM result r2
                GROUP BY r2.edition, r2.case_id)""").fetchall()
        conn.close()
        for edition, case_id, status in rows:
            matrix.setdefault(edition, {})[case_id] = status
    return results, errored, floor, checks, matrix


def incomplete(matrix):
    """Editions failing any of A01..A11 (the FR-1..FR-8 evidence)."""
    out = set()
    for ed, cases in matrix.items():
        for cid in CASE_ORDER[:11]:
            if cases.get(cid) in ("FAIL", "PARTIAL"):
                out.add(ed)
                break
    return out


def med(r, key):
    v = r.get(key)
    if not v or v.get("insufficient"):
        return None
    return v["median"]


def fmt_ms(v):
    return "N/A" if v is None else f"{v:.0f} ms"


def fmt_size(b):
    if b is None:
        return "N/A"
    return f"{b/1048576:.1f} MB" if b >= 1048576 else f"{b/1024:.0f} KB"


def bar(label, numval, unit, color, maxv):
    pct = min(100, numval / maxv * 100) if maxv else 0
    return (f'    <div class="bar-row"><span class="bl">{label}</span>'
            f'<div class="bt"><div class="bf" style="width:{pct:.0f}%;'
            f'background:{color}">{numval}{unit}</div></div></div>')


def bars_for(results, key, color, maxv=None, unit=" ms", converter=None):
    vals = []
    for r in results:
        v = med(r, key)
        if v is not None:
            vals.append(v)
    if not vals:
        return '    <div class="bar-row"><span class="bl">N/A</span></div>'
    mx = maxv or max(vals)
    lines = []
    for r in results:
        v = med(r, key)
        if v is None:
            continue
        num = converter(v) if converter else v
        lines.append(bar(LABELS.get(r["edition"], r["edition"]), num, unit, color, mx))
    return "\n".join(lines)


def matrix_rows(matrix):
    editions = sorted(matrix)
    rows = []
    for ed in editions:
        cells = "".join(
            f'<td><span class="b {STATUS_CLASS.get(matrix[ed].get(c, "-"), "b-s")}">'
            f'{matrix[ed].get(c, "-")}</span></td>' for c in CASE_ORDER)
        passed = sum(1 for c in CASE_ORDER if matrix[ed].get(c) == "PASS")
        label = f'{LABELS.get(ed, ed)} <span style="color:#475569">({LANG.get(ed, "")})</span>'
        rows.append(f'  <tr><td>{label}</td>{cells}<td>{passed}/{len(CASE_ORDER)}</td></tr>')
    return "\n".join(rows)


def measured_rows(results, matrix, incomplete_set):
    def m(key, suffix=""):
        v = med(r, key)
        return "N/A" if v is None else f"{v:.0f} {suffix}".strip()

    rows = []
    for r in results:
        ed = r["edition"]
        mark = ' <span class="b b-r">incomplete</span>' if ed in incomplete_set else ""
        rss = r.get("rss") or {}
        own = f'{rss.get("anon_kb", 0) / 1024:.0f}' if rss else "N/A"
        shd = f'{rss.get("file_kb", 0) / 1024:.0f}' if rss else "N/A"
        peak = f'{rss.get("peak_kb", 0) / 1024:.0f}' if rss else "N/A"
        s = [f'{LABELS.get(ed, ed)}',
             fmt_size(r.get("binary_size_bytes")),
             m("startup_ms"), m("open_ms"), m("save_ms"),
             m("export_html_ms"), m("export_pdf_ms"), m("edit_ms"),
             own + " MB", shd + " MB", peak + " MB"]
        rows.append("  <tr>" + "".join(f"<td>{x}</td>" for x in s) + "</tr>")
    return "\n".join(rows)


def main():
    results, errored, floor, checks, matrix = load()
    floor_ms = floor["median"]
    oh = checks[0]["overhead"] if checks else 0
    inc = incomplete(matrix)

    mx = {k: max([med(r, k) for r in results if med(r, k) is not None], default=1)
          for k in ("startup_ms", "open_ms", "save_ms", "export_html_ms",
                    "export_pdf_ms", "edit_ms")}
    mx_size = max([r["binary_size_bytes"] for r in results
                   if r.get("binary_size_bytes")], default=1)
    mx_rss_own = max([r["rss"]["anon_kb"] for r in results if r.get("rss")], default=1)
    mx_rss_file = max([r["rss"]["file_kb"] for r in results if r.get("rss")], default=1)
    mx_rss_peak = max([r["rss"]["peak_kb"] for r in results if r.get("rss")], default=1)

    grid = [
        ('Binary Size', 'binary', _size_bars(results, mx_size)),
        ('Startup', 'startup', bars_for(results, "startup_ms", C["startup"], mx["startup_ms"])),
        ('RSS Own', 'rss_own', _rss_bars(results, "anon_kb", C["rss_own"], mx_rss_own)),
        ('RSS Shared', 'rss_file', _rss_bars(results, "file_kb", C["rss_file"], mx_rss_file)),
        ('RSS Peak', 'rss_peak', _rss_bars(results, "peak_kb", C["rss_peak"], mx_rss_peak)),
    ]

    lat_cards = [
        ('Open', "open_ms", C["open"]),
        ('Save', "save_ms", C["save"]),
        ('Export HTML', "export_html_ms", C["export_html"]),
        ('Export PDF', "export_pdf_ms", C["export_pdf"]),
        ('Edit', "edit_ms", C["edit"]),
    ]
    lat_html = "".join(
        f'<div><h3 style="font-size:12px;color:#64748b;margin-bottom:8px">{t}</h3>'
        f'{bars_for(results, k, col, mx[k])}</div>' for t, k, col in lat_cards)

    stats = [
        ("Editions measured", len(results), "#22d3ee"),
        ("Capability rows", len(matrix), "#34d399"),
        ("Languages", len({LANG.get(e["edition"]) for e in results}), "#a78bfa"),
        ("Floor", f"{floor_ms:.0f} ms", "#fbbf24"),
        ("Probe OH", f"{oh:+.1f} ms", "#fb7185"),
        ("Incomplete", len(inc), "#fb923c"),
    ]
    stat_html = "".join(
        f'<div class="st"><div class="sv" style="color:{c}">{v}</div>'
        f'<div class="sl">{k}</div></div>' for k, v, c in stats)

    vchecks = "\n".join(
        f'  <tr><td>target {c["truth_ms"]} ms</td><td>{c["measured_median"]:.1f} ms</td>'
        f'<td>{c["overhead"]:+.1f} ms</td></tr>' for c in checks)
    verif_html = vchecks or '  <tr><td colspan="3">no verification data</td></tr>'

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    incompl_note = ""
    if inc:
        incompl_note = ("<p class='warn'>" +
                        "Performance figures marked <span class='b b-r'>incomplete</span> "
                        "are measured against editions failing FR-1..FR-8 evidence "
                        "(spec 6.2); their sizes and latencies must not be compared as "
                        "toolkit costs.</p>")

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FastNote Cross-Technology Comparative Tableau</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'JetBrains Mono',monospace;background:#020617;color:#e2e8f0;padding:40px}}
h1{{font-size:24px;color:#f8fafc;margin-bottom:4px}}
h2{{font-size:16px;color:#94a3b8;margin-bottom:12px;font-weight:400}}
.sub{{color:#64748b;font-size:12px;margin-bottom:24px}}
.warn{{background:#7f1d1d22;border:1px solid #7f1d1d;color:#fca5a5;padding:12px 16px;border-radius:8px;font-size:12px;margin-bottom:24px}}
.stats{{display:flex;gap:16px;margin-bottom:32px;flex-wrap:wrap}}
.st{{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:16px 20px;flex:1;min-width:150px}}
.sv{{font-size:22px;font-weight:700}}
.sl{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:4px}}
.card{{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:20px}}
.ch{{display:flex;align-items:center;gap:10px;margin-bottom:14px}}
.cd{{width:8px;height:8px;border-radius:50%}}
.ct{{font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:1px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px;margin-bottom:32px}}
.bar-row{{display:flex;align-items:center;gap:12px;margin:4px 0}}
.bl{{width:110px;font-size:11px;color:#cbd5e1;text-align:right;flex-shrink:0}}
.bt{{flex:1;height:20px;background:#1e293b;border-radius:4px;overflow:hidden}}
.bf{{height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px;font-size:10px;color:#fff;font-weight:700;min-width:46px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{text-align:left;color:#64748b;padding:8px 10px;border-bottom:1px solid #1e293b;font-weight:400;text-transform:uppercase;letter-spacing:1px}}
td{{padding:8px 10px;border-bottom:1px solid #0f172a;color:#cbd5e1}}
tr:hover td{{background:rgba(255,255,255,.02)}}
.b{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700}}
.b-g{{background:rgba(52,211,153,.15);color:#34d399}}
.b-r{{background:rgba(251,113,133,.15);color:#fb7185}}
.b-a{{background:rgba(251,191,36,.15);color:#fbbf24}}
.b-s{{background:rgba(100,116,139,.15);color:#94a3b8}}
.twrap{{overflow-x:auto;margin-bottom:32px}}
.ft{{margin-top:32px;padding-top:20px;border-top:1px solid #1e293b;font-size:10px;color:#475569}}
</style>
</head>
<body>
<h1>FastNote Cross-Technology Comparative Tableau</h1>
<h2>14 editions, one specification: what each toolkit really costs</h2>
<p class="sub">Generated {now} | capability matrix from the QA history | metrics from
calibration-gated real-input runs | keyboard-driven, no control maps</p>
{incompl_note}
<div class="stats">{stat_html}</div>
<div class="card" style="margin-bottom:32px">
  <div class="ch"><div class="cd" style="background:#34d399"></div>
  <div class="ct">Capability matrix — which edition passes which case (A01..A14)</div></div>
  <div class="twrap"><table>
    <tr><th>Edition</th>{"".join(f"<th>{c.upper()}</th>" for c in CASE_ORDER)}<th>Passed</th></tr>
{matrix_rows(matrix)}
  </table></div>
</div>
<div class="grid">
{''.join(f'  <div class="card"><div class="ch"><div class="cd" style="background:{C[k]}"></div><div class="ct">{t}</div></div><div>{b}</div></div>' for t, k, b in grid)}
</div>
<div class="card" style="margin-bottom:32px">
  <div class="ch"><div class="cd" style="background:#34d399"></div>
  <div class="ct">Interaction latency (median ms, instrument floor {floor_ms:.0f} ms)</div></div>
  <div class="grid" style="margin-bottom:0">{lat_html}</div>
</div>
<div class="card" style="margin-bottom:32px">
  <div class="ch"><div class="cd" style="background:#94a3b8"></div>
  <div class="ct">Measured table (size / startup / latency / RSS split)</div></div>
  <div class="twrap"><table>
    <tr><th>Edition</th><th>Binary</th><th>Startup</th><th>Open</th><th>Save</th>
    <th>Export HTML</th><th>Export PDF</th><th>Edit</th><th>RSS own</th>
    <th>RSS shared</th><th>RSS peak</th></tr>
{measured_rows(results, matrix, inc)}
  </table></div>
</div>
<div class="card" style="margin-bottom:32px">
  <div class="ch"><div class="cd" style="background:#94a3b8"></div>
  <div class="ct">Probe verification</div></div>
  <table><tr><th>Target</th><th>Measured</th><th>Overhead</th></tr>
{verif_html}
  </table>
</div>
<p class="sub">Incompleteness markers: editions failing any of A01..A11 cannot contribute
a meaningful performance comparison. "app" latency = median minus the {floor_ms:.0f} ms
instrument floor. RSS own = RssAnon, RSS shared = RssFile, peak = VmHWM of the whole
process tree. Startup = launch to the first painted frame ('painted' marker).</p>
<div class="ft">FastNote | one spec, fourteen stacks, measured by driving the real window</div>
</body>
</html>'''

    OUT.write_text(html)
    print(f"Report: {OUT} ({len(results)} editions measured, {len(matrix)} in matrix)")
    if errored:
        print("Editions that failed to measure:", ", ".join(errored))


def _size_bars(results, mx):
    lines = []
    for r in results:
        b = r.get("binary_size_bytes")
        if not b:
            continue
        lines.append(bar(LABELS.get(r["edition"], r["edition"]),
                         round(b / 1048576, 2), " MB", C["binary"], round(mx / 1048576, 2)))
    return "\n".join(lines) if lines else '    <div class="bar-row"><span class="bl">N/A</span></div>'


def _rss_bars(results, key, color, mx):
    lines = []
    for r in results:
        rss = r.get("rss")
        if not rss:
            continue
        v = rss.get(key, 0)
        lines.append(bar(LABELS.get(r["edition"], r["edition"]),
                         round(v / 1024, 1), " MB", color, round(mx / 1024, 1)))
    return "\n".join(lines) if lines else '    <div class="bar-row"><span class="bl">N/A</span></div>'


if __name__ == "__main__":
    main()
