"""Deterministic queries over the reconciled abstraction. Every number an answer uses comes from here.

Uncertainty is carried as ranges: `lo` counts only contacts whose inclusion is established and the low
end of any disputed duration; `hi` adds uncertain contacts and the high end of disputed durations.
"""
import json
from datetime import date as Date, timedelta

from .db import rows
from .reconcile import THERAPY_DEFAULT


def _d(s):
    return Date.fromisoformat(s)


def find_patient(con, query: str):
    q = f"%{query.strip().lower()}%"
    return rows(con, "SELECT mrn, name, dob FROM patients WHERE lower(name) LIKE ? OR lower(mrn) LIKE ?", (q, q))


def list_patients(con):
    out = []
    for p in rows(con, "SELECT * FROM patients ORDER BY mrn"):
        c = rows(con, "SELECT min(service_date) a, max(service_date) b, count(*) n FROM contacts WHERE patient_mrn=?", (p["mrn"],))[0]
        n_docs = rows(con, "SELECT count(*) n FROM documents WHERE patient_mrn=?", (p["mrn"],))[0]["n"]
        out.append({**p, "first_contact": c["a"], "last_contact": c["b"], "contacts": c["n"], "documents": n_docs})
    return out


def _resolve(con, patient):
    if not patient:
        ps = rows(con, "SELECT mrn FROM patients")
        if len(ps) == 1:
            return ps[0]["mrn"]
        raise ValueError("patient required (several patients in the collection)")
    if rows(con, "SELECT 1 FROM patients WHERE mrn=?", (patient.upper(),)):
        return patient.upper()
    m = find_patient(con, patient)
    if len(m) != 1:
        raise ValueError(f"patient '{patient}' matched {len(m)} patients: {[x['mrn'] for x in m]}")
    return m[0]["mrn"]


def treatment_goals(con, patient=None):
    mrn = _resolve(con, patient)
    gs = rows(con, "SELECT goal_id, doc_id, min_days, min_minutes, week_definition, counted_json, excluded_json, "
                   "therapy_day_definition, effective_from, effective_to, plan_signed_date, evidence, ev_line "
                   "FROM goals WHERE patient_mrn=? AND (min_days IS NOT NULL OR min_minutes IS NOT NULL) "
                   "ORDER BY effective_from, plan_signed_date", (mrn,))
    for g in gs:
        g["counted_service_types"] = json.loads(g.pop("counted_json") or "[]")
        g["excluded_service_types"] = json.loads(g.pop("excluded_json") or "[]")
    distinct = {(g["min_days"], g["min_minutes"], g["effective_from"], g["effective_to"]) for g in gs}
    return {"patient_mrn": mrn, "goals": gs, "distinct_goal_versions": len(distinct),
            "plan_change_documented": len(distinct) > 1}


def _period(con, mrn, start, end):
    if start and end:
        return start, end
    g = rows(con, "SELECT min(effective_from) a, max(effective_to) b FROM goals WHERE patient_mrn=? AND "
                  "(min_days IS NOT NULL OR min_minutes IS NOT NULL)", (mrn,))[0]
    c = rows(con, "SELECT min(service_date) a, max(service_date) b FROM contacts WHERE patient_mrn=?", (mrn,))[0]
    return start or g["a"] or c["a"], end or g["b"] or c["b"]


def _goal_at(con, mrn, day):
    gs = treatment_goals(con, mrn)["goals"]
    live = [g for g in gs if (not g["effective_from"] or g["effective_from"] <= day) and (not g["effective_to"] or day <= g["effective_to"])]
    return live[-1] if live else None


def _contacts(con, mrn, start, end):
    cs = rows(con, "SELECT * FROM contacts WHERE patient_mrn=? AND service_date BETWEEN ? AND ? ORDER BY service_date, encounter_key",
              (mrn, start, end))
    for c in cs:
        c["doc_ids"] = json.loads(c.pop("doc_ids_json"))
        c["intervals"] = json.loads(c.pop("intervals_json"))
        c["breaks"] = json.loads(c.pop("breaks_json"))
        c["issues"] = [i["issue_id"] for i in rows(con, "SELECT issue_id FROM issues WHERE contact_id=?", (c["contact_id"],))]
    return cs


def _brief(c):
    return {k: c[k] for k in ("contact_id", "service_date", "service_type", "status", "inclusion", "minutes_lo",
                              "minutes_hi", "intervals", "breaks", "minutes_basis", "doc_ids", "issues")}


