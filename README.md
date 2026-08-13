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
PDF, and never lose work (FR-1…FR-9). Every edition exposes the same
headless CLI switches (`--open`, `--insert`, `--save`, `--export`, `--headless`, `--selftest`),
and the CLI must call the *same* code paths as the GUI buttons (spec §5.2).

**Time-bound.** Version 1.0 of the specification is dated 2026-08-07. Stage 1: all twelve
editions passing FR-1…FR-9 and the full acceptance suite is complete.

## Repository layout

```
fastnote/
├── docs/           The product spec, testing protocol, structural analysis,
│                   comparison report, and shared test data (testdata/)
├── editions/       One folder per project: 12 self-contained implementations
│                   (Go/Gio, Go/Fyne, C/GTK4, C/Nuklear, C/RayGUI,
│                    Rust/GTK4, Rust/egui, Rust/Slint, Python/GTK4,
│                    Python/PyQt6, Python/PySide6, Python/DearPyGUI)
└── tools/          The machinery:
    ├── acceptance/     run.sh + ports.conf — the 13-test Category 7 harness
    ├── measure/        fnsynth/fnprobe/fnres + run.py + typecheck.sh —
                        workload generation, size/memory/startup probing,
                        real-keyboard typing checks
    └── tmp/            scratch workspace of the two tools above
```

Every edition is self-contained: it builds statically against toolkits that are compiled
from source *inside the edition folder* (`c_gtk4` carries the full GTK4 static depot; the
other C editions carry their own minimal `deps/`), so the binary size reported for a port
really is the whole toolkit, not just the app.

## Usage

```sh
# Build and test one edition
make -C editions/fastnote_c_gtk4_ed test

# Run the full acceptance suite against every edition
./tools/acceptance/run.sh --all

# Measure one edition (binary size, startup, memory)
./tools/measure/run.py --edition c_gtk4
```

Authoritative documents:

- `docs/FASTNOTE_SPECIFICATION.md` — the black-box specification. Wins all arguments.
- `docs/fastnote_testing_protocol.md` — how acceptance is defined and run.
- `docs/comparison-report_20260806.html` — the current capability matrix and measurements.
