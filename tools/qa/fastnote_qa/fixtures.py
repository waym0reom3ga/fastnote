"""Real-file fixtures. Every case works on real files in an isolated scratch
directory: a notes directory, a document far outside it, and the canonical
A12 template. Nothing is created outside the case's own work dir."""

import shutil
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "testdata" / "template.md"

MARKER = "MARKER-QA-7f1d9c"
FAR_TITLE = "Far Away Document"
FAR_CONTENT = "UNIQUE-OUTSIDE-CONTENT-8842"


def seed(work):
    """Create notes/, outside/, and the canonical documents inside them."""
    notes = work / "notes"
    outside = work / "outside"
    notes.mkdir(parents=True, exist_ok=True)
    outside.mkdir(parents=True, exist_ok=True)

    doc = notes / "doc.md"
    shutil.copy2(TEMPLATE, doc)

    far = outside / "far_away_document.md"
    far.write_text(f"# {FAR_TITLE}\n\n{FAR_CONTENT}\n")

    return {
        "notes": notes,
        "outside": outside,
        "doc": doc,
        "far": far,
    }


def seed_template(path):
    shutil.copy2(TEMPLATE, path)
    return path
