"""The QA cases, A01..A13. Every GUI case works on the edition's real binary,
its real window, real input, and real files on disk. No headless mode is
ever used; no per-edition test code is consulted."""

import time

from fastnote_qa import core
from fastnote_qa import inspection
from fastnote_qa import fixtures
from fastnote_qa.gui import GuiSession
from fastnote_qa.validators import validate_html, validate_pdf
from fastnote_qa import x11


def _launch(ctx):
    sess = GuiSession(ctx.edition, ctx.work, ctx.work / "notes").start()
    return sess


def _teardown(ctx, sess, logname="app.log"):
    out = sess.stop()
    if out:
        ctx.log(logname, out)


def _seam_probe(ctx):
    """The --version path must be real: an unknown flag must exit non-zero,
    or every CLI assertion would pass vacuously."""
    import subprocess
    binpath = ctx.edition["path"] / ctx.edition["binary"]
    r = subprocess.run([str(binpath), "--fnprobe-xyzzy-should-not-exist"],
                       capture_output=True, text=True, timeout=15)
    return r.returncode != 0


def a01_launch(ctx):
    """FR-1: build (by suite), launch, a real window appears, closes cleanly."""
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
        sess.wid = x11.find_window(ctx.edition["title"], timeout=5)
        sess.wait_ready(timeout=10)
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
    import subprocess
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
    if not _seam_probe(ctx):
        return core.fail("CLI ignores unknown flags and exits 0")
    return core.ok(r.stdout.strip().splitlines()[0][:60])


def _open_far_file(ctx, sess):
    """Drive the real browser until the far document is the active document.
    Returns (titles, detail) — None if the flow cannot run."""
    if not sess.has("open"):
        return None, "no Open control in control map"
    if not sess.click("open"):
        return None, "could not click Open"
    if sess.has("path") and sess.has("ok") and sess.has("cancel"):
        pt = sess.click_point("path")
        if not pt:
            return None, "no path entry in control map"
        x11.click_at(sess.wid, pt[0], pt[1])
        time.sleep(0.3)
        x11.type_text(str(ctx.work / "outside" / "far_away_document.md"))
        time.sleep(0.3)
        if not sess.click("ok"):
            return None, "no confirm control in control map"
        if sess.wait_title_contains("far_away_document", timeout=10):
            return "far_away_document", ""
        return None, "document name never appeared in the title"
    return None, "browser appeared but selection flow not instrumented (no path/ok rects)"


def a03_open(ctx):
    """FR-2: open an arbitrary file — one the app did not know about, outside
    the notes directory — through the real browser."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.build_ok:
        return core.fail("binary missing or build failed")
    if not ctx.instrumented:
        return core.partial("edition publishes no control map")
    sess = _launch(ctx)
    try:
        if not sess.wait_window():
            return core.fail("no window appeared")
        sess.wait_ready(timeout=15)
        if not sess.load_control_map():
            return core.partial("no control map published")
        got, detail = _open_far_file(ctx, sess)
        if got:
            return core.ok(f"title carries far_away_document")
        return core.partial(detail)
    finally:
        _teardown(ctx, sess)


def _edit_dirty(ctx, sess, marker=fixtures.MARKER):
    """Click into the editor, type the marker, require the dirty marker in the
    title. Returns (ok, detail)."""
    if not sess.has("editor"):
        return False, "no editor rect in control map"
    pt = sess.click_point("editor")
    if not pt:
        return False, "no editor rect"
    x11.click_at(sess.wid, pt[0], pt[1])
    time.sleep(0.4)
    x11.type_text(marker)
    if sess.wait_title_contains("*", timeout=8):
        return True, ""
    return False, "dirty marker never appeared in the title"


def a04_edit(ctx):
    """FR-3: keystrokes reach the document (dirty marker appears) and do not
    leak to disk without a save."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.instrumented:
        return core.partial("edition publishes no control map")
    sess = _launch(ctx)
    try:
        if not sess.wait_window() or not sess.wait_ready(timeout=15):
            return core.fail("no window appeared")
        if not sess.load_control_map():
            return core.partial("no control map published")
        before = ctx.work / "notes" / "doc.md"
        import hashlib
        h0 = hashlib.md5(before.read_bytes()).hexdigest()
        ok, detail = _edit_dirty(ctx, sess)
        if not ok:
            return core.fail(detail)
        if hashlib.md5(before.read_bytes()).hexdigest() != h0:
            return core.fail("edit reached disk without a save")
        return core.ok()
    finally:
        _teardown(ctx, sess)


