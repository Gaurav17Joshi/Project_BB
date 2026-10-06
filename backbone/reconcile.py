"""Deterministic reconciliation: verified source records -> one row per service contact.

Rules (documented in the README; every decision is written to status_basis / minutes_basis / issues):
- Records are clustered by encounter ID (linked through appointment IDs). Records without IDs join a
  same-day, same-type cluster with overlapping times, else stand alone. Non-therapy administrative
  records (outreach calls, scheduling) never merge into a therapy encounter.
- Evidence tiers: A = signed/attested clinical notes, attendance records, corrections, cancellation/no-show
  logs, telehealth logs; B = schedule exports, administrative copies, other; C = drafts/templates, billing.
  Status comes from the highest tier that speaks to attendance. Tier C never establishes that care occurred.
  A later document does not override an earlier one by date alone; only explicit corrections replace values.
- Minutes = union of patient-present segments minus documented non-therapeutic intervals, computed per
  tier-A source after applying explicit corrections. Disagreeing sources give a range [lo, hi] + an issue.
- Counting toward the goal uses the service types the treatment plan counts.
"""
import json
from collections import defaultdict
from datetime import date as _Date

from .verify import to_minutes

THERAPY_DEFAULT = ["individual_psychotherapy", "group_psychotherapy", "family_psychotherapy"]
NON_CLINICAL = {"scheduling_or_outreach", "authorization_or_administrative", "measure_or_questionnaire_review", "other"}
TIER_C = {"draft_or_template", "billing_record"}
TIER_B = {"schedule_or_status_export", "administrative_copy", "other"}
POSITIVE = {"attended_full", "attended_partial", "attended_unspecified"}
NEGATIVE = {"no_show", "patient_cancelled", "clinic_cancelled", "not_held"}
ATTENDANCE_ROLES = {"attendance_record", "correction", "telehealth_platform_log"}
ROLE_PRIORITY = ["clinical_note", "attendance_record", "telehealth_platform_log", "correction",
                 "cancellation_or_no_show_log", "schedule_or_status_export", "administrative_copy", "other",
                 "billing_record", "draft_or_template"]


def tier(rec) -> str:
    if rec["source_role"] in TIER_C:
        return "C"
    if rec["source_role"] in TIER_B:
        return "B"
    return "A"


def _interval_union(segs):
    segs = sorted((a, b) for a, b in segs if a is not None and b is not None and b > a)
    out = []
    for a, b in segs:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _overlap(segs, breaks):
    total = 0
    for a, b in segs:
        for c, d in breaks:
            total += max(0, min(b, d) - max(a, c))
    return total


def _fmt(m):
    return f"{m // 60:02d}:{m % 60:02d}"


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _cluster(records):
    uf = _UF()
    for r in records:
        uf.find(r["rec_id"])
        ids = [f"E:{r['encounter_id']}" if r["encounter_id"] else None,
               f"A:{r['appointment_id']}" if r["appointment_id"] else None]
        ids = [i for i in ids if i]
        if r["service_type"] in NON_CLINICAL:
            # administrative contacts keep their own identity even when they cite an encounter
            continue
        for i in ids:
            uf.union(r["rec_id"], f"{r['service_date']}|{i}")
    # records with no IDs: attach to a same-day same-type cluster with overlapping times
    by_root = defaultdict(list)
    for r in records:
        by_root[uf.find(r["rec_id"])].append(r)
    for r in records:
        if r["encounter_id"] or r["appointment_id"] or r["service_type"] in NON_CLINICAL:
            continue
        mine = _times(r)
        for root, members in list(by_root.items()):
            if root == uf.find(r["rec_id"]):
                continue
            m0 = members[0]
            if m0["service_date"] == r["service_date"] and m0["service_type"] == r["service_type"]:
                theirs = [t for m in members for t in _times(m)]
                if not mine or not theirs or any(a < d and c < b for a, b in mine for c, d in theirs):
                    uf.union(r["rec_id"], root)
                    break
    groups = defaultdict(list)
    for r in records:
        groups[uf.find(r["rec_id"])].append(r)
    return list(groups.values())


