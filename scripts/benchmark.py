"""Measured benchmark on the supplied documents, for the backend in BACKBONE_BACKEND.
Writes outputs/<closed|open>/benchmark.md and benchmark.json; the scratch DB goes to outputs/bench/<closed|open>/.

Steps: cold process on an empty DB -> warm re-run (cache) -> duplicate-copy test -> restart and answer
questions from the saved abstraction -> pure-code query latency -> sizes.
"""
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backbone import backend_flag  # noqa: E402

backend_flag.apply()  # --backend openai|ollama
_VARIANT = "open" if os.environ.get("BACKBONE_BACKEND", "openai").strip().lower() == "ollama" else "closed"
BENCH = ROOT / "outputs" / "bench" / _VARIANT
os.environ["BACKBONE_DB"] = str(BENCH / "abstraction.db")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from backbone import ask, config, db, pipeline, queries  # noqa: E402

UNSEEN = [
    ("NEW-01", "How many group therapy minutes did Rowan receive in the week starting January 19, 2026, and which contacts contributed?"),
    ("NEW-02", "Which patients had two consecutive Monday–Sunday weeks below their treatment-plan requirements, and whose inclusion depends on unresolved documentation?"),
    ("NEW-03", "How did the types and amounts of care delivered change before and after a treatment-plan change, for each patient?"),
]
COLLECTION_WIDE = {"NEW-02", "NEW-03"}


