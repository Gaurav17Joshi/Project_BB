# NEW-01

**Question.** How many group therapy minutes did Rowan receive in the week starting January 19, 2026, and which contacts contributed?

**Answer:** Rowan Mercer received **105 minutes** of group therapy in the week starting January 19, 2026 (January 19–25, 2026). This total came from **2 contacts**.

### Supporting Detail

| Contact ID | Date | Minutes | Calculation / Notes |
|------------|------|---------|---------------------|
| HG-M042/2026-01-19/HG-E110 | 2026-01-19 | 60 | BH-D101: 10:00–10:45, 11:00–11:15 = 60 min (departure 11:30→11:15 per correction BH-D103) \| BH-D102: 10:00–11:15 = 75 min – 15 min break = 60 min |
| HG-M042/2026-01-22/HG-E113 | 2026-01-22 | 45 | BH-D108: 10:30–11:30 = 60 min – 15 min break = 45 min |

**Total:** 60 + 45 = **105 minutes** (1.75 hours)

### Uncertainties / Issues
- Both contacts have open issues recorded: HG-M042/I005 and HG-M042/I006 respectively. These are documented in the `issues` field of each contact record but do not affect the settled minutes calculation.

---
Citation check: 0/0 quotations found verbatim in the cited documents.

<details><summary>Run details</summary>

Model `qwen3.5:9b` · 3 LLM calls · 8141 in / 972 out tokens · 20.06 s

Tool calls:
- `find_patient({"query": "Rowan Mercer"})`
- `weekly_summary({"patient": "HG-M042", "start": "2026-01-19", "end": "2026-01-25", "service_types": ["group_psychotherapy"]})`
</details>