def contacts(con, patient=None, start=None, end=None, service_types=None, inclusion=None):
    """All reconciled contacts (therapy and non-therapy) with status, inclusion decision, minutes and sources."""
    mrn = _resolve(con, patient)
    start, end = _period(con, mrn, start, end)
    cs = _contacts(con, mrn, start, end)
    if service_types:
        cs = [c for c in cs if c["service_type"] in service_types]
    if inclusion:
        cs = [c for c in cs if c["inclusion"] in inclusion]
    return {"patient_mrn": mrn, "period": [start, end], "contacts": cs}


def session_counts(con, patient=None, start=None, end=None):
    """Attended therapy sessions by service type, total, distinct days; plus excluded/uncertain records and why."""
    mrn = _resolve(con, patient)
    start, end = _period(con, mrn, start, end)
    goal = _goal_at(con, mrn, start)
    therapy = goal["counted_service_types"] if goal and goal["counted_service_types"] else THERAPY_DEFAULT
    cs = _contacts(con, mrn, start, end)
    inc = [c for c in cs if c["inclusion"] == "included"]
    unc = [c for c in cs if c["inclusion"] == "uncertain"]
    by_type = {t: {"established": sum(c["service_type"] == t for c in inc),
                   "possible_additional": sum(c["service_type"] == t for c in unc)} for t in therapy}
    days = sorted({c["service_date"] for c in inc})
    days_hi = sorted({c["service_date"] for c in inc + unc})
    return {
        "patient_mrn": mrn, "period": [start, end], "therapy_service_types": therapy,
        "by_type": by_type,
        "total_established": len(inc), "total_possible": len(inc) + len(unc),
        "distinct_therapy_days_established": len(days), "distinct_therapy_days_possible": len(days_hi),
        "therapy_days": days,
        "included_contacts": [_brief(c) for c in inc],
        "uncertain_contacts": [_brief(c) | {"why": c["inclusion_reason"]} for c in unc],
        "not_counted": [{"contact_id": c["contact_id"], "service_type": c["service_type"], "status": c["status"],
                         "why": c["inclusion_reason"], "doc_ids": c["doc_ids"]} for c in cs if c["inclusion"] == "excluded"],
        "method": "One contact per reconciled encounter (duplicate notes/copies merged). Counted if the service type "
                  "counts under the treatment plan and tier-A records establish the patient attended.",
    }


def _weeks(start, end):
    s, e = _d(start), _d(end)
    w = s - timedelta(days=s.weekday())
    while w <= e:
        yield w, w + timedelta(days=6), max(w, s), min(w + timedelta(days=6), e)
        w += timedelta(days=7)


def weekly_summary(con, patient=None, start=None, end=None, service_types=None):
    """Per Monday-Sunday week: therapy days, minutes (lo-hi) and hours, per-service-type subtotals, contributing
    contacts, plus overall totals. Pass service_types (e.g. ["group_psychotherapy"]) to total only those types."""
    mrn = _resolve(con, patient)
    start, end = _period(con, mrn, start, end)
    cs = [c for c in _contacts(con, mrn, start, end) if c["inclusion"] in ("included", "uncertain")]
    if service_types:
        cs = [c for c in cs if c["service_type"] in service_types]
    weeks, tot_lo, tot_hi = [], 0, 0
    for ws, we, cs_, ce in _weeks(start, end):
        wk = [c for c in cs if cs_.isoformat() <= c["service_date"] <= ce.isoformat()]
        inc = [c for c in wk if c["inclusion"] == "included"]
        lo = sum(c["minutes_lo"] or 0 for c in inc)
        hi = sum(c["minutes_hi"] or 0 for c in wk)
        tot_lo, tot_hi = tot_lo + lo, tot_hi + hi
        weeks.append({
            "week": f"{ws.isoformat()} to {we.isoformat()}",
            "days_in_review_period": f"{cs_.isoformat()} to {ce.isoformat()}" + (" (partial week)" if (cs_, ce) != (ws, we) else ""),
            "therapy_days_established": len({c["service_date"] for c in inc}),
            "therapy_days_possible": len({c["service_date"] for c in wk}),
            "minutes_lo": lo, "minutes_hi": hi,
            "hours_lo": round(lo / 60, 2), "hours_hi": round(hi / 60, 2),
            "minutes_settled": lo == hi,
            "by_service_type": {t: {"contacts": sum(c["service_type"] == t for c in wk),
                                    "minutes_lo": sum(c["minutes_lo"] or 0 for c in inc if c["service_type"] == t),
                                    "minutes_hi": sum(c["minutes_hi"] or 0 for c in wk if c["service_type"] == t)}
                                for t in sorted({c["service_type"] for c in wk})},
            "contacts": [{"contact_id": c["contact_id"], "date": c["service_date"], "type": c["service_type"],
                          "inclusion": c["inclusion"], "minutes": c["minutes_lo"] if c["minutes_lo"] == c["minutes_hi"]
                          else f"{c['minutes_lo']}-{c['minutes_hi']}", "calculation": c["minutes_basis"],
                          "doc_ids": c["doc_ids"], "issues": c["issues"]} for c in wk],
        })
    return {"patient_mrn": mrn, "period": [start, end], "service_types_filter": service_types, "weeks": weeks,
            "total_minutes_lo": tot_lo, "total_minutes_hi": tot_hi,
            "total_hours_lo": round(tot_lo / 60, 2), "total_hours_hi": round(tot_hi / 60, 2),
            "method": "Minutes per contact = patient-present intervals minus documented non-therapeutic breaks/disconnects, "
                      "after explicit corrections. Only service types counted by the treatment plan are included."}


