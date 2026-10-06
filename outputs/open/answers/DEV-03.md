# DEV-03

**Question.** For each week, did the delivered therapy meet the goal documented in Rowan’s treatment plan? State the goal, the relevant therapy-day and minute totals, and whether it was met, not met, or cannot be determined from the current record.

## Rowan Mercer (HG-M042) Weekly Goal Compliance Summary

**Goal documented:**  
*Goal ID:* BH-D003:G0  
*Document:* BH-D003  
*Evidence:* "Local treatment participation goal: at least 3 therapy days and at least 150 minutes of patient-present therapy in each Monday–Sunday week."

| Week | Therapy Days | Minutes | Verdict | Reason |
|------|--------------|---------|---------|--------|
| 2026-01-05 to 2026-01-11 | 3 | 140 | **not_met** | 140 min < 150 |
| 2026-01-12 to 2026-01-18 | 2 | 120 | **not_met** | 2 therapy days < 3; 120 min < 150 |
| 2026-01-19 to 2026-01-25 | 3 | 180 | **met** | Both thresholds met |
| 2026-01-26 to 2026-02-01 (partial) | 3 | 145–155 | **indeterminate** | Minutes range straddles 150; cannot determine without resolving documentation conflict (HG-M042/I007) |

### Uncertainties
- The final week (2026-01-26 to 2026-01-30, partial) has conflicting source records for the first contact: BH-D110 reports 50 minutes and BH-D111 reports 40 minutes. This creates a range of 145–155 total minutes across all contacts. The verdict is **indeterminate** until this conflict is resolved.

---
Citation check: 1/1 quotations found verbatim in the cited documents.

<details><summary>Run details</summary>

Model `qwen3.5:9b` · 2 LLM calls · 7653 in / 1124 out tokens · 23.56 s

Tool calls:
- `goal_compliance({"patient": "HG-M042", "start": "2026-01-05", "end": "2026-01-30"})`
</details>
