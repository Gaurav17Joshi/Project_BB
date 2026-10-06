"""Per-document LLM extraction (cached) and loading of verified facts into SQLite."""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config, llm, prompts, schema, verify


def pending(con, model=None, prompt_version=None) -> list[str]:
    model = model or config.EXTRACT_MODEL
    pv = prompt_version or config.EXTRACT_PROMPT_VERSION
    return [r["doc_key"] for r in con.execute(
        "SELECT doc_key FROM documents WHERE doc_key NOT IN "
        "(SELECT doc_key FROM extractions WHERE model=? AND prompt_version=?)", (model, pv))]


def system_prompt() -> str:
    """Base rules for every backend; the local model also gets rules aimed at its observed mistakes."""
    return prompts.EXTRACT_SYSTEM + (prompts.EXTRACT_SYSTEM_LOCAL_ADDENDUM if config.BACKEND == "ollama" else "")


def _extract_one(doc_key, filename, text):
    out, rec = llm.call_json(
        "extract", config.EXTRACT_MODEL, system_prompt(), prompts.EXTRACT_USER.format(name=filename, text=text),
        schema.EXTRACTION, "clinical_extraction", reasoning_effort=config.EXTRACT_REASONING,
        extra_log={"file": filename})
    return doc_key, out, rec


def run_extraction(con, doc_keys: list[str], workers=None, progress=print) -> dict:
    """Extract the given documents in parallel; results are cached by (doc_key, model, prompt_version)."""
    docs = {r["doc_key"]: r for r in con.execute(
        f"SELECT doc_key, filename, text FROM documents WHERE doc_key IN ({','.join('?' * len(doc_keys))})", doc_keys)}
    stats = {"calls": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "failed": []}
    if not doc_keys:
        return stats
    with ThreadPoolExecutor(max_workers=workers or config.EXTRACT_WORKERS) as ex:
        futs = {ex.submit(_extract_one, k, docs[k]["filename"], docs[k]["text"]): k for k in doc_keys}
        for f in as_completed(futs):
            k = futs[f]
            try:
                _, out, rec = f.result()
            except Exception as e:
                stats["failed"].append((docs[k]["filename"], f"{type(e).__name__}: {e}"))
                progress(f"  FAILED {docs[k]['filename']}: {e}")
                continue
            con.execute("INSERT OR REPLACE INTO extractions VALUES (?,?,?,?,?,?,?,?)",
                        (k, config.EXTRACT_MODEL, config.EXTRACT_PROMPT_VERSION, json.dumps(out),
                         time.strftime("%Y-%m-%dT%H:%M:%S"), rec["latency_s"], rec["input_tokens"], rec["output_tokens"]))
            con.commit()
            stats["calls"] += 1
            stats["input_tokens"] += rec["input_tokens"] or 0
            stats["cached_input_tokens"] += rec["cached_input_tokens"] or 0
            stats["output_tokens"] += rec["output_tokens"] or 0
            progress(f"  extracted {docs[k]['filename']} ({rec['latency_s']}s)")
    return stats


def _ev(text, quote):
    s, e, line, match = verify.locate(text, quote)
    return [quote, s, e, line, match]


def _intervals(text, items):
    out = []
    for it in items or []:
        s, e, line, match = verify.locate(text, it.get("evidence"))
        out.append({**it, "ev_start": s, "ev_end": e, "ev_line": line, "ev_match": match})
    return out


def _mrn(v):
    return v.strip().upper() if v else None


