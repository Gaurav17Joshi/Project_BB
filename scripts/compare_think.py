"""Try extraction with thinking off vs on for a few hard documents; compare service records to the closed-model run."""
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
os.environ["BACKBONE_BACKEND"] = "ollama"  # this experiment is about the local model
from backbone import config, ingest, llm, prompts, schema  # noqa: E402

DOCS = sys.argv[1:] or ["BH-D108_final_attendance_and_cancellation_register.txt", "BH-D113_family_therapy_2026-01-30.txt",
                        "early_appointment_status_export.txt", "BH-D112_draft_note_and_charge_extract_2026-01-27.txt"]
closed = sqlite3.connect(ROOT / "outputs" / "closed" / "abstraction.db")


def brief(sr):
    return sorted((r["service_date"], r["encounter_id"] or "-", r["service_type"][:10], r["source_role"][:12], r["attendance_status"],
                   r["patient_present"], tuple((s["start"], s["end"]) for s in r["patient_present_segments"]),
                   tuple((s["start"], s["end"]) for s in r["non_therapeutic_intervals"])) for r in sr)


for name in DOCS:
    text = ingest.normalise_text((config.DOCS_DIR / name).read_text(encoding="utf-8-sig"))
    ref = json.loads(closed.execute("SELECT e.json FROM extractions e JOIN documents d USING(doc_key) WHERE d.filename=?",
                                    (name,)).fetchone()[0])
    print(f"\n=== {name}")
    print("  closed:", brief(ref["service_records"]))
    for think in (None, "low"):
        out, rec = llm.call_json("think_test", config.EXTRACT_MODEL, prompts.EXTRACT_SYSTEM,
                                 prompts.EXTRACT_USER.format(name=name, text=text), schema.EXTRACTION, "x",
                                 reasoning_effort=think)
        b = brief(out["service_records"])
        print(f"  think={bool(think)!s:5} {rec['latency_s']:6.1f}s out={rec['output_tokens']} tok "
              f"{rec['gen_tokens_per_s']} tok/s  same_as_closed={b == brief(ref['service_records'])}")
        if b != brief(ref["service_records"]):
            print("     ", b)
