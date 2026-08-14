# FastNote Specification

**Version 1.0 — 2026-08-07**
**Status: AUTHORITATIVE.** Supersedes `structural_analysis.md`. Where any other document,
test suite, port, or commit message conflicts with this file, this file wins.

---

## 0. What this document is

FastNote is a **markdown editor defined as a black box**. This specification describes what
FastNote *does*, observable from outside, in terms a user could verify by sitting in front of
the application. It says nothing about languages, GUI toolkits, widget names, struct layouts,
or function signatures.

Every implementation — including `fastnote_go_gio_ed`, which serves as the project's
*reference implementation* — is an answer to this document. The reference implementation is
**not** the specification. If the reference implementation disagrees with this document, the
reference implementation is wrong and must be fixed.

### 0.1 Why this document exists

The project previously used a library-API analysis as its de-facto specification. That
document described `Note` structs and `render()` functions in detail and **never once
mentioned opening a file**. Ports were therefore able to satisfy the specification completely,
pass 35 of 35 tests, and be reported as "complete implementations" while being unable to
perform the primary task of a text editor.

The failure was not laziness. It was a specification that described the parts of the program
that were easy to test, and omitted the parts that were hard to test. This document is
organised the other way around: **user-observable behaviour first, internals last.**

### 0.2 The governing rule

> A capability that cannot be exercised by a user through the application's own interface
> does not exist, regardless of whether library code implementing it is present in the
> repository and regardless of whether tests for that library code pass.

Dead code is not a feature. A button with no handler is not a feature. A function that
produces a correct result which is then discarded is not a feature.

---

## 1. Product definition

FastNote is a desktop application for editing markdown documents.

A user must be able to:

1. Launch it.
2. Open a markdown or plain-text file from anywhere on their filesystem.
3. Read and edit its contents.
4. See a rendered preview of the markdown.
5. Save changes back to disk.
6. Save the document to a new location.
7. Export the rendered document to a standalone HTML file on disk.
8. Export the rendered document to a PDF file on disk.
9. Close it without losing work.

That list is the product. Everything else in this document is detail in service of it.

---

## 2. Functional requirements

Requirements are identified as `FR-n`. Each is **MUST** unless marked otherwise.
Each maps to one or more acceptance tests in `fastnote_testing_protocol.md`, Category 7.

### FR-1 — Launch

The application MUST produce a runnable binary or launchable entry point built from committed
sources by a documented, reproducible build command. It MUST open a window and remain
responsive until the user closes it. It MUST exit with status 0 on normal close.

A port that does not build, or builds but produces no window, is not an implementation of
FastNote.

### FR-2 — Open an arbitrary file

The application MUST provide a visible, labelled **Open** control in its primary interface.

Activating it MUST present a **file browser** (see §3) allowing the user to navigate the
filesystem and select any readable `.md`, `.markdown`, or `.txt` file — **including files
outside any preconfigured notes directory**.

On selection, the file's full contents MUST be loaded into the editor and become the active
document. The window title or status area MUST reflect the opened document's path.

> **This requirement is the one the project has historically failed.** Scanning a hardcoded
> directory and listing its contents in a sidebar does **not** satisfy FR-2. A sidebar that
> lists `~/Documents/*.md` is a convenience feature, not an Open capability. The test is: can
> the user open a file the application did not already know about?

### FR-3 — Edit

The editor area MUST accept keyboard input and modify the in-memory document. It MUST support
at minimum: character insertion, deletion, newlines, and cursor movement.

A read-only text display is not an editor. Rendering document text with a draw-text primitive
that has no input handling does not satisfy FR-3.

Any modification MUST set the document's dirty state, and the dirty state MUST be visible to
the user (conventionally a `*` marker in the title or status area).

### FR-4 — Preview

The application MUST display a rendered representation of the current markdown document,
updated to reflect edits. The preview MUST be visually distinguishable from the raw editor
text — showing rendered markdown, not the same plain source in a second pane.

The preview MAY be toggleable. If it is hidden by default, the control to show it MUST be
discoverable.

### FR-5 — Save

The application MUST provide a visible **Save** control, and MUST bind it to the platform
save accelerator (`Ctrl+S`, see FR-11).

Activating Save on a document with a known path MUST write the current editor contents to
that path and clear the dirty state. The bytes on disk MUST afterwards equal the editor
contents exactly.

Activating Save on a document with no path MUST behave as Save As (FR-6).

### FR-6 — Save As

The application MUST allow saving the current document to a user-chosen path via the file
browser (§3) in save mode. After a successful Save As, the document's active path MUST become
the new path.

### FR-7 — Export HTML

The application MUST provide a visible **Export** control offering HTML output.