def load_facts(con, doc_key: str) -> str | None:
    """Replace this document's fact rows from its cached extraction. Returns the patient MRN."""
    row = con.execute("SELECT e.json, d.text, d.doc_id FROM extractions e JOIN documents d USING(doc_key) "
                      "WHERE doc_key=? AND model=? AND prompt_version=?",
                      (doc_key, config.EXTRACT_MODEL, config.EXTRACT_PROMPT_VERSION)).fetchone()
    if not row:  # no extraction under the current model/prompt: drop any stale facts from older versions
        for t in ("source_records", "corrections", "goals", "measures", "observations", "admin_facts"):
            con.execute(f"DELETE FROM {t} WHERE doc_key=?", (doc_key,))
        con.commit()
        return None
    x, text, doc_id = json.loads(row["json"]), row["text"], row["doc_id"]
    d = x["document"]
    mrn = _mrn(d.get("patient_mrn")) or (f"NAME:{d['patient_name']}|{d.get('patient_dob')}" if d.get("patient_name") else "UNKNOWN")
    for t in ("source_records", "corrections", "goals", "measures", "observations", "admin_facts"):
        con.execute(f"DELETE FROM {t} WHERE doc_key=?", (doc_key,))
    con.execute("UPDATE documents SET patient_mrn=?, title=?, summary=?, is_copy=?, copy_of=? WHERE doc_key=?",
                (mrn, d.get("title"), d.get("summary"), int(bool(d.get("is_retransmission_or_copy"))), d.get("copy_of"), doc_key))
    if mrn != "UNKNOWN":
        con.execute("INSERT INTO patients(mrn, name, dob) VALUES (?,?,?) ON CONFLICT(mrn) DO UPDATE SET "
                    "name=COALESCE(patients.name, excluded.name), dob=COALESCE(patients.dob, excluded.dob)",
                    (mrn, d.get("patient_name"), d.get("patient_dob")))

    for i, r in enumerate(x["service_records"]):
        con.execute("INSERT INTO source_records VALUES (" + ",".join("?" * 28) + ")", (
            f"{doc_id}:S{i}", doc_key, doc_id, mrn, r["encounter_id"], r["appointment_id"], r["service_date"],
            r["service_type"], r["source_role"], r["attendance_status"], r["patient_present"], r["modality"],
            r["scheduled_start"], r["scheduled_end"],
            json.dumps(_intervals(text, r["patient_present_segments"])),
            json.dumps(_intervals(text, r["non_therapeutic_intervals"])),
            r["stated_patient_minutes"], json.dumps(r["clinicians"]), r["other_participants"],
            int(r["signed_final"]), r["signer_and_time"], r["reason_for_service"], r["notes"],
            *_ev(text, r["evidence"])))
    for i, c in enumerate(x["corrections"]):
        con.execute("INSERT INTO corrections VALUES (" + ",".join("?" * 15) + ")", (
            f"{doc_id}:C{i}", doc_key, doc_id, mrn, c["encounter_id"], c["service_date"], c["field"],
            c["original_value"], c["corrected_value"], c["scope"], *_ev(text, c["evidence"])))
    for i, g in enumerate(x["treatment_goals"]):
        con.execute("INSERT INTO goals VALUES (" + ",".join("?" * 18) + ")", (
            f"{doc_id}:G{i}", doc_key, doc_id, mrn, g["min_therapy_days_per_week"],
            g["min_patient_present_minutes_per_week"], g["week_definition"], json.dumps(g["counted_service_types"]),
            json.dumps(g["excluded_service_types"]), g["therapy_day_definition"], g["effective_from"],
            g["effective_to"], g["plan_signed_date"], *_ev(text, g["evidence"])))
    for i, m in enumerate(x["measures"]):
        con.execute("INSERT INTO measures VALUES (" + ",".join("?" * 15) + ")", (
            f"{doc_id}:M{i}", doc_key, doc_id, mrn, m["instrument"], m["total_score"], m["item_detail"],
            m["completed_date"], m["source_form_id"], int(m["is_copy_or_import"]), *_ev(text, m["evidence"])))
    for i, o in enumerate(x["observations"]):
        con.execute("INSERT INTO observations VALUES (" + ",".join("?" * 14) + ")", (
            f"{doc_id}:O{i}", doc_key, doc_id, mrn, o["date"], o["domain"], o["observer_type"], o["observer"],
            o["summary"], *_ev(text, o["evidence"])))
    for i, a in enumerate(x["administrative_facts"]):
        con.execute("INSERT INTO admin_facts VALUES (" + ",".join("?" * 10) + ")", (
            f"{doc_id}:A{i}", doc_key, doc_id, mrn, a["fact"], *_ev(text, a["evidence"])))
    con.commit()
    return mrn
