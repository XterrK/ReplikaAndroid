Closed: **NONE / BASELINE_RETAINED**. No promotion.

The protocol was frozen before any new hypotheses or metrics. The study reused eight actual shift=.25 native SD cases and 224 measured 512-dimensional original-PCM embeddings; D ASR words were replayed unchanged. No new neural inference, audio/model loading, ADB, Android changes, holdout/reserve/natural evaluation or speed acceptance occurred.

| Diagnostic | Saved-vector result | Required baseline/gate |
|---|---:|---:|
| Maximum exact speaker counts | 6/8 at tau 0.35 | At least 7/8 |
| Minimum native DER0 | 18.980654762% at tau .36/.37 | At most 18.298480576% (+1e-12) |
| cpWER at minimum DER | 156/533 | At most 146/533 |
| Raw ASR errors, every profile | 71/533 | Exactly 71/533 |
| Normalized ASR errors, every profile | 16/532 | Exactly 16/532 |

All 21 global thresholds (.25 through .45 inclusive, .01 step) fail the joint gate. Tau .35 reaches 6/8 but DER is 19.232064536% and cpWER is 156/533. No per-case choice, widened grid or relaxed criteria was used.

All 168 output evidence hashes, source pins, literal ASR words and weighted aggregates pass the post-run integrity audit. Tau .36 reproduces every original saved shift=.25 turn, hypothesis and core metric exactly. References, hypotheses, full metrics and diagnostics are retained per case under outputs/. Pure refiner timings are descriptive only; they do not establish NN or whole-pipeline speed.

Protocol SHA256: `e744dcc1f06bd8d437bcd35ae8165bddf95c67d31a69ddbd589940345f283caa`. Procedure SHA256: `27510d9b7879cf321291a50e22e99c0efcfde000127cb10abd8297b791ef01e5`. See final-selection.json, results.csv and integrity-audit.json.
