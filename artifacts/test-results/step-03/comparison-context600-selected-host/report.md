# Saved-run paired A/B report

Selection: `all`. Primary gate: **PASS**; accepted: **True**.

Saved host outputs only; no inference, no summary.json reads, no excluded split case/reference reads. Utterance-interval DER/timing proxy is not natural-dialogue or word-timestamp acceptance. Host RTF is not phone performance.

## dev

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| wer_raw | 23.265% | 13.321% |
| wer_punctuation_tokens | 19.103% | 10.999% |
| wer_normalized | 7.331% | 3.008% |
| cer_normalized | 3.237% | 1.367% |
| cpwer_raw | 82.927% | 77.861% |
| cpwer_normalized | 72.744% | 70.865% |
| der_collar_0ms | 46.036% | 46.903% |
| der_collar_250ms | 44.041% | 44.113% |
| native_der_collar_0ms | 43.157% | 43.157% |
| native_der_collar_250ms | 41.029% | 41.029% |
| Punctuation F1 | 66.885% | 75.083% |
| Initial-case accuracy | 86.667% | 95.556% |
| Timing reference coverage | 97.778% | 88.889% |
| Median start error (proxy ms) | 684.000 | 367.000 |
| Median end error (proxy ms) | 475.000 | 500.000 |
| Host RTF | 0.369 | 0.723 |
| export speaker-count exact rate | 25.000% | 25.000% |
| native speaker-count exact rate | 25.000% | 25.000% |

Raw S/D/I: baseline 103/11/10; candidate 62/7/2. Inspect JSON coverage for missing metrics.

Short-case deletion axis: PASS; relative reduction 100.000%.

## holdout

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| wer_raw | 16.441% | 11.036% |
| wer_punctuation_tokens | 15.000% | 9.464% |
| wer_normalized | 5.430% | 2.941% |
| cer_normalized | 2.590% | 1.097% |
| cpwer_raw | 100.450% | 97.973% |
| cpwer_normalized | 94.570% | 93.213% |
| der_collar_0ms | 54.773% | 53.554% |
| der_collar_250ms | 52.953% | 51.485% |
| native_der_collar_0ms | 51.546% | 51.546% |
| native_der_collar_250ms | 49.366% | 49.366% |
| Punctuation F1 | 70.370% | 80.000% |
| Initial-case accuracy | 93.750% | 93.750% |
| Timing reference coverage | 100.000% | 93.750% |
| Median start error (proxy ms) | 331.500 | 269.000 |
| Median end error (proxy ms) | 456.000 | 462.500 |
| Host RTF | 0.360 | 0.823 |
| export speaker-count exact rate | 40.000% | 40.000% |
| native speaker-count exact rate | 40.000% | 40.000% |

Raw S/D/I: baseline 59/9/5; candidate 37/7/5. Inspect JSON coverage for missing metrics.

Short-case deletion axis: PASS; relative reduction 50.000%.

## Primary checks

- dev_raw_wer_strictly_better: **PASS**.
- dev_normalized_wer_no_worse: **PASS**.
- holdout_raw_wer_no_worse: **PASS**.
