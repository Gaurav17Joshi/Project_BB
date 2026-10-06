# Benchmark (measured)

All numbers below were measured on this machine against the supplied 31 documents, model `gpt-6-luna`. Network latency to the API is included.

## Processing

| Run | Wall time | LLM calls | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| Cold (empty DB) | 39.88 s | 31 | 76282 | 30180 |
| Warm re-run (no new docs) | 0.051 s | 0 | 0 | 0 |
| +2 duplicate copies (exact, and CRLF/whitespace variant) | 0.02 s | 0 | 0 | 0 |

Cold breakdown: ingest 0.035 s, extraction 39.344 s (8 parallel workers), verify+reconcile 0.496 s.  
Duplicate test: 2 copies detected, contacts unchanged: **True**.  
Restart (new process loads the saved DB and runs a query): 0.17 s.

## Question latency

| Question | Scope | Latency | LLM calls | Input tokens | Output tokens | Quotes verified |
|---|---|---:|---:|---:|---:|---:|
| DEV-01 | patient | 92.66 s | 14 | 153014 | 7732 | 9/9 |
| DEV-02 | patient | 86.26 s | 11 | 164250 | 7662 | 26/26 |
| DEV-03 | patient | 19.26 s | 3 | 15784 | 1648 | 5/5 |
| DEV-04 | patient | 21.39 s | 4 | 32841 | 1824 | 5/5 |
| DEV-05 | patient | 30.28 s | 3 | 38143 | 2946 | 22/22 |
| NEW-01 | patient | 27.99 s | 7 | 34137 | 1892 | 4/4 |
| NEW-02 | collection | 35.05 s | 9 | 30871 | 2514 | 2/2 |
| NEW-03 | collection | 13.9 s | 3 | 5097 | 995 | 1/1 |

Median latency: individual-patient questions 29.1 s, collection-wide 24.5 s.

Pure-code query latency (no LLM, median of 20):

| Query | ms |
|---|---:|
| session_counts | 4.34 |
| weekly_summary | 3.15 |
| goal_compliance | 4.62 |
| day_detail | 0.88 |
| consecutive_weeks_below (collection) | 3.76 |
| compliance_all (collection) | 3.96 |

## Size

Source documents 48.9 KB · SQLite abstraction 476.0 KB (includes a copy of source text for quote lookup) · JSON export 168.3 KB.

## Tokens and cost

Total tokens this benchmark: 550419 input, 57393 output.

Prices (USD per 1M tokens): input $0.1, cached input $0.01, output $0.5.

- Extraction of all documents: $0.01586 as billed ($0.02272 if no prompt-cache hits, i.e. a first-ever run).
- All 8 questions: $0.02785.
  - DEV-01: $0.00797
  - DEV-02: $0.00755
  - DEV-03: $0.00157
  - DEV-04: $0.00218
  - DEV-05: $0.0035
  - NEW-01: $0.00194
  - NEW-02: $0.00252
  - NEW-03: $0.00062
