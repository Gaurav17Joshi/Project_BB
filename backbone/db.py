"""SQLite storage for the abstraction. Three layers:
1. documents / document_files / extractions  - what was read and what the model returned (cached)
2. source_records, corrections, goals, measures, observations, admin_facts - verified facts, one row per claim
3. contacts, contact_sources, measures_distinct, issues - reconciled by code (rebuilt cheaply per patient)
"""
import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  doc_key TEXT PRIMARY KEY,           -- sha256 of normalised text: duplicate copies share one row
  doc_id TEXT,                        -- printed ID (e.g. BH-D003) or file stem
  filename TEXT, text TEXT, n_chars INTEGER, ingested_at TEXT,
  patient_mrn TEXT, title TEXT, summary TEXT, is_copy INTEGER, copy_of TEXT
);
CREATE TABLE IF NOT EXISTS document_files (path TEXT PRIMARY KEY, doc_key TEXT, seen_at TEXT);
CREATE TABLE IF NOT EXISTS extractions (
  doc_key TEXT, model TEXT, prompt_version TEXT, json TEXT, created_at TEXT,
  latency_s REAL, input_tokens INTEGER, output_tokens INTEGER,
  PRIMARY KEY (doc_key, model, prompt_version)
);
CREATE TABLE IF NOT EXISTS patients (mrn TEXT PRIMARY KEY, name TEXT, dob TEXT);

CREATE TABLE IF NOT EXISTS source_records (
  rec_id TEXT PRIMARY KEY, doc_key TEXT, doc_id TEXT, patient_mrn TEXT,
  encounter_id TEXT, appointment_id TEXT, service_date TEXT, service_type TEXT, source_role TEXT,
  attendance_status TEXT, patient_present TEXT, modality TEXT, scheduled_start TEXT, scheduled_end TEXT,
  segments_json TEXT, breaks_json TEXT, stated_minutes INTEGER, clinicians_json TEXT, other_participants TEXT,
  signed_final INTEGER, signer_and_time TEXT, reason TEXT, notes TEXT,
  evidence TEXT, ev_start INTEGER, ev_end INTEGER, ev_line INTEGER, ev_match TEXT
);
CREATE TABLE IF NOT EXISTS corrections (
  corr_id TEXT PRIMARY KEY, doc_key TEXT, doc_id TEXT, patient_mrn TEXT, encounter_id TEXT, service_date TEXT,
  field TEXT, original_value TEXT, corrected_value TEXT, scope TEXT,
  evidence TEXT, ev_start INTEGER, ev_end INTEGER, ev_line INTEGER, ev_match TEXT
);
CREATE TABLE IF NOT EXISTS goals (
  goal_id TEXT PRIMARY KEY, doc_key TEXT, doc_id TEXT, patient_mrn TEXT,
  min_days INTEGER, min_minutes INTEGER, week_definition TEXT, counted_json TEXT, excluded_json TEXT,
  therapy_day_definition TEXT, effective_from TEXT, effective_to TEXT, plan_signed_date TEXT,
  evidence TEXT, ev_start INTEGER, ev_end INTEGER, ev_line INTEGER, ev_match TEXT
);
CREATE TABLE IF NOT EXISTS measures (
  meas_id TEXT PRIMARY KEY, doc_key TEXT, doc_id TEXT, patient_mrn TEXT, instrument TEXT, total_score REAL,
  item_detail TEXT, completed_date TEXT, source_form_id TEXT, is_copy INTEGER,
  evidence TEXT, ev_start INTEGER, ev_end INTEGER, ev_line INTEGER, ev_match TEXT
);
CREATE TABLE IF NOT EXISTS observations (
  obs_id TEXT PRIMARY KEY, doc_key TEXT, doc_id TEXT, patient_mrn TEXT, date TEXT, domain TEXT,
  observer_type TEXT, observer TEXT, summary TEXT,
  evidence TEXT, ev_start INTEGER, ev_end INTEGER, ev_line INTEGER, ev_match TEXT
);
CREATE TABLE IF NOT EXISTS admin_facts (
  fact_id TEXT PRIMARY KEY, doc_key TEXT, doc_id TEXT, patient_mrn TEXT, fact TEXT,
  evidence TEXT, ev_start INTEGER, ev_end INTEGER, ev_line INTEGER, ev_match TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
  contact_id TEXT PRIMARY KEY, patient_mrn TEXT, encounter_key TEXT, service_date TEXT, service_type TEXT,
  status TEXT, status_basis TEXT, patient_present TEXT,
  counts_toward_goal INTEGER, inclusion TEXT,       -- inclusion: included | excluded | uncertain
  inclusion_reason TEXT,
  minutes_lo INTEGER, minutes_hi INTEGER, minutes_basis TEXT, intervals_json TEXT, breaks_json TEXT,
  modality TEXT, reason TEXT, doc_ids_json TEXT
);
CREATE TABLE IF NOT EXISTS contact_sources (contact_id TEXT, rec_id TEXT, used_for TEXT);
CREATE TABLE IF NOT EXISTS measures_distinct (
  measure_key TEXT PRIMARY KEY, patient_mrn TEXT, instrument TEXT, completed_date TEXT, total_score REAL,
  item_detail TEXT, source_meas_ids_json TEXT, doc_ids_json TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS issues (
  issue_id TEXT PRIMARY KEY, patient_mrn TEXT, contact_id TEXT, kind TEXT, severity TEXT,
  description TEXT, resolution TEXT, evidence_json TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, started_at TEXT, seconds REAL, details_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_rec_patient ON source_records(patient_mrn, service_date);
CREATE INDEX IF NOT EXISTS ix_contacts_patient ON contacts(patient_mrn, service_date);
CREATE INDEX IF NOT EXISTS ix_obs_patient ON observations(patient_mrn, date);
"""

FACT_TABLES = ["source_records", "corrections", "goals", "measures", "observations", "admin_facts"]
DERIVED_TABLES = ["contacts", "contact_sources", "measures_distinct", "issues"]


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def rows(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]
