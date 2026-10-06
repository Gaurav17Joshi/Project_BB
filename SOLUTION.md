# Solution write-up: auditable clinical abstraction

This is the detailed companion to `README.md`. It covers how the system works, why it is built this way, the
full results with their evidence, how those results were checked, and what they cost.

The system runs on two interchangeable model backends: a closed model (`gpt-6-luna`, OpenAI API, the default) and
an open model run locally (`qwen3.5:9b` through Ollama). Sections 2–7 describe the shared pipeline and the
closed-model results. Section 8 covers the local model: what it got wrong at first, what was added, and how it
compares. Both backends end with identical results on the development questions.

---

## 1. The problem in one paragraph

We get 31 short records about one fictional outpatient, Rowan Mercer (MRN HG-M042), for January 5–30, 2026:
clinical notes, attendance rosters, a correction, a resent roster copy, a telehealth log, a treatment plan,
measurement reviews, a billing extract and more. We have to say what care Rowan actually received: how many
sessions, how many minutes per week, whether the plan's weekly goal was met, and what the record says about
progress. Every number must trace to a source passage. The documents are built to mislead a naive reader. They
contain duplicates, a later correction, a resent copy of the *uncorrected* roster, a telehealth dropout, an
unsigned auto-generated note plus a billing charge for a session the patient missed, partner-only contacts,
and an imported copy of an earlier questionnaire.

## 2. Approach: the LLM reads, code decides

```
documents ─► ingest ─► extract (LLM) ─► verify quotes ─► reconcile (code) ─► SQLite abstraction
                                                                                   │
question ─► LLM picks query tools ─► code computes every number ─► LLM writes ─► code checks quotes
```

The core decision is to **split reading from reasoning**:

| Job | Done by | Why |
|---|---|---|
| Turning free text into facts (dates, times, status, who was present) | LLM, once per document | Text varies in format; this is what LLMs are good at |
| Checking each fact's quote exists in the source | Code | Catches invented facts at the point of entry |
| Deciding which records describe the same session, which source wins, what counts | Code (explicit rules) | Must be consistent, explainable and the same on every run |
| Arithmetic: minutes, weeks, thresholds | Code | LLMs make arithmetic slips; reviewers need to re-run it |
| Understanding a new question and writing the answer | LLM, with query tools | Flexible over wording; cannot invent numbers |
| Checking every quote in the answer | Code | Catches paraphrased or invented quotes |

Plain retrieval (find similar passages, ask an LLM) is the wrong shape for this task. The answers need
reconciliation *across* documents (a correction in one file changes a time in another), and arithmetic over
time. Retrieval returns passages; this task needs a reconciled timeline.

## 3. How each stage works

### 3.1 Ingest (`ingest.py`)
Each file is normalised (line endings, trailing spaces) and fingerprinted with SHA-256. A document with a known
fingerprint is recorded as a duplicate copy and is never sent to the model. Measured: adding an exact copy and a
CRLF/whitespace variant of two files caused 0 model calls and no change to any result.

### 3.2 Extract (`extract.py`, `schema.py`, `prompts.py`)
One model call per document (`gpt-6-luna` or `qwen3.5:9b`), with a strict JSON schema enforced by the API or by
Ollama's constrained decoding. For each document the model returns:

- **service records**, one per encounter the document mentions, including no-shows and cancellations. Each
  has: encounter/appointment ID, date, service type, the document's role (clinical note, attendance record,
  correction, schedule export, draft, billing, copy...), attendance status, whether the patient was present,
  **actual patient-present time segments**, documented breaks or disconnects, any stated minute total, and
  whether the record is signed and final;
- **corrections**: field, old value, new value, stated scope;
- **treatment-plan goals**: thresholds, which service types count, effective dates;
- **measures** (PHQ-9): score, completion date (not import date), form ID, whether it is a copy;
- **clinical observations**: symptom, functioning, safety and engagement statements, with who observed them.

Every item carries a verbatim `evidence` quote. The model reports **times as written and never totals**, so
"13:00–13:20 and 13:30–13:55" stays two segments, and code does the subtraction. Results are cached by
(document hash, model, prompt version).

