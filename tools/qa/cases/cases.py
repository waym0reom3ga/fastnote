"""The QA cases, A01..A14. Every GUI case works on the edition's real binary,
its real window, real keyboard input, and real files on disk. No headless mode
is ever used; no per-edition test code is consulted. The edition publishes
phase completions through --event-file (spec 5.1) and is driven with the
standard accelerators (spec FR-11) and the browser keyboard contract (spec
3.2)."""

import os
import subprocess
import time

from fastnote_qa import core
from fastnote_qa import inspection
from fastnote_qa import fixtures
from fastnote_qa import x11
from fastnote_qa.gui import GuiSession, EVENT_OPEN, EVENT_SAVE, EVENT_SAVE_AS, \
    EVENT_EXPORT_HTML, EVENT_EXPORT_PDF
from fastnote_qa.validators import validate_html, validate_pdf


def _launch(ctx, event_file=False):
    sess = GuiSession(ctx.edition, ctx.work, ctx.work / "notes")
    return sess.start(event_file=event_file)


def _teardown(ctx, sess, logname="app.log"):
    out = sess.stop()
    if out:
        ctx.log(logname, out)


def _ready(ctx, sess):
    """Wait for the window, then the first painted frame marker."""
    if not sess.wait_window():
        return False, "no window appeared"
    if not sess.wait_ready(timeout=20):
        return False, "edition never reported the 'painted' marker"
    return True, ""


def _open_file(ctx, sess, path, timeout=20):
    """Ctrl+O, Ctrl+L, type the path, Enter, wait for the open marker."""
    sess.open_path(path)
    if not sess.wait_event(EVENT_OPEN, timeout=timeout):
        return False, "open marker never arrived (file did not load)"
    return True, ""


def _edit_dirty(ctx, sess, marker=fixtures.MARKER, timeout=8):
    """Type the marker; require the dirty marker in the title. Keystrokes are
    delivered to whatever has focus; an edition that does not focus its editor
    after opening a document fails here, as a user would notice."""
    x11.type_text(marker)
    if sess.wait_title_contains("*", timeout=timeout):
        return True, ""
    return False, "dirty marker never appeared in the title"


def _export(ctx, sess, accel, marker, filename, validator, out):
    """Press the export accelerator, type the destination path, confirm; wait
    for the phase marker; validate the real artifact on disk."""
    sess.press(accel)
    sess.press("ctrl+l")
    x11.type_text(str(out))
    time.sleep(0.3)
    sess.press("Return", settle=0)
    if not sess.wait_event(marker, timeout=20):
        return core.fail(f"{marker} marker never arrived; no export completed")
    if not out.exists():
        return core.fail(f"no file written to {out}")
    ok, detail = validator(out)
    if not ok:
        return core.fail(detail)
    ctx.copy_artifact(out)
    return core.ok(detail)


# ---------------------------------------------------------------------------