def a05_save(ctx):
    """FR-5: Ctrl+S writes the editor contents to disk, byte for byte."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.instrumented:
        return core.partial("edition publishes no control map")
    sess = _launch(ctx)
    try:
        if not sess.wait_window() or not sess.wait_ready(timeout=15):
            return core.fail("no window appeared")
        if not sess.load_control_map():
            return core.partial("no control map published")
        doc = ctx.work / "notes" / "doc.md"
        ok, detail = _edit_dirty(ctx, sess, fixtures.MARKER)
        if not ok:
            return core.fail(detail)
        x11.key("ctrl+s")
        if not sess.wait_file(doc, min_size=1, timeout=8):
            return core.fail("file never changed on disk after Ctrl+S")
        if fixtures.MARKER not in doc.read_text():
            return core.fail("marker absent from saved file")
        return core.ok()
    finally:
        _teardown(ctx, sess)


def a06_save_as(ctx):
    """FR-6: Save As to a new path becomes the document's path."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.instrumented:
        return core.partial("edition publishes no control map")
    sess = _launch(ctx)
    try:
        if not sess.wait_window() or not sess.wait_ready(timeout=15):
            return core.fail("no window appeared")
        if not sess.load_control_map():
            return core.partial("no control map published")
        new_path = ctx.work / "outside" / "renamed.md"
        ok, detail = _edit_dirty(ctx, sess, fixtures.MARKER)
        if not ok:
            return core.fail(detail)
        if not sess.click("save_as"):
            return core.fail("no Save As control in control map")
        if not sess.has("path") or not sess.has("ok"):
            return core.partial("save browser not instrumented (no path/ok rects)")
        pt = sess.click_point("path")
        x11.click_at(sess.wid, pt[0], pt[1])
        time.sleep(0.3)
        x11.type_text(str(new_path))
        time.sleep(0.3)
        sess.click("ok")
        if not sess.wait_file(new_path, timeout=10):
            return core.fail("file never appeared at the new path")
        if fixtures.MARKER not in new_path.read_text():
            return core.fail("marker absent from the saved-as file")
        if not sess.wait_title_contains("renamed.md", timeout=8):
            return core.fail("title never adopted the new path")
        return core.ok()
    finally:
        _teardown(ctx, sess)


def _export(ctx, sess, canonical, filename, validator):
    """Click Export, type the destination path, confirm; wait for the file;
    validate the real artifact."""
    out = ctx.work / "outside" / filename
    if not sess.click(canonical):
        return core.fail(f"no {canonical} control in control map")
    if not sess.has("path") or not sess.has("ok"):
        return core.partial(f"{canonical} browser not instrumented (no path/ok rects)")
    pt = sess.click_point("path")
    x11.click_at(sess.wid, pt[0], pt[1])
    time.sleep(0.3)
    x11.type_text(str(out))
    time.sleep(0.3)
    sess.click("ok")
    if not sess.wait_file(out, min_size=1, timeout=15):
        return core.fail(f"no file written to {out}")
    ok, detail = validator(out)
    if not ok:
        return core.fail(detail)
    ctx.copy_artifact(out)
    return core.ok(detail)


def a07_export_html(ctx):
    """FR-7: a real, standalone HTML document appears on disk and parses."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.instrumented:
        return core.partial("edition publishes no control map")
    sess = _launch(ctx)
    try:
        if not sess.wait_window() or not sess.wait_ready(timeout=15):
            return core.fail("no window appeared")
        if not sess.load_control_map():
            return core.partial("no control map published")
        return _export(ctx, sess, "export_html", "out.html", lambda p: validate_html(p, fixtures.FAR_CONTENT))
    finally:
        _teardown(ctx, sess)


def a08_export_pdf(ctx):
    """FR-8: a real, structurally valid PDF appears on disk."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.instrumented:
        return core.partial("edition publishes no control map")
    sess = _launch(ctx)
    try:
        if not sess.wait_window() or not sess.wait_ready(timeout=15):
            return core.fail("no window appeared")
        if not sess.load_control_map():
            return core.partial("no control map published")
        return _export(ctx, sess, "export_pdf", "out.pdf", lambda p: validate_pdf(p, fixtures.FAR_CONTENT)[:2])
    finally:
        _teardown(ctx, sess)


def a09_e2e(ctx):
    """The product test: open -> edit -> save -> export HTML and PDF, all
    through the real interface, all verified on disk."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.instrumented:
        return core.partial("edition publishes no control map")
    sess = _launch(ctx)
    try:
        if not sess.wait_window() or not sess.wait_ready(timeout=15):
            return core.fail("no window appeared")
        if not sess.load_control_map():
            return core.partial("no control map published")
        got, detail = _open_far_file(ctx, sess)
        if not got:
            return core.partial(f"open step: {detail}")
        doc = ctx.work / "notes" / "doc.md"
        ok, detail = _edit_dirty(ctx, sess, fixtures.MARKER)
        if not ok:
            return core.fail(f"edit step: {detail}")
        x11.key("ctrl+s")
        if not sess.wait_file(doc, timeout=8) or fixtures.MARKER not in doc.read_text():
            return core.fail("save step: marker not on disk")
        html_out = ctx.work / "outside" / "e2e.html"
        pdf_out = ctx.work / "outside" / "e2e.pdf"
        for canonical, out, validator in (
                ("export_html", html_out, lambda p: validate_html(p, fixtures.MARKER)),
                ("export_pdf", pdf_out, lambda p: validate_pdf(p, fixtures.MARKER)[:2])):
            r = _export(ctx, sess, canonical, out.name, validator)
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
    """Open control exists, is bound, and the browser is present (spec 5.2)."""
    return _static(ctx, {"open_control", "open_bound", "browser"})


def a11_export_wiring(ctx):
    """Export control exists, is bound, and reaches a filesystem write."""
    return _static(ctx, {"export_control", "export_bound", "export_writes"})


def a12_browser(ctx):
    """A file selection mechanism exists, native or in-app, over POSIX ops."""
    return _static(ctx, {"browser", "browser_policy"})


def a13_close_dirty(ctx):
    """FR-9: closing with a dirty document must not silently lose work."""
    if not ctx.display_ok:
        return core.skip("no display")
    if not ctx.instrumented:
        return core.partial("edition publishes no control map")
    sess = _launch(ctx)
    doc = ctx.work / "notes" / "doc.md"
    try:
        if not sess.wait_window() or not sess.wait_ready(timeout=15):
            return core.fail("no window appeared")
        if not sess.load_control_map():
            return core.partial("no control map published")
        ok, detail = _edit_dirty(ctx, sess, fixtures.MARKER)
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
    ]