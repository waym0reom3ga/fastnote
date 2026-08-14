# FastNote

A markdown editor, implemented to the same specifications over and over, using different technology stacks.
The point of the project is not the editor. The point is : which toolkits
cost what, in binary size, memory, and engineering effort

## The Goal

**Context.** Various programming paradigms and GUI toolkits make different promises, but their
real cost only shows in a real, complete product. So FastNote is defined as a *black box* by
user-observable behaviour (`docs/FASTNOTE_SPECIFICATION.md`), and every edition implements
the same box with a different toolkit. The specification is the authority; a reference
implementation (`go_gio`) is not.

**Specific.** Each edition must, through its own interface, launch, open any markdown/txt
file from anywhere on disk, edit, show a rendered preview, save / save-as, export HTML and
PDF, and never lose work (FR-1…FR-11). Every edition exposes the same standard keyboard
accelerators — `Ctrl+O` open, `Ctrl+S` save, `Ctrl+Shift+S` save-as, `Ctrl+E` export,
`Ctrl+Shift+E` export PDF — and the same single test flag, `--event-file`, which only reports
when a user-visible phase completes. There is no headless mode and no CLI editing path: the
accelerators and the buttons MUST call the *same* code (spec §5.2).

**Time-bound.** Version 1.0 of the specification is dated 2026-08-07. Stage 1 — all fourteen
editions passing FR-1…FR-11 and the keyboard-driven Category 7 suite — is in progress:
the repair lineage (spec §8) re-proves each edition against the real GUI before the
comparative tableau is populated with measured results.

## Repository layout

```
fastnote/
├── docs/           The product spec, testing protocol, shared test data (testdata/),
│                   and the live comparative tableau (benchmark-report.html)
├── editions/       One folder per project: 14 self-contained implementations
│                   (Go/Gio, Go/Fyne, Go/GTK4, Go/Wails3, C/GTK4, C/Nuklear,
│                    C/RayGUI, Rust/GTK4, Rust/egui, Rust/Slint, Python/GTK4,
│                    Python/PyQt6, Python/PySide6, Python/DearPyGUI)
└── tools/          The machinery:
    ├── qa/         suite.py + fastnote_qa/ — the test authority: builds each edition,
    │               launches its real window, drives it with real keyboard input, waits
    │               on --event-file markers, verifies files on disk; SQLite history +
    │               capability matrix + Markdown/HTML/JUnit reports
    ├── measure/    fnprobe/fnsynth/fnres + run.py + gen_report.py — calibration-gated
    │               size/memory/startup probing and the comparative tableau renderer
    └── tmp/        scratch workspace of the tools above
```

Every edition is self-contained: it builds statically against toolkits that are compiled
from source *inside the edition folder* (`c_gtk4` carries the full GTK4 static depot; the
other C editions carry their own minimal `deps/`), so the binary size reported for a port
really is the whole toolkit, not just the app.

## Usage

```sh
# Run the QA suite against one edition (builds, launches, drives the real GUI)
python3 tools/qa/suite.py --edition c_gtk4

# Run the full suite against every edition
python3 tools/qa/suite.py --all

# Measure one edition (binary size, startup, memory, operation latencies)
python3 tools/qa/suite.py --edition c_gtk4 --measure

# Regenerate the comparative tableau from the latest measurement results
python3 tools/measure/gen_report.py
```

Authoritative documents:

- `docs/FASTNOTE_SPECIFICATION.md` — the black-box specification. Wins all arguments.
- `docs/fastnote_testing_protocol.md` — how acceptance is defined and run (Category 7 only).
- `docs/benchmark-report.html` — the live multi-metric comparative tableau: the capability
  matrix (which edition passes which FR) alongside binary size, startup, memory, and
  interaction latency for every edition.
