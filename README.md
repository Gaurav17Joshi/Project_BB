# Clinical abstraction prototype

Reads the supplied behavioral-health records, builds an auditable abstraction of each patient's care in
SQLite, and answers questions from it. **The model reads and writes; code decides and counts.**

![Method: the model extracts facts once, code verifies, reconciles and counts; questions are answered by the model through code queries, and code checks every quote in the answer](docs/method.png)

*The robot marks model steps; everything else is plain code. Figure source: `docs/figure/method.tex`.*

The system runs on `gpt-6-luna` through the OpenAI API. As a comparison, the same pipeline was also run with a
small open model on a local GPU (`qwen3.5:9b` through Ollama). It reached identical results; see
[Closed vs local model](#closed-vs-local-model). The instructions below are for the GPT version, which is the one
to run.

## Quick start

Needs **Python 3.10+**. The commands are the same on Windows and macOS once the virtual environment is
active; only the setup lines differ.

**1. Install**

Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux (Terminal):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Add your OpenAI key** in one of three ways. The key is never stored in the repo.

| | Windows (PowerShell) | macOS / Linux |
|---|---|---|
| Key in the environment | `$env:OPENAI_API_KEY="sk-..."` | `export OPENAI_API_KEY=sk-...` |
| Key in a file elsewhere | `$env:OPENAI_KEY_FILE="C:\path\key.txt"` | `export OPENAI_KEY_FILE=~/path/key.txt` |
| `.env` file in this folder | copy `.env.example` to `.env` and fill it in | same |

**3. Run**

```bash
python cli.py process                      # ingest + extract new documents + reconcile
python cli.py answer-file                  # answer data/questions.json -> outputs/closed/answers/
python cli.py ask "How many group minutes did Rowan get in the week of Jan 19?"
python web/server.py --open                # browser chat at http://127.0.0.1:8000
python scripts/benchmark.py                # measured benchmark -> outputs/closed/benchmark.md
```

These need **no key**; they only read the saved abstraction (included in `outputs/closed/`):

```bash
python cli.py show contacts                # one row per reconciled contact, with inclusion decision and minutes
python cli.py show weeks                   # weekly days / minutes / hours
python cli.py show goal                    # weekly verdict vs the treatment-plan goal
python cli.py show counts | issues | measures | patients
python cli.py show day --date 2026-01-19   # every source record behind one day
python cli.py rebuild                      # re-verify + re-reconcile from cached extractions
```

New documents: drop them into `data/documents/` (or pass `--docs DIR`) and run `process` again. Only unseen
documents are sent to the model, and only the affected patients are re-reconciled. New questions use the saved
abstraction; nothing is rebuilt per question.

The browser chat (`web/`, standard library only, screenshot at the end) shows the patient summary from the
abstraction and answers questions through the same pipeline as `cli.py ask`. Each answer shows its quote check,
cost and the queries it used. Clicking a document tag such as **BH-D103** opens the source with the quoted
passages highlighted.

## What is where

| Path | Contents |
|---|---|
| `SOLUTION.md` | Detailed write-up: design, rules, every contact, results, checks, both backends, cost. |
| `outputs/closed/` (GPT, the main results), `outputs/open/` (local model, for comparison) | Each has `abstraction.db` (SQLite), `abstraction.json` and `contacts.csv` (exports), `answers/` (DEV-01–05 plus unseen NEW-01–03, each with its quote check and tool calls), `benchmark.md` / `.json`. |
| `outputs/comparison.md` | Local vs closed abstraction, contact by contact. |
| `logs/<closed|open>/llm_calls.jsonl` | Every model call: step, model, latency, tokens. The `runs` table in each DB logs every process/ask run. |
| `backbone/` | `ingest` → `extract` (+ `schema`, `prompts`) → `verify` → `reconcile` → `queries` → `ask`. Backends: `llm_openai.py`, `llm_ollama.py`, chosen in `config.py`. |
| `web/` | Browser chat (GPT backend). |
| `scripts/` | `benchmark.py`, `compare_backends.py`, `compare_think.py` (thinking on/off test), `check_model.py` (lists the models your key can use). |
| `docs/` | The method figure and its TikZ source (`docs/figure/build.ps1` on Windows, `build.sh` on macOS). |

## The abstraction

Three layers, all in one SQLite file. Every fact keeps its source document, a verbatim quote, and the quote's
character offsets and line number.

1. **Documents.** One row per distinct text (SHA-256 of whitespace-normalised text), so duplicate copies of a
   file are detected before any model call. Extractions are cached by `(document, model, prompt version)`.
2. **Facts** (one row per claim, from the model): service records (one per encounter mentioned in a document,
   including no-shows and cancellations), corrections, treatment-plan goals, standardized measures, clinical
   observations. The model reports **times as written**, never totals; `verify.py` locates every quote in the
   source.
3. **Reconciled** (pure code, `reconcile.py`): one `contacts` row per real encounter, with status, the basis for
   that status, whether it counts toward the plan goal (`included / excluded / uncertain`) and why, minutes as a
   `lo–hi` range with the calculation written out, and links to every source record. Plus `measures_distinct`
   (one row per administration) and `issues` (conflicts, merged duplicates, how each was resolved).

### Reconciliation rules (`reconcile.py`, the same for both backends)

- Records are grouped by encounter or appointment ID. Notes from two clinicians, resent copies, and telehealth
  reconnects under one appointment become **one contact**.
- Evidence tiers. **A:** signed notes, attendance records, corrections, cancellation and no-show logs. **B:**
  schedule exports and copies. **C:** drafts, templates and billing. Status comes from the highest tier that speaks
  to attendance. **Tier C never establishes that care happened.** A later date alone never overrides; only explicit
  corrections replace a value, and only the field they name.
- For arrival and departure times, attendance records and corrections outrank narrative notes within a tier.
- Minutes = patient-present intervals − documented breaks/disconnects, after corrections. If final records
  disagree and nothing resolves it, the contact gets a range and a `duration_conflict` issue. Weekly verdicts are
  `met` / `not_met` / `indeterminate` depending on whether the whole range clears the threshold.
- **Schedule-echo rule.** If two signed records for one session disagree and one gives exactly the booked slot,
  that value is set aside as a likely copied default and logged as an issue for review. This is the failure the
  Jan 19 roster itself shows (BH-D102, corrected by BH-D103).
- What counts toward the goal is read from the treatment plan's own definition (extracted), not hard-coded. Only
  goals with numeric thresholds are used. Records without a single valid calendar date are flagged and left out.

No patient facts or answers are encoded anywhere; the rules are about document types, not about Rowan. Several
of these rules were added after the local model's first run exposed failure modes (see SOLUTION.md section 8).
Re-running the closed model's cached extractions through the final rules gives identical results, contact by
contact.

## Results on the development questions

| | Result (both backends) |
|---|---|
| Sessions (Jan 5–30) | 12 attended: 5 individual, 5 group, 2 family; 11 distinct days |
| Minutes | 585–595 (9.75–9.92 h). Weeks: 140 · 120 · 180 · 145–155 |
| Goal (≥3 days and ≥150 min per week) | Week 1 not met (minutes), week 2 not met (both), week 3 met, week 4 **cannot be determined** |
| The one open conflict | Jan 26 individual session: two signed final notes give 09:00–09:50 (50 min) and 09:10–09:50 (40 min). It decides week 4. |
| Jan 19 | 2 contacts, 90 min: group 10:00–11:15 per correction BH-D103, minus 15-min break = 60; individual 30 |
| Jan 21 | 1 contact, 45 min: one video encounter, two connections, 10-min drop excluded |
| PHQ-9 | 3 distinct administrations: 18 → 14 → 10. The Jan 26 import (BH-D014) is a copy of the Jan 16 form, not a new assessment |
| Not counted | Jan 8 no-show, Jan 15 clinic cancellation, Jan 27 no-show despite an unsigned template note and posted charge, Jan 28 patient cancellation, medication visits, partner-only collateral, care coordination |

Full answers with quotes: `outputs/closed/answers/` and `outputs/open/answers/`.

### Closed vs local model

The local abstraction matches the closed one on every headline number and on 20/20 encounter contacts
(`outputs/comparison.md`). It took several steps to get there:

| Local version | Same outcome as closed | Headline results |
|---|---:|---|
| v1: same prompt as closed, no extra safeguards | 13/20 | **Wrong:** weeks 1–2 and 4 marked "met"; 615–655 min |
| + code safeguards (numeric goals only; attendance records outrank notes for times) | 14/20 | sessions right, minutes still off (Jan 6) |
| + prompt v2 (rules aimed at the observed mistakes) | 18/20 | Jan 6 and Jan 22 became ranges; one document failed (output loop) |
| + retry with sampling, schedule-echo rule, date validation | **20/20** | all match |

What still differs is the writing. The local answers repeat some of the 9B model's labelling errors; one
called the correction BH-D103 a "duplicate copy". The numbers are right because code computes them.
Extraction quotes were found exactly 136/159 times for the local model and 137/137 for the closed model; the
rest are flagged in `issues`.

How the comparison was produced: the local model runs through the same code with `--backend ollama`
(`backbone/llm_ollama.py`), using `qwen3.5:9b` in Ollama on an RTX 2080 Ti (11 GB). Its saved results are in
`outputs/open/`, and `python scripts/compare_backends.py` rebuilds `outputs/comparison.md` from the two saved
databases without calling either model. Re-running the local extraction is not needed to review it, and takes
about 23 minutes on that GPU. Details are in SOLUTION.md section 8.

## Design decisions tested

**1. Code-checked citations.** Every answer is checked by code: each quotation must be found in a document
cited on the same line. If any fails, the model gets one repair pass with the failing quotes listed, and the
result is printed under each answer.
- Before the check, 3 of 94 quotations in the first closed run were not in the source. Two were invented
  paraphrases. One of those also carried a factual error: it called BH-D104 a copy of the *final* roster, when
  it is a resent copy of the *original, uncorrected* roster.
- With the check, every quotation verified in two full closed benchmark runs (103/103 and 74/74, 8 questions
  each). The repair pass was needed in 1 and 2 answers of 8.

What I learned: the numbers were never the problem, because they come from code. The model's errors showed up
in the wording around the evidence, so the quotes themselves have to be checked.

**2. Thinking on or off for local extraction.** Tested on 4 hard documents (`scripts/compare_think.py`): thinking
was about 4× slower (167–193 s vs 25–74 s per document), fixed one document, left the important errors in place,
and looped past the 12K-token cap on one. Decision: thinking off for extraction, on for answering.

## Observed limitation

**Questions that assume facts the record does not contain.** Asked how care changed "before and after a
treatment-plan change", the closed system first invented a change. It treated the plan's signing on Jan 5 as the
change and produced a confident before/after table. The record has one plan version. I fixed this case two ways:
`plan_change_comparison` now refuses when no second plan version exists, and the prompt tells the model to say
when a premise is absent. But the general failure, bending other events to fit a question's premise, is still
possible for other question types.

How I would investigate it next: write a set of false-premise and out-of-scope questions (a plan change, a
second patient, an anxiety scale that was never given, a session on a date with none), run them on both
backends, and measure how often an answer asserts something the abstraction doesn't contain. Then test whether
a `what_does_the_record_contain` tool that runs before answering lowers that rate.

A smaller judgement I made deliberately: for the Jan 26 duration conflict, the system reports a 40–50 minute
range and does not pick a winner. The second note is more specific ("Rowan entered the treatment room at
09:10"), but neither note corrects the other.

## Performance (measured)

Full tables: `outputs/closed/benchmark.md` and `outputs/open/benchmark.md`.

| Measured on the 31 documents | `openai` (gpt-6-luna) | `ollama` (qwen3.5:9b, RTX 2080 Ti) |
|---|---:|---:|
| Process all documents, cold | 40 s (8 workers) | 1,357 s = 22.6 min (1 at a time, ~44 s per document) |
| Extraction tokens (input / output) | 76K / 30K | 39K / 45K |
| Re-run with nothing new; adding duplicate copies | 0.05 s, 0 model calls | 0.05 s, 0 model calls |
| Restart and query the saved abstraction | 0.17 s | 0.19 s |
| Code-only query (counts, weeks, verdicts) | 1–5 ms | 1–5 ms |
| One question through the model (8 questions) | 14–93 s, median 29 s | 20–277 s, median 63 s |
| Answer quotes verified against sources | 74/74 | 40/47 (the 7 failures are shown with their answers) |
| Saved abstraction (SQLite, incl. a copy of the 49 KB source text) | 476 KB | 560 KB |
| Cost | $0.023 extraction (first-ever run), $0.028 for all 8 questions | $0 (local; machine time and power only) |

Both backends give the same headline results. The difference is speed and wording: the local model is about 34×
slower to extract on this GPU, and its answers less often quote the sources word for word. The check catches
that, and the unverified quotes are listed under each answer rather than hidden.

## Scaling to 500K–1M documents (estimates, not measured)

- **First bottleneck at 1M documents: extraction throughput and cost.** `extract.run_extraction` makes one model
  call per document, about 2.5K input and 1K output tokens each.
  - Closed: about 2.5B input and 1B output tokens, about **$730** at the standard price ($365 for 500K documents),
    half with the Batch API. About 14 days at 8-way concurrency, so API rate limits set the pace.
  - Local: about 44 s per document one at a time on the RTX 2080 Ti, so roughly **250 days for 500K documents** and 500 days for 1M on one such GPU. No per-token cost, but it only scales with more or faster GPUs and a batching server.
  - What I'd change: the Batch API for the backfill (closed) or a batching server such as vLLM on more GPUs
    (local); send structured document types (rosters, exports, billing) to a cheaper model or a template parser;
    keep the static system prompt first so prompt caching applies. Daily new documents stay cheap, since only new
    hashes are extracted.
- **Next: the answering step.** `ask.answer` puts `list_patients()` into the prompt, which breaks at about 100K
  patients. The collection-wide tools recompute every patient on the fly (3–4 ms each, so about 6 minutes for
  100K patients) and return full lists. What I'd change: materialise a per-patient weekly table at reconcile
  time, return aggregates plus paginated IDs, and drop the patient list from the prompt.
- **Then:** `ingest.ingest` re-hashes every file on each run (index by path, size and modified time instead);
  `search_documents` scans all text (use SQLite FTS5); SQLite allows one writer (move to Postgres once several
  workers write at once).
- **Repeated reviews:** reconciliation is partitioned by patient, so a new document re-reconciles one patient in
  milliseconds. A change to the extraction prompt invalidates every cached extraction for that backend.

## Models, settings, assistance

- **`openai`:** `gpt-6-luna` through the Responses API. Extraction uses strict JSON-schema output,
  `reasoning.effort = low` and 8 parallel workers; prompt version `extract-v1`. Answering uses function tools with
  `reasoning.effort = medium`, and the repair pass uses `low`. Prices are `gpt-6-luna` standard tier from OpenAI's
  pricing docs (checked 2026-10-05): $0.10 per 1M input tokens, $0.01 cached input, $0.50 output; the Batch API is
  half. They are defaults in `backbone/config.py` and can be overridden with environment variables.
- **`ollama`:** `qwen3.5:9b` (Q4_K_M) through Ollama 0.35. JSON-schema output is enforced by Ollama's constrained
  decoding. Temperature 0, context 32K tokens, output capped at 12K, one request at a time. Extraction runs with
  thinking off and the extra local-model rules (prompt version `extract-v2-local`), and retries truncated JSON at
  temperature 0.3, then 0.6. Answering runs with thinking on, and tool results are cut at 24K characters so a
  prompt never overflows the context window.
- **Coding assistance:** Claude Code (Claude Opus 5.5, `claude-opus-5-5`) wrote the code with me; I directed the
  design and reviewed the outputs against the source documents.
- **Runtime and cost:** see Performance. All closed-model development work, about 300 model calls, cost about $0.17.

## Incomplete work and trade-offs

- Patient identity is the printed MRN. There is no cross-MRN matching for typos or merged charts.
- Reconciliation rules were written against this document set, and the local-model safeguards were validated only
  on these 31 documents. A fair test would run both backends on fresh documents.
- Answers are generated per question with no answer cache; the abstraction, not the answer, is the reusable unit.
- The SQLite file keeps a copy of each document's text so quotes can be looked up. At scale, the text would live
  in object storage instead.

## Browser chat

`python web/server.py --open` serves this page at http://127.0.0.1:8000. It answers with the GPT backend from the
saved abstraction, shows the quote check under each answer, and opens the cited source when a document tag is clicked.

![The browser chat answering which weeks met the treatment-plan goal, with the patient summary on the left](docs/web_chat.png)