def _times(r):
    t = [(to_minutes(s["start"]), to_minutes(s["end"])) for s in r["segments"]]
    if r["scheduled_start"] and r["scheduled_end"]:
        t.append((to_minutes(r["scheduled_start"]), to_minutes(r["scheduled_end"])))
    return [x for x in t if None not in x]


def _evidence(r, quote=None):
    return {"doc_id": r["doc_id"], "line": r["ev_line"], "quote": quote or r["evidence"], "rec_id": r["rec_id"]}


def rebuild_patient(con, mrn: str):
    for t in ("contacts", "issues", "measures_distinct"):
        con.execute(f"DELETE FROM {t} WHERE patient_mrn=?", (mrn,))
    con.execute("DELETE FROM contact_sources WHERE contact_id LIKE ?", (f"{mrn}/%",))

    recs = [dict(r) for r in con.execute("SELECT * FROM source_records WHERE patient_mrn=?", (mrn,))]
    for r in recs:
        r["segments"] = json.loads(r["segments_json"])
        r["breaks"] = json.loads(r["breaks_json"])
    corrections = [dict(c) for c in con.execute("SELECT * FROM corrections WHERE patient_mrn=?", (mrn,))]
    # Only participation goals with a numeric threshold define what counts; narrative goals are ignored here.
    goals = [dict(g) for g in con.execute("SELECT * FROM goals WHERE patient_mrn=? AND "
                                          "(min_days IS NOT NULL OR min_minutes IS NOT NULL)", (mrn,))]
    issues = []

    def issue(kind, severity, description, contact_id=None, resolution=None, evidence=()):
        issues.append((f"{mrn}/I{len(issues) + 1:03d}", mrn, contact_id, kind, severity, description, resolution,
                       json.dumps(list(evidence))))

    for c in corrections:
        if c["ev_match"] == "missing":
            issue("unverified_evidence", "medium", f"Correction {c['corr_id']} quote not found in source.")

    def _valid_date(s):
        try:
            _Date.fromisoformat(s or "")
            return True
        except ValueError:
            return False
    for r in [r for r in recs if not _valid_date(r["service_date"])]:
        issue("invalid_date", "medium", f"Record {r['rec_id']} has service date '{r['service_date']}', not a single "
              f"calendar date; left out of contacts.", evidence=[_evidence(r)])
    recs = [r for r in recs if _valid_date(r["service_date"])]

    for cluster in _cluster(recs):
        _build_contact(con, mrn, cluster, corrections, goals, issue)

    _build_measures(con, mrn, issue)
    for r in recs:
        if r["ev_match"] == "missing":
            issue("unverified_evidence", "medium", f"Record {r['rec_id']} evidence quote not found in source text.")
    con.executemany("INSERT INTO issues VALUES (?,?,?,?,?,?,?,?)", issues)
    con.commit()


def _goal_for(goals, date):
    live = [g for g in goals if (not g["effective_from"] or g["effective_from"] <= date)
            and (not g["effective_to"] or date <= g["effective_to"])]
    live.sort(key=lambda g: (g["effective_from"] or "", g["plan_signed_date"] or ""))
    return live[-1] if live else None


