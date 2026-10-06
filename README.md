# Clinical abstraction prototype

Reads the supplied behavioral-health records, builds an auditable abstraction of the patient's care in SQLite, and
answers questions from it. **The model reads and writes; code decides and counts.**

![Method: the model extracts facts once, code verifies, reconciles and counts; questions are answered by the model through code queries, and code checks every quote in the answer](docs/method.png)

*The robot marks model steps; everything else is plain code.*

## Approach

The answers here aren't sitting in any single passage—you only get them after merging three or four documents that
describe the same session and then doing arithmetic over what survives—so I built a reconciled timeline rather than
a retrieval pipeline. The model (`gpt-6-luna`) reads each document once and pulls out facts against a strict schema,
with every fact carrying a verbatim quote that code then locates in the source. Everything after that is plain code:
records about the same encounter merge into one contact, signed records outrank copies and schedule exports, drafts
and billing can never prove care happened, only explicit corrections override earlier values, and genuine
disagreements are kept as ranges with an open issue rather than guessed. To answer a question, the model calls query
functions that compute every number, writes the prose around them, and code checks each quotation against the
document it cites. The result for Rowan: 12 sessions on 11 days, 585–595 minutes, and weekly goal verdicts of not
met, not met, met and cannot be determined (the answers are in `outputs/closed/answers/`). As a comparison, the same
pipeline run on a small local model (`qwen3.5:9b`) reached identical results.

## Setup and running

Needs Python 3.10+. Install, then add your OpenAI key (or copy `.env.example` to `.env`):

| Windows (PowerShell) | macOS / Linux |
|---|---|
| `python -m venv .venv` | `python3 -m venv .venv` |
| `.venv\Scripts\Activate.ps1` | `source .venv/bin/activate` |
| `pip install -r requirements.txt` | `pip install -r requirements.txt` |
| `$env:OPENAI_API_KEY="sk-..."` | `export OPENAI_API_KEY=sk-...` |

The abstraction of the 31 documents is already saved in `outputs/closed/abstraction.db`, so nothing needs to be
processed first:

```bash
python cli.py ask "How many group minutes did Rowan get in the week of Jan 19?"   # new question, saved abstraction
python web/server.py --open                 # the same as a browser chat (screenshot at the end)
python cli.py show goal                     # inspect without a key: contacts | weeks | goal | issues | day --date ...
python cli.py process                       # new documents in data/documents/: extracts only unseen ones
python -m unittest discover tests           # checks the saved abstraction against hand-worked answers
```

## Design decision tested

The decision I learned the most from was checking citations in code. Since every number comes from the query
functions, I expected the answers to be trustworthy once the arithmetic was right—but in the first full run, 3 of
94 quotations weren't actually in the source. Two were paraphrases dressed up as quotes, and one carried a real
factual error: it called BH-D104 a copy of the *final* roster when it's a resent copy of the *original,
uncorrected* one, which is exactly the distinction that decides whether the Jan 19 correction holds. So now code
re-locates every quotation in the document it cites, gives the model one repair pass on a miss, and prints the
result under the answer. With that in place, every quotation verified across two full benchmark runs (103/103 and
74/74). What this taught me is that grounding a model in tool outputs isn't enough on its own—the errors simply
move from the numbers into the wording around them, so the quotes need checking too.

## Observed limitation

The limitation that worried me most is questions that assume something the record doesn't contain. When I asked
how care changed "before and after a treatment-plan change," the system invented one—it treated the plan's signing
on Jan 5 as the change and produced a confident before/after table, even though the record has only one plan
version. I fixed that case by making `plan_change_comparison` refuse when no second version exists and telling the
model to say plainly when a premise is missing, but the underlying tendency to bend events to fit a question can
still show up elsewhere. To investigate it properly, I'd write a set of false-premise questions—a plan change, a
second patient, a scale that was never given, a session on an empty date—run them, and measure how often an answer
claims something the abstraction doesn't hold. Then I'd test whether a `what_does_the_record_contain` tool, called
before answering, brings that rate down.

## First bottleneck at a million documents

I expect it to be extraction, in `extract.run_extraction`, which makes one model call per document at roughly 2.5K
input and 1K output tokens. At a million documents that's about 2.5B input and 1B output tokens—around **$730** at
the standard price, or half through the Batch API—and about 14 days at the current 8-way concurrency, so API rate
limits end up setting the pace (these are estimates extrapolated from the measured run). I'd move the backfill to the
Batch API, route simple structured documents like rosters, exports and billing to a cheaper model or a template
parser, and keep the static prompt first so prompt caching applies. Daily arrivals stay cheap either way, since only
unseen fingerprints get extracted and only the affected patient is re-reconciled.

## Models, settings, assistance, runtime and cost

| Step | Model and settings |
|---|---|
| Extraction, once per document | `gpt-6-luna` (OpenAI Responses API), strict JSON schema, reasoning effort **low**, 8 parallel workers |
| Answering a question | `gpt-6-luna` with function tools, reasoning effort **medium** |
| Repair pass, when a quote fails the check | `gpt-6-luna`, reasoning effort **low** |
| Ingest, verify, reconcile, all arithmetic, quote check | no model, plain code |

| Measured on the 31 documents | Runtime | Cost |
|---|---|---|
| Processing all documents | about 40 s | $0.023 |
| One question | 14–93 s, median about 29 s | under $0.01 |
| Full benchmark (processing + 8 questions) | about 6 min | about $0.04 |

Prices are `gpt-6-luna` standard tier ($0.10 per 1M input tokens, $0.01 cached, $0.50 output). All closed-model
development work, about 300 model calls, cost about $0.17. The local comparison model was `qwen3.5:9b` through
Ollama on an RTX 2080 Ti, with thinking off for extraction (it was 4× slower with it on, without fixing the important
errors); it took 22.6 minutes for the 31 documents at no API cost.

**Coding assistance:** Claude Code (Claude Opus 5.5, `claude-opus-5-5`). I first worked through the task and read a
few of the documents, wrote down my initial idea in `Rough_idea.txt`, and then worked with Claude to turn it into
the full `Plan.md`. Claude then coded it up with my comments and steering, and I checked the design and reviewed the
outputs against the source documents.

## More details

- [MORE_DETAILS.md](MORE_DETAILS.md): the abstraction and its rules, full results, the next scaling bottlenecks,
  the local-model comparison, thinking settings, incomplete work and trade-offs, and what is where in the repo.
- [SOLUTION.md](SOLUTION.md): the full write-up, with every contact and how each result was checked.
- [PERFORMANCE.md](PERFORMANCE.md): detailed measurements for both models.

## Browser chat

![The browser chat answering which weeks met the treatment-plan goal, with the patient summary on the left](docs/web_chat.png)