def a01_launch(ctx):
    """FR-1: build (by suite), launch bare, a real window appears, closes
    cleanly with exit 0."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.build_ok:
        return core.fail("binary missing or build failed")
    sess = _launch(ctx)
    try:
        if not sess.wait_window():
            ctx.log("app.log", sess.proc.stdout.read().decode(errors="replace")
                    if sess.proc.stdout else "")
            return core.fail("no window appeared")
        if not sess.close_via_wm(wait=8):
            return core.fail("window did not close on WM close request")
        rc = sess.proc.returncode
        if rc != 0:
            return core.fail(f"exit status {rc} on normal close (expected 0)")
        return core.ok()
    finally:
        _teardown(ctx, sess)


def a02_version(ctx):
    """A real --version run: exit 0, prints the port identifier, and the
    argument parser is real (unknown flags fail)."""
    binpath = ctx.edition["path"] / ctx.edition["binary"]
    if not binpath.exists():
        return core.fail("binary missing")
    try:
        r = subprocess.run([str(binpath), "--version"], capture_output=True,
                           text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return core.fail("--version hung")
    if r.returncode != 0:
        return core.fail(f"--version exited {r.returncode}")
    if not r.stdout.strip():
        return core.fail("--version printed nothing")
    import re as _re
    if _re.search(r'unknown|unrecognized|invalid option|usage:', r.stdout, _re.I):
        return core.fail(f"--version not supported: {r.stdout.strip()[:60]!r}")
    probe = subprocess.run([str(binpath), "--fnprobe-xyzzy-should-not-exist"],
                           capture_output=True, text=True, timeout=15)
    if probe.returncode == 0:
        return core.fail("CLI ignores unknown flags and exits 0")
    return core.ok(r.stdout.strip().splitlines()[0][:60])


def a03_open(ctx):
    """FR-2: open an arbitrary file — one the app did not know about, outside
    the notes directory — through the real browser, by keyboard."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.build_ok:
        return core.fail("binary missing or build failed")
    if not ctx.edition["event"]:
        return core.partial("edition does not publish --event-file yet")
    sess = _launch(ctx, event_file=True)
    try:
        ok, detail = _ready(ctx, sess)
        if not ok:
            return core.fail(detail)
        far = ctx.work / "outside" / "far_away_document.md"
        ok, detail = _open_file(ctx, sess, far)
        if not ok:
            return core.fail(detail)
        if not sess.wait_title_contains("far_away_document", timeout=8):
            return core.fail("document name never appeared in the title")
        return core.ok("opened a file the app had not listed")
    finally:
        _teardown(ctx, sess)


def a04_edit(ctx):
    """FR-3: keystrokes reach the document (dirty marker appears) and do not
    leak to disk without a save."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.edition["event"]:
        return core.partial("edition does not publish --event-file yet")
    sess = _launch(ctx, event_file=True)
    try:
        ok, detail = _ready(ctx, sess)
        if not ok:
            return core.fail(detail)
        doc = ctx.work / "notes" / "doc.md"
        ok, detail = _open_file(ctx, sess, doc)
        if not ok:
            return core.fail(detail)
        import hashlib
        h0 = hashlib.md5(doc.read_bytes()).hexdigest()
        ok, detail = _edit_dirty(ctx, sess)
        if not ok:
            return core.fail(detail)
        if hashlib.md5(doc.read_bytes()).hexdigest() != h0:
            return core.fail("edit reached disk without a save")
        return core.ok()
    finally:
        _teardown(ctx, sess)


def a05_save(ctx):
    """FR-5: Ctrl+S writes the editor contents to disk, byte for byte."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.edition["event"]:
        return core.partial("edition does not publish --event-file yet")
    sess = _launch(ctx, event_file=True)
    try:
        ok, detail = _ready(ctx, sess)
        if not ok:
            return core.fail(detail)
        doc = ctx.work / "notes" / "doc.md"
        ok, detail = _open_file(ctx, sess, doc)
        if not ok:
            return core.fail(detail)
        ok, detail = _edit_dirty(ctx, sess)
        if not ok:
            return core.fail(detail)
        sess.press("ctrl+s")
        if not sess.wait_event(EVENT_SAVE, timeout=15):
            return core.fail("save marker never arrived")
        if fixtures.MARKER not in doc.read_text():
            return core.fail("marker absent from saved file")
        return core.ok()
    finally:
        _teardown(ctx, sess)