def _build_contact(con, mrn, cluster, corrections, goals, issue):
    cluster.sort(key=lambda r: ROLE_PRIORITY.index(r["source_role"]) if r["source_role"] in ROLE_PRIORITY else 99)
    date = sorted({r["service_date"] for r in cluster})[0]
    enc = next((r["encounter_id"] for r in cluster if r["encounter_id"]), None)
    appt = next((r["appointment_id"] for r in cluster if r["appointment_id"]), None)
    if cluster[0]["service_type"] in NON_CLINICAL or not (enc or appt):
        enc_key = f"{cluster[0]['service_type']}#{cluster[0]['rec_id']}"
    else:
        enc_key = enc or appt
    cid = f"{mrn}/{date}/{enc_key}"
    if con.execute("SELECT 1 FROM contacts WHERE contact_id=?", (cid,)).fetchone():
        enc_key += f"#{cluster[0]['rec_id']}"
        cid = f"{mrn}/{date}/{enc_key}"
    dates = {r["service_date"] for r in cluster}
    if len(dates) > 1:
        issue("date_conflict", "high", f"Records for {enc_key} give different service dates {sorted(dates)}.", cid,
              evidence=[_evidence(r) for r in cluster])

    # service type: majority among tier A/B records, ties broken by role priority (cluster is sorted)
    typed = [r["service_type"] for r in cluster if tier(r) != "C"] or [r["service_type"] for r in cluster]
    stype = max(dict.fromkeys(typed), key=typed.count)
    if len(set(typed)) > 1:
        issue("service_type_conflict", "medium", f"{enc_key}: sources disagree on service type {sorted(set(typed))}; using {stype}.", cid,
              evidence=[_evidence(r) for r in cluster])

    # ---- attendance status ----
    status, basis, certainty = "unknown", "no source states attendance", "uncertain"
    for t in ("A", "B"):
        speak = [r for r in cluster if tier(r) == t and (r["attendance_status"] in POSITIVE | NEGATIVE)]
        if not speak:
            continue
        pos = [r for r in speak if r["attendance_status"] in POSITIVE]
        neg = [r for r in speak if r["attendance_status"] in NEGATIVE]
        if pos and neg:
            status, certainty = "disputed", "uncertain"
            basis = f"tier-{t} sources disagree: attended per {[r['doc_id'] for r in pos]}, not per {[r['doc_id'] for r in neg]}"
            issue("attendance_conflict", "high", f"{enc_key} on {date}: {basis}.", cid,
                  evidence=[_evidence(r) for r in speak])
        elif pos:
            status = "attended"
            certainty = "certain" if t == "A" else "uncertain"
            basis = f"attendance stated by tier-{t} source(s) {sorted({r['doc_id'] for r in pos})}"
            if t == "B" and stype not in NON_CLINICAL:
                issue("weak_attendance_evidence", "medium",
                      f"{enc_key} on {date}: attendance supported only by schedule/copy records.", cid,
                      evidence=[_evidence(r) for r in pos])
        else:
            status = sorted({r["attendance_status"] for r in neg})[0]
            certainty = "certain" if t == "A" else "uncertain"
            basis = f"{status} per tier-{t} source(s) {sorted({r['doc_id'] for r in neg})}"
        break
    lower_pos = [r for r in cluster if tier(r) == "C"]
    if lower_pos and status != "attended":
        issue("draft_or_billing_without_service", "high",
              f"{enc_key} on {date}: draft/template or billing record exists, but signed records show '{status}'. "
              f"Not counted: drafts and charges do not establish that care occurred.", cid,
              resolution=f"Followed {basis}.", evidence=[_evidence(r) for r in lower_pos])

    pres_vals = [r["patient_present"] for r in cluster if tier(r) == "A"] or [r["patient_present"] for r in cluster]
    present = "yes" if "yes" in pres_vals else "partial" if "partial" in pres_vals else "no" if "no" in pres_vals else "unknown"

    # ---- minutes ----
    breaks_src = [(r, b) for r in cluster if tier(r) != "C" for b in r["breaks"]]
    breaks = _interval_union([(to_minutes(b["start"]), to_minutes(b["end"])) for _, b in breaks_src])
    my_corr = [c for c in corrections if (c["encounter_id"] and c["encounter_id"] in (enc, appt))
               or (not c["encounter_id"] and c["service_date"] == date)]
    candidates = []  # (minutes, rec, intervals, note)
    # Arrival/departure: attendance-type records outrank narrative notes within a tier (notes often restate the
    # scheduled slot); notes are used when no attendance-type record gives times.
    passes = [(t, att) for t in ("A", "B") for att in (True, False)]
    for t, att in passes:
        for r in cluster:
            if tier(r) != t or not r["segments"] or (r["source_role"] in ATTENDANCE_ROLES) != att:
                continue
            segs = [[to_minutes(s["start"]), to_minutes(s["end"])] for s in r["segments"]]
            notes = []
            if r["source_role"] != "correction":
                for c in my_corr:
                    old, new = to_minutes(c["original_value"]), to_minutes(c["corrected_value"])
                    if new is None:
                        continue
                    if c["field"] == "departure" and (old is None or segs[-1][1] == old):
                        notes.append(f"departure {_fmt(segs[-1][1])}->{c['corrected_value']} per correction {c['doc_id']}")
                        segs[-1][1] = new
                    elif c["field"] == "arrival" and (old is None or segs[0][0] == old):
                        notes.append(f"arrival {_fmt(segs[0][0])}->{c['corrected_value']} per correction {c['doc_id']}")
                        segs[0][0] = new
            u = _interval_union(segs)
            gross = sum(b - a for a, b in u)
            off = _overlap(u, breaks)
            candidates.append((gross - off, r, u, notes, gross, off))
            if r["stated_minutes"] is not None and r["stated_minutes"] != gross - off and r["stated_minutes"] != gross:
                issue("stated_minutes_mismatch", "low",
                      f"{r['doc_id']} states {r['stated_minutes']} min but its intervals give {gross - off} min "
                      f"after breaks ({gross} gross).", cid, evidence=[_evidence(r)])
        if candidates:
            break
    if not candidates:
        stated = [(r["stated_minutes"], r) for r in cluster if tier(r) != "C" and r["stated_minutes"] is not None]
        for m, r in stated:
            candidates.append((m, r, [], ["stated total; no intervals documented"], m, 0))

    # Schedule-echo rule: if sources disagree and some give exactly the booked slot while others give different
    # times, the slot-matching values are treated as a copied schedule default (the failure mode BH-D102/BH-D103
    # document for rosters) and set aside. Logged as an issue so a reviewer can override.
    slots = {(to_minutes(r["scheduled_start"]), to_minutes(r["scheduled_end"])) for r in cluster
             if to_minutes(r["scheduled_start"]) is not None and to_minutes(r["scheduled_end"]) is not None}
    if len({c[0] for c in candidates}) > 1 and slots:
        echo = lambda c: bool(c[2]) and (c[2][0][0], c[2][-1][1]) in slots  # noqa: E731
        kept = [c for c in candidates if not echo(c)]
        dropped = [c for c in candidates if echo(c)]
        if kept and dropped:
            issue("schedule_echo_discarded", "medium",
                  f"{enc_key} on {date}: {', '.join(c[1]['doc_id'] for c in dropped)} gives exactly the scheduled slot as "
                  f"patient time while {', '.join(c[1]['doc_id'] for c in kept)} records different actual times; "
                  f"the schedule-matching value was set aside.", cid,
                  resolution="Used the non-schedule times; review if the schedule-matching source is authoritative.",
                  evidence=[_evidence(c[1]) for c in dropped + kept])
            candidates = kept

    if candidates:
        vals = sorted({c[0] for c in candidates})
        lo, hi = vals[0], vals[-1]
        parts = []
        for m, r, u, notes, gross, off in candidates:
            iv = ", ".join(f"{_fmt(a)}-{_fmt(b)}" for a, b in u) or "n/a"
            parts.append(f"{r['doc_id']}: {iv} = {gross} min" + (f" - {off} min break" if off else "")
                         + f" = {m} min" + (f" ({'; '.join(notes)})" if notes else ""))
        mbasis = " | ".join(parts)
        intervals = candidates[0][2]
        if lo != hi:
            issue("duration_conflict", "high",
                  f"{enc_key} on {date}: final records disagree on patient-present time ({lo}-{hi} min). "
                  f"No correction resolves it; reported as a range.", cid,
                  resolution="Unresolved: needs an attestation/correction from the treating clinicians.",
                  evidence=[_evidence(c[1], c[1]['segments'][0]['evidence'] if c[1]['segments'] else None) for c in candidates])
    else:
        lo = hi = None
        mbasis, intervals = "no patient-present intervals or totals documented", []

    # ---- inclusion toward the treatment-plan goal ----
    goal = _goal_for(goals, date)
    counted_types = json.loads(goal["counted_json"]) if goal and goal["counted_json"] not in (None, "[]") else THERAPY_DEFAULT
    if stype not in counted_types:
        inclusion, reason = "excluded", f"service type {stype} does not count toward the plan goal"
    elif status == "attended" and present in ("yes", "partial"):
        inclusion = "included" if certainty == "certain" else "uncertain"
        reason = f"patient-present {stype}; {basis}"
    elif status == "attended":
        inclusion, reason = "uncertain", f"attended per {basis} but patient presence is '{present}'"
    elif status in ("disputed", "unknown"):
        inclusion, reason = "uncertain", basis
    else:
        inclusion, reason = "excluded", basis
    if inclusion == "included" and lo is None:
        issue("duration_missing", "medium", f"{enc_key} on {date}: counted contact has no documented duration.", cid)
    if inclusion == "excluded" and stype in counted_types:
        lo = hi = 0 if lo is not None else None

    if any(r["source_role"] == "administrative_copy" for r in cluster):
        copies = [r for r in cluster if r["source_role"] == "administrative_copy"]
        issue("duplicate_copy", "info", f"{enc_key} on {date}: {', '.join(r['doc_id'] for r in copies)} is a resent/imported "
              f"copy of an existing record; merged into the same contact, not counted again.", cid,
              resolution="merged", evidence=[_evidence(r) for r in copies])
    same_role = defaultdict(list)
    for r in cluster:
        if r["source_role"] == "clinical_note":
            same_role[r["service_date"]].append(r)
    for d, notes in same_role.items():
        if len(notes) > 1:
            issue("multiple_notes_one_encounter", "info",
                  f"{enc_key} on {d}: {len(notes)} clinical notes ({', '.join(n['doc_id'] for n in notes)}) describe the "
                  f"same encounter; counted once.", cid, resolution="merged", evidence=[_evidence(n) for n in notes])

    modality = next((r["modality"] for r in cluster if r["modality"] != "unknown"), "unknown")
    reason_txt = next((r["reason"] for r in cluster if r["reason"]), None)
    con.execute("INSERT INTO contacts VALUES (" + ",".join("?" * 19) + ")", (
        cid, mrn, enc_key, date, stype, status, basis, present, int(inclusion == "included"), inclusion, reason,
        lo, hi, mbasis, json.dumps([[_fmt(a), _fmt(b)] for a, b in intervals]),
        json.dumps([[_fmt(a), _fmt(b)] for a, b in breaks]), modality, reason_txt,
        json.dumps(sorted({r["doc_id"] for r in cluster}))))
    for r in cluster:
        con.execute("INSERT INTO contact_sources VALUES (?,?,?)", (cid, r["rec_id"], f"tier {tier(r)} / {r['source_role']}"))


