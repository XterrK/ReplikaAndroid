# C1 Kotlin draft review

The pure `SpeakerRefiner.kt` draft is ready outside the checkout under the private
toolchain's `drafts/task04-c1/`. It has not been applied to the app, model pack or
Gradle configuration. The paired JSON report pins all draft/harness sources and
the 23 real input/source-output evidence chains.

The draft ports frozen Python C1 `speaker_refiner.py`
`4f52854185c9ad4b2e54b9679a9670b5415d5a9fcc1c16d0c5f392eb6aa69eb1`.
Kotlin source SHA-256:
`d0701bb38241c9631daf7445ce00d19c04d5b7b5de1473ea7d4d523ff500885d`.
The existing domain `Turn(Long,Long,Int)` is reused. No audio, NN, text, expected K
or independent reference enters either refinement algorithm.

API: `SpeakerRefiner.cleanWindows`, `estimateSpeakers`, and
`refine(turns, windows, durationMs, config)`. Nested `EmbeddingWindow` stores
`Long` endpoints, `Int` source label, `DoubleArray` actual embedding, and `clean`.
`Config` exposes every Python option with camelCase names; `asMap()` preserves
the original diagnostic keys. `Result` contains turns, computational `accepted`
and `Map<String,Any?>` diagnostics. The selected policy is threshold `.7`, minimum
small-cluster cosine `.7`, temporal missing-centroid policy, all other C1 defaults.

All stages are present: stable normalization and duration-weighted centroids,
strict cosine merges, optional complete-link guard, normalized-Laplacian
eigengap, small and temporal assignments, hard cap, overlap accounting, smoothing
and stable IDs. The pure Jacobi solver is bounded to 256 centroids and 80 sweeps;
nonconvergence rejects the calculation. A controlled test exercises an actual
eigengap merge with cosine merging disabled. This is the C1 heuristic, not the
separate window-overclustering prototype or published NME-SC.

Validation used standalone cached Kotlin 2.1.20 with JDK17, without Android Gradle:

- **16 JUnit tests PASS**, including strict thresholds, complete-link, temporal
  fallback, short-voice guard, invalid/duplicate/extreme vectors, actual spectral
  reduction, flat spectra, hard cap, exact smoothing boundaries and Long clocks.
- **274 Python/Kotlin differential cases PASS:** 23 actual vector/turn cases
  (dev8, old holdout5, reserve10), 24 controlled, 160 seeded random refinement and
  67 spectral cases including the 256/257 bound.
- All returned interval endpoints, speaker IDs and `accepted` flags match
  exactly. Full nested diagnostics match within `1e-9 + 1e-9*abs(reference)`;
  maximum observed numeric difference is **6.217248937900877e-15**.
- Before comparison, all 23 Python results exactly reproduced their saved
  selected-policy turns. All source case/evidence hashes were checked.

Two initial differential issues were fixed before final validation: stock JVM
`JSONObject(Map)` drops null-valued keys, so the probe uses a recursive
`JSONObject.NULL` adapter; and a symmetric two-dimensional norm rounding tie is
covered by a regression test. The domain code stays JSON-free; the integrating
Worker must preserve diagnostic nulls when serializing its maps. Earlier attempt
snapshots remain outside Git.

Compiler and pure-helper resource logs are recorded in the JSON report. They are
host tool measurements, not model/audio RTF or Android performance acceptance.
Formal host policy gates, Android window extraction/full-pipeline parity and the
usual JVM/APK checks remain required before any promotion. No native inference,
Android behavior change or Git commit was performed by this draft task.
