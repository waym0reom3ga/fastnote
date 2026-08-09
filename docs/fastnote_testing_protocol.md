# FastNotes Testing Protocol

**Version 2.0 — 2026-08-07.** Subordinate to `FASTNOTE_SPECIFICATION.md`.

## Objective

Measure the impact of each GUI technology stack on a standardized markdown editor product.
Every port implements the same tests, measuring identical operations, with identical
assertions. No port gets extra tests. No port gets fewer.

## What went wrong in version 1

Version 1 of this protocol defined 35 tests across 6 categories. All ports were reported as
passing 35/35. In reality no port could open a file, most could not export one, and three
produced no runnable binary.

The protocol was not being violated — it was being satisfied. Categories 1–6 test the model,
renderer and export **libraries**. They never construct a widget. The five "UI Layer" tests
that were supposed to cover the interface were tautological; the canonical example is:

```c
ASSERT(app->editor_text != NULL, "editor_text is NULL");
```

where `editor_text` is a fixed-size array inside a `calloc`'d struct. That assertion cannot
fail. Neither can `strlen(app->editor_text) == 0` on a freshly zeroed buffer.

The `TestE2EWorkflow` test — nominally the end-to-end proof — called the model, renderer and
exporter functions directly in sequence. It never touched the UI layer. The pipeline worked;
the buttons that should have invoked it did not exist.

Two structural corrections follow:

1. **Category 7 (GUI Acceptance)** is added. It runs against the *built binary* via the CLI
   seam defined in specification §5, and it is the only category that constitutes evidence
   that the application works.
2. **Test counts are no longer a completeness measure.** Completeness is the capability
   matrix in specification §9. A port passing every test in Categories 1–6 while failing
   FR-2 is reported as failing FR-2.

## Canonical Test Suite (35 library tests + 13 acceptance tests)

### Category 1: Model Layer (8 tests)

Measures: File I/O, serialization, search algorithms, directory traversal. Framework-independent business logic.

| # | Test | Operation | Assertion |
|---|------|-----------|-----------|
| 1 | `TestNoteNew` | Create empty note from path | Title derived from filename, content empty, dirty=false |
| 2 | `TestNoteLoadSave` | Write to disk, read back, compare | Content matches exactly, dirty=false after save |
| 3 | `TestNoteDirty` | Set dirty flag, verify title display | Title shows "*" suffix when dirty |
| 4 | `TestNoteList` | List .md files in directory, filter non-.md | Returns only .md files, count matches |
| 5 | `TestFolderTree` | Build recursive tree from nested dirs | Non-empty tree, subfolder notes found |
| 6 | `TestSearchNotes` | Case-insensitive search across note contents | Matches found for multi-note query, exact match for unique term |
| 7 | `TestGlobalSearch` | GlobalSearch struct wraps search_notes | Same results as direct search_notes call |
| 8 | `TestSettingsSaveLoad` | Serialize Settings to JSON, deserialize, compare | All fields preserved (theme, font_size, auto_save, etc.) |

### Category 2: Renderer Layer (12 tests)

Measures: Markdown parser throughput, HTML output correctness, feature support. Library-dependent (goldmark vs pulldown-cmark).

| # | Test | Operation | Assertion |
|---|------|-----------|-----------|
| 9 | `TestRenderMarkdown` | Render headings, bold, italic, lists, code, tables | Output contains `<h1>`, `<strong>`, `<em>`, `<code>` |
| 10 | `TestRenderCodeBlocks` | Render fenced code with language spec | Keywords present, `<pre>` or `<code>` wrapper |
| 11 | `TestRenderTables` | Render pipe-style table | Headers and cells present in output |
| 12 | `TestRenderDarkMode` | Render same markdown with light vs dark theme | Both produce valid HTML with content |
| 13 | `TestRenderFullHTML` | Generate complete HTML document | Contains DOCTYPE, `<html>`, `<style>`, title |
| 14 | `TestRenderTOC` | Extract headings, build TOC entries | Entry count matches heading count, levels correct |
| 15 | `TestRenderTOCAsHTML` | Convert TOC entries to nested HTML list | Contains all heading titles |
| 16 | `TestRenderWikiLinks` | Convert `[[Name]]` to `[Name](path)` | Both links converted with correct paths |
| 17 | `TestRenderCheckboxes` | Process `- [x]` and `- [ ]` syntax | Checked and unchecked states preserved |
| 18 | `TestRenderMathInline` | Convert `$...$` to LaTeX delimiters | `\( \)` delimiters present |
| 19 | `TestRenderMathBlock` | Convert `$$...$$` to LaTeX delimiters | Block math preserved |
| 20 | `TestBuildNoteIndex` | Build path map from file list | Index contains underscore and space variants |

### Category 3: Export Layer (3 tests)