### 3.3 Verify (`verify.py`)
Each quote is located in the source (exact match, then with dashes, quotes and whitespace folded, then fuzzy)
and stored with character offsets and line number. **On the supplied documents, 137/137 extracted quotes
matched exactly for the closed model** (136/159 for the local model; the rest are flagged, see section 8).

### 3.4 Reconcile (`reconcile.py`): the rules

| Rule | What it handles here |
|---|---|
| Records sharing an encounter or appointment ID form **one contact** | Two clinicians' notes for Jan 9 family and Jan 26 individual; resent Jan 19 roster; Jan 21 video reconnect under one appointment |
| **Evidence tiers.** A: signed notes, attendance records, corrections, cancellation and no-show logs. B: schedule exports, copies. C: drafts, billing | Status comes from the highest tier that speaks to attendance |
| **Tier C never proves care happened** | Jan 27: an unsigned template says "attended the full session" and a charge is posted, but the signed register says no-show. Result: no-show, plus a high-severity issue |
| **Later ≠ truer.** Only an explicit correction replaces a value, and only the field it names | Jan 19: correction BH-D103 changes departure 11:30 → 11:15. The resent copy BH-D104 (received Jan 26, still showing 11:30) does not undo it |
| **Minutes = patient-present segments − documented breaks** | Group breaks of 15 min subtracted; telehealth dropout excluded; Jan 30 partner-only first 15 min excluded |
| **Disagreement without resolution becomes a range** | Jan 26: two signed notes, 09:00–09:50 vs 09:10–09:50, give 40–50 min |
| **Counting follows the plan's own definition** (extracted, not hard-coded) | Medication management, partner-only collateral and care coordination are excluded |
| Administrative contacts (outreach calls, notices) never merge into therapy encounters | Jan 8 callback, Jan 15 notice call, Jan 27 outreach message |
| Measures are one row per (instrument, completion date) | Jan 16 PHQ-9 and its Jan 26 import become one administration |
| For arrival and departure, attendance records and corrections outrank narrative notes within a tier | A facilitator note that restates the scheduled slot cannot override the roster's actual times |
| **Schedule-echo rule.** If signed records disagree and one gives exactly the booked slot, that value is set aside (logged as an issue) | The failure the Jan 19 roster shows: BH-D102 kept the scheduled close, which BH-D103 corrected |
| Only goals with numeric thresholds define what counts; records without a single valid date are flagged and left out | Narrative goals ("continue the plan") can't turn every week into "met" |

The last three rows were added after the local model's first run (section 8). They are general rules about
document types, and re-running the closed model's cached extractions through them changes nothing: all 24
contacts are identical.

Each contact stores its status and the basis for it, its inclusion decision and the reason, its minutes with
the calculation written out, and links to every source record. Every non-trivial decision is written to an
`issues` table.

### 3.5 Query and answer (`queries.py`, `ask.py`)
`queries.py` holds plain functions: `session_counts`, `weekly_summary`, `goal_compliance`, `day_detail`,
`measures`, `observations`, `issues`, collection-wide `compliance_all`, `consecutive_weeks_below`,
`plan_change_comparison`, plus `get_document_passage` and `search_documents` for checking wording. The model
gets them as tools and is told it may not compute numbers itself. After it writes an answer, code checks
every quotation against the cited document. If any fail, the model gets one repair pass. The check result is
printed under each answer.

Uncertainty propagates as ranges. A week's verdict is **met** only if the low end clears both thresholds,
**not met** if even the high end falls short, and **indeterminate** otherwise.

## 4. Worked example: tracing January 19

| Step | What happens |
|---|---|
| Extracted | BH-D101 group note: break 10:45–11:00. BH-D102 signed roster: 10:00–11:30, attended. BH-D103 correction: departure 11:30 → 11:15, "applies only to Rowan Mercer's departure field". BH-D104 resent copy: 10:00–11:30. BH-D105 individual note: 11:15–11:45, added because Rowan "became anxious during group" |
| Grouped | BH-D101–104 share encounter HG-E110, giving one group contact. BH-D105 is HG-E111, a separate contact |
| Corrected | BH-D102's departure 11:30 matches the correction's old value, so it becomes 11:15. The copy is tier B and does not override |
| Calculated | `BH-D102: 10:00-11:15 = 75 min - 15 min break = 60 min (departure 11:30->11:15 per correction BH-D103)` |
| Result | 2 therapy contacts, 60 + 30 = **90 patient therapy minutes** |