Activating it MUST allow the user to choose a destination path, and MUST **write a file to
that path**. The written file MUST be a complete standalone HTML document: a `DOCTYPE`, an
`<html>` element, an embedded `<style>` block, a `<title>` derived from the document, and the
rendered body content.

> Generating an HTML string in memory and then discarding it does not satisfy FR-7. Neither
> does possessing a working exporter module that no interface element calls. The acceptance
> criterion is a **file present on disk, non-empty, containing the document's content**.

### FR-8 — Export PDF

The application MUST provide PDF export through the same control as FR-7 and MUST write a
valid PDF file to the chosen path.

Where PDF generation requires an external tool that is absent, the application MUST report
the unavailability to the user clearly and MUST NOT silently do nothing. Absence of the
external tool is an acceptable runtime failure; absence of the capability from the interface
is not.

### FR-9 — Do not lose work

Closing the application, or opening a different document, while the current document is dirty
MUST NOT silently discard changes. The application MUST either prompt, or auto-save. Which of
the two is an implementation choice; silent loss is not.

### FR-10 — Notes directory (convenience, retained)

The application MAY present a sidebar listing markdown files found under a configured notes
directory, for quick switching. This is permitted and encouraged, but it is **supplementary
to FR-2, never a substitute for it**.

### FR-11 — Standard keyboard accelerators

Every operation in §1 MUST be reachable by a standard keyboard accelerator, using the
conventional Windows-style mapping, so that a user can drive the application without first
locating a button and without moving the pointer:

| Accelerator | Action | FR |
|---|---|---|
| `Ctrl+O` | Open (show the file browser in open mode) | FR-2 |
| `Ctrl+S` | Save the current document | FR-5 |
| `Ctrl+Shift+S` | Save the current document to a new path (Save As) | FR-6 |
| `Ctrl+E` | Export (show the file browser in export mode, offering HTML and PDF) | FR-7, FR-8 |
| `Ctrl+Shift+E` | Export PDF directly | FR-8 |

The accelerators MUST invoke the same code paths as the corresponding on-screen controls
(shared-path rule, §5.2). An accelerator that does nothing when its control is visible is a
specification violation. A port that cannot bind the literal `Ctrl` combination MAY bind the
platform-standard replacement (e.g. `Meta` on macOS) and MUST document the mapping; on every
other platform the literal mapping above applies.

The file browser's keyboard contract (path entry, confirm, cancel) is specified in §3.2.

---

## 3. The File Browser component

FastNote requires file selection in three places (FR-2 Open, FR-6 Save As, FR-7/8 Export
destination). This is specified as a single reusable component.

### 3.1 POSIX compliance

The file browser MUST use POSIX-compliant filesystem operations (`opendir`/`readdir`,
`stat`, `open`, `read`, `write`, or equivalent standard library abstractions). No
requirement is placed on the presentation layer: native platform dialogs, toolkit-native
file pickers, and custom-built browsers are all acceptable.

### 3.2 Required behaviour

The browser MUST:

