# Evaluation results (holdout set)

- Date: 2026-11-12 21:42 UTC
- Generation model: `gemini-3.5-flash-lite` · Judge model: `gemini-3.5-flash-lite`
- Embedding model: `gemini-embedding-2` (768 dims)
- RETRIEVAL_MIN_SCORE: 0.65 · top-k: 4
- Golden set: 10 questions (7 answerable, 3 unanswerable)

## Summary

| Metric | Value |
|---|---|
| Retrieval hit@1 | 100% |
| Retrieval hit@4 | 100% |
| Answer correctness (judge score 2/2) | 86% |
| Mean judge score (0-2) | 1.86 |
| Citation accuracy | 100% |
| Correct-refusal rate (unanswerable) | 100% |
| False-refusal rate (answerable) | 0% |
| Average latency | 2.94 s |
| Errors | 0 |

## RETRIEVAL_MIN_SCORE calibration (top retrieval score only)

| Threshold | Answerable kept | Unanswerable blocked |
|---|---|---|
| 0.30 | 100% | 0% |
| 0.35 | 100% | 0% |
| 0.40 | 100% | 0% |
| 0.45 | 100% | 0% |
| 0.50 | 100% | 0% |
| 0.55 | 100% | 0% |
| 0.60 | 100% | 0% |
| 0.65 | 100% | 33% |
| 0.70 | 100% | 67% |
| 0.75 | 86% | 100% |
| 0.80 | 43% | 100% |

## Per question

| ID | Expected | Rank | Top score | Outcome | Cited | Judge |
|---|---|---|---|---|---|---|
| h-mail-01 | email-problems.md | 1 | 0.798 | answered | email-problems.md | 2 |
| h-erp-01 | erp-access-error.md | 1 | 0.775 | answered | erp-access-error.md | 2 |
| h-print-01 | printer-issues.md | 1 | 0.819 | answered | printer-issues.md | 2 |
| h-pwd-01 | password-reset.md | 1 | 0.744 | answered | password-reset.md | 2 |
| h-vpn-01 | vpn-access.md | 1 | 0.802 | answered | vpn-access.md | 1 |
| h-laptop-01 | new-laptop-onboarding.md | 1 | 0.760 | answered | new-laptop-onboarding.md | 2 |
| h-sev-01 | incident-severity-definitions.md | 1 | 0.821 | answered | incident-severity-definitions.md | 2 |
| h-na-01 | - | - | 0.649 | low_confidence | - |  |
| h-na-02 | - | - | 0.653 | low_confidence | - |  |
| h-na-03 | - | - | 0.733 | low_confidence | - |  |

> The judge is from the same model family as the generator, so scores can be biased in the bot's favor. Treat them as a regression signal, not an absolute quality measure.
