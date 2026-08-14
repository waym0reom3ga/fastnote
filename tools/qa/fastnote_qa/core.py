"""Test model and runner. A case is a callable taking a CaseContext and
returning a Result. The runner collects results, captures evidence and is the
single place pass/fail is decided."""

import shutil
import subprocess
import time
from pathlib import Path

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
PARTIAL = "PARTIAL"


class Result:
    def __init__(self, status, detail="", seconds=0.0):
        self.status = status
        self.detail = detail
        self.seconds = seconds

    def to_row(self):
        return self.status, self.detail, self.seconds


def ok(detail="", seconds=0.0):
    return Result(PASS, detail, seconds)


def fail(detail=""):
    return Result(FAIL, detail)


def skip(detail=""):
    return Result(SKIP, detail)


def partial(detail=""):
    return Result(PARTIAL, detail)


class CaseContext:
    def __init__(self, edition, work, evidence, display_ok, instrumented, build_ok):
        self.edition = edition          # manifest entry dict
        self.work = work                # Path, per-case scratch dir
        self.evidence = evidence        # Path, evidence dir for this case
        self.display_ok = display_ok    # bool: usable X display present
        self.instrumented = instrumented  # bool: control map available
        self.build_ok = build_ok        # bool: binary present and current runnable

    def log(self, name, text):
        (self.evidence / name).write_text(text)

    def copy_artifact(self, path, name=None):
        p = Path(path)
        if p.exists():
            shutil.copy2(p, self.evidence / (name or p.name))


class Runner:
    def __init__(self, cases, workroot, evidence_root, db):
        self.cases = cases              # ordered list of (id, callable)
        self.workroot = workroot
        self.evidence_root = evidence_root
        self.db = db                    # results.Store or None

    def run_edition(self, entry, display_ok, instrumented, build_ok, build_log_dir,
                    case_filter=None):
        name = entry["name"]
        rows = []
        for case_id, fn in self.cases:
            if case_filter and case_id not in case_filter:
                continue
            work = self.workroot / name / case_id
            if work.exists():
                shutil.rmtree(work)
            work.mkdir(parents=True)
            evidence = self.evidence_root / name / case_id
            if evidence.exists():
                shutil.rmtree(evidence)
            evidence.mkdir(parents=True)
            shutil.copy2(build_log_dir / "build.log", evidence / "build.log")

            ctx = CaseContext(entry, work, evidence, display_ok, instrumented, build_ok)
            t0 = time.monotonic()
            try:
                r = fn(ctx)
            except Exception as e:  # a crashed case is a failed test, not a suite bug
                r = fail(f"case crashed: {type(e).__name__}: {e}")
            r.seconds = time.monotonic() - t0
            rows.append((case_id, r))
            if self.db:
                self.db.record(name, case_id, r.to_row())
        return rows
