# NEW-01

**Question.** How many group therapy minutes did Rowan receive in the week starting January 19, 2026, and which contacts contributed?

Rowan received **105 group therapy minutes** during the week starting January 19, 2026. The weekly summary includes two contacts:

| Contact | Minutes |
|---|---:|
| `HG-M042/2026-01-19/HG-E110` | 60 |
| `HG-M042/2026-01-22/HG-E113` | 45 |

The January 19 roster copy says, “The attached attendance sheet was resent following a request for the original group roster.” [BH-D104] The abstraction identifies that copy as merged into the existing January 19 contact, not counted as an additional contact.

---
Citation check: 1/1 quotations found verbatim in the cited documents (first draft had 1 unverified; one repair pass run).

<details><summary>Run details</summary>

Model `gpt-6-luna` · 6 LLM calls · 19265 in / 1475 out tokens · 23.95 s

Tool calls:
- `weekly_summary({"patient": "Rowan Mercer", "start": "2026-01-19", "end": "2026-01-25", "service_types": ["group_psychotherapy"]})`
- `contacts({"patient": "Rowan Mercer", "start": "2026-01-19", "end": "2026-01-25", "service_types": ["group_psychotherapy"], "inclusion": ["included", "excluded", "uncertain"]})`
- `issues({"patient": "Rowan Mercer", "kinds": ["all"]})`
- `get_document_passage({"doc_id": "BH-D102", "quote": "10:00", "line": 0, "context": 5})`
- `get_document_passage({"doc_id": "BH-D103", "quote": "correction", "line": 0, "context": 5})`
- `get_document_passage({"doc_id": "BH-D108", "quote": "10:30", "line": 0, "context": 5})`
- `get_document_passage({"doc_id": "BH-D101", "quote": "Attended", "line": 0, "context": 4})`
- `get_document_passage({"doc_id": "BH-D107", "quote": "Attended", "line": 0, "context": 4})`
- `get_document_passage({"doc_id": "BH-D104", "quote": "resent", "line": 0, "context": 3})`
- `weekly_summary({"patient": "Rowan", "start": "2026-01-19", "end": "2026-01-25", "service_types": ["group_psychotherapy"]})`
- `issues({"patient": "Rowan", "kinds": []})`
- `get_document_passage({"doc_id": "BH-D104", "quote": "ATTACHED ROSTER COPY", "line": 10, "context": 8})`
</details>
