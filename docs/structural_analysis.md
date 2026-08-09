# FastNotes Structural Analysis

> **SUPERSEDED 2026-08-07 — RETAINED FOR REFERENCE ONLY.**
>
> This document is a *library-API* analysis. It defines "canonical" structs, methods and
> functions, and says nothing about what the application must *do* for a user. It never
> mentions opening a file. Because it was treated as the specification, every port could
> satisfy it completely while remaining unusable — and did.
>
> The authoritative specification is now **`FASTNOTE_SPECIFICATION.md`**, which defines
> FastNote as observable user-facing behaviour. This file remains useful only as a record of
> internal API divergence between ports; where it conflicts with the specification, the
> specification wins.

## Overview

This document analyzes structural differences between all 5 FastNotes editions and proposes standardization. Goal: each component should be a "black box" with identical input/output contracts across all ports.

---

## 1. MODEL LAYER

### 1.1 Note Struct

| Field | Go/Fyne | Go/Gio | Rust/egui | Rust/Slint | Rust/GTK4 | Status |
|-------|---------|--------|-----------|------------|-----------|--------|
| path | string | string | String | String | String | IDENTICAL |
| folder | string | string | MISSING | MISSING | MISSING | DIVERGED |
| title | string | string | String | String | String | IDENTICAL |
| content | string | string | String | String | String | IDENTICAL |
| modified | time.Time | time.Time | MISSING | MISSING | MISSING | DIVERGED |
| dirty | bool | bool | bool | bool | bool | IDENTICAL |

**Issue:** Go has `folder` and `modified` fields. Rust does not.

**Fix:** Add `folder` and `modified` (timestamp) to Rust Note struct. Remove from Go to match Rust is worse -- Go's fields provide useful metadata. Standardize by adding to Rust.

### 1.2 Note Methods

| Method | Go | Rust | Status |
|--------|-----|------|--------|
| new(path) | ReadNote(path) -> (*Note, error) | Note::new(path) -> Self | DIVERGED |
| load(path) | ReadNote(path) -> (*Note, error) | Note::load(path) -> Result<Self, String> | IDENTICAL |
| save() | Note.Save() -> error | Note.save() -> Result<(), String> | IDENTICAL |
| title_with_dirty() | MISSING | Note.title_with_dirty() -> String | DIVERGED |

**Issue:** Go has `ReadNote` as a standalone function. Rust has both `Note::new` (empty note from path) and `Note::load` (read from disk). Go's `ReadNote` = Rust's `Note::load`.

**Fix:** Add `Note::new` equivalent to Go. Add `title_with_dirty()` to Go.

### 1.3 Folder Tree

| Field | Go (FolderInfo) | Rust (FolderNode) | Status |
|-------|-----------------|-------------------|--------|
| path | string | MISSING | DIVERGED |
| name | string | name: String | IDENTICAL |
| children | []FolderInfo | children: Vec<FolderNode> | IDENTICAL |
| note_count | int | notes: Vec<Note> | DIVERGED |
| expanded | bool | MISSING | DIVERGED |

**Issue:** Go counts notes per folder. Rust stores full Note objects in each folder node. Go has `expanded` UI state. Rust has `path`.

**Fix:** Standardize on: name, path, children, note_count (int). Remove `notes: Vec<Note>` from Rust (expensive, duplicates data). Add `path` to Go (already has it). Keep `expanded` as UI state, not model.

### 1.4 Search

| Function | Go | Rust | Status |
|----------|-----|------|--------|
| search_notes | SearchNotes(root, query) -> []SearchResult | search_notes(dir, query) -> Result<Vec<Note>, String> | DIVERGED |
| global_search | MISSING | GlobalSearch::new(dir).search(query) -> Vec<Note> | DIVERGED |

**Issue:** Go returns `SearchResult` (path, title, line, text snippet). Rust returns full `Note` objects. Go has no GlobalSearch wrapper.

**Fix:** Standardize on returning `[]SearchResult` with fields: path, title, line, text. Add GlobalSearch wrapper to Go.

### 1.5 Settings