def goal_compliance(con, patient=None, start=None, end=None):
    """Per week: goal in effect, days and minutes vs thresholds, verdict met / not_met / indeterminate."""
    ws = weekly_summary(con, patient, start, end)
    mrn = ws["patient_mrn"]
    out = []
    for w in ws["weeks"]:
        wstart = w["days_in_review_period"][:10]
        g = _goal_at(con, mrn, wstart)
        if not g:
            out.append({**{k: w[k] for k in ("week", "days_in_review_period")}, "verdict": "no_goal_in_effect"})
            continue
        D, M = g["min_days"] or 0, g["min_minutes"] or 0
        days_ok_lo, days_ok_hi = w["therapy_days_established"] >= D, w["therapy_days_possible"] >= D
        min_ok_lo, min_ok_hi = w["minutes_lo"] >= M, w["minutes_hi"] >= M
        if days_ok_lo and min_ok_lo:
            verdict = "met"
        elif not days_ok_hi or not min_ok_hi:
            verdict = "not_met"
        else:
            verdict = "indeterminate"
        reasons = []
        if not days_ok_hi:
            reasons.append(f"{w['therapy_days_possible']} therapy days < {D}")
        if not min_ok_hi:
            reasons.append(f"{w['minutes_hi']} min < {M}")
        if verdict == "indeterminate":
            reasons.append(f"minutes range {w['minutes_lo']}-{w['minutes_hi']} straddles {M}" if not min_ok_lo else
                           f"days range {w['therapy_days_established']}-{w['therapy_days_possible']} straddles {D}")
        out.append({"week": w["week"], "days_in_review_period": w["days_in_review_period"],
                    "goal": {"min_days": D, "min_minutes": M, "goal_id": g["goal_id"], "doc_id": g["doc_id"],
                             "evidence": g["evidence"]},
                    "therapy_days": w["therapy_days_established"] if w["therapy_days_established"] == w["therapy_days_possible"]
                    else f"{w['therapy_days_established']}-{w['therapy_days_possible']}",
                    "minutes": w["minutes_lo"] if w["minutes_settled"] else f"{w['minutes_lo']}-{w['minutes_hi']}",
                    "verdict": verdict, "why": "; ".join(reasons) or "both thresholds met",
                    "contacts": w["contacts"]})
    return {"patient_mrn": mrn, "period": ws["period"], "weeks": out}


def day_detail(con, patient=None, date=None):
    """Everything recorded for one date: reconciled contacts, each underlying source record with evidence, issues."""
    mrn = _resolve(con, patient)
    cs = _contacts(con, mrn, date, date)
    for c in cs:
        c["sources"] = rows(con, "SELECT s.rec_id, s.doc_id, s.source_role, s.attendance_status, s.patient_present, "
                                 "s.segments_json, s.breaks_json, s.stated_minutes, s.signed_final, s.modality, s.notes, "
                                 "s.reason, s.evidence, s.ev_line, cs.used_for FROM contact_sources cs "
                                 "JOIN source_records s USING(rec_id) WHERE cs.contact_id=?", (c["contact_id"],))
        for s in c["sources"]:
            s["segments"] = [(x["start"], x["end"], x["evidence"]) for x in json.loads(s.pop("segments_json"))]
            s["breaks"] = [(x["start"], x["end"], x["evidence"]) for x in json.loads(s.pop("breaks_json"))]
        c["issue_details"] = rows(con, "SELECT * FROM issues WHERE contact_id=?", (c["contact_id"],))
    corr = rows(con, "SELECT corr_id, doc_id, encounter_id, field, original_value, corrected_value, scope, evidence, ev_line "
                     "FROM corrections WHERE patient_mrn=? AND service_date=?", (mrn, date))
    therapy = [c for c in cs if c["inclusion"] in ("included", "uncertain")]
    return {"patient_mrn": mrn, "date": date, "contacts": cs, "corrections": corr,
            "therapy_contacts_established": sum(c["inclusion"] == "included" for c in therapy),
            "therapy_contacts_possible": len(therapy),
            "patient_therapy_minutes_lo": sum(c["minutes_lo"] or 0 for c in therapy if c["inclusion"] == "included"),
            "patient_therapy_minutes_hi": sum(c["minutes_hi"] or 0 for c in therapy)}


