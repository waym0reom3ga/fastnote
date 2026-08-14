#!/usr/bin/env python3
"""Generate an HTML benchmark report from the raw JSON results."""
import json
from datetime import datetime
from pathlib import Path

def main():
    base = Path("/home/waymore/Documents/AI_generated_software/GOS/fastnote")
    data = json.loads((base / "tools" / "tmp" / "measure" / "results.json").read_text())
    results = [r for r in data["results"] if "error" not in r]
    floor = data["floor"]
    checks = data.get("verification", [])

    C = {
        "startup": "#22d3ee", "open": "#34d399", "edit": "#a78bfa",
        "save": "#fbbf24", "export": "#fb7185", "rss_own": "#38bdf8",
        "rss_file": "#94a3b8", "rss_peak": "#fb923c",
    }

    def bar(label, numval, unit, color, maxv):
        pct = min(100, numval / maxv * 100) if maxv else 0
        return f'    <div class="bar-row"><span class="bl">{label}</span><div class="bt"><div class="bf" style="width:{pct:.0f}%;background:{color}">{numval}{unit}</div></div></div>'

    def badge(key):
        if not key or key.get("insufficient"):
            return '<span class="b b-r">N/A</span>'
        app = max(0, key["median"] - floor["median"])
        return f'<span class="b b-g">{key["median"]:.0f} (app {app:.0f})</span>'

    def med(k):
        v = results[0].get(k)
        return v["median"] if v and not v.get("insufficient") else None

    # max values
    mx_startup = max(r["startup_ms"]["median"] for r in results)
    mx_open = max(r["open_ms"]["median"] for r in results if not r["open_ms"].get("insufficient"))
    mx_edit = max((r["edit_ms"]["median"] for r in results if r.get("edit_ms") and not r["edit_ms"].get("insufficient")), default=1)
    mx_save = max((r["save_ms"]["median"] for r in results if r.get("save_ms") and not r["save_ms"].get("insufficient")), default=1)
    mx_export = max(r["export_ms"]["median"] for r in results if not r["export_ms"].get("insufficient"))
    mx_rss_own = max(r["rss"]["anon_kb"] for r in results if r.get("rss"))
    mx_rss_file = max(r["rss"]["file_kb"] for r in results if r.get("rss"))
    mx_rss_peak = max(r["rss"]["peak_kb"] for r in results if r.get("rss"))

    # startup bars
    sb = "\n".join(bar(r["edition"], r["startup_ms"]["median"], " ms", C["startup"], mx_startup) for r in results)

    # rss bars
    rob = "\n".join(bar(r["edition"], r["rss"]["anon_kb"]/1024, " MB", C["rss_own"], mx_rss_own/1024) for r in results if r.get("rss"))
    rfb = "\n".join(bar(r["edition"], r["rss"]["file_kb"]/1024, " MB", C["rss_file"], mx_rss_file/1024) for r in results if r.get("rss"))
    rpb = "\n".join(bar(r["edition"], r["rss"]["peak_kb"]/1024, " MB", C["rss_peak"], mx_rss_peak/1024) for r in results if r.get("rss"))

    # latency bars
    def lb(key, color, mx):
        lines = []
        for r in results:
            v = r.get(key)
            if v and not v.get("insufficient"):
                lines.append(bar(r["edition"], v["median"], " ms", color, mx))
        return "\n".join(lines) if lines else '    <div class="bar-row"><span class="bl">N/A</span></div>'

    ob = lb("open_ms", C["open"], mx_open)
    eb = lb("edit_ms", C["edit"], mx_edit)
    savb = lb("save_ms", C["save"], mx_save)
    expb = lb("export_ms", C["export"], mx_export)

    # table
    tr = "\n".join(
        f'  <tr><td>{r["edition"]}</td><td>{badge(r.get("startup_ms"))}</td><td>{badge(r.get("open_ms"))}</td><td>{badge(r.get("edit_ms"))}</td><td>{badge(r.get("save_ms"))}</td><td>{badge(r.get("export_ms"))}</td></tr>'
        for r in results
    )

    vr = "\n".join(
        f'  <tr><td>target {c["truth_ms"]} ms</td><td>{c["measured_median"]:.1f} ms</td><td>{c["overhead"]:+.1f} ms</td></tr>'
        for c in checks
    )

    # notes
    nl = []
    for r in results:
        for k, label in [("edit_ms", "edit"), ("save_ms", "save")]:
            v = r.get(k)
            if v and v.get("insufficient"):
                nl.append(f'{r["edition"]} {label}: only {v["n"]}/{v["wanted"]} samples detected pixel change (withheld)')
    nh = "\n".join(f"  <li>{n}</li>" for n in nl)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    floor_ms = floor["median"]
    oh = checks[0]["overhead"] if checks else 0

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FastNote Go Editions Benchmark</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'JetBrains Mono',monospace;background:#020617;color:#e2e8f0;padding:40px}}
h1{{font-size:24px;color:#f8fafc;margin-bottom:4px}}
h2{{font-size:16px;color:#94a3b8;margin-bottom:32px;font-weight:400}}
.sub{{color:#64748b;font-size:12px;margin-bottom:40px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px;margin-bottom:40px}}
.card{{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:24px}}
.ch{{display:flex;align-items:center;gap:10px;margin-bottom:16px}}
.cd{{width:8px;height:8px;border-radius:50%}}
.ct{{font-size:13px;color:#94a3b8;text-transform:uppercase;letter-spacing:1px}}
.bar-row{{display:flex;align-items:center;gap:12px;margin:4px 0}}
.bl{{width:80px;font-size:11px;color:#cbd5e1;text-align:right;flex-shrink:0}}
.bt{{flex:1;height:22px;background:#1e293b;border-radius:4px;overflow:hidden}}
.bf{{height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px;font-size:10px;color:#fff;font-weight:700;min-width:50px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{text-align:left;color:#64748b;padding:8px 12px;border-bottom:1px solid #1e293b;font-weight:400;text-transform:uppercase;letter-spacing:1px}}
td{{padding:8px 12px;border-bottom:1px solid #0f172a;color:#cbd5e1}}
tr:hover td{{background:rgba(255,255,255,.02)}}
.b{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700}}
.b-g{{background:rgba(52,211,153,.15);color:#34d399}}
.b-r{{background:rgba(251,113,133,.15);color:#fb7185}}
.stats{{display:flex;gap:24px;margin-bottom:40px;flex-wrap:wrap}}
.st{{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:20px 24px;flex:1;min-width:180px}}
.sv{{font-size:28px;font-weight:700}}
.sl{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:4px}}
.twrap{{overflow-x:auto;margin-bottom:40px}}
.notes{{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:16px 20px;margin-bottom:40px;font-size:11px;color:#94a3b8}}
.notes li{{margin:4px 0}}
.ft{{margin-top:40px;padding-top:20px;border-top:1px solid #1e293b;font-size:10px;color:#475569}}
</style>
</head>
<body>
<h1>FastNote Go Editions Benchmark</h1>
<h2>gio vs fyne -- real windows, real clicks, real pixels</h2>
<p class="sub">Generated {now} | 7 reps per operation | instrument floor {floor_ms:.0f} ms</p>
<div class="stats">
  <div class="st"><div class="sv" style="color:#22d3ee">{len(results)}</div><div class="sl">Editions</div></div>
  <div class="st"><div class="sv" style="color:#34d399">{floor_ms:.0f} ms</div><div class="sl">Floor</div></div>
  <div class="st"><div class="sv" style="color:#a78bfa">7</div><div class="sl">Reps</div></div>
  <div class="st"><div class="sv" style="color:#fbbf24">{oh:+.1f} ms</div><div class="sl">Probe OH</div></div>
</div>
<div class="grid">
  <div class="card"><div class="ch"><div class="cd" style="background:#22d3ee"></div><div class="ct">Startup</div></div><div>{sb}</div></div>
  <div class="card"><div class="ch"><div class="cd" style="background:#38bdf8"></div><div class="ct">RSS Own</div></div><div>{rob}</div></div>
  <div class="card"><div class="ch"><div class="cd" style="background:#94a3b8"></div><div class="ct">RSS Shared</div></div><div>{rfb}</div></div>
  <div class="card"><div class="ch"><div class="cd" style="background:#fb923c"></div><div class="ct">RSS Peak</div></div><div>{rpb}</div></div>
</div>
<div class="card" style="margin-bottom:40px">
  <div class="ch"><div class="cd" style="background:#34d399"></div><div class="ct">Interaction Latency</div></div>
  <div class="grid" style="margin-bottom:0">
    <div><h3 style="font-size:12px;color:#64748b;margin-bottom:8px">Open</h3><div>{ob}</div></div>
    <div><h3 style="font-size:12px;color:#64748b;margin-bottom:8px">Edit</h3><div>{eb}</div></div>
    <div><h3 style="font-size:12px;color:#64748b;margin-bottom:8px">Save</h3><div>{savb}</div></div>
    <div><h3 style="font-size:12px;color:#64748b;margin-bottom:8px">Export</h3><div>{expb}</div></div>
  </div>
</div>
<div class="twrap">
  <table>
    <tr><th>Edition</th><th>Startup</th><th>Open</th><th>Edit</th><th>Save</th><th>Export</th></tr>
{tr}
  </table>
</div>
<div class="card" style="margin-bottom:40px">
  <div class="ch"><div class="cd" style="background:#94a3b8"></div><div class="ct">Probe Verification</div></div>
  <table>
    <tr><th>Target</th><th>Measured</th><th>Overhead</th></tr>
{vr}
  </table>
</div>
<ul class="notes">
  <li>Instrument floor: {floor_ms:.0f} ms (60 Hz frame interval)</li>
  <li>"app" = median minus floor, the edition's own share</li>
  <li>RSS own = RssAnon; RSS shared = RssFile; Peak = VmHWM</li>
  <li>Startup = launch to first painted frame, median of 5 after warm-up</li>
{nh}
</ul>
<div class="ft">FastNote benchmark | Real binaries, real windows, real input, real pixels</div>
</body>
</html>'''

    out = base / "docs" / "benchmark-report.html"
    out.write_text(html)
    print(f"Report: {out}")

if __name__ == "__main__":
    main()