| Field | Go (17 fields) | Rust (10 fields) | Status |
|-------|----------------|------------------|--------|
| notes_dir | string | String | IDENTICAL |
| theme | string | String | IDENTICAL |
| sidebar_width | int | f32 | DIVERGED (type) |
| split_offset | int | MISSING | DIVERGED |
| font_size | int | f32 | DIVERGED (type) |
| show_line_nums | bool | bool | IDENTICAL |
| auto_save | bool | bool | IDENTICAL |
| auto_save_delay | int | u64 | DIVERGED (type) |
| sync_scroll | bool | MISSING | DIVERGED |
| show_preview | bool | MISSING | DIVERGED |
| show_sidebar | bool | MISSING | DIVERGED |
| custom_css | string | String | IDENTICAL |
| last_window_w | int | MISSING | DIVERGED |
| last_window_h | int | MISSING | DIVERGED |
| editor_tab_width | int | usize | DIVERGED (type) |
| wrap_text | bool | bool | IDENTICAL |

**Issue:** Go has 17 fields. Rust has 10. Rust is missing: split_offset, sync_scroll, show_preview, show_sidebar, last_window_w, last_window_h. Types differ for numeric fields.

**Fix:** Standardize on the 10-field Rust set as minimum. Add the 7 missing Go fields to Rust. Standardize types: sidebar_width=int, font_size=int, auto_save_delay=int, editor_tab_width=int.

### 1.6 Model Standardization Plan

**Canonical Note struct:**
```
path: string
folder: string
title: string
content: string
modified: timestamp
dirty: bool
```

**Canonical methods:**
- `new(path) -> Note` -- create empty note from path
- `load(path) -> (Note, error)` -- read from disk
- `save() -> error` -- write to disk, clear dirty
- `title_with_dirty() -> string` -- title with "*" suffix if dirty

**Canonical FolderNode:**
```
name: string
path: string
children: []FolderNode
note_count: int
```

**Canonical Search:**
- `search_notes(dir, query) -> []SearchResult`
- `SearchResult: {path, title, line, text}`
- `GlobalSearch.new(dir).search(query) -> []SearchResult`

**Canonical Settings (17 fields, int types):**
```
notes_dir, theme, sidebar_width, split_offset, font_size,
show_line_nums, auto_save, auto_save_delay, sync_scroll,
show_preview, show_sidebar, custom_css, last_window_w,
last_window_h, editor_tab_width, wrap_text
```

---

## 2. RENDERER LAYER

### 2.1 Core Renderer

| Aspect | Go (goldmark) | Rust (pulldown-cmark) | Status |
|--------|---------------|----------------------|--------|
| Library | goldmark + extensions | pulldown-cmark | DIVERGED |
| Syntax highlighting | Chroma (github/dracula themes) | MISSING | DIVERGED |
| CSS sanitization | sanitizeCSS() | html_escape() | DIVERGED |
| Dark mode | gmLight/gmDark instances | base_css("dark"/"light") | DIVERGED |
| Extensions | GFM, Typographer, Meta, Highlighting | Tables, Strikethrough, Footnotes, Tasklists, HeadingAttrs | DIVERGED |

**Issue:** Go uses goldmark with Chroma syntax highlighting. Rust uses pulldown-cmark without syntax highlighting. Go sanitizes CSS. Rust escapes HTML.

**Fix:** Add syntax highlighting to Rust (syntect crate). Add CSS sanitization to Rust. Standardize extension support.

### 2.2 Advanced Renderer

| Function | Go | Rust | Status |
|----------|-----|------|--------|
| GenerateTOC | GenerateTOC(md) -> []TableOfEntry | generate_toc(md) -> Vec<TOCEntry> | IDENTICAL |
| RenderTOCAsHTML | RenderTOCAsHTML(md) -> string | render_toc_as_html(md) -> string | IDENTICAL |
| ProcessWikiLinks | ProcessWikiLinks(md, paths) -> string | process_wiki_links(md, paths) -> string | IDENTICAL |
| ProcessCheckboxes | ProcessCheckboxes(md) -> string | process_checkboxes(md) -> string | IDENTICAL |
| BuildNoteIndex | BuildNoteIndex(paths) -> map[string]string | build_note_index(paths) -> HashMap | IDENTICAL |
| RenderMath | RenderMath(md) -> string | render_math(md) -> string | IDENTICAL |
| headingToID | headingToID(title) -> string | MISSING | DIVERGED |

**Issue:** Go has `headingToID` helper. Rust generates IDs inline. Otherwise identical functionality.