Run `python cli.py show day --date 2026-01-19` to see every source record, quote and line number behind this.

## 5. Results

### 5.1 Every contact in the episode

| Date | Contact | Status | Counted | Minutes | How minutes were derived | Sources |
|---|---|---|---|---:|---|---|
| Jan 5 | Individual HG-E101 | attended | yes | 50 | 09:00–09:50 | BH-D002, BH-D006 |
| Jan 6 | Group HG-E102 | attended (partial) | yes | 45 | 10:15–11:15 − 15 min break | BH-D004, BH-D005, BH-D006 |
| Jan 8 | Individual HG-E103 | no-show | no | – | – | BH-D006, BH-D015 |
| Jan 8 | Scheduling callback | – | no | – | not therapy | BH-D015 |
| Jan 9 | Family HG-E104 | attended | yes | 45 | 14:00–14:45; two notes = one session | BH-D006, BH-D007, BH-D008 |
| Jan 12 | Group HG-E105 | attended | yes | 75 | 10:00–11:30 − 15 min break | BH-D005, BH-D006, BH-D009 |
| Jan 13 | Medication mgmt HG-E106 | attended | no | (25) | not psychotherapy per plan | BH-D006, BH-D010 |
| Jan 14 | Individual HG-E107 | attended | yes | 45 | 11:00–11:45 | BH-D006, BH-D011 |
| Jan 15 | Group HG-E108 | clinic cancelled | no | – | – | BH-D006, BH-D016 |
| Jan 16 | Collateral HG-E109 | partner only | no | – | Rowan absent | BH-D006, BH-D012 |
| Jan 19 | Group HG-E110 | attended | yes | 60 | 10:00–11:15 (corrected) − 15 min break | BH-D101–BH-D104 |
| Jan 19 | Individual HG-E111 | attended | yes | 30 | 11:15–11:45 | BH-D105 |
| Jan 21 | Individual HG-E112 (video) | attended | yes | 45 | 13:00–13:20 + 13:30–13:55 | BH-D106 |
| Jan 22 | Group HG-E113 | attended (late) | yes | 45 | 10:30–11:30 − 15 min break | BH-D107, BH-D108 |
| Jan 23 | Care coordination HG-E114 | no patient | no | – | professionals only | BH-D109 |
| Jan 26 | Individual HG-E115 | attended | yes | **40–50** | two signed notes disagree | BH-D110, BH-D111 |
| Jan 27 | Group HG-E116 | no-show | no | – | draft + charge do not count | BH-D108, BH-D112 |
| Jan 28 | Individual HG-E117 | patient cancelled | no | – | – | BH-D108 |
| Jan 29 | Group HG-E118 | attended | yes | 75 | 10:00–11:30 − 15 min break | BH-D107, BH-D108 |
| Jan 30 | Family HG-E119 | attended | yes | 30 | 13:15–13:45 (partner alone before 13:15) | BH-D113 |
| Jan 30 | Medication mgmt HG-E120 | attended | no | (20) | not psychotherapy per plan | BH-D114 |

### 5.2 DEV-01 and DEV-02: sessions, days, minutes

- **12 therapy sessions**: 5 individual, 5 group, 2 family, on **11 distinct days**.
- **585–595 minutes (9.75–9.92 hours)**. The 10-minute range comes entirely from the Jan 26 conflict.

### 5.3 DEV-03: weekly goal (≥ 3 therapy days and ≥ 150 patient-present minutes, BH-D003)

| Week (Mon–Sun) | Therapy days | Minutes | Hours | Verdict |
|---|---:|---:|---:|---|
| Jan 5–11 | 3 | 140 | 2.33 | **Not met** (minutes) |
| Jan 12–18 | 2 | 120 | 2.00 | **Not met** (days and minutes) |
| Jan 19–25 | 3 | 180 | 3.00 | **Met** |
| Jan 26–Feb 1 (review ends Jan 30) | 3 | 145–155 | 2.42–2.58 | **Cannot be determined** |

Week 4 hinges on one question: did the Jan 26 session start at 09:00 (BH-D110) or 09:10 (BH-D111)? The record
does not settle it. A correction or attestation from the treating clinicians would. The system reports this
rather than picking a side.

