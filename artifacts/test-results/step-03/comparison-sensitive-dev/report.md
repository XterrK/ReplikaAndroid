# Saved-run paired A/B report

Selection: `dev`. Primary gate: **PENDING_UNEVALUATED_SPLIT**; accepted: **False**.

Saved host outputs only; no inference, no summary.json reads, no excluded split case/reference reads. Utterance-interval DER/timing proxy is not natural-dialogue or word-timestamp acceptance. Host RTF is not phone performance.

## dev

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| wer_raw | 23.265% | 16.698% |
| wer_punctuation_tokens | 19.103% | 13.459% |
| wer_normalized | 7.331% | 4.135% |
| cer_normalized | 3.237% | 2.086% |
| cpwer_raw | 82.927% | 79.925% |
| cpwer_normalized | 72.744% | 71.241% |
| der_collar_0ms | 46.036% | 50.904% |
| der_collar_250ms | 44.041% | 48.613% |
| native_der_collar_0ms | 43.157% | 43.157% |
| native_der_collar_250ms | 41.029% | 41.029% |
| Punctuation F1 | 66.885% | 71.096% |
| Initial-case accuracy | 86.667% | 97.778% |
| Timing reference coverage | 97.778% | 95.556% |
| Median start error (proxy ms) | 684.000 | 781.000 |
| Median end error (proxy ms) | 475.000 | 516.000 |
| Host RTF | 0.369 | 0.846 |
| export speaker-count exact rate | 25.000% | 25.000% |
| native speaker-count exact rate | 25.000% | 25.000% |

Raw S/D/I: baseline 103/11/10; candidate 80/8/1. Inspect JSON coverage for missing metrics.

Short-case deletion axis: FAIL; relative reduction 0.000%.

## Primary checks

- dev_raw_wer_strictly_better: **PASS**.
- dev_normalized_wer_no_worse: **PASS**.
- holdout_raw_wer_no_worse: **NOT_EVALUATED**.