def _build_measures(con, mrn, issue):
    rows = [dict(r) for r in con.execute("SELECT * FROM measures WHERE patient_mrn=?", (mrn,))]
    groups = defaultdict(list)
    for m in rows:
        groups[(m["instrument"].upper().replace(" ", ""), m["completed_date"])].append(m)
    for (inst, date), ms in sorted(groups.items(), key=lambda kv: kv[0][1] or ""):
        scores = sorted({m["total_score"] for m in ms if m["total_score"] is not None})
        if len(scores) > 1:
            issue("measure_conflict", "high", f"{inst} completed {date}: sources report different scores {scores}.",
                  evidence=[{"doc_id": m["doc_id"], "line": m["ev_line"], "quote": m["evidence"]} for m in ms])
        note = None
        if len(ms) > 1:
            note = (f"{len(ms)} records of one administration (" + ", ".join(
                f"{m['doc_id']}{' [copy/import]' if m['is_copy'] else ''}" for m in ms) + "); counted once")
            issue("duplicate_measure", "info", f"{inst} completed {date}: {note}.", resolution="merged",
                  evidence=[{"doc_id": m["doc_id"], "line": m["ev_line"], "quote": m["evidence"]} for m in ms])
        item = next((m["item_detail"] for m in ms if m["item_detail"]), None)
        con.execute("INSERT INTO measures_distinct VALUES (?,?,?,?,?,?,?,?,?)", (
            f"{mrn}/{inst}/{date}", mrn, inst, date, scores[0] if len(scores) == 1 else None, item,
            json.dumps([m["meas_id"] for m in ms]), json.dumps(sorted({m["doc_id"] for m in ms})), note))
