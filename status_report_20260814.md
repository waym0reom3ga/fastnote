# FastNote Status Report — 2026-08-14

Combined status from **Session A** (12-edition rebuild), **Session B** (QA/QC suite),
and **this session** (c_gtk4 audit + c_nuklear completion).

---

## 1. Big picture

The repo holds **14 edition directories** (C, Go, Python, Rust ports of the same
markdown editor). Docs (spec §9, testing protocol, README) historically claimed
13/13 acceptance for all editions, but those claims describe trees that no
longer exist:

- Rust editions were rewritten as fresh single commits on **Aug 10** (no history,
  no tests, no `--insert`, no A13 artifact).
- c_gtk4's committed binary was stale (built before its last source edit).
- Acceptance logs in `tools/tmp/acceptance/` are dated **Aug 9**.
- The acceptance suite never tested PDF export (zero PDF assertions in
  `run.sh`; protocol Category 7 has no FR-8 row).
- Shipped tests were sometimes tautological (e.g. python_gtk4 asserting its own
  assignment — the pattern §6.1 bans).

The agreed repair lineage (Session B): go_gio → go_fyne → c_nuklear →
python_gtk4 → downstreams → c_gtk4 → c_raygui → rust_gtk4 → rust_egui →
rust_slint → go_gtk4 → go_wails3. Each edition is proven through its own real
GUI before moving on.

---

## 2. Session A — edition rebuild status (7 of 12 originally done)

| Edition | Commit | Status |
|---------|--------|--------|
| python_dearpygui | e50cb05 | 13/13 |
| python_gtk4 | c804cc2 | 13/13 |
| python_pyqt6 | 217cf30 | 13/13 |
| python_pyside6 | feff0cd | 13/13 |
| go_gio | 0989cdb | 13/13 |
| go_fyne | 24c6181 | 13/13 |
| c_nuklear | 73c3201 (initial "13/13" claim) | **now 26/26 in-process suite, seam-free** (this session) |
| c_gtk4 | fastnote_c_gtk4 v1.0 | **22/22, zero warnings** (this session) |

Root repo register commits: a60b088 (python_dearpygui), 80332f0 (python_gtk4/
pyqt6/pyside6). **Root register commit for the two Go editions and the current
round of fixes is still pending.**

Guardrail from Session B: **no git operations, working-tree edits only** — this
has been observed this session (nothing committed).

---

## 3. Session B — QA/QC suite (`tools/qa/`)

A new fully-real QA/QC suite was built (Phase 1 complete, uncommitted):

- **One suite, fully real.** Library test categories 1–6 deleted from the
  protocol; per-edition test files deleted. Every case drives the real window on
  the real display with OS-level input (control-map/ready-file flags, XTEST
  clicks via fnprobe/xdotool, pixel + window-title + disk assertions,
  `--sabotage` validation mode).
- **No headless seam.** The user rejected headless testing ("I don't want
  headless SHIT"); spec §5.1/§5.3 headless mandate is being removed from the
  docs.
- **Cases A01–A13:** build → launch → version → open arbitrary file → edit/dirty
  → save → Save As → export HTML → export PDF (structurally validated) → E2E →
  wiring (static) → browser (static) → close-with-dirty (FR-9).
- **Measurement:** binary size, startup, VmHWM RAM, latencies (fnprobe),
  calibration-gated (floor ≈ 18 ms, overhead ≈ 17 ms).
- **Results:** SQLite history + capability matrix + Markdown/HTML/JUnit report.
- **Baseline smoke passes:** go_gio + python_gtk4 A02/A10/A11/A12.

Manifest fix made in Session B: rust_gtk4 binary corrected to
`target/release/fastnote-rust-gtk4`.

---

## 4. This session — c_gtk4 audit (completed) + c_nuklear (completed)

### 4.1 c_gtk4 — finished, verified

- **Renderer rewritten** with GString + run-based HTML escaping of `<`, `>`, `&`,
  `"` (fixes a heap overflow: `# ` expands 5.5x vs the old 2x+100 buffer).
- file_browser.c `current_dir` freed before `g_strdup` (leak, two call sites).
- ui.c `defpath`/basename leaks fixed (export + Save As dialogs).
- Dead seam-era `actions_open_file` removed from actions.c/actions.h.
- export.c PDF tag-strip now decodes `&lt; &gt; &amp; &quot;`.
- Tests strengthened: %PDF magic bytes, renderer escaping (text + headings),
  5000-heading overflow. **22/22 pass, `FASTNOTE_SABOTAGE=1` exits 1, clean
  build zero warnings, binary `fastnote_c_gtk4` v1.0.**

### 4.2 c_nuklear — debugging + completion

Six real bugs found and fixed:

1. **Off-by-one widget rect recording** — `nk_widget_bounds()` peeks the *next*
   layout slot; rects recorded after drawing pointed at the following widget.
   Fixed with record-before + static rows for the toolbar and OK/Cancel row
   (a 6-column dynamic row overflowed by spacing and wrapped the Theme button to
   a second row; the 2-column dynamic OK/Cancel row stacked vertically).
2. **Insert-button doc wipe** — the per-frame editor↔doc sync always overwrote
   the doc from the editor text, so `on_insert`'s change was reverted the same
   frame. Fixed with a bidirectional sync (editor typed → doc follows; doc
   changed by a handler → editor follows doc).
3. **Double ".." listing** — `browser_refresh` added ".." explicitly while the
   readdir loop only skipped ".".
4. **Literal ".." path** — `browser_activate("..")` built a literal
   `".../sub/.."` cwd; now routes to `browser_parent()`.
5. **Stale duplicate cancel_rect recording** after the Cancel button drew
   (recorded the wrapped next-row position, so the cancel click missed).
6. **Reopened FileBrowser dead (NK_WINDOW_ROM)** — the last blocker. The test
   suite's `click()` skipped `nk_clear` on the release frame, so the closed
   browser window kept its stale seq, survived GC, and was found-but-buried on
   reopen: the full-screen main window promoted itself to the top of the
   window stack and the browser was permanently marked NK_WINDOW_ROM (all its
   widgets receive `in=NULL` → no hit-testing). Fixed by adding the per-frame
   `nk_clear` to the test's click helper (matching the real GLFW backend,
   which clears every frame in `nk_glfw3_render`).

