"""Command line entry point. Add --backend ollama to any command to use the local model (default: openai).

  python cli.py process [--docs DIR]        ingest + extract new docs + reconcile (LLM only for new docs)
  python cli.py rebuild                     re-verify and re-reconcile from cached extractions (no LLM)
  python cli.py ask "question" [--id X]     answer a new question from the saved abstraction
  python cli.py answer-file data/questions.json
  python cli.py show contacts|weeks|goal|issues|measures|counts|day [--patient P] [--date D] [--start D --end D]
  python cli.py export                      write abstraction.json and contacts.csv to outputs/<closed|open>/
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from backbone import backend_flag  # noqa: E402

backend_flag.apply()  # --backend openai|ollama (default: BACKBONE_BACKEND, else openai)
from backbone import ask, config, db, pipeline, queries  # noqa: E402


def _print_table(rows, cols):
    widths = [max(len(c), *(len(str(r.get(c, ""))) for r in rows)) if rows else len(c) for c in cols]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(w) for c, w in zip(cols, widths)))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("process"); p.add_argument("--docs", type=Path, default=config.DOCS_DIR)
    sub.add_parser("rebuild")
    sub.add_parser("export")
    p = sub.add_parser("ask"); p.add_argument("question"); p.add_argument("--id")
    p = sub.add_parser("answer-file"); p.add_argument("path", type=Path, nargs="?", default=config.DATA_DIR / "questions.json")
    p = sub.add_parser("show")
    p.add_argument("what", choices=["contacts", "weeks", "goal", "issues", "measures", "counts", "day", "patients"])
    for a in ("--patient", "--date", "--start", "--end"):
        p.add_argument(a)
    args = ap.parse_args()
    con = db.connect()

    if args.cmd == "process":
        print(json.dumps(pipeline.process(con, args.docs), indent=1))
        pipeline.export(con)
    elif args.cmd == "rebuild":
        print("rebuilt", pipeline.rebuild_all(con))
        pipeline.export(con)
    elif args.cmd == "export":
        print("wrote", pipeline.export(con))
    elif args.cmd == "ask":
        r = ask.answer(con, args.question, args.id, config.OUT_DIR / "answers")
        print(r["answer"])
        print(f"\n[{r['latency_s']} s, {r['llm_calls']} LLM calls, {r['input_tokens']} in / {r['output_tokens']} out tokens]")
    elif args.cmd == "answer-file":
        for q in json.loads(args.path.read_text(encoding="utf-8")):
            r = ask.answer(con, q["question"], q["id"], config.OUT_DIR / "answers")
            print(f"{q['id']}: {r['latency_s']} s, {r['llm_calls']} calls, {r['input_tokens']}/{r['output_tokens']} tokens")
    elif args.cmd == "show":
        kw = {"patient": args.patient}
        if args.what == "patients":
            _print_table(queries.list_patients(con), ["mrn", "name", "dob", "first_contact", "last_contact", "contacts", "documents"])
        elif args.what == "contacts":
            cs = queries.contacts(con, start=args.start, end=args.end, **kw)["contacts"]
            for c in cs:
                c["minutes"] = c["minutes_lo"] if c["minutes_lo"] == c["minutes_hi"] else f"{c['minutes_lo']}-{c['minutes_hi']}"
                c["docs"] = ",".join(c["doc_ids"])
            _print_table(cs, ["service_date", "encounter_key", "service_type", "status", "inclusion", "minutes", "intervals", "breaks", "docs"])
        elif args.what == "weeks":
            r = queries.weekly_summary(con, start=args.start, end=args.end, **kw)
            _print_table(r["weeks"], ["week", "therapy_days_established", "therapy_days_possible", "minutes_lo", "minutes_hi", "hours_lo", "hours_hi"])
            print(f"total minutes {r['total_minutes_lo']}-{r['total_minutes_hi']}  hours {r['total_hours_lo']}-{r['total_hours_hi']}")
        elif args.what == "goal":
            _print_table(queries.goal_compliance(con, start=args.start, end=args.end, **kw)["weeks"],
                         ["week", "therapy_days", "minutes", "verdict", "why"])
        elif args.what == "counts":
            r = queries.session_counts(con, start=args.start, end=args.end, **kw)
            print(json.dumps({k: r[k] for k in ("period", "by_type", "total_established", "total_possible",
                                                "distinct_therapy_days_established", "distinct_therapy_days_possible")}, indent=1))
        elif args.what == "issues":
            _print_table(queries.issues(con, **kw)["issues"], ["issue_id", "severity", "kind", "description"])
        elif args.what == "measures":
            _print_table(queries.measures(con, **kw)["distinct_administrations"],
                         ["instrument", "completed_date", "total_score", "change_from_previous", "doc_ids", "note"])
        elif args.what == "day":
            print(json.dumps(queries.day_detail(con, date=args.date, **kw), indent=1, default=str))


if __name__ == "__main__":
    main()
