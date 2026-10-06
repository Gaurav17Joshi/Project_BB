# plan.md — build spec for the Backbone take-home

What I want built here is a system that reads a folder of clinical records and turns them into an
abstraction a reviewer can actually audit, rather than a pipeline that produces plausible numbers nobody
can trace. The dataset is in `Backbone_ Building Clinical Intelligence 09.27/` (31 `.txt` files plus
`questions.json`). Follow this end to end.

## 1. What we are building

Input:-
    - 31 plain .txt files containing a mix of different medical documents like clinical notes, attendance rosters, a signed treatment plan etc.
    - Set of 5 questions for these.
Output
    - The text answers for these questions

What we have to build is an AI system that can go through txt files and turn it into a structured, inspectable database of what actually happened and then answer questions based on that.

Three rules carry most of the grade:
    - Numbers come from code. Session counts, minutes, weekly totals — computed in Python/SQL over the abstraction. The LLM may extract facts and phrase the final prose, but must not do math.
    - Every claim traces to a quote. A reviewer picks any number in your answer and you show them: these contact records → built from these documents → at this exact passage.
    - Documents disagree, and you must handle it on purpose. Same session written up twice, a later correction, a draft vs. a signed note, a billing charge with no attendance proof. Resolve it with a stated rule, or record it as an open issue — never silently pick one.

One constraint I want to be strict about: no patient facts get hard-coded anywhere in the pipeline. No
names, no dates, no minute totals, no expected answers. They will run unseen documents and unseen
questions through this code on a follow-up call, so the rules live in code and the facts come only from
the documents.

## 2. The algorithm

```
documents/ ─► 1. ingest ─► 2. extract (LLM) ─► 3. verify ─► 4. reconcile (code) ─► SQLite
                                                                                      │
question ──► 5. route (LLM picks tools) ─► 6. compute (code) ─► 7. write (LLM) ─► 8. quote-check ◄┘
```

The principle the whole design rests on is that the LLM reads and the code decides. What makes this task
interesting is that these two jobs have opposite requirements: pulling structure out of free text rewards
flexibility, which is exactly what a language model gives you, while deciding which record wins and
adding up minutes rewards being boringly identical on every run, which is exactly what a model does not
give you. So I want the model confined to reading and phrasing, and every judgement and every arithmetic
operation implemented in code where a reviewer can re-run it. Steps 1 through 4 run once per new
document, and steps 5 through 8 run per question and never touch the source files again.

This is also why I don't want it built as a retrieval pipeline. The answers here are not sitting in any
single passage—you only get them after merging three or four documents that describe the same session and
then doing arithmetic over what survives. Retrieval hands you passages; this task needs a reconciled
timeline.

**1. Ingest.** Normalise the text (line endings, trailing whitespace) and fingerprint it with SHA-256. A
document whose hash we have already seen gets logged as a duplicate copy and is never sent to the model.
The requirement being satisfied is that duplicate copies of a document must not change a single number.

**2. Extract.** One LLM call per document against a strict JSON schema. The important discipline is that
the model reports times **as written and never totals them**, so "13:00–13:20 and 13:30–13:55" stays two
segments and code does the subtraction. No-shows and cancellations are extracted as service records too,
since a question about what did not happen needs them. Every item carries a verbatim `evidence` quote, and
results are cached by `(doc_hash, model, prompt_version)` so re-runs cost nothing and a prompt change only
re-extracts what it has to.

```json
{
  "doc_id": "BH-D102", "signed": true, "patient": {"name": "...", "mrn": "..."},
  "doc_role": "clinical_note|attendance_record|correction|schedule_export|draft|billing|copy",
  "service_records": [{
    "encounter_id": "HG-E110", "appointment_id": "HG-A110", "date": "2026-01-19",
    "service": "individual|group|family|medication|collateral|coordination",
    "modality": "in_person|video|phone", "status": "attended|cancelled|no_show|draft",
    "patient_present": true, "segments": [["10:00","11:30"]], "breaks": [["10:45","11:00"]],
    "stated_total_minutes": null, "signed_final": true,
    "evidence": "Patient arrival: 10:00 | Patient departure: 11:30 | Status: Attended"
  }],
  "corrections": [{"applies_to": "HG-E110", "field": "departure", "old": "11:30", "new": "11:15",
                   "scope": "departure field only", "evidence": "..."}],
  "goals": [{"min_days_per_week": 3, "min_minutes_per_week": 150, "effective_from": "2026-01-05",
             "counting_services": ["individual","group","family"], "evidence": "..."}],
  "measures": [{"name": "PHQ-9", "score": 14, "completed_date": "2026-01-16",
                "form_id": "HG-Q116", "is_copy": false, "evidence": "..."}],
  "observations": [{"domain": "symptom|functioning|safety|engagement", "statement": "...",
                    "observed_by": "...", "date": "...", "evidence": "..."}]
}
```

