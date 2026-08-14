"""Results store and report generation. Every verdict lands in SQLite so
history accumulates: a regression is a formerly-passing edition now failing.
Reports are rendered from the store, never from this run's memory."""

import html
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path


class Store:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                edition TEXT NOT NULL,
                note TEXT
            )""")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                case_id TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT,
                seconds REAL
            )""")
        self.conn.commit()
        self.run_id = None

    def begin_run(self, edition, note=""):
        cur = self.conn.execute(
            "INSERT INTO run (ts, edition, note) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), edition, note))
        self.conn.commit()
        self.run_id = cur.lastrowid

    def record(self, edition, case_id, row):
        status, detail, seconds = row
        self.conn.execute(
            "INSERT INTO result (run_id, case_id, status, detail, seconds) VALUES (?, ?, ?, ?, ?)",
            (self.run_id, case_id, status, detail, seconds))
        self.conn.commit()

    def latest_rows(self):
        return self.conn.execute("""
            SELECT r.edition, res.case_id, res.status, res.detail, res.seconds
            FROM result res JOIN run r ON r.id = res.run_id
            WHERE r.id = (SELECT MAX(id) FROM run)
            ORDER BY r.edition, res.case_id""").fetchall()

    def per_edition_latest(self):
        """The most recent run per edition: {edition: {case_id: status}}.
        Used by the comparative tableau for the capability matrix."""
        rows = self.conn.execute("""
            SELECT r.edition, res.case_id, res.status
            FROM result res JOIN run r ON r.id = res.run_id
            WHERE r.id = (SELECT MAX(r2.id) FROM run r2
                          WHERE r2.edition = r.edition)
            ORDER BY r.edition, res.case_id""").fetchall()
        matrix = {}
        for edition, case_id, status in rows:
            matrix.setdefault(edition, {})[case_id] = status
        return matrix


CASE_ORDER = ["a01", "a02", "a03", "a04", "a05", "a06", "a07", "a08",
              "a09", "a10", "a11", "a12", "a13", "a14"]


def report_markdown(rows):
    by_edition = {}
    for edition, case_id, status, detail, seconds in rows:
        by_edition.setdefault(edition, {})[case_id] = status
    editions = sorted(by_edition)
    case_ids = sorted({c for _, cs in by_edition.items() for c in cs},
                      key=lambda c: (c,))
    out = ["# FastNote QA results", "",
           f"run timestamp: {datetime.now().isoformat(timespec='seconds')}", ""]
    header = "| edition | " + " | ".join(c.upper() for c in case_ids) + " | result |"
    sep = "|" + "---|" * (len(case_ids) + 2)
    out += [header, sep]
    for ed in editions:
        cs = by_edition[ed]
        cells = [cs.get(c, "-") for c in case_ids]
        passed = sum(1 for s in cells if s == "PASS")
        out.append(f"| {ed} | " + " | ".join(cells) + f" | {passed}/{len(case_ids)} |")
    out.append("")
    for edition, case_id, status, detail, seconds in rows:
        if status != "PASS":
            out.append(f"- **{edition} {case_id.upper()}**: {status} — {detail}")
    return "\n".join(out) + "\n"


def report_json(rows):
    return json.dumps(rows, indent=2)


def report_html(rows):
    md = report_markdown(rows)
    body = html.escape(md).replace("\n", "<br>")
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>FastNote QA</title></head><body><pre>{body}</pre></body></html>\n"