### 5.4 DEV-04: January 19 and 21
- **Jan 19:** 2 contacts, 90 minutes (see section 4).
- **Jan 21:** 1 contact, 45 minutes. The platform export shows two calls (VC-112A, VC-112B), but both are under
  appointment HG-A112, and the note says the reconnection "continued the same clinical encounter". The
  10-minute dropout is excluded.

### 5.5 DEV-05: symptom course
- **Distinct assessments:** PHQ-9 on Jan 5 (**18**), Jan 16 (**14**) and Jan 30 (**10**, item 9 = 0). The Jan 26
  "measure summary" (BH-D014) copies form HG-Q116 from Jan 16 and is not a fourth assessment.
- **Jan 19 extra contact:** added because Rowan became anxious in group when returning to work was discussed
  and needed individual grounding (BH-D105).
- **Supported:** partial improvement in depressive symptoms. Scores fell, and clinicians wrote "some
  improvement" (Jan 16) and "partial improvement" (Jan 30).
- **Not supported:** remission, resolved anxiety, restored work functioning, or treatment *causing* the change.
  Avoidance, sleep disruption and work-related anxiety are documented as persisting through Jan 30.

### 5.6 Unseen questions (not tuned for)
- **"Group minutes in the week of Jan 19?"** 105 minutes (60 + 45), with contacts listed. In the benchmark run
  the model gave 60 and 45 but **refused to add them**, because no tool returned a group-only total and it is not
  allowed to do arithmetic. That is the rule working as intended, but it exposed a missing tool.
  `weekly_summary` now returns per-service-type subtotals; re-asked, the answer is 105. (The NEW-01 row in
  `benchmark.md` is from the earlier run.)
- **"Which patients had two consecutive weeks below goal, and which depend on unresolved documentation?"**
  Rowan, weeks 1–2, definitely below goal. No patient's inclusion depends on the unresolved Jan 26 conflict,
  which falls in week 4.
- **"How did care change before and after a treatment-plan change?"** No plan change is documented, so no
  comparison is possible. (The first version invented one; see 6.4.)

### 5.7 Issues the system raised on its own

| Severity | Issue |
|---|---|
| high | Jan 26 HG-E115: signed notes disagree on duration (40 vs 50 min); unresolved, reported as a range |
| high | Jan 27 HG-E116: draft note and posted charge exist for a session the signed register records as a no-show |
| info | Jan 9 HG-E104 and Jan 26 HG-E115: two notes each for one encounter, counted once |
| info | Jan 19 HG-E110: BH-D104 is a resent copy, merged and not counted again |
| info | Jan 16 PHQ-9: original plus import, one administration |

## 6. How the outputs were checked

### 6.1 Against a hand reconciliation
Before writing reconciliation code I read all 31 documents and worked out the expected answers by hand. The
system matches all of them: session counts, every contact's minutes, weekly totals, verdicts, and PHQ-9
distinctness. No expected value is encoded anywhere in the code.

### 6.2 Extraction stability
Two independent cold extractions produced identical contacts, minutes, verdicts, measures and issues. The one
difference, how a single outreach phone call was labelled, exposed a bug (duplicate contact ID), which I fixed.

### 6.3 Quotes in answers
- Without the check, the first answer run had **3 of 94** quotations that were not in the source. Two were
  paraphrases presented as quotes. One of those also carried a factual error: it called BH-D104 a copy of the
  *final* roster, when it is a copy of the *original, uncorrected* roster.
- With the check and the repair pass, two full benchmark runs had **103/103** and **74/74** quotations verified.
  The repair pass was triggered in 1 and 2 answers (of 8) respectively.

### 6.4 False premises
The plan-change question showed that the model will bend other events to fit a question's premise. The tool now
refuses to compare around a plan change that is not documented, and the prompt tells the model to say when a
premise is absent. The next step would be a dedicated set of false-premise questions to measure this
systematically.

## 7. Performance and cost

**Measured** on the 31 documents, closed model (`outputs/closed/benchmark.md`). Prices are `gpt-6-luna` standard
tier from OpenAI's pricing docs: $0.10 per 1M input tokens, $0.01 cached input, $0.50 output. The local model's
numbers are in section 8.4.