def a06_save_as(ctx):
    """FR-6: Save As to a new path becomes the document's path."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.edition["event"]:
        return core.partial("edition does not publish --event-file yet")
    sess = _launch(ctx, event_file=True)
    try:
        ok, detail = _ready(ctx, sess)
        if not ok:
            return core.fail(detail)
        doc = ctx.work / "notes" / "doc.md"
        ok, detail = _open_file(ctx, sess, doc)
        if not ok:
            return core.fail(detail)
        ok, detail = _edit_dirty(ctx, sess)
        if not ok:
            return core.fail(detail)
        new_path = ctx.work / "outside" / "renamed.md"
        sess.press("ctrl+shift+s")
        sess.press("ctrl+l")
        x11.type_text(str(new_path))
        time.sleep(0.3)
        sess.press("Return", settle=0)
        if not sess.wait_event(EVENT_SAVE_AS, timeout=15):
            return core.fail("save-as marker never arrived")
        if not new_path.exists():
            return core.fail("file never appeared at the new path")
        if fixtures.MARKER not in new_path.read_text():
            return core.fail("marker absent from the saved-as file")
        if not sess.wait_title_contains("renamed.md", timeout=8):
            return core.fail("title never adopted the new path")
        return core.ok()
    finally:
        _teardown(ctx, sess)


def a07_export_html(ctx):
    """FR-7: a real, standalone HTML document appears on disk and parses."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.edition["event"]:
        return core.partial("edition does not publish --event-file yet")
    sess = _launch(ctx, event_file=True)
    try:
        ok, detail = _ready(ctx, sess)
        if not ok:
            return core.fail(detail)
        far = ctx.work / "outside" / "far_away_document.md"
        ok, detail = _open_file(ctx, sess, far)
        if not ok:
            return core.fail(detail)
        out = ctx.work / "outside" / "out.html"
        return _export(ctx, sess, "ctrl+e", EVENT_EXPORT_HTML, "out.html",
                       lambda p: validate_html(p, fixtures.FAR_CONTENT), out)
    finally:
        _teardown(ctx, sess)


def a08_export_pdf(ctx):
    """FR-8: a real, structurally valid PDF appears on disk."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.edition["event"]:
        return core.partial("edition does not publish --event-file yet")
    sess = _launch(ctx, event_file=True)
    try:
        ok, detail = _ready(ctx, sess)
        if not ok:
            return core.fail(detail)
        far = ctx.work / "outside" / "far_away_document.md"
        ok, detail = _open_file(ctx, sess, far)
        if not ok:
            return core.fail(detail)
        out = ctx.work / "outside" / "out.pdf"
        return _export(ctx, sess, "ctrl+shift+e", EVENT_EXPORT_PDF, "out.pdf",
                       lambda p: validate_pdf(p)[:2], out)
    finally:
        _teardown(ctx, sess)


def a09_e2e(ctx):
    """The product test: open -> edit -> save -> export HTML and PDF, all
    through the real interface, all verified on disk."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.edition["event"]:
        return core.partial("edition does not publish --event-file yet")
    sess = _launch(ctx, event_file=True)
    try:
        ok, detail = _ready(ctx, sess)
        if not ok:
            return core.fail(detail)
        far = ctx.work / "outside" / "far_away_document.md"
        ok, detail = _open_file(ctx, sess, far)
        if not ok:
            return core.fail(f"open step: {detail}")
        ok, detail = _edit_dirty(ctx, sess)
        if not ok:
            return core.fail(f"edit step: {detail}")
        sess.press("ctrl+s")
        if not sess.wait_event(EVENT_SAVE, timeout=15):
            return core.fail("save marker never arrived")
        if fixtures.MARKER not in far.read_text():
            return core.fail("save step: marker not on disk")
        html_out = ctx.work / "outside" / "e2e.html"
        pdf_out = ctx.work / "outside" / "e2e.pdf"
        r = _export(ctx, sess, "ctrl+e", EVENT_EXPORT_HTML, "e2e.html",
                    lambda p: validate_html(p, fixtures.MARKER), html_out)
        if r.status != core.PASS:
            return r
        r = _export(ctx, sess, "ctrl+shift+e", EVENT_EXPORT_PDF, "e2e.pdf",
                    lambda p: validate_pdf(p)[:2], pdf_out)
        if r.status != core.PASS:
            return r
        return core.ok("open -> edit -> save -> export html+pdf, all verified on disk")
    finally:
        _teardown(ctx, sess)


