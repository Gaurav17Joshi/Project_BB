"""Checks the saved abstractions against answers worked out by hand from the documents (Plan.md section 5).

These values live only here, never in the pipeline: they are what the rules should produce, not inputs to them.
No API key or model is needed; the tests read the saved databases in outputs/.

    python -m unittest discover tests -v
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backbone import queries  # noqa: E402

DBS = {"closed (gpt-6-luna)": ROOT / "outputs" / "closed" / "abstraction.db",
       "open (qwen3.5:9b)": ROOT / "outputs" / "open" / "abstraction.db"}

EXPECTED_WEEKS = [  # (week, therapy days, minutes, verdict)
    ("2026-01-05 to 2026-01-11", 3, 140, "not_met"),
    ("2026-01-12 to 2026-01-18", 2, 120, "not_met"),
    ("2026-01-19 to 2026-01-25", 3, 180, "met"),
    ("2026-01-26 to 2026-02-01", 3, "145-155", "indeterminate"),
]


def connect(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)  # read-only: tests never change the saved abstraction
    con.row_factory = sqlite3.Row
    return con


class ExpectedAnswers(unittest.TestCase):
    """DEV-01 to DEV-05 headline results, for both saved abstractions."""

    def each_db(self):
        for name, path in DBS.items():
            if not path.exists():
                self.skipTest(f"{path} not found")
            with self.subTest(abstraction=name):
                yield connect(path)

    def test_sessions_by_type_and_days(self):
        for con in self.each_db():
            r = queries.session_counts(con)
            self.assertEqual({t: v["established"] for t, v in r["by_type"].items()},
                             {"individual_psychotherapy": 5, "group_psychotherapy": 5, "family_psychotherapy": 2})
            self.assertEqual((r["total_established"], r["total_possible"]), (12, 12))
            self.assertEqual(r["distinct_therapy_days_established"], 11)

    def test_total_minutes_is_a_range(self):
        for con in self.each_db():
            w = queries.weekly_summary(con)
            self.assertEqual((w["total_minutes_lo"], w["total_minutes_hi"]), (585, 595))

    def test_weekly_goal_verdicts(self):
        for con in self.each_db():
            weeks = [(w["week"], w["therapy_days"], w["minutes"], w["verdict"])
                     for w in queries.goal_compliance(con)["weeks"]]
            self.assertEqual(weeks, EXPECTED_WEEKS)
            g = queries.treatment_goals(con)["goals"][0]
            self.assertEqual((g["min_days"], g["min_minutes"]), (3, 150))

    def test_jan_19_and_21(self):
        for con in self.each_db():
            d19 = queries.day_detail(con, date="2026-01-19")
            self.assertEqual((d19["therapy_contacts_established"], d19["patient_therapy_minutes_lo"],
                              d19["patient_therapy_minutes_hi"]), (2, 90, 90))
            d21 = queries.day_detail(con, date="2026-01-21")
            self.assertEqual((d21["therapy_contacts_established"], d21["patient_therapy_minutes_lo"]), (1, 45))

    def test_phq9_distinct_administrations(self):
        for con in self.each_db():
            m = queries.measures(con)["distinct_administrations"]
            self.assertEqual([(x["completed_date"], x["total_score"]) for x in m],
                             [("2026-01-05", 18), ("2026-01-16", 14), ("2026-01-30", 10)])
            jan16 = next(x for x in m if x["completed_date"] == "2026-01-16")
            self.assertEqual(len(jan16["records"]), 2, "Jan 16 form and its Jan 26 import should merge into one")

    def test_non_therapy_contacts_not_counted(self):
        for con in self.each_db():
            counted = {c["service_type"] for c in queries.contacts(con, inclusion=["included"])["contacts"]}
            for t in ("medication_management", "collateral_contact", "care_coordination"):
                self.assertNotIn(t, counted)
            jan27 = queries.day_detail(con, date="2026-01-27")
            self.assertEqual(jan27["therapy_contacts_established"], 0, "draft note + charge must not count Jan 27")


class ExpectedIssues(unittest.TestCase):
    """Conflicts the closed abstraction should raise on its own."""

    def setUp(self):
        self.issues = queries.issues(connect(DBS["closed (gpt-6-luna)"]))["issues"]

    def kinds(self, severity):
        return {(i["kind"], i["contact_id"].rsplit("/", 1)[-1] if i["contact_id"] else None)
                for i in self.issues if i["severity"] == severity}

    def test_high_severity(self):
        self.assertEqual(self.kinds("high"), {("duration_conflict", "HG-E115"),
                                              ("draft_or_billing_without_service", "HG-E116")})

    def test_merged_duplicates(self):
        info = self.kinds("info")
        self.assertIn(("multiple_notes_one_encounter", "HG-E104"), info)
        self.assertIn(("multiple_notes_one_encounter", "HG-E115"), info)
        self.assertIn(("duplicate_copy", "HG-E110"), info)
        self.assertIn(("duplicate_measure", None), info)


class Behaviour(unittest.TestCase):
    """Duplicates never change results, and questions work from the saved database after a restart."""

    def test_duplicate_copies_change_nothing(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copy(DBS["closed (gpt-6-luna)"], tmp / "t.db")
            docs = ROOT / "data" / "documents"
            src = sorted(docs.glob("*.txt"))
            (tmp / "docs").mkdir()
            shutil.copy(src[0], tmp / "docs" / f"COPY_{src[0].name}")
            (tmp / "docs" / f"RESCAN_{src[1].name}").write_text(
                src[1].read_text(encoding="utf-8").replace("\n", "\r\n") + "\n\n", encoding="utf-8")
            code = (
                "import sys; sys.path.insert(0, r'%s');"
                "from backbone import db, pipeline, queries; c = db.connect();"
                "before = queries.weekly_summary(c)['total_minutes_lo'];"
                "r = pipeline.process(c, r'%s', progress=lambda *_: None);"
                "print(r['new_documents'], r['extracted'], len(r['duplicate_copies']), before,"
                " queries.weekly_summary(c)['total_minutes_lo'])" % (ROOT, tmp / "docs"))
            env = {**os.environ, "BACKBONE_DB": str(tmp / "t.db"), "BACKBONE_BACKEND": "openai"}
            env.pop("OPENAI_API_KEY", None)  # proves no model call is needed
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
            new, calls, dups, before, after = out.stdout.split()
            self.assertEqual((new, calls, dups), ("0", "0", "2"))
            self.assertEqual(before, after)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_restart_reads_saved_abstraction_without_documents(self):
        env = {**os.environ, "BACKBONE_BACKEND": "openai"}
        env.pop("OPENAI_API_KEY", None)
        out = subprocess.run([sys.executable, str(ROOT / "cli.py"), "show", "goal"], capture_output=True,
                             text=True, env=env, cwd=tempfile.gettempdir(), check=True, encoding="utf-8")
        self.assertIn("145-155", out.stdout)
        self.assertIn("indeterminate", out.stdout)


if __name__ == "__main__":
    unittest.main()
