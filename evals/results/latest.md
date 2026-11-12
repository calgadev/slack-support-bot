# Evaluation results

- Date: 2026-11-12 21:08 UTC
- Generation and judge: skipped (`--retrieval-only`)
- Embedding model: `gemini-embedding-2` (768 dims)
- RETRIEVAL_MIN_SCORE: 0.65 · top-k: 4
- Golden set: 30 questions (25 answerable, 5 unanswerable)

## Summary

| Metric | Value |
|---|---|
| Retrieval hit@1 | 92% |
| Retrieval hit@4 | 100% |

## RETRIEVAL_MIN_SCORE calibration (top retrieval score only)

| Threshold | Answerable kept | Unanswerable blocked |
|---|---|---|
| 0.30 | 100% | 0% |
| 0.35 | 100% | 0% |
| 0.40 | 100% | 0% |
| 0.45 | 100% | 0% |
| 0.50 | 100% | 0% |
| 0.55 | 100% | 0% |
| 0.60 | 100% | 20% |
| 0.65 | 100% | 60% |
| 0.70 | 92% | 80% |
| 0.75 | 76% | 100% |
| 0.80 | 36% | 100% |

## Per question

| ID | Expected | Rank | Top score | Outcome | Cited | Judge |
|---|---|---|---|---|---|---|
| vpn-01 | vpn-access.md | 1 | 0.784 | - | - |  |
| vpn-02 | vpn-access.md | 1 | 0.783 | - | - |  |
| vpn-03 | vpn-access.md | 1 | 0.663 | - | - |  |
| pwd-01 | password-reset.md | 1 | 0.779 | - | - |  |
| pwd-02 | password-reset.md | 1 | 0.808 | - | - |  |
| pwd-03 | password-reset.md | 1 | 0.743 | - | - |  |
| mfa-01 | mfa-issues.md | 1 | 0.773 | - | - |  |
| mfa-02 | mfa-issues.md | 1 | 0.807 | - | - |  |
| mfa-03 | mfa-issues.md | 1 | 0.855 | - | - |  |
| erp-01 | erp-access-error.md | 1 | 0.885 | - | - |  |
| erp-02 | erp-access-error.md | 1 | 0.777 | - | - |  |
| ssl-01 | ssl-certificate-expiry.md | 1 | 0.821 | - | - |  |
| ssl-02 | ssl-certificate-expiry.md | 1 | 0.795 | - | - |  |
| drive-01 | shared-drive-access.md | 1 | 0.849 | - | - |  |
| drive-02 | shared-drive-access.md | 1 | 0.726 | - | - |  |
| laptop-01 | new-laptop-onboarding.md | 1 | 0.804 | - | - |  |
| laptop-02 | new-laptop-onboarding.md | 1 | 0.715 | - | - |  |
| sw-01 | software-request-process.md | 1 | 0.781 | - | - |  |
| sw-02 | software-request-process.md | 1 | 0.662 | - | - |  |
| sev-01 | incident-severity-definitions.md | 1 | 0.838 | - | - |  |
| sev-02 | incident-severity-definitions.md | 2 | 0.859 | - | - |  |
| mail-01 | email-problems.md | 1 | 0.764 | - | - |  |
| mail-02 | email-problems.md | 1 | 0.724 | - | - |  |
| print-01 | printer-issues.md | 1 | 0.778 | - | - |  |
| ticket-01 | how-to-open-a-ticket.md | 2 | 0.761 | - | - |  |
| na-01 | - | - | 0.664 | - | - |  |
| na-02 | - | - | 0.557 | - | - |  |
| na-03 | - | - | 0.625 | - | - |  |
| na-04 | - | - | 0.649 | - | - |  |
| na-05 | - | - | 0.728 | - | - |  |

> The judge is from the same model family as the generator, so scores can be biased in the bot's favor. Treat them as a regression signal, not an absolute quality measure.