def _static(ctx, wanted):
    if not ctx.build_ok:
        return core.fail("binary missing")
    checks, files = inspection.check_wiring(ctx.edition["path"], ctx.edition["name"])
    if not files:
        return core.skip("no UI sources matched")
    failed = [(k, v) for k, (ok_, v) in checks.items() if k in wanted and not ok_]
    if failed:
        return core.fail("; ".join(f"{k}: {v}" for k, v in failed))
    return core.ok()


def a10_open_wiring(ctx):
    """Open control exists, is bound, has the Ctrl+O accelerator, and the
    event-file publication exists (spec 5.1/5.2)."""
    return _static(ctx, {"open_control", "open_bound", "accel_open", "event_file"})


def a11_export_wiring(ctx):
    """Export control exists, is bound, reaches a filesystem write, has the
    Ctrl+E / Ctrl+Shift+E accelerators, and publishes event markers."""
    return _static(ctx, {"export_control", "export_bound", "export_writes",
                         "accel_export", "accel_export_pdf", "event_file",
                         "event_markers"})


def a12_browser(ctx):
    """A file-selection mechanism exists (in-app over POSIX ops, or native)
    with the keyboard path-entry contract (spec 3.2)."""
    return _static(ctx, {"browser", "browser_policy", "keyboard_contract",
                         "accel_focus_path"})


def a13_close_dirty(ctx):
    """FR-9: closing with a dirty document must not silently lose work."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.edition["event"]:
        return core.partial("edition does not publish --event-file yet")
    sess = _launch(ctx, event_file=True)
    doc = ctx.work / "notes" / "doc.md"
    try:
        ok, detail = _ready(ctx, sess)
        if not ok:
            return core.fail(detail)
        ok, detail = _open_file(ctx, sess, doc)
        if not ok:
            return core.fail(f"could not open document: {detail}")
        ok, detail = _edit_dirty(ctx, sess)
        if not ok:
            return core.fail(f"could not establish dirty state: {detail}")
        before = doc.read_text()
        x11.close_window(sess.wid)
        time.sleep(1.5)
        still_open = x11.find_window(ctx.edition["title"], timeout=2) is not None
        if still_open:
            return core.ok("close request answered with a prompt (window still open)")
        if doc.read_text() != before:
            return core.ok("dirty document was saved on close")
        return core.fail("window closed and the dirty edit was silently discarded")
    finally:
        _teardown(ctx, sess)


def a14_sabotage(ctx):
    """A12 enforcement (protocol, sabotage validation): the edition's GUI
    event suite must pass as shipped and fail under FASTNOTE_SABOTAGE=1."""
    if not ctx.display_ok:
        return core.skip("no display")
    cmd = ctx.edition.get("suite") or ""
    if not cmd:
        return core.skip("edition declares no GUI event suite")
    try:
        r = subprocess.run(["bash", "-lc", cmd], cwd=ctx.edition["path"],
                           capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return core.fail("GUI event suite hung as shipped")
    if r.returncode != 0:
        return core.fail(f"GUI event suite failed as shipped (rc {r.returncode})")
    env = dict(os.environ)
    env["FASTNOTE_SABOTAGE"] = "1"
    try:
        rs = subprocess.run(["bash", "-lc", cmd], cwd=ctx.edition["path"],
                            env=env, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return core.fail("GUI event suite hung under sabotage")
    if rs.returncode == 0:
        return core.fail("GUI event suite passed with a control unbound — it tests nothing")
    return core.ok("suite passes as shipped and fails under sabotage")


def all_cases():
    return [
        ("a01", a01_launch),
        ("a02", a02_version),
        ("a03", a03_open),
        ("a04", a04_edit),
        ("a05", a05_save),
        ("a06", a06_save_as),
        ("a07", a07_export_html),
        ("a08", a08_export_pdf),
        ("a09", a09_e2e),
        ("a10", a10_open_wiring),
        ("a11", a11_export_wiring),
        ("a12", a12_browser),
        ("a13", a13_close_dirty),
        ("a14", a14_sabotage),
    ]
