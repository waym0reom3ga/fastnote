# FastNote Testing Protocol

**Version 4.0 — 2026-08-14.** Subordinate to `FASTNOTE_SPECIFICATION.md`.

## Objective

Measure the impact of each GUI technology stack on a standardized markdown editor product.
Every edition implements the same black-box behaviour (the specification) with a different
toolkit, and every edition is held to the same acceptance tests, measuring identical
operations with identical assertions. No edition gets extra tests. No edition gets fewer.

The product under test is a **GUI editor**. Every acceptance test therefore drives the
actual window on a real display, delivers input the way a user would, and asserts on what a
user can observe: files on disk, window titles, and rendered output. There is no headless
mode, no CLI editing seam, and no library-only shortcut to acceptance.

## Why versions 2 and 3 were discarded

**Version 2** defined a "headless control seam": every edition exposed `--open`, `--insert`,
`--save`, `--export` and `--headless`, and the harness drove those flags instead of the GUI.
That seam became a second, parallel application — ports passed all CLI tests while their
toolbar was inert, and the v1 failure (35/35 passing, no port could open a file) reproduced
in miniature. The seam is gone.

**Version 3** removed the seam but still located controls by their published geometry: each
edition wrote a control map of widget rectangles and the harness clicked those coordinates.
Two things made that wrong. First, it required every edition to expose test-only geometry,
a hook the specification does not permit. Second, it measured whether a click landed on a
button, which is a test of the control map, not of the product. A port could pass with
buttons that a real user could not find.

**Version 4 drives the keyboard.** The specification now mandates standard accelerators
(FR-11) and a keyboard contract for the file browser (§3.2 of the specification): `Ctrl+O`
opens, `Ctrl+S` saves, `Ctrl+E` exports, `Ctrl+Shift+S` saves as, `Ctrl+Shift+E` exports
PDF, `Ctrl+L` focuses the browser's path field, `Enter` confirms, `Escape` cancels. The
harness types paths and presses keys exactly as a user would. No coordinates, no control
maps, no per-edition geometry. If a control cannot be reached by keyboard, the edition
fails.

## What the tests are allowed to do

An acceptance run is allowed exactly three privileges beyond a real user:

1. **A display may be virtual.** The suite runs under a live desktop or under Xvfb (or an
   equivalent virtual display server). This is a real display: the window is mapped, widgets
   lay out, and events are dispatched through the framework's normal pipeline. What is
   virtual is only the physical screen, not the GUI.
2. **Pointer and keyboard events may be synthesised.** The main test cases deliver input at
   the OS level through XTEST (`xdotool`): real key presses, real pointer motion, real
   clicks. The in-edition GUI event suites (used for sabotage validation, below) inject
   events through the framework's own input API.
3. **The edition publishes phase completions through `--event-file`** (specification §5.1).
   The harness waits for a phase marker before asserting or timing an operation. This is the
   edition's only permitted instrumentation flag, it is a reporting outlet and never a
   command path, and a marker written without the operation being performed is a
   specification violation and fails the port.

Everything else is identical to a user session: the binary launches, the window appears, the
user's keystrokes are the test's keystrokes.

**Banned:** calling a handler function directly, routing through a hand-rolled control
registry, stubbing the widget tree, reading a test-only control map, asserting on internal
fields without a user-visible event having been delivered, and any test whose outcome is
unchanged when the control under test is deleted.

---

## Category 7: GUI acceptance (the only category)

**This is the only category of test that constitutes evidence.** Categories 1–6 of earlier
protocol versions (model, renderer, export, wiring, edge case, integration library tests)
are deleted: they validated library layers that every edition shares and none of which can
prove the product works. The library code still exists in each edition and is still
exercised, but through the real interface and the real files it produces, never as a
separate unit suite with its own claims.

All thirteen tests are executed by the shared harness `tools/qa/suite.py` against each
edition's **built binary**, launched under a display, driven by keyboard, and verified by
what lands on disk and in the window title.

A port failing any Category 7 test is incomplete regardless of anything else that builds or
passes.

