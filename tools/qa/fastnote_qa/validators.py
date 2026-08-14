"""Real artifact validators. A verdict is only PASS when the exported file on
disk actually satisfies the format's structure, not when some code path ran."""

import re
from html.parser import HTMLParser


class _HtmlCheck(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.has_doctype = False
        self.has_html = False
        self.has_style = False
        self.title = ""
        self._in_title = False
        self.script_count = 0

    def handle_decl(self, decl):
        if decl.upper().startswith("DOCTYPE"):
            self.has_doctype = True

    def handle_starttag(self, tag, attrs):
        if tag == "html":
            self.has_html = True
        elif tag == "style":
            self.has_style = True
        elif tag == "title":
            self._in_title = True
        elif tag == "script":
            self.script_count += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def validate_html(path, required_text=None):
    """Check the file is a complete standalone HTML document.

    Returns (ok, problems). required_text must appear verbatim in the file.
    """
    raw = path.read_bytes()
    if not raw:
        return False, "empty file"
    text = raw.decode("utf-8", errors="replace")
    if not text.lstrip().lower().startswith("<!doctype"):
        return False, "no DOCTYPE at start"

    checker = _HtmlCheck()
    try:
        checker.feed(text)
        checker.close()
    except Exception as e:
        return False, f"unparseable as HTML: {e}"

    problems = []
    if not checker.has_doctype:
        problems.append("no DOCTYPE")
    if not checker.has_html:
        problems.append("no <html>")
    if not checker.has_style:
        problems.append("no <style>")
    if not checker.title.strip():
        problems.append("empty <title>")
    if checker.script_count > 0:
        problems.append(f"{checker.script_count} literal <script> element(s); markdown must be escaped")
    if required_text and required_text not in text:
        problems.append(f"required content missing: {required_text[:40]!r}")
    return (not problems), "; ".join(problems)


def validate_pdf(path, required_text=None):
    """Check the file is a structurally valid PDF 1.x document.

    The hard gate is structure: header, xref table, trailer, %%EOF within the
    last 1024 bytes, non-trivial size. Marker presence is recorded separately
    because compressed streams legitimately hide text from a byte scan.
    """
    if not path.exists():
        return False, "file not created", False
    raw = path.read_bytes()
    if not raw:
        return False, "empty file", False
    if not raw.startswith(b"%PDF-"):
        return False, f"bad header: {raw[:16]!r}", False
    if len(raw) < 300:
        return False, f"suspiciously small ({len(raw)} bytes)", False
    tail = raw[-1024:]
    if b"%%EOF" not in tail:
        return False, "no %%EOF trailer", False
    if b"xref" not in raw:
        return False, "no xref table", False
    marker_present = (required_text is not None) and (required_text.encode("utf-8") in raw)
    return True, f"{len(raw)} bytes", marker_present