def contacts_hash(con):
    rows = db.rows(con, "SELECT contact_id, status, inclusion, minutes_lo, minutes_hi FROM contacts ORDER BY contact_id")
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def main():
    if BENCH.exists():
        shutil.rmtree(BENCH)
    BENCH.mkdir(parents=True)
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    res = {"backend": config.BACKEND, "model": config.EXTRACT_MODEL, "answer_model": config.ANSWER_MODEL, "documents_dir": str(config.DOCS_DIR)}
    quiet = lambda *_: None  # noqa: E731

    # 1. cold
    con = db.connect()
    t = time.perf_counter()
    cold = pipeline.process(con, progress=quiet)
    res["cold_process"] = {**cold, "wall_s": round(time.perf_counter() - t, 2)}
    h_cold = contacts_hash(con)

    # 2. warm (same docs, nothing new)
    t = time.perf_counter()
    warm = pipeline.process(con, progress=quiet)
    res["warm_process"] = {**warm, "wall_s": round(time.perf_counter() - t, 3)}

    # 3. duplicate copies: same docs + exact and whitespace-variant copies of two files
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "docs").mkdir()
        src = sorted(config.DOCS_DIR.glob("*.txt"))
        shutil.copy(src[0], tmp / "docs" / f"COPY_{src[0].name}")
        txt = src[1].read_text(encoding="utf-8")
        (tmp / "docs" / f"RESCAN_{src[1].name}").write_text(txt.replace("\n", "\r\n") + "\n\n", encoding="utf-8")
        t = time.perf_counter()
        dup = pipeline.process(con, tmp / "docs", progress=quiet)
        res["duplicate_test"] = {"added_files": 2, "new_documents": dup["new_documents"], "llm_calls": dup["extracted"],
                                 "duplicates_detected": dup["duplicate_copies"], "wall_s": round(time.perf_counter() - t, 3),
                                 "contacts_unchanged": contacts_hash(con) == h_cold}

    # 4. pure-code query latency (no LLM)
    lat = {}
    for name, fn in [("session_counts", lambda: queries.session_counts(con)),
                     ("weekly_summary", lambda: queries.weekly_summary(con)),
                     ("goal_compliance", lambda: queries.goal_compliance(con)),
                     ("day_detail", lambda: queries.day_detail(con, date="2026-01-19")),
                     ("consecutive_weeks_below (collection)", lambda: queries.consecutive_weeks_below(con)),
                     ("compliance_all (collection)", lambda: queries.compliance_all(con))]:
        ts = []
        for _ in range(20):
            t = time.perf_counter(); fn(); ts.append((time.perf_counter() - t) * 1000)
        lat[name] = round(statistics.median(ts), 2)
    res["query_latency_ms_median_of_20"] = lat
    con.close()

    # 5. restart: answer questions in a fresh process from the saved abstraction
    t = time.perf_counter()
    out = subprocess.run([sys.executable, "-c",
                          "import sys; sys.path.insert(0, r'%s');" % ROOT +
                          "from backbone import db, queries; c=db.connect(); print(queries.weekly_summary(c)['total_minutes_lo'])"],
                         capture_output=True, text=True, env=os.environ)
    res["restart_load_and_query_s"] = round(time.perf_counter() - t, 2)
    res["restart_query_output"] = out.stdout.strip()

    con = db.connect()
    qs = [(q["id"], q["question"]) for q in json.loads((config.DATA_DIR / "questions.json").read_text(encoding="utf-8"))] + UNSEEN
    answers = []
    for qid, q in qs:
        r = ask.answer(con, q, qid, config.OUT_DIR / "answers")
        answers.append({"id": qid, "scope": "collection" if qid in COLLECTION_WIDE else "patient",
                        "latency_s": r["latency_s"], "llm_calls": r["llm_calls"], "input_tokens": r["input_tokens"],
                        "output_tokens": r["output_tokens"], "cached_input_tokens": r["cached_input_tokens"],
                        "cost_usd": r["cost_usd"], "citations": {k: v for k, v in r["citations"].items() if k != "unverified"}})
        print(qid, r["latency_s"], "s")
    res["questions"] = answers

    # 6. sizes
    pipeline.export(con, BENCH)
    con.close()
    raw = sum(p.stat().st_size for p in config.DOCS_DIR.glob("*") if p.is_file())
    res["sizes_bytes"] = {"source_documents": raw, "sqlite_db": (BENCH / "abstraction.db").stat().st_size,
                          "abstraction_json": (BENCH / "abstraction.json").stat().st_size}

    # cost from the configured per-token prices (0 for the local model)
    tin = cold["input_tokens"] + sum(a["input_tokens"] for a in answers)
    tout = cold["output_tokens"] + sum(a["output_tokens"] for a in answers)
    res["tokens_total"] = {"input": tin, "output": tout}
    res["cost_usd"] = {
        "extraction_billed": cold["cost_usd"],
        "extraction_uncached": round(config.cost_usd(cold["input_tokens"], 0, cold["output_tokens"]), 5),
        "questions_billed": round(sum(a["cost_usd"] for a in answers), 5),
        "prices_per_1M": {"input": config.PRICE_IN, "cached_input": config.PRICE_CACHED_IN, "output": config.PRICE_OUT}}
    (config.OUT_DIR / "benchmark.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    write_md(res)


def write_md(r):
    c, w, d = r["cold_process"], r["warm_process"], r["duplicate_test"]
    pq = [a for a in r["questions"] if a["scope"] == "patient"]
    cq = [a for a in r["questions"] if a["scope"] == "collection"]
    med = lambda xs: round(statistics.median(xs), 1) if xs else None  # noqa: E731
    lines = [
        "# Benchmark (measured)", "",
        f"All numbers below were measured on this machine against the supplied {c['files_seen']} documents, "
        f"model `{r['model']}` (backend `{r['backend']}`). "
        + ("Network latency to the API is included." if r["backend"] == "openai" else "The model runs locally through Ollama."), "",
        "## Processing", "",
        "| Run | Wall time | LLM calls | Input tokens | Output tokens |", "|---|---:|---:|---:|---:|",
        f"| Cold (empty DB) | {c['wall_s']} s | {c['extracted']} | {c['input_tokens']} | {c['output_tokens']} |",
        f"| Warm re-run (no new docs) | {w['wall_s']} s | {w['extracted']} | 0 | 0 |",
        f"| +2 duplicate copies (exact, and CRLF/whitespace variant) | {d['wall_s']} s | {d['llm_calls']} | 0 | 0 |", "",
        f"Cold breakdown: ingest {c['seconds']['ingest']} s, extraction {c['seconds']['extract']} s "
        f"({config.EXTRACT_WORKERS} parallel workers), verify+reconcile {c['seconds']['load_and_reconcile']} s.  ",
        f"Duplicate test: {len(d['duplicates_detected'])} copies detected, contacts unchanged: **{d['contacts_unchanged']}**.  ",
        f"Restart (new process loads the saved DB and runs a query): {r['restart_load_and_query_s']} s.", "",
        "## Question latency", "",
        "| Question | Scope | Latency | LLM calls | Input tokens | Output tokens | Quotes verified |",
        "|---|---|---:|---:|---:|---:|---:|",
        *[f"| {a['id']} | {a['scope']} | {a['latency_s']} s | {a['llm_calls']} | {a['input_tokens']} | {a['output_tokens']} | "
          f"{a['citations']['verified']}/{a['citations']['checked']} |" for a in r["questions"]], "",
        f"Median latency: individual-patient questions {med([a['latency_s'] for a in pq])} s, "
        f"collection-wide {med([a['latency_s'] for a in cq])} s.", "",
        "Pure-code query latency (no LLM, median of 20):", "",
        "| Query | ms |", "|---|---:|", *[f"| {k} | {v} |" for k, v in r["query_latency_ms_median_of_20"].items()], "",
        "## Size", "",
        f"Source documents {r['sizes_bytes']['source_documents'] / 1024:.1f} KB · SQLite abstraction "
        f"{r['sizes_bytes']['sqlite_db'] / 1024:.1f} KB (includes a copy of source text for quote lookup) · JSON export "
        f"{r['sizes_bytes']['abstraction_json'] / 1024:.1f} KB.", "",
        "## Tokens and cost", "",
        f"Total tokens this benchmark: {r['tokens_total']['input']} input, {r['tokens_total']['output']} output.", "",
        *(cost_lines(r)),
    ]
    (config.OUT_DIR / "benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def cost_lines(r):
    c = r["cost_usd"]
    if r["backend"] != "openai":
        return ["API cost: $0. The model runs locally through Ollama; the only cost is machine time and power."]
    p = c["prices_per_1M"]
    return [f"Prices (USD per 1M tokens): input ${p['input']}, cached input ${p['cached_input']}, output ${p['output']}.", "",
            f"- Extraction of all documents: ${c['extraction_billed']} as billed "
            f"(${c['extraction_uncached']} if no prompt-cache hits, i.e. a first-ever run).",
            f"- All {len(r['questions'])} questions: ${c['questions_billed']}.",
            *[f"  - {a['id']}: ${a['cost_usd']}" for a in r["questions"]]]


if __name__ == "__main__":
    main()