**3. Verify.** Locate every `evidence` quote in its source text—exact match first, then with dashes,
quotes and whitespace folded, then fuzzy—and store the character offsets and line number. A quote that
cannot be located means the fact is dropped and flagged, so it never reaches the database. This is the
cheapest guard we get against invented facts, because it catches them at the point of entry rather than
in the final answer. Print the match rate at the end of a run (`137/137 quotes matched`); it goes in the
benchmark.

**4. Reconcile.** This is where the real work is, and I want all of it in code with the rules written
down, because every one of them is something a reviewer may want to argue with:

- **Records sharing an encounter or appointment ID are one contact.** This is what handles two clinicians
  writing up the same session, a resent roster, and a video call that dropped and reconnected under one
  appointment.
- **Evidence tiers.** Tier A is signed notes, attendance records, corrections and cancellation or no-show
  logs; tier B is schedule exports and copies; tier C is drafts and billing. Status comes from the highest
  tier that actually speaks to attendance, and an unrecognised document role falls to tier B and gets
  flagged rather than silently counted.
- **Tier C never proves care happened.** An unsigned template saying "attended the full session" plus a
  posted charge loses to a signed register recording a no-show, and the contradiction becomes a
  high-severity issue instead of disappearing.
- **Later is not truer.** Only an explicit correction replaces a value, and only the field it names. A
  copy of an older uncorrected document that arrives later does not undo a correction.
- **Minutes are patient-present segments minus documented breaks.** Telehealth dropouts come out, and so
  does any interval the patient was not in the room, such as the partner-only portion of a family session.
- **Unresolved disagreement becomes a range, not a guess.** Two signed notes giving 40 and 50 minutes get
  stored as 40–50 with an issue logged.
- **Counting follows the treatment plan's own definition**, read out of the plan document rather than
  hard-coded, since the next patient's plan will say something different.
- **Administrative contacts never merge into therapy encounters**—outreach calls, scheduling callbacks and
  cancellation notices stay separate.
- **Measures are one row per instrument and completion date.** An imported summary of an earlier
  questionnaire is the same administration, and the form ID is what catches it.

Each contact stores its status and the basis for it, its inclusion decision and the reason, its minutes
along with the calculation, and links to every source record. Every non-trivial decision gets a row in
`issues`. Reviewers read the calculation strings directly on the follow-up call, so write them to be read:

```
"10:00-11:15 = 75min - 15min break = 60min (departure 11:30->11:15 per correction BH-D103)"
```

**5 through 8. Query and answer.** `queries.py` is plain functions over SQLite with no model involved, and
each one returns its figures together with the contact IDs and quotes behind them:

```
session_counts   weekly_summary (with per-service-type subtotals)   goal_compliance   day_detail
measures   observations   issues   compliance_all   consecutive_weeks_below
plan_change_comparison   get_document_passage   search_documents
```

These go to the model as tools, with an instruction that it may not compute numbers itself. Two details
matter more than they look. First, `weekly_summary` has to return per-service subtotals, because otherwise
a question like "group minutes this week" leaves the model with two numbers it is forbidden to add, and
the honest refusal that follows is really a missing tool. Second, the system has to refuse false premises:
if a question assumes something the record does not contain, such as a treatment-plan change that was
never documented, the tool returns not-documented and the prompt tells the model to say the premise is
absent rather than bending other events to fit it.

Uncertainty propagates as ranges. A week counts as **met** only when the low end clears both thresholds,
**not met** when even the high end falls short, and **indeterminate** in between. After the model writes,
code re-locates every quotation in the document it cites, gives it one repair pass on a miss, and prints
the result under the answer (`103/103 quotations verified`).

## 3. CLI

The processing command
Input:   python cli.py process documents/
         (a directory of .txt clinical records)

Output:  a persisted abstraction, e.g. data/abstraction.db
         ├─ documents   one row per file: hash, path, doc_type, signed?
         ├─ facts       raw extracted facts, each with its verbatim quote + char offsets
         ├─ contacts    reconciled real-world sessions: date, service type,
         │              encounter id, patient-present minutes, counts_toward_goal + why
         ├─ sources     which facts built each contact (the audit trail)
         ├─ goals       "≥3 therapy days and ≥150 min/week, from 2026-01-05"
         ├─ measures    symptom scores over time
         └─ issues      unresolved conflicts and gaps, stated explicitly


The question command

Input:   python cli.py ask "How many therapy minutes did Rowan receive in each week?"
         (free-text question, read against the saved abstraction only)