**Fix:** Add `heading_to_id` to Rust. Already functionally equivalent.

### 2.3 TOC Entry Struct

| Field | Go (TableOfEntry) | Rust (TOCEntry) | Status |
|-------|-------------------|-----------------|--------|
| level | int | u8 | DIVERGED (type) |
| title | string | String | IDENTICAL |
| id | string | MISSING | DIVERGED |

**Issue:** Go TOC entries have an `id` field (HTML anchor). Rust does not.

**Fix:** Add `id: String` to Rust TOCEntry. Change level to int in both.

### 2.4 Renderer Standardization Plan

**Canonical functions:**
- `render(md, dark_mode) -> string`
- `render_to_full_html(md, title, dark_mode, custom_css) -> string`
- `generate_toc(md) -> []TOCEntry`
- `render_toc_as_html(md) -> string`
- `process_wiki_links(md, paths) -> string`
- `process_checkboxes(md) -> string`
- `render_math(md) -> string`
- `build_note_index(paths) -> map[string]string`
- `syntax_highlight(code, lang, dark_mode) -> string`
- `heading_to_id(title) -> string`
- `sanitize_css(css) -> string`

**Canonical TOCEntry:**
```
level: int
title: string
id: string
```

---

## 3. EXPORT LAYER

### 3.1 Exporters

| Aspect | Go | Rust | Status |
|--------|-----|------|--------|
| HTMLExporter | HTMLExporter with customCSS | MISSING | DIVERGED |
| PDFExporter | PDFExporter (wkhtmltopdf/chrome) | MISSING | DIVERGED |
| ExportManager | ExportManager with format routing | MISSING | DIVERGED |
| HTML template | text/template with color vars | format!() string interpolation | DIVERGED |
| CSS sanitization | sanitizeCSS() | html_escape() only | DIVERGED |

**Issue:** Go has full export layer (HTML, PDF, Manager). Rust has NO export layer -- it uses `render_to_full_html` directly.

**Fix:** Add HTMLExporter, PDFExporter, ExportManager to Rust. Use same template approach.

### 3.2 Export Standardization Plan

**Canonical types:**
- `HTMLExporter { custom_css: string }`
  - `NewHTMLExporter() -> HTMLExporter`
  - `SetCustomCSS(css)`
  - `Export(md, title, dark_mode) -> string`
  - `SaveToFile(md, title, path, dark_mode) -> error`
- `PDFExporter { custom_css: string }`
  - `NewPDFExporter() -> PDFExporter`
  - `SetCustomCSS(css)`
  - `Export(md, title, dark_mode) -> ([]byte, error)`
  - `SaveToFile(md, title, path, dark_mode) -> error`
- `ExportManager { html_exporter, pdf_exporter }`
  - `NewExportManager() -> ExportManager`
  - `ExportNote(content, title, format, dark_mode) -> ([]byte, error)`
  - `SetCustomCSS(css)`
- `CheckPDFSupport() -> string`

---

## 4. UI LAYER

### 4.1 App Structure

| Component | Go/Fyne | Go/Gio | Rust/egui | Rust/Slint | Rust/GTK4 | Status |
|-----------|---------|--------|-----------|------------|-----------|--------|
| Main struct | FastNotes | FastNotes | App | FastNotesApp | App | DIVERGED |
| Sidebar | ui.Sidebar | app.Sidebar | egui sidebar | Slint ListView | GTK Sidebar | DIVERGED |
| Editor | ui.Editor | app.Editor | egui text_edit | Slint TextInput | GTK TextView | DIVERGED |
| Preview | ui.Preview | app.Preview | egui label | Slint TextEdit | GTK TextView | DIVERGED |
| Toolbar | ui.Toolbar | inline buttons | egui top bar | Slint buttons | GTK menu bar | DIVERGED |
| Search | ui.SearchBar | app.SearchBar | egui search | MISSING | GTK search | DIVERGED |
| Settings | ui.SettingsDialog | MISSING | egui dialog | MISSING | GTK dialog | DIVERGED |

**Issue:** UI components are framework-specific by nature. However, the COMPONENT API should be standardized.

### 4.2 Editor Component

