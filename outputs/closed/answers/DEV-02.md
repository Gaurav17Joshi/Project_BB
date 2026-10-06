# DEV-02

**Question.** How many therapy minutes and hours did Rowan actually receive during the review period, overall and for each Monday–Sunday week? Show calculations or supporting detail, and report any conclusion the available documents do not settle.

## Direct answer

Rowan received **585–595 therapy minutes overall, or 9.75–9.92 hours** during the review period. The records do **not** settle one exact total: the January 26 individual-therapy contact has conflicting final documentation. The weekly figures below are the abstraction’s reported totals, with supporting contact detail.

| Monday–Sunday week | Therapy minutes received | Therapy hours | Included contacts and supporting detail |
|---|---:|---:|---|
| **2026-01-05 to 2026-01-11** | **140 minutes** | **2.33 hours** | **HG-M042/2026-01-05/HG-E101:** 50 minutes; [BH-D002] “Patient-present individual therapy: 09:00–09:50 local; completed, 50 minutes.” **HG-M042/2026-01-06/HG-E102:** 45 minutes net; [BH-D005] “2026-01-06 \| HG-E102 \| 10:00–11:30 \| 10:15 \| 11:15 \| Attended part”; [BH-D004] “The whole group took a break from 10:45 to 11:00. No therapy was conducted during that interval.” **HG-M042/2026-01-09/HG-E104:** 45 minutes; [BH-D007] “Patient-present family therapy duration: 45 minutes” |
| **2026-01-12 to 2026-01-18** | **120 minutes** | **2.0 hours** | **HG-M042/2026-01-12/HG-E105:** 75 minutes net; [BH-D005] “2026-01-12 \| HG-E105 \| 10:00–11:30 \| 10:00 \| 11:30 \| Attended full”; [BH-D009] “Group break: 10:40–10:55; no therapeutic activity occurred during the break.” **HG-M042/2026-01-14/HG-E107:** 45 minutes; [BH-D011] “Patient-present session 11:00–11:45 local; completed, 45 minutes” |
| **2026-01-19 to 2026-01-25** | **180 minutes** | **3.0 hours** | **HG-M042/2026-01-19/HG-E110:** 60 minutes net; [BH-D103] “Correction: Patient departure for HG-E110 is 11:15, replacing the original roster value of 11:30. Patient arrival remains 10:00.” [BH-D101] “Scheduled group: 10:00–11:30. Nontherapeutic break: 10:45–11:00.” **HG-M042/2026-01-19/HG-E111:** 30 minutes; [BH-D105] “Patient contact: 11:15–11:45 \| Completed: 30 minutes”. **HG-M042/2026-01-21/HG-E112:** 45 minutes; [BH-D106] “Patient contact occurred 13:00–13:20 and 13:30–13:55. Connection was lost from 13:20–13:30; there was no therapeutic contact during that interval. Total patient psychotherapy contact: 45 minutes.” **HG-M042/2026-01-22/HG-E113:** 45 minutes net; [BH-D108] “January 22 \| HG-E113 \| Skills group \| 10:00–11:30 \| 10:30 \| 11:30 \| Attended, late arrival”; [BH-D107] “Scheduled group 10:00–11:30. Nontherapeutic break 10:45–11:00.” |
| **2026-01-26 to 2026-02-01** *(partial review week; records through January 30)* | **145–155 minutes** | **2.42–2.58 hours** | **HG-M042/2026-01-26/HG-E115:** **40–50 minutes**, unresolved; see below. **HG-M042/2026-01-29/HG-E118:** 75 minutes net; [BH-D108] “January 29 \| HG-E118 \| Skills group \| 10:00–11:30 \| 10:00 \| 11:30 \| Attended”; [BH-D107] “Scheduled group 10:00–11:30. Nontherapeutic break 10:45–11:00.” **HG-M042/2026-01-30/HG-E119:** 30 minutes of Rowan’s participation; [BH-D113] “Partner only: 13:00–13:15. Rowan present with partner: 13:15–13:45, 30 minutes.” |

### What is and is not settled

The January 26 contact **HG-M042/2026-01-26/HG-E115** is documented differently in two final notes: [BH-D111] “The full patient-contact interval for the encounter was 09:10–09:50.” versus [BH-D110] “Actual patient psychotherapy contact: 09:00–09:50, 50 minutes.” The abstraction therefore reports **40–50 minutes** for that contact and a range for the final week and review-period total. A treating-clinician attestation or correction is needed to settle the exact duration.

### Counting decisions affecting the totals

The treatment plan says [BH-D003] “Patient-present individual, group, and family therapy contribute to the minute goal. Medication management, contacts with collateral informants only, and care coordination do not contribute.” Accordingly, medication-management contacts **HG-E106** and **HG-E120** and care-coordination contact **HG-E114** are excluded; the care-coordination record states [BH-D109] “Patient participation: None. No patient contact occurred.” For the January 30 family session, the partner-only portion is not included; only Rowan’s documented participation contributes.

No-shows, cancellations, and clinic cancellations are not counted as received therapy: the records identify, among others, **HG-E103** as [BH-D015] “Appointment marked no show. Rowan was not seen for the scheduled individual visit,” **HG-E108** as “Clinic cancelled” [BH-D006], and **HG-E117** as cancelled before its scheduled start [BH-D108] “Appointment HG-E117 was cancelled before the scheduled start; no replacement appointment was booked within January 2026.” The January 27 draft/billing material does not establish treatment: [BH-D112] “Status: DRAFT — UNSIGNED — system populated from scheduled group template”; the reconciled contact **HG-E116** is a no-show [BH-D108] “No show; patient did not attend.”