def measures(con, patient=None):
    """Distinct standardized-measure administrations (duplicates/imports merged) with their source records."""
    mrn = _resolve(con, patient)
    ds = rows(con, "SELECT * FROM measures_distinct WHERE patient_mrn=? ORDER BY completed_date", (mrn,))
    for d in ds:
        ids = json.loads(d.pop("source_meas_ids_json"))
        d["doc_ids"] = json.loads(d.pop("doc_ids_json"))
        d["records"] = rows(con, f"SELECT meas_id, doc_id, total_score, completed_date, source_form_id, is_copy, evidence, ev_line "
                                 f"FROM measures WHERE meas_id IN ({','.join('?' * len(ids))})", ids)
    for a, b in zip(ds, ds[1:]):
        if a["instrument"] == b["instrument"] and a["total_score"] is not None and b["total_score"] is not None:
            b["change_from_previous"] = b["total_score"] - a["total_score"]
    return {"patient_mrn": mrn, "distinct_administrations": ds}


def observations(con, patient=None, domains=None, start=None, end=None, observer_types=None):
    """Clinical observations (symptoms, functioning, safety, progress) with verbatim evidence, chronological."""
    mrn = _resolve(con, patient)
    start, end = _period(con, mrn, start, end)
    os_ = rows(con, "SELECT obs_id, date, domain, observer_type, observer, summary, doc_id, evidence, ev_line FROM observations "
                    "WHERE patient_mrn=? AND date BETWEEN ? AND ? ORDER BY date, doc_id", (mrn, start, end))
    if domains:
        os_ = [o for o in os_ if o["domain"] in domains]
    if observer_types:
        os_ = [o for o in os_ if o["observer_type"] in observer_types]
    return {"patient_mrn": mrn, "observations": os_}


def issues(con, patient=None, kinds=None):
    """Open conflicts, gaps, merged duplicates and the basis of each resolution."""
    mrn = _resolve(con, patient)
    iss = rows(con, "SELECT * FROM issues WHERE patient_mrn=? ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' "
                    "THEN 1 WHEN 'low' THEN 2 ELSE 3 END, issue_id", (mrn,))
    for i in iss:
        i["evidence"] = json.loads(i.pop("evidence_json"))
    known = {i["kind"] for i in iss}
    if kinds and set(kinds) & known:  # ignore empty / unknown filters such as ["all"]
        iss = [i for i in iss if i["kind"] in kinds]
    return {"patient_mrn": mrn, "issues": iss}


# ---------- collection-wide ----------

def compliance_all(con, start=None, end=None):
    """Weekly goal verdicts for every patient."""
    out = []
    for p in rows(con, "SELECT mrn, name FROM patients ORDER BY mrn"):
        gc = goal_compliance(con, p["mrn"], start, end)
        out.append({"patient_mrn": p["mrn"], "name": p["name"],
                    "weeks": [{k: w.get(k) for k in ("week", "days_in_review_period", "therapy_days", "minutes", "verdict", "why")}
                              for w in gc["weeks"]]})
    return {"patients": out}


def consecutive_weeks_below(con, n=2, start=None, end=None):
    """Patients with n consecutive weeks below goal: definite (all not_met) vs depends on unresolved documentation."""
    definite, depends = [], []
    for p in compliance_all(con, start, end)["patients"]:
        ws = p["weeks"]
        for i in range(len(ws) - n + 1):
            run = ws[i:i + n]
            vs = [w["verdict"] for w in run]
            if all(v == "not_met" for v in vs):
                definite.append({"patient_mrn": p["patient_mrn"], "name": p["name"], "weeks": run})
                break
        else:
            for i in range(len(ws) - n + 1):
                run = ws[i:i + n]
                vs = [w["verdict"] for w in run]
                if all(v in ("not_met", "indeterminate") for v in vs) and "indeterminate" in vs:
                    depends.append({"patient_mrn": p["patient_mrn"], "name": p["name"], "weeks": run})
                    break
    return {"n_consecutive": n, "definite": definite, "depends_on_unresolved_documentation": depends}


