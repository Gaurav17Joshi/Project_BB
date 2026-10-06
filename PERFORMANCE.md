# Performance (measured)

All numbers were measured on the 31 supplied documents and 8 questions (the five development questions plus three
unseen ones), on the same machine. The raw benchmark output is in `outputs/closed/benchmark.md` and
`outputs/open/benchmark.md`; rerun with `python scripts/benchmark.py`.

| | `openai` (gpt-6-luna) | `ollama` (qwen3.5:9b, RTX 2080 Ti) |
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
slower to extract on this GPU, and its answers less often quote the sources word for word. The check catches that,
and the unverified quotes are listed under each answer rather than hidden.

Prices are `gpt-6-luna` standard tier from OpenAI's pricing docs (checked 2026-10-05): $0.10 per 1M input tokens,
$0.01 cached input, $0.50 output; the Batch API is half. All closed-model development work, about 300 model calls,
cost about $0.17.
