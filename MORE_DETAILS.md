# More details

Everything the README leaves out for brevity. The full write-up, with every contact and how each result was
checked, is in [SOLUTION.md](SOLUTION.md).

## Setup in full

Needs **Python 3.10+**. The commands are the same on Windows and macOS once the virtual environment is active.

**Install**

Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**OpenAI key**, in one of three ways. The key is never stored in the repo.

| | Windows (PowerShell) | macOS / Linux |
|---|---|---|
| Key in the environment | `$env:OPENAI_API_KEY="sk-..."` | `export OPENAI_API_KEY=sk-...` |
| Key in a file elsewhere | `$env:OPENAI_KEY_FILE="C:\path\key.txt"` | `export OPENAI_KEY_FILE=~/path/key.txt` |
| `.env` file in this folder | copy `.env.example` to `.env` and fill it in | same |

**Use the saved abstraction.** The abstraction of the 31 supplied documents is already built
(`outputs/closed/abstraction.db`), along with the answers to the five development questions
(`outputs/closed/answers/`). Nothing needs to be processed first.

```bash
python cli.py ask "How many group minutes did Rowan get in the week of Jan 19?"
python web/server.py --open                # the same, as a browser chat at http://127.0.0.1:8000
python cli.py answer-file                  # re-answer data/questions.json -> outputs/closed/answers/
```

Inspect it (no key needed):

```bash
python cli.py show contacts                # one row per reconciled contact, with inclusion decision and minutes
python cli.py show weeks                   # weekly days / minutes / hours
python cli.py show goal                    # weekly verdict vs the treatment-plan goal
python cli.py show counts | issues | measures | patients
python cli.py show day --date 2026-01-19   # every source record behind one day
python -m unittest discover tests -v       # the saved abstractions vs answers worked out by hand
```

**Process new documents.** Drop new files into `data/documents/` (or pass `--docs DIR`) and run
`python cli.py process`. Documents already in the abstraction are skipped (re-running `process` on the supplied set
makes 0 model calls), and duplicate copies are detected by fingerprint and never change a number. To rebuild
everything from scratch, delete `outputs/closed/abstraction.db` first (about 40 s and $0.02).
`python scripts/benchmark.py` measures that cold run in a separate scratch database, without touching the saved one.

**Browser chat.** `web/` uses only the standard library. It shows the patient summary from the abstraction and
answers questions through the same pipeline as `cli.py ask`. Each answer shows its quote check, cost and the queries
it used, and clicking a document tag such as **BH-D103** opens the source with the quoted passages highlighted.

## What is where

| Path | Contents |
|---|---|
| `SOLUTION.md` | Detailed write-up: design, rules, every contact, results, checks, both backends, cost. |
| `PERFORMANCE.md` | Detailed measurements for both backends. |
| `Rough_idea.txt`, `Plan.md` | My first notes on the problem, and the build plan written from them. |
| `outputs/closed/` (GPT, the main results), `outputs/open/` (local model, for comparison) | Each has `abstraction.db` (SQLite), `abstraction.json` and `contacts.csv` (exports), `answers/` (DEV-01–05 plus unseen NEW-01–03, each with its quote check and tool calls), `benchmark.md` / `.json`. |
| `outputs/comparison.md` | Local vs closed abstraction, contact by contact. |
| `logs/<closed|open>/llm_calls.jsonl` | Every model call: step, model, latency, tokens. The `runs` table in each DB logs every process/ask run. |
| `backbone/` | `ingest` → `extract` (+ `schema`, `prompts`) → `verify` → `reconcile` → `queries` → `ask`. Backends: `llm_openai.py`, `llm_ollama.py`, chosen in `config.py`. |
| `tests/` | `test_expected.py`: the hand-worked answers from Plan.md section 5, duplicate handling, and restart. |
| `web/` | Browser chat (GPT backend). |
| `scripts/` | `benchmark.py`, `compare_backends.py`, `compare_think.py` (thinking on/off test), `check_model.py` (lists the models your key can use). |
| `docs/` | The method figure and its TikZ source (`docs/figure/build.ps1` on Windows, `build.sh` on macOS). |

## The abstraction

The abstraction lives in a single SQLite file and is built in three layers, where every fact keeps the document
it came from, a verbatim quote, and that quote's exact position in the source. The first layer is the documents
themselves, fingerprinted by content so a duplicate copy is caught before it ever reaches the model. The second is
what the model extracts—one row per claim, covering service records (no-shows and cancellations included),
corrections, plan goals, PHQ-9 scores and clinical observations—where I made the model report times exactly as
written and never add them up, and code then checks that every quote really exists in the source. The third layer
is where the actual decisions happen, all in plain code: records about the same encounter merge into one contact,
signed records outrank schedule exports and copies, and a draft or a billing entry can never prove that care took
place. A later document only overrides an earlier one through an explicit correction, and only for the field it
names. Minutes are patient-present time minus documented breaks, and when signed records genuinely disagree, the
contact keeps a range and an open issue rather than a guess. None of the rules mention Rowan, dates or document
IDs—they're about document types—and the full list is in SOLUTION.md section 3.4.

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

