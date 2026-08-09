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

The application MUST provide a visible **Save** control, and SHOULD bind it to the platform
save accelerator (`Ctrl+S`).

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

---

## 3. The File Browser component

FastNote requires file selection in three places (FR-2 Open, FR-6 Save As, FR-7/8 Export
destination). This is specified as a single reusable component.

### 3.1 Native dialogs are prohibited

Implementations MUST NOT use the host platform's native file dialog
(`GtkFileChooser`, `QFileDialog`, `rfd`, `tinyfiledialogs`, `gioui.org/x/explorer`, or
equivalent). The browser MUST be built from the port's own GUI toolkit primitives.

**Rationale.** This project exists to measure the cost of GUI technologies. A native dialog
imports an entire foreign toolkit into the process, distorting binary size and peak resident
memory — the exact quantities under measurement. If one port links `rfd` and another draws
its own list, the comparison measures dialog backends rather than the toolkits under test.

The secondary benefit is that the file browser is the single most informative component in
the whole comparison: implementing it exercises scrollable lists, dynamic layout, text input,
click handling, and keyboard focus simultaneously. It is a better benchmark than the editor.

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

## 5. The headless control seam

Every port MUST expose a command-line interface. This exists so that the acceptance suite in
§6 can drive all ports identically, without screenshot comparison or platform-specific UI
automation.

### 5.1 Required arguments

| Argument | Behaviour |
|---|---|
| `--open <path>` | Open `<path>` as the active document at startup |
| `--export <path>` | Export the active document to `<path>`; format inferred from extension |
| `--insert <text>` | Append `<text>` to the active document (drives the "edit" step) |
| `--save` | Save the active document to its current path |
| `--headless` | Execute the requested actions without creating a window, then exit |
| `--notes-dir <path>` | Override the notes directory |
| `--selftest` | Run the port's internal consistency checks, exit 0 on success |
| `--version` | Print port identifier and version, exit 0 |

Arguments MUST be processed in the order: `--open`, `--insert`, `--save`, `--export`.

Exit status MUST be 0 on success and non-zero on failure. A failure to open, save, or export
MUST produce a non-zero exit and a diagnostic on stderr.

### 5.2 The shared-path rule

**The CLI MUST invoke the same functions the GUI controls invoke.**

`--export` must call the identical code path as clicking the Export button. If the two are
implemented separately, the acceptance tests will pass while the button remains broken — this
is precisely how the previous test suite came to report success on non-functional software.

Reviewers should verify this by inspection: a GUI handler and a CLI handler that both contain
their own copy of the logic is a specification violation even if both work.

### 5.3 Headless mode

Under `--headless` a port MUST NOT require a display server. Application state, document
loading, editing, saving, rendering, and export MUST all function. Only window creation and
event loop entry are skipped.

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

Recorded so that progress is measured against reality.

| Port | FR-1 build | FR-2 open | FR-3 edit | FR-5 save | FR-7 export |
|---|---|---|---|---|---|
| go_gio | pass | pass | pass | pass | pass |
| go_fyne | pass | pass | pass | pass | pass |
| c_nuklear | pass | pass | pass | pass | pass |
| c_gtk4 | pass | pass | pass | pass | pass |
| c_raygui | pass | pass | pass | pass | pass |
| rust_egui | pass | pass | pass | pass | pass |
| rust_gtk4 | pass | pass | pass | pass | pass |
| rust_slint | pass | pass | pass | pass | pass |
| python ×4 | pass | pass | pass | pass | pass |

All twelve ports now satisfy FR-1 through FR-9 and pass all thirteen acceptance tests.
FR-2, the gap that defined this project for a month, is closed everywhere.
