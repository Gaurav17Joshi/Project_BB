# Benchmark (measured)

All numbers below were measured on this machine against the supplied 31 documents, model `qwen3.5:9b` running locally (Ollama 0.35.1, RTX 2080 Ti 11 GB, one request at a time).

## Processing

| Run | Wall time | LLM calls | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| Cold (empty DB) | 1356.94 s | 31 | 39407 | 45166 |
| Warm re-run (no new docs) | 0.045 s | 0 | 0 | 0 |
| +2 duplicate copies (exact, and CRLF/whitespace variant) | 0.02 s | 0 | 0 | 0 |

Cold breakdown: ingest 0.036 s, extraction 1355.955 s (1 parallel workers), verify+reconcile 0.941 s.  
Duplicate test: 2 copies detected, contacts unchanged: **True**.  
Restart (new process loads the saved DB and runs a query): 0.19 s.

## Question latency

| Question | Scope | Latency | LLM calls | Input tokens | Output tokens | Quotes verified |
|---|---|---:|---:|---:|---:|---:|
| DEV-01 | patient | 96.67 s | 4 | 24669 | 4469 | 1/4 |
| DEV-02 | patient | 168.96 s | 5 | 32905 | 8593 | 2/2 |
| DEV-03 | patient | 23.56 s | 2 | 7653 | 1124 | 1/1 |
| DEV-04 | patient | 29.91 s | 2 | 8579 | 1483 | 1/1 |
| DEV-05 | patient | 276.99 s | 4 | 36731 | 13248 | 35/35 |
| NEW-01 | patient | 20.06 s | 3 | 8141 | 972 | 0/0 |
| NEW-02 | collection | 33.77 s | 4 | 10811 | 1666 | 0/3 |
| NEW-03 | collection | 55.22 s | 6 | 16361 | 2762 | 0/1 |

Median latency: individual-patient questions 63.3 s, collection-wide 44.5 s.

Pure-code query latency (no LLM, median of 20):

| Query | ms |
|---|---:|
| session_counts | 2.91 |
| weekly_summary | 2.88 |
| goal_compliance | 3.63 |
| day_detail | 0.77 |
| consecutive_weeks_below (collection) | 3.37 |
| compliance_all (collection) | 3.52 |

## Size

Source documents 48.9 KB · SQLite abstraction 560.0 KB (includes a copy of source text for quote lookup) · JSON export 242.2 KB.

## Tokens and cost

Total tokens this benchmark: 185257 input, 79483 output.

API cost: $0. The model runs locally (Ollama, RTX 2080 Ti 11 GB). The only cost is machine time and power.