Also fixed: `render_doc_title` ignored its first-line bound and returned the
whole multiline doc as the export filename (now returns just the title line);
a test assertion updated to match `render_plain`'s real output (H1s are
uppercased → `HELLO`).

### 4.3 c_nuklear — seam removal + housekeeping

- **main.c rewritten to be seam-free**: only `--version` (prints
  `fastnote_c_nuklear v1.0.0`); bare launch opens the GUI. Removed
  `--open/--insert/--save/--export/--headless/--selftest/--notes-dir`.
- **Makefile**: `TARGET = fastnote_c_nuklear`; seam-based `test:` target
  replaced with `--version` + `test-ui`.
- **Removed dead seam code**: `RunCLIActions` (actions.c) and the entire
  `selftest.c/selftest.h` module (referenced only by the old seam).
- **Deleted `src/renderer.c.bak`**.
- **Sabotage hook added** to `test_ui.c` (unbind Open under
  `FASTNOTE_SABOTAGE=1`), satisfying the harness's A12Sabotage requirement.
- **Zero-warning build** (silenced the vendored nuklear.h unused-variable
  warning and fixed pre-existing renderer.c const/truncation warnings).

**Result: in-process suite 26/26 passes; sabotage run fails as required; clean
build; binary `fastnote_c_nuklear`.** ports.conf still lists `bin_rel =
fastnote` and must be updated to `fastnote_c_nuklear`.

---

## 5. Current uncommitted state

- `editions/fastnote_c_nuklear_ed/` — many modified files, uncommitted
  (actions.c, app.c, app.h, app_ui.c, export.c, file_browser.c/h, renderer.c,
  test_ui.c, ui.h; selftest.c/h and renderer.c.bak deleted; main.c + Makefile
  rewritten).
- `editions/fastnote_c_gtk4_ed/` — submodule dirty (fixes not committed).
- Root repo — modified: `docs/FASTNOTE_SPECIFICATION.md`,
  `docs/fastnote_testing_protocol.md`, `tools/acceptance/ports.conf`,
  `tools/acceptance/run.sh`, `tools/measure/run.py`; untracked:
  `docs/benchmark-report.html`, `tools/qa/`, `tools/measure/gen_report.py`,
  `session_a.md`, `session_b.md`.

---

## 6. Remaining work (priority order)

1. **ports.conf**: point c_nuklear `bin_rel` at `fastnote_c_nuklear`.
2. Run `tools/acceptance/run.sh fastnote_c_nuklear_ed` and
   `tools/acceptance/run.sh fastnote_c_gtk4_ed` to confirm A1–A13 (A2 needs the
   user's display/compositor up).
3. Re-run the **tools/qa** suite baseline (Phase A) on the four GTK4 editions
   once the user's display environment is up.
4. Commit: c_nuklear edition repo + c_gtk4 fixes + root register commits
   (including the Go editions) — per the user's go-ahead.
5. Continue the repair lineage: c_raygui → rust_gtk4 → rust_egui → rust_slint →
   go_gtk4 → go_wails3.
6. Phase C: measurement pass, capability matrix, retire `tools/acceptance/` and
   `typecheck.sh`, reconcile docs (spec §9, protocol table, README, §5 headless
   seam removal) from measured results.

---

## 7. Key technical facts

- Vendored Nuklear differs from upstream: `enum nk_widget_layout_states` order
  is `INVALID=0, VALID=1, ROM=2, DISABLED=3`; buttons click on the **press**
  frame (`is_mouse_pressed = down && clicked`).
- `nk_widget_bounds() == nk_layout_peek()` returns the **next** slot — record
  widget rects before drawing.
- A window skipped for one frame survives GC (seq semantics); a window that is
  neither `ctx->end` nor transferring via `!iter` gets `NK_WINDOW_ROM`, killing
  all its input. The real GLFW backend calls `nk_clear` every frame (in
  `nk_glfw3_render`).
- Toolbar order: Open(0), Save(1), Insert(2), Export(3), Export PDF(4),
  Theme(5).
- No native file dialogs anywhere; in-app FileBrowser (spec 3.1). Export HTML
  via `render_page` (standalone DOCTYPE doc); PDF via `render_plain` →
  `pdf_from_lines` (PDF/1.4, Helvetica).
- Recovery is permanently cancelled; do not reuse any recovery artifacts.
