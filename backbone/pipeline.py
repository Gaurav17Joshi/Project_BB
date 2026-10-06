"""process = ingest -> extract (only new/changed docs) -> verify+load facts -> reconcile affected patients."""
import csv
import json
import time

from . import config, db, extract, ingest, reconcile


def process(con, docs_dir=None, progress=print) -> dict:
    t0 = time.perf_counter()
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    ing = ingest.ingest(con, docs_dir or config.DOCS_DIR)
    t_ing = time.perf_counter() - t0
    todo = extract.pending(con)
    progress(f"ingest: {ing['seen']} files, {len(ing['new'])} new, {len(ing['duplicates'])} duplicate copies; "
             f"{len(todo)} need extraction")
    t1 = time.perf_counter()
    ex = extract.run_extraction(con, todo, progress=progress)
    t_ext = time.perf_counter() - t1

    t2 = time.perf_counter()
    affected = set()
    for k in todo:
        mrn = extract.load_facts(con, k)
        if mrn:
            affected.add(mrn)
    for mrn in sorted(affected):
        reconcile.rebuild_patient(con, mrn)
    t_rec = time.perf_counter() - t2
    details = {
        "files_seen": ing["seen"], "new_documents": len(ing["new"]), "duplicate_copies": ing["duplicates"],
        "extracted": ex["calls"], "failed": ex["failed"], "input_tokens": ex["input_tokens"],
        "cached_input_tokens": ex["cached_input_tokens"], "output_tokens": ex["output_tokens"],
        "cost_usd": round(config.cost_usd(ex["input_tokens"], ex["cached_input_tokens"], ex["output_tokens"]), 5),
        "patients_rebuilt": sorted(affected),
        "seconds": {"ingest": round(t_ing, 3), "extract": round(t_ext, 3), "load_and_reconcile": round(t_rec, 3)},
        "model": config.EXTRACT_MODEL, "prompt_version": config.EXTRACT_PROMPT_VERSION,
    }
    total = time.perf_counter() - t0
    con.execute("INSERT INTO runs(kind, started_at, seconds, details_json) VALUES (?,?,?,?)",
                ("process", started, total, json.dumps(details)))
    con.commit()
    details["seconds"]["total"] = round(total, 3)
    return details


def rebuild_all(con):
    """Re-run verification + reconciliation from cached extractions (no LLM calls)."""
    mrns = set()
    for (k,) in con.execute("SELECT doc_key FROM documents").fetchall():
        m = extract.load_facts(con, k)
        if m:
            mrns.add(m)
    for m in sorted(mrns):
        reconcile.rebuild_patient(con, m)
    return sorted(mrns)


def export(con, out_dir=None):
    """Write the abstraction as inspectable JSON + CSV next to the SQLite file."""
    out_dir = out_dir or config.DB_PATH.parent
    data = {}
    for t in ["patients", "contacts", "contact_sources", "issues", "measures_distinct", "goals", "corrections",
              "source_records", "measures", "observations", "admin_facts"]:
        data[t] = db.rows(con, f"SELECT * FROM {t}")
    data["documents"] = db.rows(con, "SELECT doc_id, filename, title, summary, patient_mrn, is_copy, copy_of, n_chars FROM documents")
    (out_dir / "abstraction.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(out_dir / "contacts.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["contact_id", "service_date", "service_type", "status", "inclusion", "minutes_lo", "minutes_hi",
                "intervals_json", "breaks_json", "doc_ids_json", "inclusion_reason", "minutes_basis"]
        w = csv.writer(f)
        w.writerow(cols)
        for c in data["contacts"]:
            w.writerow([c[k] for k in cols])
    return out_dir