| | Time | Model calls | Cost |
|---|---:|---:|---:|
| Process all documents (cold) | 35–40 s | 31 | $0.023 uncached ($0.016 with cache hits) |
| Re-run with nothing new | 0.05 s | 0 | $0 |
| Add duplicate copies | 0.02 s | 0 | $0 |
| Restart and query saved abstraction | 0.2 s | 0 | $0 |
| Code-only query (counts, weeks, verdicts) | 1–5 ms | 0 | $0 |
| One question via the LLM | 14–93 s (median ≈ 29 s) | 3–14 | $0.0006–$0.008 |
| Whole benchmark (extract + 8 questions) | ≈ 6 min | ≈ 85 | ≈ $0.04 |

Saved abstraction: about 470 KB SQLite (including a copy of the 49 KB of source text) and a 168 KB JSON
export. Per document: about 2.5K input and 1K output tokens; output tokens are about two-thirds of the cost.

**Estimated** (extrapolated, not measured):

| Scale | Extraction tokens | Extraction cost (standard / Batch) | Time at current 8-way concurrency |
|---|---|---:|---:|
| 500K docs | 1.2B in, 0.5B out | ≈ $365 / $183 | ≈ 7 days |
| 1M docs | 2.5B in, 1B out | ≈ $730 / $365 | ≈ 14 days |

**First bottleneck at 1M documents:** extraction throughput (`extract.run_extraction`, one model call per
document). Remedies:
- Use the Batch API for the backfill.
- Send structured document types (rosters, exports, billing) to a cheaper model or a template parser.
- Raise concurrency to the rate limit.
- Daily new documents stay cheap, because only new fingerprints are extracted and only affected patients are re-reconciled.

**Next bottlenecks:**
- **Answer step.** It lists all patients in the prompt, and collection-wide tools recompute every patient
  (3–4 ms each, about 6 minutes for 100K patients) and return full lists. Remedies: a materialised weekly table,
  aggregate and paginated tool results, and no patient list in the prompt.
- **Ingest.** It re-hashes every file on each run. Index by path, size and modified time instead.
- **Keyword search.** It scans all text. Use FTS5 instead.
- **Concurrent writers.** SQLite allows one writer, so several workers writing at once would need Postgres.

## 8. The local-model backend

Same pipeline, schema, rules and queries; only the model layer changes (`backbone/llm_ollama.py`). Model:
`qwen3.5:9b` (9B parameters, 4-bit Q4_K_M, 6.6 GB) through Ollama 0.35 on an RTX 2080 Ti (11 GB). No API key,
no data leaves the machine, and no per-token cost.

### 8.1 Result
The local abstraction matches the closed one on every headline result and on **20/20** encounter contacts
(`outputs/comparison.md`): 12 sessions on 11 days, 585–595 minutes, the same four weekly verdicts, Jan 19 and
21 the same, and PHQ-9 18 → 14 → 10 with the Jan 16 import merged.

### 8.2 How it got there

| Local version | Same outcome as closed | Headline results |
|---|---:|---|
| v1: same prompt as closed, no extra safeguards | 13/20 | **Wrong:** weeks 1–2 and 4 marked "met"; 615–655 min |
| + code safeguards (numeric goals only; attendance records outrank notes for times) | 14/20 | sessions right, minutes still off (Jan 6) |
| + prompt v2 (rules aimed at the observed mistakes) | 18/20 | Jan 6 and Jan 22 became ranges; one document failed (output loop) |
| + retry with sampling, schedule-echo rule, date validation | **20/20** | all match |

