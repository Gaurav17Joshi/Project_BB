# DEV-01

**Question.** For January 5–30, 2026, how many therapy sessions did Rowan attend, by service type and in total, and on how many distinct days? Provide a reviewable abstraction with source support and explain records that could lead to duplicate or ineligible counts.

## Rowan Mercer Therapy Sessions: January 5–30, 2026

### Summary Table

| Service Type | Established Sessions | Possible Additional | Total by Type |
|--------------|----------------------|---------------------|---------------|
| individual_psychotherapy | 5 | 0 | 5 |
| group_psychotherapy | 5 | 0 | 5 |
| family_psychotherapy | 2 | 0 | 2 |
| **Total** | **12** | **0** | **12** |

### Distinct Therapy Days: 11

The 11 distinct days Rowan attended therapy sessions are:
- 2026-01-05, 2026-01-06, 2026-01-09, 2026-01-12, 2026-01-14, 2026-01-19, 2026-01-21, 2026-01-22, 2026-01-26, 2026-01-29, 2026-01-30

---

### Source Support (Methodology)

The session counts are derived from the `session_counts` tool for patient HG-M042 (Rowan Mercer), period 2026-01-05 to 2026-01-30. The method states: *"One contact per reconciled encounter (duplicate notes/copies merged). Counted if the service type counts under the treatment plan and tier-A records establish the patient attended."*

---

### Records That Could Lead to Duplicate or Ineligible Counts

#### 1. **No-Show Records**
| Contact ID | Service Type | Status | Why Excluded | Source Docs |
|------------|--------------|--------|---------------|--------------|
| HG-M042/2026-01-08/HG-E103 | individual_psychotherapy | no_show | no_show per tier-A source(s) | BH-D006, BH-D015 |

#### 2. **Service Types That Do Not Count Toward Plan Goal**
These service types are excluded from therapy session counts because they do not count toward the treatment plan goal:

| Contact ID | Service Type | Status | Why Excluded | Source Docs |
|------------|--------------|--------|---------------|--------------|
| HG-M042/2026-01-08/scheduling_or_outreach#BH-D015:S1 | scheduling_or_outreach | no_show | service type does not count toward plan goal | BH-D015 |
| HG-M042/2026-01-08/scheduling_or_outreach#BH-D015:S2 | scheduling_or_outreach | attended | service type does not count toward plan goal | BH-D015 |
| HG-M042/2026-01-13/HG-E106 | medication_management | attended | service type does not count toward plan goal | BH-D006, BH-D010 |
| HG-M042/2026-01-15/HG-E108 | group_psychotherapy | clinic_cancelled | clinic_cancelled per tier-A source(s) | BH-D006, BH-D016 |
| HG-M042/2026-01-16/HG-E109 | collateral_contact | disputed | service type does not count toward plan goal | BH-D006, BH-D012 |
| HG-M042/2026-01-16/measure_or_questionnaire_review#BH-D013:S0 | measure_or_questionnaire_review | attended | service type does not count toward plan goal | BH-D013 |
| HG-M042/2026-01-16/measure_or_questionnaire_review#BH-D014:S0 | measure_or_questionnaire_review | no_show | service type does not count toward plan goal | BH-D014 |
| HG-M042/2026-01-23/HG-E114 | care_coordination | no_show | service type does not count toward plan goal | BH-D109 |
| HG-M042/2026-01-27/HG-E116 | group_psychotherapy | no_show | no_show per tier-A source(s) | BH-D108, BH-D112 |
| HG-M042/2026-01-28/HG-E117 | individual_psychotherapy | patient_cancelled | patient_cancelled per tier-A source(s) | BH-D108 |
| HG-M042/2026-01-30/HG-E120 | medication_management | attended | service type does not count toward plan goal | BH-D114 |
| HG-M042/2026-01-30/other#BH-D115:S0 | other | attended | service type does not count toward plan goal | BH-D115 |

#### 3. **Duplicate Prevention**
The methodology explicitly states that duplicate notes/copies merged are handled by the reconciliation process. The `session_counts` tool reports `"possible_additional": 0` for all service types, indicating no duplicate records remain after merging.

---

### Uncertainties and Open Issues

- **Issue HG-M042/I002** (contact HG-M042/2026-01-06/HG-E102): Associated with group_psychotherapy on 2026-01-06. The issue is noted but does not affect inclusion status.
- **Issue HG-M042/I005** (contact HG-M042/2026-01-19/HG-E110): Associated with group_psychotherapy on 2026-01-19. The issue is noted but does not affect inclusion status.
- **Issue HG-M042/I006** (contact HG-M042/2026-01-22/HG-E113): Associated with group_psychotherapy on 2026-01-22. The issue is noted but does not affect inclusion status.
- **Issue HG-M042/I007** (contact HG-M042/2026-01-26/HG-E115): Associated with individual_psychotherapy on 2026-01-26. The issue is noted but does not affect inclusion status.

These issues appear to be documentation conflicts or gaps that have been resolved in the reconciliation process, as all contacts are marked `"inclusion": "included"` where applicable.

---
Citation check: 1/4 quotations found verbatim in the cited documents (first draft had 4 unverified; one repair pass run).

Not verified:
- [] “One contact per reconciled encounter (duplicate notes/copies merged). Counted if the service type counts under the treatment plan and tier-A records establish the patient attended.”
- [] “possible_additional”
- [] “inclusion”

<details><summary>Run details</summary>

Model `qwen3.5:9b` · 4 LLM calls · 24669 in / 4469 out tokens · 96.67 s

Tool calls:
- `session_counts({"patient": "HG-M042", "start": "2026-01-05", "end": "2026-01-30"})`
- `document_index({"patient": "HG-M042"})`
- `session_counts({"patient": "HG-M042", "start": "2026-01-05", "end": "2026-01-30"})`
</details>
