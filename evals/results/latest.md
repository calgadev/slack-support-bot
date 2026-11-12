# Evaluation results

- Date: 2026-11-12 21:24 UTC
- Generation model: `gemini-3.5-flash-lite` · Judge model: `gemini-3.5-flash-lite`
- Embedding model: `gemini-embedding-2` (768 dims)
- RETRIEVAL_MIN_SCORE: 0.65 · top-k: 4
- Golden set: 30 questions (25 answerable, 5 unanswerable)

## Summary

| Metric | Value |
|---|---|
| Retrieval hit@1 | 92% |
| Retrieval hit@4 | 100% |
| Answer correctness (judge score 2/2) | 88% |
| Mean judge score (0-2) | 1.88 |
| Citation accuracy | 100% |
| Correct-refusal rate (unanswerable) | 100% |
| False-refusal rate (answerable) | 0% |
| Average latency | 3.27 s |
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
| 0.60 | 100% | 20% |
| 0.65 | 100% | 60% |
| 0.70 | 92% | 80% |
| 0.75 | 76% | 100% |
| 0.80 | 36% | 100% |

## Per question

| ID | Expected | Rank | Top score | Outcome | Cited | Judge |
|---|---|---|---|---|---|---|
| vpn-01 | vpn-access.md | 1 | 0.784 | answered | vpn-access.md | 2 |
| vpn-02 | vpn-access.md | 1 | 0.783 | answered | vpn-access.md | 2 |
| vpn-03 | vpn-access.md | 1 | 0.663 | answered | vpn-access.md | 2 |
| pwd-01 | password-reset.md | 1 | 0.779 | answered | password-reset.md | 2 |
| pwd-02 | password-reset.md | 1 | 0.808 | answered | password-reset.md | 2 |
| pwd-03 | password-reset.md | 1 | 0.743 | answered | password-reset.md | 2 |
| mfa-01 | mfa-issues.md | 1 | 0.773 | answered | mfa-issues.md | 2 |
| mfa-02 | mfa-issues.md | 1 | 0.807 | answered | mfa-issues.md | 2 |
| mfa-03 | mfa-issues.md | 1 | 0.855 | answered | mfa-issues.md | 2 |
| erp-01 | erp-access-error.md | 1 | 0.885 | answered | erp-access-error.md | 2 |
| erp-02 | erp-access-error.md | 1 | 0.777 | answered | erp-access-error.md | 2 |
| ssl-01 | ssl-certificate-expiry.md | 1 | 0.821 | answered | ssl-certificate-expiry.md | 2 |
| ssl-02 | ssl-certificate-expiry.md | 1 | 0.795 | answered | ssl-certificate-expiry.md | 1 |
| drive-01 | shared-drive-access.md | 1 | 0.849 | answered | shared-drive-access.md | 2 |
| drive-02 | shared-drive-access.md | 1 | 0.726 | answered | shared-drive-access.md | 2 |
| laptop-01 | new-laptop-onboarding.md | 1 | 0.804 | answered | new-laptop-onboarding.md | 2 |
| laptop-02 | new-laptop-onboarding.md | 1 | 0.715 | answered | incident-severity-definitions.md, new-laptop-onboarding.md | 2 |
| sw-01 | software-request-process.md | 1 | 0.781 | answered | software-request-process.md | 2 |
| sw-02 | software-request-process.md | 1 | 0.662 | answered | software-request-process.md | 2 |
| sev-01 | incident-severity-definitions.md | 1 | 0.838 | answered | incident-severity-definitions.md | 1 |
| sev-02 | incident-severity-definitions.md | 2 | 0.859 | answered | how-to-open-a-ticket.md, incident-severity-definitions.md | 2 |
| mail-01 | email-problems.md | 1 | 0.764 | answered | email-problems.md | 1 |
| mail-02 | email-problems.md | 1 | 0.724 | answered | email-problems.md | 2 |
| print-01 | printer-issues.md | 1 | 0.778 | answered | printer-issues.md | 2 |
| ticket-01 | how-to-open-a-ticket.md | 2 | 0.761 | answered | how-to-open-a-ticket.md, mfa-issues.md, password-reset.md | 2 |
| na-01 | - | - | 0.664 | low_confidence | - |  |
| na-02 | - | - | 0.557 | low_confidence | - |  |
| na-03 | - | - | 0.625 | low_confidence | - |  |
| na-04 | - | - | 0.649 | low_confidence | - |  |
| na-05 | - | - | 0.728 | low_confidence | - |  |

> The judge is from the same model family as the generator, so scores can be biased in the bot's favor. Treat them as a regression signal, not an absolute quality measure.