- Display the contents of a starting directory (the current document's directory, or the
  notes directory, or the user's home directory).
- Distinguish directories from files visually.
- Navigate into a directory on activation.
- Navigate to the parent directory via a `..` entry or an equivalent control.
- Scroll when contents exceed the visible area.
- Filter to relevant extensions in open mode (`.md`, `.markdown`, `.txt`), with a way to show
  all files.
- Provide a text field for typing a path directly. In save/export mode this field supplies
  the new filename.
- Offer explicit confirm and cancel actions. Cancel MUST leave application state unchanged.

The browser MUST be fully operable from the keyboard. The tests and the acceptance suite
drive the browser by typing a path and confirming it, never by guessing control coordinates,
so the following key contract is part of the specification:

- `Ctrl+L` focuses the path text field and selects its contents, ready for typing.
- Typing a path into the focused field replaces the current selection.
- `Enter` confirms: in open mode, the browser opens the typed file if it exists (or the
  currently highlighted entry); in save/export mode, it returns the typed path, which need
  not exist.
- `Escape` cancels the browser and MUST leave application state unchanged.

A browser whose only usable path is pointer interaction does not satisfy FR-2/FR-6/FR-7/FR-8.

The browser SHOULD present a hierarchical tree of the notes directory where the toolkit makes
this natural, but a flat navigable list satisfies the requirement.

### 3.3 Contract

Conceptually the browser is one operation:

```
browse(mode, start_directory, extension_filter) -> selected_path | cancelled
```

`mode` is `open` or `save`. In `open` mode the returned path MUST exist. In `save` mode it
need not.

---

## 4. Markdown support

The renderer MUST handle, at minimum:

| Feature | Requirement |
|---|---|
| Headings, `#`..`######` | MUST |
| Bold, italic, strikethrough | MUST |
| Ordered and unordered lists | MUST |
| Inline code and fenced code blocks | MUST |
| Fenced blocks with a language tag | MUST render; syntax colouring SHOULD |
| Links and images | MUST |
| Blockquotes, horizontal rules | MUST |
| Pipe tables | MUST |
| Task list items `- [ ]` / `- [x]` | MUST preserve checked state |
| Wiki links `[[Name]]` | MUST resolve to a note path where resolvable |
| Inline math `$..$`, block math `$$..$$` | MUST emit LaTeX delimiters |
| Table of contents from headings | MUST |
| Light and dark themes | MUST |
| Custom CSS injected into exports | MUST, sanitised |

HTML in source markdown MUST be escaped such that a `<script>` element in a document cannot
execute in the preview or in exported output.

The renderer MUST handle empty input, very large input (60 KB / ~1000 headings) within 5
seconds, and arbitrary Unicode (CJK, Cyrillic, emoji) without corruption or crash.

---

## 5. Testability

FastNote is a GUI editor. It has no headless mode: a mode in which a user cannot see what
they are editing is not FastNote. Testing therefore drives the real window.

### 5.1 Permitted CLI flags

The binary MUST NOT accept any argument that constitutes an editing path or a command.
Exactly two arguments are permitted:

| Argument | Behaviour |
|---|---|
| `--version` | Print port identifier and version, exit 0 |
| `--event-file PATH` | Append one line to PATH each time a user-visible phase completes. No other effect. |

`--event-file` is the measurement trigger, and its only purpose is measurement. The
application appends one line per completed phase, written only after the phase has actually
finished — the document is loaded, the bytes are on disk, the frame is presented — so an
external harness can time the operation and is signalled to start the next one. The
recognised phase markers are:

| Marker | Meaning |
|---|---|
| `painted` | The first frame has been presented and the window is responsive (startup complete) |
| `open` | The file browser confirmed an open and the document is loaded |
| `save` | A save completed; the editor contents are on disk |
| `save-as` | A Save As completed; the document's path is the new path |
| `export-html` | An HTML export completed; the standalone document is on disk |
| `export-pdf` | A PDF export completed; the PDF file is on disk |

`--event-file` is a reporting outlet, never a command path. It MUST NOT cause, trigger, or
simulate any operation; every phase marker is written by the same code path the GUI uses. A
port that writes a marker without performing the operation is a specification violation.

The binary MUST NOT accept `--open`, `--insert`, `--save`, `--export`, `--headless`,
`--selftest`, `--notes-dir`, `--control-map`, or any other flag that exists to reach
application functionality without the GUI. A port that implements any such flag violates
this specification: such flags create a second application whose test coverage substitutes
for — and masks the absence of — a working GUI.

### 5.2 The shared-path rule

The GUI controls and their standard accelerators (FR-11) MUST be the only paths to
application functionality. There is no seam, no hidden command, no second entry point.
Every functional requirement FR-1 through FR-11 is reachable by a user with a mouse and
keyboard, and by the acceptance suite with synthesized pointer and key events delivered
through the framework's own input pipeline. The only flag a binary accepts beyond `--version`
is `--event-file` (§5.1), which reports completed phases and can neither invoke nor simulate
any operation.

Reviewers should verify by inspection that no port contains a duplicate implementation of
open/edit/save/export reachable by command line. A GUI handler and a CLI handler that each
contain their own copy of the logic is a specification violation even if both work.

### 5.3 Testing under a display

The acceptance suite MAY run the port under a virtual display server (e.g. Xvfb) and MUST
inject pointer and keyboard events through the framework's own event pipeline. Synthesized
events are delivered by the toolkit's official input API (`test.Tap`, `QTest::mouseClick`,
`gtk_test_widget_click`, `input.Router.Queue`, simulated input, or the immediate-mode
toolkit's event-injection entry points). Routing clicks through a hand-written registry that
bypasses the framework is prohibited: it tests the registry, not the interface.

---

## 6. Acceptance

A port is **complete** when, and only when, all of the following hold:

1. It builds from committed sources with a single documented command, from a clean checkout.
2. It produces a runnable GUI binary or entry point.
3. It passes all library-level tests (Categories 1–6 of the testing protocol).
4. It passes all GUI acceptance tests (Category 7) **executed against the built binary**.
5. Every functional requirement FR-1 through FR-9 is reachable through the application's own
   interface by a user with a mouse and keyboard.
6. Its capability matrix row in the comparison report is filled in from measured results, not
   from intent.

Partial completion is reported as a capability matrix, never as a test-count percentage. A
port with 100 % of its tests passing and no Open button is reported as **failing FR-2**, not
as "100 %".

### 6.1 Prohibited test patterns

The following do not constitute evidence and MUST NOT appear in any port's suite:

- Asserting that a fixed-size array member is non-null. It cannot be null.
- Asserting only that a constructor returned non-null, as the entirety of a UI test.
- Computing a value and discarding it without assertion (`_ = x`).
- Asserting that a freshly constructed empty buffer is empty.
- Any test whose name implies UI coverage but which never causes a widget to exist.

### 6.2 Reporting integrity

Test counts MUST NOT be used as a completeness measure. Two ports each passing 35 tests are
not equivalent if one can open files and the other cannot. The comparison report MUST lead
with the capability matrix; performance figures for a port that fails any of FR-1 through
FR-8 MUST be marked as measured against an incomplete implementation.

---

## 7. Internal architecture

Ports SHOULD organise code into four layers — **model**, **renderer**, **export**, **ui** —
to keep the comparison meaningful, since the first three should differ little between ports
and the fourth is what is actually being measured.

`structural_analysis.md` documents the intended shape of the first three layers and remains
useful for that purpose. It is advisory. **Conformance to it is not evidence of conformance
to this specification**, and the layer boundaries MUST NOT be used to argue that a port is
complete when its ui layer does not expose the functionality.

---

## 8. Reference hierarchy

```
FASTNOTE_SPECIFICATION.md   (this document — the actual authority)
        |
   go_gio                   (project reference implementation)
        |
        +-- c_nuklear       (C reference)   --> c_gtk4, c_raygui
        +-- rust_gtk4       (Rust reference) --> rust_egui, rust_slint
        +-- python_gtk4     (Python reference) --> python_pyqt6, python_pyside6, python_dearpygui
```

A downstream port MUST NOT be started until its reference passes acceptance. Downstream ports
match their reference's *behaviour*; they express it in their own toolkit's idiom rather than
imitating its structure.

`go_gio` is the reference because it is the most complete existing port with a live window
and a working editor. It is a reference for *behaviour*, not authority: it too is measured
against this document. It now satisfies FR-1 through FR-9 and passes all thirteen acceptance
tests, as does `go_fyne`.

---

## 9. Known deviations at time of writing

Recorded so that progress is measured against reality. **The previous edition of this table —
claiming pass everywhere — is withdrawn. It described trees that no longer exist.** Every
edition carries a seam-era tree (banned flags, no accelerators) until the repair lineage
(§8) and the keyboard-driven acceptance suite re-prove it. This table is repopulated from
measured results as each edition passes.

| Port | Seam-free §5.1 | Accelerators FR-11 | Event-file §5.1 | Keyboard acceptance | Current state |
|---|---|---|---|---|---|
| go_gio | no | not verified | not verified | pending | seam-era tree; reference behaviour |
| go_fyne | no | not verified | not verified | pending | seam-era tree |
| c_nuklear | yes | not verified | not verified | pending | 26/26 in-process GUI suite |
| c_gtk4 | yes | not verified | not verified | pending | 22/22 in-process GUI suite |
| c_raygui | no | no | no | pending | repair pending |
| rust_egui | no | not verified | not verified | pending | repair pending |
| rust_gtk4 | no | not verified | not verified | pending | repair pending |
| rust_slint | no | not verified | not verified | pending | repair pending |
| go_gtk4 | no | not verified | not verified | pending | repair pending |
| go_wails3 | no | not verified | not verified | pending | repair pending |
| python_gtk4 | no | not verified | not verified | pending | seam-era tree |
| python_pyqt6 | no | not verified | not verified | pending | seam-era tree |
| python_pyside6 | no | not verified | not verified | pending | seam-era tree |
| python_dearpygui | no | not verified | not verified | pending | seam-era tree |

FR-2 — opening an arbitrary file through the application's own interface — remains the test
that defines this project. It is not yet re-proven under the keyboard-driven protocol for any
port; that proof is the first criterion of the repair lineage.

## 10. Change log

- 2026-08-14: FR-11 added (standard keyboard accelerators Ctrl+O/S, Ctrl+Shift+S, Ctrl+E,
  Ctrl+Shift+E). §3.2 gains the browser keyboard contract (Ctrl+L, Enter, Escape). §5.1
  rewritten: exactly two permitted flags, `--version` and `--event-file` (a measurement-only
  completion trigger); all editing-path flags banned. §5.2 updated for the accelerator path.
  §9 reset: the all-pass table is withdrawn as describing trees that no longer exist; the
  table now records the audit state and is repopulated from measured results.
- 2026-08-11: §3.1 rewritten. Native dialogs are no longer banned. The only requirement is POSIX-compliant filesystem operations. Presentation layer is up to each port.
