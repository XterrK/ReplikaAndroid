# C2 Kotlin draft review

External pure domain draft `WindowSpeakerRefiner.kt` is ready in the private
toolchain's `drafts/task04-c2/`; it has not been applied to the app. Kotlin source
SHA-256 is `69498c73d0489a8381ef2a00dd53afde6c3c4fb02e54a348d63beae89c3e4d67`.
It ports frozen Python `window_overcluster.py` SHA
`23cffbba55b75e69695a2b508093505dcad74c804cb7913fd77356b67196acd4` and reuses
unchanged C1 `SpeakerRefiner` SHA `d0701bb38241c9631daf7445ce00d19c04d5b7b5de1473ea7d4d523ff500885d`.

`overcluster` and its `refine` alias accept only predicted `List<Turn>`, real
`List<SpeakerRefiner.EmbeddingWindow>`, `Long` duration and global `Config`.
`Result` contains turns, computational support and nullable diagnostic maps.
`Config` mirrors all ten Python settings. The selected dev configuration is
`tau=.36`, `method=average`, `reassignSmall=true`, with all other frozen defaults.

Complete/average hierarchy reproduces the official SciPy1.18.1 nearest-neighbor
chain, previous-neighbor tie preference, stable distance sorting and union-find
node relabeling. The cut is inclusive; the same hierarchy continues for a forced
cap. Distances are quadratic and leaf sets use `BitSet`; inputs above 2048 windows
reject before hierarchy construction. The source-contract version is explicit
alongside a diagnostic stating that the backend is pure Kotlin without SciPy.

The port retains activity-confined 125ms voting, triangle/overlap weights,
same-source then global time fallback, optional small assignments, smoothing,
stable IDs, missing-vector and overlap diagnostics. New grid boundaries remain
timing proxies. C1's bounded Jacobi eigengap implementation remains diagnostic
only in C2. No expected K, gold text, reference, audio or neural model enters it.

Validation without Gradle or NN:

- **12 standalone JUnit tests PASS**, covering split, ordering/duplicates,
  inclusive cut, complete/average, tie-tree/cap, gaps, overlaps, fragments,
  small-voice guard, invalid evidence/configuration and Long clocks.
- **157 Python/Kotlin differential cases PASS:** 23 actual selected files
  (dev8, original holdout5, reserve10), 44 controlled geometries and 90 cases with fixed seed1904. Before parity,
  Python exactly reproduced the saved selected-profile outputs from real windows.
- Returned intervals, speaker IDs and `accepted` match exactly. Integer values,
  structures, cluster labels/tree, votes, fallbacks and nullable fields match;
  floating tolerance is `1e-9 + 1e-9*abs(reference)`, observed maximum difference
  **8.881784197001252e-16**. Only the added Kotlin backend-attribution field is
  excluded from mathematical parity.

The adapted hierarchy follows [official SciPy source](https://github.com/scipy/scipy/blob/e4e854eaa8f18d807cd3496028e257e36caa93cc/scipy/cluster/hierarchy/_hierarchy.pyx).
Its BSD3 license and captured sources remain beside the external draft; the
integrator must retain that notice in binary redistribution materials. Diagnostic
serialization must preserve null map entries explicitly with `JSONObject.NULL`.

The paired JSON pins all sources, real input evidence, outputs and resource logs.
Compiler and helper timings are host tooling measurements, not audio RTF or
Android performance. Original-holdout/reserve parity uses the same frozen compiled
helper as the initial dev-only stage; the earlier dev8 snapshot is preserved.
Actual native extraction/full-worker parity remains required. No Android model,
manifest, model pack, Worker, Gradle or Git change was performed by this draft
task; C1 packaging draft remains on HOLD.

The external `integration/` draft contains only a new pure `DiarizationPlan.kt`,
the `app/build.gradle.kts` opt-in patch and **7 passing standalone plan JUnit
tests**. IDs are `v16` and `eres2net_window_v1`; null historical WorkData resolves
to legacy, and manual counts1–20 select the unchanged legacy diarization path.
Only automatic−1 selects C2. The new build flag defaults to v16 and requires
`vad_words_context600` when C2 is explicitly selected. Both plans use the original
embedding/segmentation paths and seven model files; there are no ModelManager,
embedded-pack or model-lock changes. The root agent owns Worker/EvalBatch wiring
and application of the reviewed patch.