Output:  an answer with
         - the computed figures
         - the exact contact IDs and documents behind each figure
         - inclusion/exclusion decisions ("med management excluded: plan says
           it doesn't count toward the minute goal")
         - anything the record cannot settle, said out loud

I also want `show day --date`, `show contact <id>`, `export --json` and `benchmark`, since those are what
make the abstraction inspectable on the call rather than just in principle. `ask` has to work in a fresh
process with no documents present, reading the database alone—that is the across-restarts requirement, so
please confirm it genuinely holds rather than assuming it does.

Layout is `backbone/` holding `cli.py ingest.py extract.py verify.py reconcile.py queries.py ask.py
schema.py prompts.py`, plus `data/ outputs/ logs/ tests/` and a `README.md`.

## 4. Model settings

Extraction runs on `gpt-6-luna`, priced at $0.10 per 1M input tokens, $0.01 cached input and $0.50 per 1M
output. A smaller or cheaper variant is fine for routing and answer writing. Use structured outputs with a
JSON schema and `strict: true` so every reply parses, and temperature 0 wherever it is accepted—reasoning
models may ignore it, so set a low reasoning effort for extraction instead. Log every call with its model,
prompt version, input and output tokens, latency and cost, because the benchmark section depends on having
them.

## 5. Validation

I worked these out by hand from the documents before any code existed. They belong in `tests/` as a
fixture to assert against, and nowhere near the pipeline itself—the point is that they fall out of the
rules rather than being coded for.

- 12 therapy sessions: 5 individual, 5 group, 2 family, across 11 distinct days
- 585–595 patient-present minutes (9.75–9.92 hours), where the 10-minute range comes entirely from the
  January 26 conflict
- the plan goal is at least 3 therapy days and at least 150 patient-present minutes per Monday–Sunday week
- January 19: 2 contacts, 90 minutes. January 21: 1 contact, 45 minutes, since the two calls sit under one
  appointment and the dropout is excluded
- distinct PHQ-9 administrations are January 5 at 18, January 16 at 14 and January 30 at 10. The January 26
  "measure summary" copies form HG-Q116 from January 16 and is not a fourth assessment
- medication management, partner-only collateral and care coordination are excluded from minute totals

| week (Mon–Sun) | days | minutes | verdict |
|---|---:|---:|---|
| Jan 5–11 | 3 | 140 | not met (minutes) |
| Jan 12–18 | 2 | 120 | not met (days and minutes) |
| Jan 19–25 | 3 | 180 | met |
| Jan 26–Feb 1 | 3 | 145–155 | cannot be determined |

The system should raise these on its own. High severity: January 26 HG-E115, where two signed notes
disagree on duration and the conflict is unresolved, so it is reported as a range; and January 27 HG-E116,
where a draft note and a posted charge exist for a session the signed register records as a no-show. Info
level: January 9 and January 26 each have two notes for one encounter, counted once; January 19's BH-D104
is a resent copy, merged and not re-counted; and the January 16 PHQ-9 appears as an original plus an
import, which is one administration.

Three checks worth running and reporting. The duplicate test adds an exact copy and a CRLF variant of two
files and re-runs `process`, expecting zero model calls and no change to any number. The stability test
runs two independent cold extractions and diffs the contacts, minutes, verdicts, measures and issues.
And running the answers once with the quote-checker disabled tells us how many quotations fail without it,
which is the most honest way to show the checker is doing something.

## 6. Benchmarks and deliverables

Label measured results separately from estimates. Measure a cold `process` over the 31 documents for time,
calls, tokens and cost; a re-run with nothing new; a re-run after adding duplicates; a restart followed by
a query against the saved abstraction; code-only query latency; one full question through the LLM for its
latency range, median, calls and cost; the whole benchmark end to end; and the size of the abstraction
along with tokens per document. Then extrapolate tokens, cost and time at 500K and 1M documents, standard
tier against the Batch API, and say clearly that those are extrapolations.

The first bottleneck I expect at a million documents is extraction throughput, since it is one model call
per document—name the function in the README. The fixes are the Batch API for the backfill, a cheaper
model or a template parser for the structured document types like rosters, exports and billing, and
raising concurrency to the rate limit. Daily arrivals stay cheap either way, because only new fingerprints
get extracted and only affected patients get re-reconciled. After that the next constraints are the answer
step re-sending full tool payloads every turn, which dominates cost; ingest re-hashing every file instead
of indexing by path, size and mtime; keyword search scanning all text instead of using FTS5; and SQLite's
single writer, which means Postgres once several workers write at once.

What ships is the runnable code with setup instructions for processing documents and asking new questions
off the saved database, `outputs/answers.md` with the five answers and their sources,
`outputs/benchmark.md`, `outputs/abstraction.json`, `logs/`, and a short `README.md` covering the approach,
one design decision I tested and what it showed, one observed limitation and how I would investigate it
next, the first bottleneck at a million documents, model names and settings, coding assistance used, and
approximate runtime and cost.

The scope is 2 to 5 hours. Anything left incomplete gets written down with the tradeoff rather than
hidden—documenting a gap honestly is worth more here than a pipeline that quietly papers over one.