Measures: Export pipeline, format routing, theme-aware output.

| # | Test | Operation | Assertion |
|---|------|-----------|-----------|
| 21 | `TestExportHTML` | HTMLExporter.Export() with custom CSS | Output contains DOCTYPE, title, content, custom CSS |
| 22 | `TestExportHTMLDarkMode` | Export with dark=true | Output contains dark color values (#1e1e1e or #c9d1d9) |
| 23 | `TestExportManager` | ExportNote() for html and unsupported format | HTML succeeds, docx returns error |

### Category 4: UI Layer (5 tests)

Measures: application state wiring. **Rewritten in v2** — the v1 versions of tests 24–27 were
tautological and provided no evidence. Each assertion below must be capable of failing.

| # | Test | Operation | Assertion |
|---|------|-----------|-----------|
| 24 | `TestAppCreation` | New(notesDir) on a seeded dir | App non-nil AND notes_dir equals the dir passed in AND settings loaded AND export manager present |
| 25 | `TestAppEditor` | Open a known note, read editor buffer | Editor buffer content equals the file's bytes exactly. Then mutate and assert buffer changed and dirty is set |
| 26 | `TestAppPreview` | Open a note containing `# Heading`, trigger preview update | Preview output is non-empty, differs from the raw source, and contains rendered evidence (`<h1>` or equivalent) |
| 27 | `TestAppSettings` | Load, mutate a field, save, reload | Mutated value survives the round trip |
| 28 | `TestAppNoteList` | Create 3 notes in dir, construct app | Note count is exactly 3 AND each expected title is present |

**Banned in this category** (specification §6.1): asserting a fixed-size array is non-null;
asserting only that a constructor returned non-null; asserting a fresh empty buffer is empty;
`_ = x` with no assertion.

### Category 5: Edge Cases (5 tests)

Measures: Robustness, memory behavior, encoding correctness.

| # | Test | Operation | Assertion |
|---|------|-----------|-----------|
| 29 | `TestEmptyNote` | Load empty .md, render empty string | No panic/crash, renders empty or minimal HTML |
| 30 | `TestLargeNote` | Render 1000-heading note (~60KB) | Completes in <5s, output larger than input |
| 31 | `TestSpecialCharacters` | Render `<script>`, `&`, `"` | No crash, script tags escaped |
| 32 | `TestUnicodeContent` | Render CJK, emoji, Cyrillic | Content preserved in output |
| 33 | `TestNoteIndex` | Build index from 3 paths | Index has entries for each path |

### Category 6: Integration (2 tests)

Measures: Full pipeline latency, data consistency across layers.

| # | Test | Operation | Assertion |
|---|------|-----------|-----------|
| 34 | `TestE2EWorkflow` | Create note -> read -> render -> export -> modify -> save | Each step succeeds, final content persisted |
| 35 | `TestE2ESearch` | Create 3 notes -> global search -> verify results | Search finds correct notes with correct counts |

> Note: tests 34–35 are **library-level** pipeline tests. They call model/renderer/export
> functions directly and prove nothing about the application. The equivalent user-facing
> proof is `Accept12E2EWorkflow` in Category 7. Do not cite test 34 as evidence that the
> editor works; that was the central error of v1.

---

### Category 7: GUI Acceptance (13 tests)

**This is the category that matters.** Executed by a shared harness against each port's
**built binary**, driving the CLI seam from specification §5. Because the seam shares code
paths with the GUI handlers (spec §5.2), these tests exercise the same logic a user's clicks
would reach.

A port failing any Category 7 test is incomplete regardless of its Category 1–6 results.

| # | Test | Operation | Assertion | FR |
|---|------|-----------|-----------|-----|
| A1 | `AcceptBinaryExists` | Locate built artifact | Binary/entry point exists, is executable, built from committed sources | FR-1 |
| A2 | `AcceptVersion` | Run `--version` | Exit 0, prints a port identifier on stdout | FR-1 |
| A3 | `AcceptSelfTest` | Run `--selftest` | Exit 0 | FR-1 |
| A4 | `AcceptHeadlessNoDisplay` | Run `--headless --version` with no `DISPLAY`/`WAYLAND_DISPLAY` | Exit 0, does not hang, no X/Wayland connection required | FR-1, §5.3 |
| A5 | `AcceptOpenArbitraryFile` | Seed a `.md` in a temp dir **outside** the notes dir; `--headless --open <path> --export <out.html>` | Exit 0; `out.html` exists and contains the seeded file's distinctive content | FR-2 |
| A6 | `AcceptOpenControlPresent` | Static inspection of UI source | An Open control exists, is added to a container, AND is bound to a handler that reaches the open code path | FR-2 |
| A7 | `AcceptFileBrowserExists` | Static + runtime inspection | A file browser component exists, built from the port's own toolkit; no native dialog symbol is linked or imported | FR-2, §3.1 |
| A8 | `AcceptEditSave` | `--headless --open <f> --insert "<marker>" --save`, then read file | Exit 0; file on disk now contains `<marker>`; byte length increased | FR-3, FR-5 |
| A9 | `AcceptDirtyState` | Open, insert without saving, query state | Document reports dirty; after `--save`, reports clean | FR-3 |
| A10 | `AcceptExportHTMLFile` | `--headless --open <f> --export <out.html>` | `out.html` exists, non-empty, contains DOCTYPE, `<html>`, `<style>`, a `<title>`, and the document's content | FR-7 |
| A11 | `AcceptExportControlWired` | Static inspection of UI source | Export control exists AND is bound to a handler AND that handler's result reaches a filesystem write | FR-7 |
| A12 | `AcceptE2EWorkflow` | **The primary test.** Copy the canonical template `.md` to a temp dir; `--open` it; `--insert` a marker; `--save`; `--export` to HTML; verify | Every step exits 0; saved `.md` contains the marker; exported `.html` exists, is non-empty, contains both the template's original heading and the inserted marker | FR-2,3,5,7 |
| A13 | `AcceptUIClickTests` | Run the port's pointer-event test suite: build the real widget tree, inject press/release at the control's coordinates, assert on the outcome | Suite passes. Must include: Open control present in the rendered tree; clicking Open shows the browser; clicking a file loads it into the editor; clicking Export writes a file | FR-2,3,5,7 |

#### A13 is not optional, and it is the test that matters most

A1–A12 drive the CLI seam. They prove the *logic* works. **They cannot prove the buttons
work.** A port can pass all twelve while its toolbar is completely inert.

This is not hypothetical. During development of the reference implementation, `go_gio`
passed A1–A12 with a full green board while clicking Open did nothing at all — the button
rendered, the handler was written, and the click never reached it. The CLI-driven suite was
structurally incapable of noticing, which is the identical blind spot that produced the
original "35/35 passing" on software that could not open a file.

A13 must inject genuine pointer events into the framework's own event pipeline. Acceptable:
Gio's `input.Router.Queue` with `pointer.Event`; GTK's `GtkTestUtils` / event emission;
Qt's `QTest::mouseClick`; egui's simulated input; raw event injection for immediate-mode C.
Not acceptable: calling the handler function directly, which tests the handler and not the
binding.

Each port's A13 suite must be verified by **sabotage**: temporarily unbind a control and
confirm the suite fails. A suite that passes on a deliberately broken button is worthless.
The reference implementation's suite was validated against all three defects observed in
this repository — unbound control, missing control, and export that discards its output —
and detected each one.

#### A12 canonical template

All ports run A12 against the identical template, stored at `testdata/template.md` in the
repository root, so that the end-to-end path is byte-identical across the comparison.

#### Notes on A6, A7, A11

These three are static-inspection tests. They exist because a runtime CLI test cannot
distinguish "the GUI button works" from "the CLI has its own copy of the logic". They are the
enforcement mechanism for the shared-path rule (spec §5.2).

They must verify three things in sequence, all of which have been observed missing in this
project:

1. The control is **constructed** — `fastnote_rust_gtk4_ed/src/main.rs:101` constructs an
   Export button.
2. The control is **added to a container** — the same button is packed at `main.rs:128`.
3. The control is **bound to a handler** — the same button has no `connect_clicked` anywhere.
   It is visible, clickable, and does nothing.

Checking only (1) and (2) would have passed that port.

---

## Benchmark exclusion rule

Performance figures from a port that fails any of A1–A12 MUST be published with an
incompleteness marker. Comparing the binary size of a port that cannot export against one
that can measures nothing about the toolkits.

## Current Port Status

Library tests (Categories 1–6) and acceptance (Category 7) reported separately, because the
first column is the one that misled this project for a month.

| Port | Lib tests | Category 7 | Blocking failures |
|------|-----------|------------|-------------------|
| Go/Gio *(reference)* | 42 | **13/13** | none — reference implementation complete |
| Go/Fyne | 40 | **13/13** | none |
| C/Nuklear *(C ref)* | 36 | **13/13** | none |
| C/GTK4 | 36 | **13/13** | none |
| C/RayGUI | 36 | **13/13** | none |
| Rust/GTK4 *(Rust ref)* | 74 | **13/13** | none |
| Rust/egui | 90 | **13/13** | none |
| Rust/Slint | 74 | **13/13** | none |
| Python/GTK4 *(Py ref)* | 43 | **13/13** | none |
| Python/PyQt6 | 43 | **13/13** | none |
| Python/PySide6 | 43 | **13/13** | none |
| Python/DearPyGui | 43 | **13/13** | none |

Every port now passes all thirteen acceptance tests. Each earned it the same way: an Open
control, an in-app file browser, a wired Export that reaches a filesystem write, a command
line seam sharing those code paths, and a click suite validated by sabotage.

## Deviations Explained

### Removed from Fyne (3 tests)
- `TestExportPDF` - Requires external wkhtmltopdf/chromium. Not reproducible. Skipped on most systems.
- `TestScreenshotApp` - Fyne-specific headless capture. Other frameworks cannot do this. Unfair advantage.
- `TestScreenshotEditorWithContent` - Same as above.

### Removed from Fyne (1 test)
- `TestUISyntaxHighlighter` - Tests Chroma library directly, not the framework. Covered by `TestRenderCodeBlocks`.
- `TestUISearchBar` - Covered by `TestAppEditor` + `TestSearchNotes`.
- `TestUIGlobalSearch` - Covered by `TestGlobalSearch` + `TestE2ESearch`.
- `TestUISettingsDialog` - Covered by `TestAppSettings`.
- `TestUIEditor` - Covered by `TestAppEditor`.

### Added to all ports
- `TestNoteDirty` - Measures dirty state tracking (UI-critical feature)
- `TestRenderMathBlock` - Separated from inline math (different code paths)
- `TestRenderTOCAsHTML` - Tests TOC HTML rendering (separate from TOC generation)
- `TestE2ESearch` - End-to-end search verification

## Benchmark Suite (12 benchmarks)

Same across all ports. Measures raw throughput of core operations.

| # | Benchmark | Input | Measures |
|---|-----------|-------|----------|
| 1 | `NoteCreate` | New note struct | Allocation, initialization |
| 2 | `NoteSave` | 1KB note to disk | File I/O latency |
| 3 | `NoteLoad` | 1KB note from disk | File read + parse |
| 4 | `NoteDelete` | Remove from disk | File removal |
| 5 | `RenderMarkdown` | 1KB markdown | Parser throughput, allocs |
| 6 | `RenderLargeNote` | 60KB markdown | Memory, render time |
| 7 | `ExportHTML` | 1KB note to HTML | Full export pipeline |
| 8 | `FolderTree` | 100 files in nested dirs | Recursive traversal |
| 9 | `WikiLinks` | 10 wiki links in content | Regex + path resolution |
| 10 | `Checkboxes` | 50 checkbox items | Checkbox detection |
| 11 | `Math` | Inline + block math | LaTeX detection/wrapping |
| 12 | `GlobalSearch` | 100 notes, 1KB each | Multi-file search |

## Quality Gates

1. All 35 library tests must pass on every port
2. Test names must match canonical names exactly
3. No `t.Skip()` or `#[ignore]` without documented justification
4. Benchmarks must use identical input sizes across ports
5. Assertions must verify the same conditions (not just "no crash")
6. **A port is not complete without a launchable GUI artifact produced by a clean build from
   committed sources.** Passing library tests with no binary is not partial completion; it is
   a failure of FR-1. All twelve ports now satisfy this gate.
7. **No tautological assertions.** The patterns banned in specification §6.1 are rejected in
   review. Any UI-category test that cannot fail is treated as an absent test.
8. **All 13 Category 7 acceptance tests must pass against the built binary.** Categories 1–6
   are necessary but never sufficient, and A1–A12 are not sufficient without A13: only A13
   presses the button.
9. **Completeness is reported as a capability matrix, never as a test-count percentage.** The
   phrase "35/35" is not a statement about the product.
10. **Commit messages must not claim "complete implementation"** unless gates 1–9 all hold.
    Six of the existing ports carry such a claim; none of the six satisfy it.

## Execution

### Library tests (Categories 1–6)

```bash
# Go/Fyne
cd fastnote_go_fyne_ed && go test -v -count=1 ./...

# Go/Gio
cd fastnote_go_gio_ed && go test -v -count=1 ./...

# Rust ports
cd fastnote_rust_egui_ed  && cargo test --release
cd fastnote_rust_slint_ed && cargo test --release
cd fastnote_rust_gtk4_ed  && cargo test --release

# C ports
cd fastnote_c_nuklear_ed && make test
cd fastnote_c_gtk4_ed    && make test
cd fastnote_c_raygui_ed  && make test

# Python ports
cd fastnote_python_gtk4_ed && python -m pytest tests/ -v
```

### Acceptance tests (Category 7)

Run by the shared harness against built binaries. One harness, all ports, identical
assertions:

```bash
./acceptance/run.sh <port-directory>     # single port
./acceptance/run.sh --all                # full matrix
```

The harness locates the port's binary, executes the CLI seam (spec §5), inspects the
filesystem results, and performs the static wiring checks A6/A7/A11. It is deliberately
external to every port so that no port can influence its own verdict.