| # | Test | Operation | Assertion | FR |
|---|------|-----------|-----------|-----|
| A01 | `AcceptLaunches` | Launch the binary; wait for a real window; close it via a WM close request | Window maps; process exits 0 on normal close | FR-1 |
| A02 | `AcceptVersion` | Run `--version`; then run an unknown flag | Exit 0 and a port identifier; unknown flags exit non-zero | FR-1 |
| A03 | `AcceptOpenArbitraryFile` | `Ctrl+O`; `Ctrl+L`; type the path of a seeded `.md` **outside** any notes dir; `Enter`; wait for the `open` marker | Editor contains the file's contents; title/status reflects the path | FR-2 |
| A04 | `AcceptEdit` | Click into the editor, type a marker; wait for the dirty marker in the title; confirm no disk write | Keystrokes reach the document; dirty state visible; disk unchanged without a save | FR-3 |
| A05 | `AcceptSave` | Edit (A04), then `Ctrl+S`; wait for the `save` marker | File on disk equals the editor contents byte-for-byte; dirty state cleared | FR-3, FR-5 |
| A06 | `AcceptSaveAs` | Edit, then `Ctrl+Shift+S`; type a new path; `Enter`; wait for the `save-as` marker | File appears at the new path; the document's active path becomes the new path | FR-6 |
| A07 | `AcceptExportHTML` | `Ctrl+E`; type an export path; `Enter`; wait for the `export-html` marker | Standalone `.html` on disk: DOCTYPE, `<html>`, `<style>`, `<title>`, document content | FR-7 |
| A08 | `AcceptExportPDF` | `Ctrl+Shift+E`; type an export path; `Enter`; wait for the `export-pdf` marker | Structurally valid PDF on disk (header, xref, trailer, non-trivial size) | FR-8 |
| A09 | `AcceptE2EWorkflow` | **The primary test.** Open the canonical template (A03), type a marker, save (A05), export HTML and PDF (A07/A08) | Saved `.md` contains the marker; both exported artifacts are valid and contain the document | FR-2,3,5,6,7,8 |
| A10 | `AcceptOpenWiring` | Static inspection of UI sources | Open control present, an accelerator binding exists, and the handler reaches the open path | FR-2 |
| A11 | `AcceptExportWiring` | Static inspection of UI sources | Export control present, accelerator bound, and the handler reaches a filesystem write | FR-7 |
| A12 | `AcceptBrowserKeyboard` | Static + runtime inspection | A file-selection mechanism exists (in-app browser over POSIX operations, or a native dialog), with a path field reachable via `Ctrl+L` and confirm/cancel via `Enter`/`Escape` | FR-2 |
| A13 | `AcceptCloseDirty` | Make the document dirty (A04), then request a WM close | Either a prompt appears (window stays open) or the document is saved; never silently discarded | FR-9 |

### The event-file rule (A03, A05–A09)

The harness never guesses that an operation finished. It presses the accelerator, then waits
for the corresponding phase marker in the `--event-file` (§5.1 of the specification) before
asserting on disk state or timing the operation. `painted` gates the launch, `open` gates
open, `save` gates save, `save-as` gates Save As, `export-html` gates the HTML export, and
`export-pdf` gates the PDF export. If the marker never arrives, the test fails — the
operation did not complete.

A marker written by code that is not the real operation (a test stub that reports success
without doing the work) fails the port. The sabotage validation below is the enforcement.

### Sabotage validation (mandatory for A12-style suites)

Each edition ships a small GUI event suite that drives the edition's real widget tree
through the toolkit's own input API. The harness runs it twice:

1. As shipped — it MUST pass.
2. Under `FASTNOTE_SABOTAGE=1`, which asks the suite to unbind (or delete) a control — it
   MUST fail. A suite that still passes with a control unbound is testing nothing and is
   treated as an absent suite.

The three canonical defects, each observed in this repository:

1. **Unbound control** — button constructed, never connected to a handler.
2. **Missing control** — button not added to any container.
3. **Export discards output** — handler runs but the result never reaches a filesystem write.

The QA suite performs this check for at least one control per edition before accepting the
edition's event suite.

### Static checks (A10–A12)

These remain because they catch the "control exists but is a dead end" class of defect
cheaply by inspection. They are **guards**, not evidence: A03/A05/A07/A08 are the evidence,
and they come from pressing the actual keys and asserting on actual files.

---

## The GUI must exist (benchmark exclusion rule)

Performance figures from an edition that fails any of A01–A11 MUST be published with an
incompleteness marker. Comparing the binary size of an edition that cannot open a file
against one that can measures nothing about the toolkits.

## Execution

```bash
# one edition; the harness builds, launches, types, and asserts
python3 tools/qa/suite.py --edition c_gtk4

# every edition, every case
python3 tools/qa/suite.py --all

# measurement pass (calibration gate + metrics), then the comparative tableau
python3 tools/qa/suite.py --all --measure
```

The harness is external to every edition. No edition can influence its own verdict: the
harness owns the display, the seeded files, the injected keystrokes, and the assertions.
Results accumulate in a SQLite history, so a regression is a formerly-passing edition now
failing.

## Quality Gates

1. All thirteen Category 7 tests must pass against the built binary under a display.
2. The binary accepts exactly `--version` and `--event-file` (specification §5.1). Any other
   flag — `--open`, `--insert`, `--save`, `--export`, `--headless`, `--selftest`,
   `--notes-dir`, `--control-map` — fails the edition.
3. Every §1 operation is reachable by the FR-11 accelerators; the browser is reachable by
   the §3.2 keyboard contract.
4. **No tautological assertions.** The patterns banned in specification §6.1 are rejected in
   review. Any UI-category test that cannot fail is treated as an absent test.
5. Each edition's GUI event suite passes as shipped and fails under `FASTNOTE_SABOTAGE=1`.
6. Every phase marker in the `--event-file` is written by the real operation, not by a
   stub.
7. Completeness is reported as a capability matrix, never as a test-count percentage.
   "13/13" is not a statement about the product; it is the matrix row for an edition that
   passes all thirteen tests.
8. Commit messages must not claim "complete implementation" unless gates 1–7 all hold.