| Method | Go/Fyne | Go/Gio | Rust/egui | Rust/Slint | Rust/GTK4 | Status |
|--------|---------|--------|-----------|------------|-----------|--------|
| New(settings) | NewEditor(settings) | NewEditor(settings) | N/A | N/A | N/A | DIVERGED |
| OpenNote(note) | editor.OpenNote(note) | editor.OpenNote(note) | N/A | N/A | N/A | DIVERGED |
| Save() | editor.Save() | editor.Save() | N/A | N/A | N/A | DIVERGED |
| GetText() | editor.GetText() | editor.GetText() | N/A | N/A | N/A | DIVERGED |
| SetText(text) | MISSING | editor.SetText(text) | N/A | N/A | N/A | DIVERGED |
| InsertText(text) | editor.InsertText(text) | editor.InsertText(text) | N/A | N/A | N/A | DIVERGED |
| WrapSelection(p,s) | editor.WrapSelection(p,s) | editor.WrapSelection(p,s) | N/A | N/A | N/A | DIVERGED |
| FindAndReplace(f,r,all) | editor.FindAndReplace(f,r,all) | editor.FindAndReplace(f,r,all) | N/A | N/A | N/A | DIVERGED |
| FindNext(find) | editor.FindNext(find) | MISSING | N/A | N/A | N/A | DIVERGED |
| CurrentNote() | editor.CurrentNote() | MISSING | N/A | N/A | N/A | DIVERGED |
| Line numbers | Yes (widget.List) | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| Status bar | Yes (Ln, Col, chars) | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| Auto-save | Yes (timer) | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| Syntax highlighting | ui.SyntaxHighlighter | MISSING | MISSING | MISSING | MISSING | DIVERGED |

**Issue:** Go/Fyne has full-featured Editor (line numbers, status bar, auto-save, syntax highlighting, find/replace, find next). Go/Gio has basic Editor. Rust ports have NO editor component -- editing is handled inline in main.rs.

**Fix:** Extract editor component from Rust main.rs files. Add basic line numbers and status bar. Add auto-save timer.

### 4.3 Preview Component

| Method | Go/Fyne | Go/Gio | Rust/egui | Rust/Slint | Rust/GTK4 | Status |
|--------|---------|--------|-----------|------------|-----------|--------|
| New(dark_mode) | NewPreview(dark) | NewPreview() | N/A | N/A | N/A | DIVERGED |
| Update(md, title) | preview.Update(md, title) | preview.Update(md) | N/A | N/A | N/A | DIVERGED |
| SetDarkMode(dark) | preview.SetDarkMode(dark) | MISSING | MISSING | MISSING | MISSING | DIVERGED |

**Issue:** Go/Fyne preview takes title parameter. Go/Gio does not. Rust ports have no separate preview component.

**Fix:** Standardize on `Update(md, title)`. Add `SetDarkMode(dark)`. Extract from Rust main.rs.

### 4.4 App Component

| Method | Go/Fyne | Go/Gio | Rust/egui | Rust/Slint | Rust/GTK4 | Status |
|--------|---------|--------|-----------|------------|-----------|--------|
| New(notesDir) | New(notesDir) | New(notesDir) | N/A | N/A | N/A | DIVERGED |
| onNoteSelect(note) | a.onNoteSelect(note) | callback in sidebar | N/A | N/A | N/A | DIVERGED |
| updatePreview() | a.updatePreview() | inline | N/A | N/A | N/A | DIVERGED |
| onNewNote() | a.onNewNote() | fa.createNewNote() | N/A | N/A | N/A | DIVERGED |
| onNewFolder() | a.onNewFolder() | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| onDelete() | a.onDelete() | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| toggleSidebar() | a.toggleSidebar() | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| togglePreview() | a.togglePreview() | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| toggleTheme() | a.toggleTheme() | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| exportHTML() | a.exportHTML() | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| showSearch() | a.showSearch() | MISSING | MISSING | MISSING | MISSING | DIVERGED |

**Issue:** Go/Fyne has full app with folder creation, note deletion, sidebar toggle, preview toggle, theme toggle, export, search. Go/Gio has basic new note. Rust ports have minimal app shells.

**Fix:** Add missing features to all ports. Standardize on Go/Fyne feature set.

---

## 5. BENCHMARK LAYER

### 5.1 Benchmarks