Records for the same encounter were not counted as extra therapy: the two January 9 family notes are merged under **HG-E104**, and the January 19 resent roster [BH-D104] “The attached attendance sheet was resent following a request for the original group roster.” The corrected January 19 departure, rather than the original roster time, was used.

---
Citation check: 26/26 quotations found verbatim in the cited documents.

<details><summary>Run details</summary>

Model `gpt-6-luna` · 11 LLM calls · 164250 in / 7662 out tokens · 86.26 s

Tool calls:
- `weekly_summary({"patient": "Rowan Mercer", "start": "2026-01-05", "end": "2026-01-30"})`
- `contacts({"patient": "Rowan Mercer", "start": "2026-01-05", "end": "2026-01-30", "service_types": ["individual_psychotherapy", "group_psychotherapy", "family_psychotherapy", "medication_management", "care_coordination"], "inclusion": ["included", "excluded", "uncertain"]})`
- `issues({"patient": "Rowan Mercer", "kinds": ["all"]})`
- `day_detail({"patient": "Rowan Mercer", "date": "2026-01-19"})`
- `day_detail({"patient": "Rowan Mercer", "date": "2026-01-26"})`
- `search_documents({"text": "Patient contact", "patient": "Rowan Mercer"})`
- `search_documents({"text": "10:15", "patient": "Rowan Mercer"})`
- `search_documents({"text": "2026-01-05", "patient": "Rowan Mercer"})`
- `search_documents({"text": "2026-01-06", "patient": "Rowan Mercer"})`
- `search_documents({"text": "2026-01-09", "patient": "Rowan Mercer"})`
- `search_documents({"text": "2026-01-12", "patient": "Rowan Mercer"})`
- `search_documents({"text": "2026-01-14", "patient": "Rowan Mercer"})`
- `search_documents({"text": "2026-01-21", "patient": "Rowan Mercer"})`
- `search_documents({"text": "2026-01-22", "patient": "Rowan Mercer"})`
- `search_documents({"text": "2026-01-29", "patient": "Rowan Mercer"})`
- `search_documents({"text": "2026-01-30", "patient": "Rowan Mercer"})`
- `get_document_passage({"doc_id": "BH-D002", "quote": "Encounter HG-E101 | Service date 2026-01-05", "line": 6, "context": 4})`
- `get_document_passage({"doc_id": "BH-D005", "quote": "2026-01-06 | HG-E102", "line": 10, "context": 2})`
- `get_document_passage({"doc_id": "BH-D007", "quote": "Encounter HG-E104 | 2026-01-09", "line": 6, "context": 5})`
- `get_document_passage({"doc_id": "BH-D009", "quote": "Service date 2026-01-12", "line": 6, "context": 6})`
- `get_document_passage({"doc_id": "BH-D011", "quote": "Encounter HG-E107 | Date 2026-01-14", "line": 6, "context": 5})`
- `get_document_passage({"doc_id": "BH-D106", "quote": "Patient contact occurred", "line": 7, "context": 1})`
- `get_document_passage({"doc_id": "BH-D108", "quote": "2026-01-22", "line": 0, "context": 2})`
- `get_document_passage({"doc_id": "BH-D113", "quote": "13:15", "line": 1, "context": 4})`
- `get_document_passage({"doc_id": "BH-D108", "quote": "10:00-11:30", "line": 0, "context": 2})`
- `get_document_passage({"doc_id": "BH-D005", "quote": "10:45", "line": 10, "context": 7})`
- `get_document_passage({"doc_id": "BH-D101", "quote": "10:45", "line": 0, "context": 10})`
- `get_document_passage({"doc_id": "BH-D107", "quote": "10:45", "line": 0, "context": 10})`
- `get_document_passage({"doc_id": "BH-D108", "quote": "January 29 | HG-E118", "line": 12, "context": 9})`
- `get_document_passage({"doc_id": "BH-D103", "quote": "Patient departure for HG-E110 is 11:15", "line": 7, "context": 1})`
- `get_document_passage({"doc_id": "BH-D110", "quote": "Actual patient psychotherapy contact: 09:00", "line": 16, "context": 1})`
- `get_document_passage({"doc_id": "BH-D111", "quote": "The full patient-contact interval for the encounter was 09:10", "line": 17, "context": 1})`
- `search_documents({"text": "10:45", "patient": "Rowan Mercer"})`
- `search_documents({"text": "Medication review", "patient": "Rowan Mercer"})`
- `search_documents({"text": "care coordination", "patient": "Rowan Mercer"})`
- `search_documents({"text": "Clinic cancelled", "patient": "Rowan Mercer"})`
- `search_documents({"text": "No show", "patient": "Rowan Mercer"})`
- `search_documents({"text": "Partner only", "patient": "Rowan Mercer"})`
- `search_documents({"text": "resent", "patient": "Rowan Mercer"})`
- `search_documents({"text": "DRAFT", "patient": "Rowan Mercer"})`
- `get_document_passage({"doc_id": "BH-D003", "quote": "Local treatment participation goal", "line": 12, "context": 0})`
- `get_document_passage({"doc_id": "BH-D109", "quote": "Patient participation: None", "line": 7, "context": 0})`
- `get_document_passage({"doc_id": "BH-D104", "quote": "The attached attendance sheet was resent", "line": 8, "context": 2})`
- `get_document_passage({"doc_id": "BH-D112", "quote": "Status: DRAFT", "line": 9, "context": 7})`
- `get_document_passage({"doc_id": "BH-D108", "quote": "January 28 scheduling entry", "line": 18, "context": 1})`
</details>