What the 9B model got wrong on the first run, and what the closed model did not:
- **Narrative goals logged as treatment goals.** It extracted 12 "goals", 11 with no numbers ("continue the
  plan"). The code then used a goal with no thresholds, so every week was "met".
- **Scheduled slots copied into facilitator notes as the patient's times**, despite the instruction not to.
  Jan 6 became 75 min instead of 45.
- **Wrong document roles.** Rosters and exports were labelled "resent copies", giving 16 false duplicate warnings.
- **The Jan 27 trap.** It read the unsigned template note as "attended full, 10:00–11:30". The reconciliation
  rules still kept Jan 27 a no-show, because the signed register outranks it.
- **Repetition loops.** One document produced 12,000 tokens of looping output until the cap, giving truncated JSON.
- **Time format.** Times sometimes came back as `2026-01-22T10:30`; the parser now accepts this.
- **Quotes.** 136/159 evidence quotes matched exactly, against 137/137 for the closed model. The rest were
  normalised or approximate matches, plus 8 not found; all are flagged in `issues`.

### 8.3 What was added
**Code safeguards**, in `reconcile.py` and `queries.py` and applied to both backends (section 3.4): numeric goals
only, attendance records outrank notes for times, the schedule-echo rule, date validation, and never mixing stale
facts from an older prompt version with new ones.

**Model-side measures**, local backend only:
1. An extra block of extraction rules (`prompts.EXTRACT_SYSTEM_LOCAL_ADDENDUM`): what counts as a roster versus a
   copy, don't put scheduled times into notes, only numeric goals, who cancelled. Its own prompt version,
   `extract-v2-local`, so the two backends' extraction caches never mix.
2. Retry on truncated or invalid JSON at temperature 0.3, then 0.6. At temperature 0 a looping model loops identically.
3. Output capped at 12K tokens; tool results cut at 24K characters so a prompt never overflows the 32K context
   (Ollama would otherwise silently drop the start of the prompt).

Caveat: these were added after seeing this dataset's errors. The code rules are general (none mention Rowan,
dates or document IDs), but they were validated only on these 31 documents. A fair test would run both
backends on fresh documents.

**Design decision tested: thinking on or off for extraction.** On 4 hard documents (the register, the family
session, the schedule export, the draft-plus-charge; `scripts/compare_think.py`):

| | Thinking off | Thinking on |
|---|---|---|
| Time per document | 25–74 s | 167–193 s, about 4× slower |
| Output tokens | 1–3.5K | 8.5–9.7K |
| Correct where off was wrong | | 1 document (family session) |
| Still wrong | | Jan 28 "clinic" vs "patient" cancelled, scheduled times copied |
| Failure | | Looped past 12K tokens on the draft-plus-charge document; no output |

Decision: thinking off for extraction, on for answering, where choosing tools needs planning.

### 8.4 Performance (measured)

From `outputs/open/benchmark.md` (same 31 documents and 8 questions as the closed benchmark):

| | Local (qwen3.5:9b) | Closed (gpt-6-luna) |
|---|---:|---:|
| Process all documents, cold | 1,357 s (22.6 min), ~44 s per document, one at a time | 40 s, 8 workers |
| Extraction tokens (input / output) | 39K / 45K | 76K / 30K |
| Warm re-run; duplicate copies | 0.05 s, 0 calls | 0.05 s, 0 calls |
| One question | 20–277 s, median 63 s (patient) and 45 s (collection-wide) | 14–93 s, median 29 s and 25 s |
| Answer quotes verified | 40/47 | 74/74 |
| Saved abstraction | 560 KB | 476 KB |
| Cost | $0 | about $0.04 for the whole benchmark |

The fresh cold extraction in this benchmark reproduced the earlier local abstraction contact for contact. Answer
quotes are the weak point: the 9B model paraphrases inside quotation marks more often, and one repair pass does not
always fix it. The check still catches every one, and the 7 that failed are printed under their answers.

### 8.5 Where the local model is weaker
- **Answer wording.** Answers repeat the 9B model's labelling errors; one called the correction BH-D103 a
  "duplicate copy". The numbers are right because code computes them, but the narrative is less reliable.
- **Throughput.** One document at a time. At about 44 s per document (measured), 500K documents would take roughly 250 days on this one GPU (an estimate). The local route only scales with more GPUs, a faster
  card, or a serving stack that batches requests (e.g. vLLM).

## 9. Limitations and next steps

- **False-premise questions** (6.4): fixed for plan changes, not solved in general. Next step: build a test set.
- **The Jan 26 judgement**: the system does not weigh which conflicting note is more credible. It reports a
  range. That is deliberate, but a reviewer might reasonably prefer the more specific 09:10 account.
- **Rules were written against this document set.** A new kind of document (e.g. a group sign-in sheet with
  per-member rows) may need a new source role or tier rule. Unknown roles fall into tier B and get flagged rather
  than silently counted.
- **Patient identity is the printed MRN.** There is no matching across typos or merged charts.
- **Answer cost is dominated by tool output re-sent each turn** (up to 164K input tokens for one question).
  Trimming tool payloads would cut answer cost and latency the most.
