# FastNote Status Report — 2026-08-15

---

## 1. Edition status

| Edition | --version | --event-file | Keyboard | GUI | Binary |
|---------|-----------|--------------|----------|-----|--------|
| go_gio | ✓ | ✓ | ✓ | BROKEN (event loop fix pending) | 10.8 MB |
| go_fyne | ✓ | ✓ | ✓ | BROKEN (layout broken) | 32.0 MB |
| go_gtk4 | ✓ | ✓ | ✓ | NOT REBUILT (build timeout) | 17.8 MB |
| go_wails3 | ✓ | ✓ | ✓ | NOT TESTED | 8.9 MB |
| c_gtk4 | ✓ | ✓ | ✓ | ✓ WORKING | 62 KB |
| c_nuklear | ✓ | ✓ | ✓ | BROKEN (black canvas) | 523 KB |
| c_raygui | ✓ | ✓ | ✓ | NOT TESTED | 145 KB |
| rust_gtk4 | ✓ | ✓ | ✓ | NOT REBUILT (old binary) | 600 KB |
| rust_egui | ✓ | ✓ | ✓ | BROKEN (empty canvas) | 19.2 MB |
| rust_slint | ✓ | ✓ | ✓ | BROKEN (empty editor) | 30.2 MB |
| python_gtk4 | ✓ | ✓ | ✓ | CRASH (Nuitka gi bug) | 11.7 MB |
| python_pyqt6 | ✓ | ✓ | ✓ | ✓ WORKING | 10.1 MB |
| python_pyside6 | ✓ | ✓ | ✓ | ✓ WORKING | 11.5 MB |
| python_dearpygui | ✓ | ✓ | ✓ | CRASH (runtime error) | 10.8 MB |

---

## 2. To-do: GUI fixes (CRITICAL)

### 2.1 go_gio — event loop broken
- **Cause**: Added button click checking after `e.Frame(gtx.Ops)` and `case key.Event` handler — Gio doesn't work that way
- **Fix**: Reverted event loop to old working pattern. Binary rebuilt.
- **Status**: Needs test with qwen3.8

### 2.2 python_gtk4 — Nuitka crash
- **Cause**: GLib 2.88.3 / gi 3.56.3 — `unix_signal_add_full` deprecated but not in `__all__`, triggers AssertionError in `gi/overrides/__init__.py:161`
- **Fix**: Created local patched gi copy with `__all__` fix. Nuitka build uses patched gi.
- **Status**: Needs rebuild + test

### 2.3 python_dearpygui — runtime crash
- **Cause**: Not yet investigated
- **Status**: Needs investigation

### 2.4 c_nuklear — black canvas
- **Cause**: Unknown. OpenGL rendering not reaching screen. `glClear` to red didn't show.
- **Status**: Needs investigation

### 2.5 go_fyne — layout broken
- **Cause**: Unknown. Toolbar visible but editor/preview collapsed.
- **Status**: Needs investigation

### 2.6 rust_egui — empty canvas
- **Cause**: Unknown. Switched from glow (GL) to wgpu — same result.
- **Status**: Needs investigation

### 2.7 rust_slint — empty editor
- **Cause**: Unknown. Toolbar visible but editor blank.
- **Status**: Needs investigation

### 2.8 Validate all fixes with qwen3.8
- Screenshot each edition
- Send to LM Studio at http://192.168.2.22:1234/v1 (model: qwen/qwen3.8-27b, key: 1234)
- Ask: "Is this FastNote GUI rendering properly? Are buttons, editor, preview visible?"

---

## 3. To-do: Rebuilds

### 3.1 rust_gtk4
- Old binary from Aug 13, missing --event-file support
- Source code updated but not rebuilt
- Needs: `cargo build --release`

### 3.2 go_gtk4
- Build times out (>10 min) due to CGo gotk4 bindings
- Needs: build with `GOMAXPROCS=1` or incremental build

### 3.3 go_wails3
- Binary exists but GUI never tested
- Needs: launch + screenshot + qwen3.8 validation

### 3.4 c_raygui
- Binary exists but GUI never tested
- Needs: launch + screenshot + qwen3.8 validation

---

## 4. To-do: Measurements

### 4.1 Run measurements on all validated editions
```bash
./run_all.sh --all --measure --reps 5
```
Collects per-edition:
- Binary size + dynamic lib sizes
- Startup time + peak RAM
- Open/save/export-html/export-pdf latency + peak RAM per operation
- Edit latency (keystroke → render)
- Close time (WM close → PID gone) + peak RAM

### 4.2 Generate comparative tableau
```bash
python3 tools/measure/gen_report.py
```
Produces `docs/benchmark-report.html` with capability matrix + performance bars.

---

## 5. To-do: Documentation

### 5.1 Update spec §9
Known deviations table — repopulate from measured results.

### 5.2 Update README
Reflect current state: all 14 editions have --version, --event-file, keyboard accelerators.

### 5.3 Commit and push
- Root repo: all tool changes, status report
- Each submodule: rebuilt binaries, test_config.txt, EDITION_NOTES.md

---

## 6. What was accomplished this session

- All 14 editions: --version, --event-file, keyboard accelerators (FR-11)
- Deleted all headless test files (spec §5.1/§5.2/§5.3)
- Python editions: Nuitka binaries (10-12 MB each)
- Measurement infrastructure: RamSampler, per-op peak RAM, close time
- Per-edition test_config.txt for measurement configuration
- Report aggregator (tools/report_aggregate.py)
- Automation script (run_all.sh)
- QA suite fixes: multi-edition reporting, --reps flag, go_gio manifest

---

## 7. Tools

| Tool | Purpose |
|------|---------|
| `run_all.sh` | Full pipeline: build + measure + test + report |
| `tools/report_aggregate.py` | Binary + lib size report, merges measurement data |
| `tools/qa/suite.py` | QA test suite (A01-A14) |
| `tools/qa/fastnote_qa/measurements.py` | RamSampler, per-op timing + RAM |
| `tools/measure/gen_report.py` | Comparative tableau HTML |
| `editions/*/test_config.txt` | Per-edition measurement config |

---

## 8. Git state

Root repo last push: `32c6c3d`
14 submodules last push: each pushed separately

Uncommitted:
- go_gio event loop fix (rebuild pending)
- python_gtk4 gi patch (rebuild pending)
- This status report