def plan_change_comparison(con, patient=None, change_date=None):
    """Care delivered by service type before vs after a treatment-plan change (or a given date)."""
    mrn = _resolve(con, patient)
    g = treatment_goals(con, mrn)
    starts = sorted({x["effective_from"] for x in g["goals"] if x["effective_from"]})
    documented = g["plan_change_documented"]
    if not change_date:
        if not documented or len(starts) < 2:
            return {"patient_mrn": mrn, "plan_change_documented": False,
                    "note": "Only one treatment-plan goal version is documented, so there is no plan change to compare "
                            "around. Report that no change is documented; do not treat the initial plan as a change.",
                    "goals": g["goals"]}
        change_date = starts[1]
    elif not documented:
        return {"patient_mrn": mrn, "plan_change_documented": False, "requested_change_date": change_date,
                "note": "No treatment-plan change is documented for this patient (one goal version). A comparison around "
                        "an arbitrary date would not describe a plan change. Report that no change is documented; use "
                        "weekly_summary if the user explicitly wants a before/after split at a given date.",
                "goals": g["goals"]}
    start, end = _period(con, mrn, None, None)
    before_end = (_d(change_date) - timedelta(days=1)).isoformat()
    res = {}
    for label, a, b in (("before", start, before_end), ("after", change_date, end)):
        cs = [c for c in _contacts(con, mrn, a, b) if c["inclusion"] in ("included", "uncertain")]
        n_weeks = max(1, ((_d(b) - _d(a)).days + 1) / 7)
        by = {}
        for c in cs:
            t = by.setdefault(c["service_type"], {"contacts": 0, "minutes_lo": 0, "minutes_hi": 0})
            t["contacts"] += 1
            t["minutes_lo"] += (c["minutes_lo"] or 0) if c["inclusion"] == "included" else 0
            t["minutes_hi"] += c["minutes_hi"] or 0
        for t in by.values():
            t["minutes_per_week_lo"] = round(t["minutes_lo"] / n_weeks, 1)
            t["minutes_per_week_hi"] = round(t["minutes_hi"] / n_weeks, 1)
        res[label] = {"period": [a, b], "weeks": round(n_weeks, 2), "by_service_type": by}
    return {"patient_mrn": mrn, "change_date": change_date, **res}


def get_document_passage(con, doc_id, quote=None, line=None, context=2):
    """Return numbered lines from a source document around a quote or line number."""
    d = rows(con, "SELECT doc_id, filename, text FROM documents WHERE doc_id=? OR filename=?", (doc_id, doc_id))
    if not d:
        return {"error": f"unknown document {doc_id}"}
    lines = d[0]["text"].split("\n")
    out = {"doc_id": d[0]["doc_id"], "filename": d[0]["filename"]}
    if quote:
        from .verify import locate
        ln, match = locate(d[0]["text"], quote)[2:]
        out["quote_found"] = match in ("exact", "normalised")
        line = ln if out["quote_found"] else None
    if not line:  # no anchor (or quote not found): return the whole document, capped
        out["lines"] = {i: l for i, l in enumerate(lines[:120], 1)}
        return out
    lo, hi = max(1, line - context), min(len(lines), line + context)
    out["lines"] = {i: lines[i - 1] for i in range(lo, hi + 1)}
    return out


def search_documents(con, text, patient=None):
    """Case-insensitive keyword search over source text; returns doc_id, line number and line."""
    mrn = _resolve(con, patient) if patient else None
    out = []
    for d in rows(con, "SELECT doc_id, patient_mrn, text FROM documents" + (" WHERE patient_mrn=?" if mrn else ""),
                  (mrn,) if mrn else ()):
        for i, l in enumerate(d["text"].split("\n"), 1):
            if text.lower() in l.lower():
                out.append({"doc_id": d["doc_id"], "line": i, "text": l.strip()[:300]})
    return {"matches": out[:40], "truncated": len(out) > 40}


def document_index(con, patient=None):
    """List documents with title, one-line summary, and whether they are copies."""
    mrn = _resolve(con, patient) if patient else None
    return rows(con, "SELECT doc_id, filename, title, summary, is_copy, copy_of FROM documents"
                + (" WHERE patient_mrn=?" if mrn else "") + " ORDER BY doc_id", (mrn,) if mrn else ())
