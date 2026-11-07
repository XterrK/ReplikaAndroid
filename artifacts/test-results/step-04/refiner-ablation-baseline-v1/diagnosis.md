# C2 dev-only refiner ablation — FAIL

196 global profiles,1568 case projections,dev8 and232 real saved vectors. No new neural inference; no holdout or RTF claim.
All profiles preserve raw WER71/533 and literal token order. None reaches the unchanged7/8 exact-count and nativeDER0≤28.8851817% joint gate.

| Family | Missing policy | Max exact K /8 | DER0 at max K | Lowest DER0 | Exact K there /8 |
| --- | --- | ---: | ---: | ---: | ---: |
| full | retain | 4 | 32.103% | 27.689% | 2 |
| full | temporal | 5 | 31.627% | 27.213% | 3 |
| no_eigengap | retain | 4 | 32.103% | 27.689% | 2 |
| no_eigengap | temporal | 5 | 31.627% | 27.213% | 3 |
| merge_only | retain | 4 | 27.515% | 27.515% | 4 |
| merge_only | temporal | 4 | 27.515% | 27.515% | 4 |
| small_smooth_only | retain | 1 | 42.518% | 42.518% | 1 |
| small_smooth_only | temporal | 2 | 41.916% | 41.916% | 2 |
| full_small_cos_0p3 | retain | 3 | 27.689% | 27.689% | 3 |
| full_small_cos_0p3 | temporal | 4 | 27.213% | 27.213% | 4 |
| full_small_cos_0p5 | retain | 4 | 27.515% | 27.515% | 4 |
| full_small_cos_0p5 | temporal | 5 | 27.039% | 27.039% | 5 |
| full_small_cos_0p7 | retain | 4 | 27.515% | 27.515% | 4 |
| full_small_cos_0p7 | temporal | 5 | 27.039% | 27.039% | 5 |

The full/no-eigengap outputs are byte-identical for all224 paired cases; actual eigengap merge events are zero.
The short predicted label in dev03 is removed by small-cluster reassignment at τ0.60, cosine0.4997777. The global minimum0.5 guard retains it; its result is still not a passing global profile.
Per-stage counts, cosine/temporal assignments, blocked reassignments, overlap collapses, fallback reasons, all turns/hypotheses/references/metrics and hashes remain under each profile. Old C1FAIL evidence is untouched.
Best-DER and maximum-count columns may come from different global τ values; diagnosis.json records both exact profile IDs. No per-case choices are made.
