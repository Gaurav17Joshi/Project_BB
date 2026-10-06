"""Compare the local-model abstraction (outputs/open) with the closed-model one (outputs/closed), contact by contact.

Reads both saved databases; no model is called. Writes outputs/comparison.md.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from backbone import queries  # noqa: E402

CLOSED = ROOT / "outputs" / "closed" / "abstraction.db"
OPEN = ROOT / "outputs" / "open" / "abstraction.db"


def connect(p):
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    return c


def therapy_key(c):
    return (c["service_date"], c["encounter_key"])


def main():
    o, cl = connect(OPEN), connect(CLOSED)
    lines = ["# Local (qwen3.5:9b) vs closed (gpt-6-luna) abstraction", ""]
    oc = {therapy_key(c): dict(c) for c in o.execute("SELECT * FROM contacts")}
    cc = {therapy_key(c): dict(c) for c in cl.execute("SELECT * FROM contacts")}
    clinical = [k for k in cc if "#" not in k[1]]  # encounter contacts (skip administrative calls)
    rows, agree = [], 0
    for k in sorted(clinical):
        a, b = cc[k], oc.get(k)
        # Outcome = what affects any count: type, inclusion, and minutes of counted contacts.
        def outcome(c):
            m = (c["minutes_lo"], c["minutes_hi"]) if c["inclusion"] != "excluded" else None
            return (c["service_type"], c["inclusion"], m)
        same = b is not None and outcome(a) == outcome(b)
        label_only = same and a["status"] != b["status"]
        agree += same
        fmt = lambda c: "missing" if c is None else (f"{c['service_type'][:14]} {c['status']} {c['inclusion']} "  # noqa: E731
                                                       f"{c['minutes_lo']}-{c['minutes_hi']}")
        mark = "✓ (status label differs)" if label_only else "✓" if same else "**✗**"
        rows.append(f"| {k[0]} | {k[1]} | {fmt(a)} | {fmt(b)} | {mark} |")
    extra = sorted(k for k in oc if "#" not in k[1] and k not in cc)
    lines += [f"**Encounter contacts with the same outcome as the closed model: {agree}/{len(clinical)}** "
              f"(service type, counted or not, minutes of counted contacts).", "",
              "| Date | Encounter | Closed | Local | Same |", "|---|---|---|---|---|", *rows]
    if extra:
        lines += ["", "Contacts only in the local abstraction: " + ", ".join(f"{d} {e}" for d, e in extra)]

    def weeks(con):
        return [(w["week"], w["therapy_days"], w["minutes"], w["verdict"]) for w in queries.goal_compliance(con)["weeks"]]

    def counts(con):
        r = queries.session_counts(con)
        return (r["by_type"], r["total_established"], r["distinct_therapy_days_established"])

    def meas(con):
        return [(m["completed_date"], m["total_score"]) for m in queries.measures(con)["distinct_administrations"]]

    lines += ["", "## Headline results", "", "| | Closed | Local | Same |", "|---|---|---|---|"]
    for name, fn in (("Session counts", counts), ("Weekly goal", weeks), ("PHQ-9 administrations", meas)):
        a, b = fn(cl), fn(o)
        lines.append(f"| {name} | {a} | {b} | {'✓' if a == b else '**✗**'} |")
    wa = queries.weekly_summary(cl)
    wb = queries.weekly_summary(o)
    lines.append(f"| Total minutes | {wa['total_minutes_lo']}-{wa['total_minutes_hi']} | "
                 f"{wb['total_minutes_lo']}-{wb['total_minutes_hi']} | "
                 f"{'✓' if (wa['total_minutes_lo'], wa['total_minutes_hi']) == (wb['total_minutes_lo'], wb['total_minutes_hi']) else '**✗**'} |")

    lines += ["", "## Issues raised", "", "| Closed | Local |", "|---|---|"]
    ia = sorted(f"{i['kind']}: {i['description'][:90]}" for i in cl.execute("SELECT * FROM issues"))
    ib = sorted(f"{i['kind']}: {i['description'][:90]}" for i in o.execute("SELECT * FROM issues"))
    for k in range(max(len(ia), len(ib))):
        lines.append(f"| {ia[k] if k < len(ia) else ''} | {ib[k] if k < len(ib) else ''} |")
    vm = [dict(r) for r in o.execute("SELECT ev_match, count(*) n FROM (SELECT ev_match FROM source_records UNION ALL "
                                     "SELECT ev_match FROM observations UNION ALL SELECT ev_match FROM measures UNION ALL "
                                     "SELECT ev_match FROM corrections UNION ALL SELECT ev_match FROM goals) GROUP BY ev_match")]
    lines += ["", f"Local extraction quote verification: {vm}"]
    text = "\n".join(lines) + "\n"
    (ROOT / "outputs" / "comparison.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