Full answers with quotes: `outputs/closed/answers/` and `outputs/open/answers/`. For the Jan 26 conflict the system
reports 40–50 minutes instead of picking a winner, because neither note corrects the other.

## Scaling beyond the first bottleneck (estimates, not measured)

The README covers the first bottleneck, extraction. The local model would hit it far harder: roughly 500 days for a
million documents on a single RTX 2080 Ti, so it only becomes realistic with more GPUs and a batching server like
vLLM. After extraction, the next pressure point is answering: `ask.answer` puts the patient list into the prompt, and
the collection-wide tools recompute every patient on the fly, which would take about 6 minutes at 100K patients. I'd
materialise a per-patient weekly table at reconcile time and have the tools return aggregates with paginated IDs.
Beyond that, ingest re-hashes every file on each run instead of indexing by path, size and modification time,
keyword search scans all text instead of using SQLite FTS5, and SQLite's single writer would have to become Postgres
once several workers write at once.

## Closed vs local model

Out of curiosity, I also ran the exact same pipeline on a small open model—`qwen3.5:9b` running locally through
Ollama on an RTX 2080 Ti—to see how much of the result depends on the model and how much on the code. It ended up
matching GPT on every headline number and on all 20 encounter contacts (`outputs/comparison.md`), but it didn't start
there: the first run got only 13 of 20 right and marked almost every week as "met," because the 9B model logged
narrative goals like "continue the plan" as treatment goals and copied scheduled times into notes as if they were
real attendance. General safeguards in code, clearer extraction rules and a retry when the model got stuck repeating
itself brought it to 20/20, and re-running GPT's cached extractions through the same final rules changed nothing.
What still differs is the writing—the local answers repeat some of the small model's labelling mistakes, even though
the numbers stay right because code computes them. Its saved results are in `outputs/open/`, and the full story is
in SOLUTION.md section 8.

| | Local 9B | GPT-6 Luna |
|---|---|---|
| Processing all 31 documents | 22.6 minutes | 35–40 seconds |
| Typical question | 45–63 seconds | 25–29 seconds |
| Answer quotes verified | 40 of 47 | all of them |
| Cost | $0 | about $0.04 per full run |

I also tested whether letting the local model "think" before extracting would help. On four hard documents it was
about 4× slower, fixed one document, left the important errors in place and got stuck in a loop on another, so
thinking stays off for extraction and on for answering.

## Thinking settings

| Step | GPT-6 Luna (main system) | Local qwen3.5:9b (comparison only) |
|---|---|---|
| Extraction, once per document | low reasoning effort | off |
| Answering a question (choosing queries and writing the answer) | medium | on |
| Repair pass, only when a quote fails the check | low | on |
| Ingest, verify, reconcile, all calculations, quote check | no model, plain code | no model, plain code |

Extraction is mostly careful reading, so it runs on low; answering gets medium because it has to plan its queries.
Ollama only has on or off, and I turned it off for extraction after the test above showed it was 4× slower without
fixing the important errors. Settings live in `backbone/config.py` (extraction) and `backbone/ask.py` (answering).

Other settings: the OpenAI backend uses the Responses API with strict JSON-schema output, 8 parallel extraction
workers and prompt version `extract-v1`; prices default to the `gpt-6-luna` standard tier in `backbone/config.py` and
can be overridden with environment variables. The local backend uses `qwen3.5:9b` (Q4_K_M) through Ollama 0.35, with
JSON-schema output enforced by constrained decoding, temperature 0, a 32K-token context, output capped at 12K tokens,
one request at a time, the extra local-model rules (prompt version `extract-v2-local`), and retries on truncated JSON
at temperature 0.3, then 0.6. Tool results are cut at 24K characters so a prompt never overflows the context window.

## Incomplete work and trade-offs

- The brief describes multiple patients, but the supplied data has only one (Rowan Mercer). Everything is keyed by
  patient and the collection-wide tools (`compliance_all`, `consecutive_weeks_below`) exist, but they have only been
  exercised on this one patient.
- Patient identity is the printed MRN. There is no cross-MRN matching for typos or merged charts.
- Reconciliation rules were written against this document set, and the local-model safeguards were validated only
  on these 31 documents. A fair test would run both backends on fresh documents.
- Answers are generated per question with no answer cache; the abstraction, not the answer, is the reusable unit.
- The SQLite file keeps a copy of each document's text so quotes can be looked up. At scale, the text would live
  in object storage instead.