| Benchmark | Go/Fyne | Go/Gio | Rust/egui | Rust/Slint | Rust/GTK4 | Status |
|-----------|---------|--------|-----------|------------|-----------|--------|
| NoteCreate | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| NoteSave | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| NoteLoad | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| NoteDelete | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| RenderMarkdown | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| RenderLargeNote | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| ExportHTML | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| FolderTree | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| WikiLinks | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| Checkboxes | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| Math | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| GlobalSearch | Yes | Yes | Yes | Yes | Yes | IDENTICAL |
| AppCreate | Yes | Yes | MISSING | MISSING | MISSING | DIVERGED |
| LayoutPass | Yes | Yes | MISSING | MISSING | MISSING | DIVERGED |
| WidgetCreate | Yes | Yes | MISSING | MISSING | MISSING | DIVERGED |
| EditorFind | Yes | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| PreviewRender | Yes | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| SettingsSave | Yes | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| TOCGenerate | Yes | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| WikiLinkProcess | Yes | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| CheckboxProcess | Yes | MISSING | MISSING | MISSING | MISSING | DIVERGED |
| MathRender | Yes | MISSING | MISSING | MISSING | MISSING | DIVERGED |

**Issue:** Go/Fyne has 22 benchmarks. Go/Gio has 6. Rust ports have 12 (library-only). Go/Fyne has UI benchmarks (AppCreate, LayoutPass, WidgetCreate, EditorFind, PreviewRender, SettingsSave, TOCGenerate, WikiLinkProcess, CheckboxProcess, MathRender).

**Fix:** Add UI benchmarks to all ports. Standardize on the 22-benchmark Go/Fyne set.

---

## 6. STANDARDIZATION ROADMAP

### Phase 1: Model (highest priority, shared across all ports)
1. Add `folder` and `modified` fields to Rust Note struct
2. Add `title_with_dirty()` method to Go model
3. Standardize FolderNode: add `path`, remove `notes: Vec<Note>`, add `note_count`
4. Add `SearchResult` struct to Rust (path, title, line, text)
5. Add `GlobalSearch` wrapper to Go model
6. Add 7 missing Settings fields to Rust
7. Standardize numeric types in Settings (all int)

### Phase 2: Renderer
1. Add syntax highlighting to Rust (syntect crate)
2. Add CSS sanitization to Rust
3. Add `id` field to Rust TOCEntry
4. Add `heading_to_id` function to Rust
5. Ensure both use same CSS base (light/dark themes)

### Phase 3: Export
1. Add HTMLExporter to Rust
2. Add PDFExporter to Rust
3. Add ExportManager to Rust
4. Add CheckPDFSupport to Rust

### Phase 4: UI Components
1. Extract Editor component from Rust main.rs files
2. Add line numbers, status bar, auto-save to all editors
3. Extract Preview component from Rust main.rs files
4. Add onNewFolder, onDelete, toggleSidebar, togglePreview, toggleTheme, exportHTML, showSearch to all ports

### Phase 5: Benchmarks
1. Add UI benchmarks to Rust ports (AppCreate, LayoutPass, WidgetCreate, etc.)
2. Add missing benchmarks to Go/Gio (EditorFind, PreviewRender, SettingsSave, etc.)
3. Standardize input sizes across all ports

### Phase 6: Tests
1. Normalize all ports to 35 canonical tests (per testing protocol)
2. Ensure identical assertions across ports
3. Remove framework-specific tests (screenshots, PDF)

---

## 7. CURRENT DIVERGENCE SUMMARY

| Component | Go/Fyne | Go/Gio | Rust/egui | Rust/Slint | Rust/GTK4 |
|-----------|---------|--------|-----------|------------|-----------|
| Model fields | 6+17 | 6+17 | 4+10 | 4+10 | 4+10 |
| Renderer features | goldmark+chroma | goldmark+chroma | pulldown-cmark | pulldown-cmark | pulldown-cmark |
| Export layer | HTML+PDF+Manager | HTML+PDF+Manager | render_to_full_html only | render_to_full_html only | render_to_full_html only |
| UI components | 8 (Sidebar,Editor,Preview,Toolbar,Search,Settings,Syntax,Theme) | 5 (Sidebar,Editor,Preview,SearchBar,App) | inline in main.rs | inline in main.rs+ui.slint | inline in main.rs |
| Tests | 31 | 35 | 31 | 31 | 31 |
| Benchmarks | 22 | 6 | 12 | 12 | 12 |

**Total divergence points: 47**
