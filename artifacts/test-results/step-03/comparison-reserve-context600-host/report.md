# Saved-run paired A/B report

Selection: `all`. Primary gate: **PENDING_UNEVALUATED_SPLIT**; accepted: **False**.

Saved host outputs only; no inference, no summary.json reads, no excluded split case/reference reads. Utterance-interval DER/timing proxy is not natural-dialogue or word-timestamp acceptance. Host RTF is not phone performance.

## holdout

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| wer_raw | 18.170% | 11.171% |
| wer_punctuation_tokens | 15.723% | 9.748% |
| wer_normalized | 5.645% | 3.226% |
| cer_normalized | 4.098% | 3.002% |
| cpwer_raw | 76.985% | 74.159% |
| cpwer_normalized | 71.102% | 70.699% |
| der_collar_0ms | 49.100% | 50.021% |
| der_collar_250ms | 47.034% | 47.600% |
| native_der_collar_0ms | 47.659% | 47.659% |
| native_der_collar_250ms | 45.406% | 45.406% |
| Punctuation F1 | 74.346% | 80.412% |
| Initial-case accuracy | 90.000% | 91.667% |
| Timing reference coverage | 96.667% | 86.667% |
| Median start error (proxy ms) | 372.000 | 391.000 |
| Median end error (proxy ms) | 460.500 | 513.000 |
| Host RTF | 0.873 | 0.866 |
| export speaker-count exact rate | 10.000% | 10.000% |
| native speaker-count exact rate | 10.000% | 10.000% |

Raw S/D/I: baseline 111/18/6; candidate 71/11/1. Inspect JSON coverage for missing metrics.

Short-case deletion axis: UNASSESSABLE; relative reduction N/A.

## Primary checks

- dev_raw_wer_strictly_better: **NOT_EVALUATED**.
- dev_normalized_wer_no_worse: **NOT_EVALUATED**.
- holdout_raw_wer_no_worse: **PASS**.
