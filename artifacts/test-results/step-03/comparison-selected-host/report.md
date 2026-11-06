# Saved-run paired A/B report

Selection: `all`. Primary gate: **FAIL**; accepted: **False**.

Saved host outputs only; no inference, no summary.json reads, no excluded split case/reference reads. Utterance-interval DER/timing proxy is not natural-dialogue or word-timestamp acceptance. Host RTF is not phone performance.

## dev

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| wer_raw | 23.265% | 18.011% |
| wer_punctuation_tokens | 19.103% | 14.616% |
| wer_normalized | 7.331% | 3.383% |
| cer_normalized | 3.237% | 1.547% |
| cpwer_raw | 82.927% | 81.989% |
| cpwer_normalized | 72.744% | 71.241% |
| der_collar_0ms | 46.036% | 53.084% |
| der_collar_250ms | 44.041% | 51.117% |
| native_der_collar_0ms | 43.157% | 43.157% |
| native_der_collar_250ms | 41.029% | 41.029% |
| Punctuation F1 | 66.885% | 69.536% |
| Initial-case accuracy | 86.667% | 100.000% |
| Timing reference coverage | 97.778% | 100.000% |
| Median start error (proxy ms) | 684.000 | 776.000 |
| Median end error (proxy ms) | 475.000 | 580.000 |
| Host RTF | 0.369 | 0.631 |
| export speaker-count exact rate | 25.000% | 25.000% |
| native speaker-count exact rate | 25.000% | 25.000% |

Raw S/D/I: baseline 103/11/10; candidate 88/6/2. Inspect JSON coverage for missing metrics.

Short-case deletion axis: PASS; relative reduction 100.000%.

## holdout

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| wer_raw | 16.441% | 17.568% |
| wer_punctuation_tokens | 15.000% | 14.643% |
| wer_normalized | 5.430% | 3.620% |
| cer_normalized | 2.590% | 1.361% |
| cpwer_raw | 100.450% | 101.577% |
| cpwer_normalized | 94.570% | 93.891% |
| der_collar_0ms | 54.773% | 60.396% |
| der_collar_250ms | 52.953% | 58.681% |
| native_der_collar_0ms | 51.546% | 51.546% |
| native_der_collar_250ms | 49.366% | 49.366% |
| Punctuation F1 | 70.370% | 66.055% |
| Initial-case accuracy | 93.750% | 96.875% |
| Timing reference coverage | 100.000% | 100.000% |
| Median start error (proxy ms) | 331.500 | 1036.000 |
| Median end error (proxy ms) | 456.000 | 642.500 |
| Host RTF | 0.360 | 0.630 |
| export speaker-count exact rate | 40.000% | 40.000% |
| native speaker-count exact rate | 40.000% | 40.000% |

Raw S/D/I: baseline 59/9/5; candidate 71/5/2. Inspect JSON coverage for missing metrics.

Short-case deletion axis: PASS; relative reduction 100.000%.

## Primary checks

- dev_raw_wer_strictly_better: **PASS**.
- dev_normalized_wer_no_worse: **PASS**.
- holdout_raw_wer_no_worse: **FAIL**.
