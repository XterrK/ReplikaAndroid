# C: validity of actor counts and diarization evaluation

Read-only audit, 2026-11-07. No new audio, model inference, listening-based relabeling, corpus edits or scorer edits. The checks below use saved publisher metadata, generation code, provenance and reference JSON. They do not constitute a fresh acoustic verification of every source WAV.

**Finding:** every montage has a defensible **author-labelled known-K research oracle**. No selected-row/actor/reference mapping defect was found. This does not establish natural-dialogue speech-activity gold, independent actor verification or general speaker-count accuracy.

## Identity and construction evidence

The pinned [author dataset card](../../../benchmark/eval/sources/README.md) describes three professional actors and explicitly defines `M = Masha (F)`, `S = Sveta (F)`, `D = Dima (M)`. These are actor identities, not arbitrary dialogue-local role numbers. Revision: `a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd`. The retained card, both CSVs, license and audio index match their saved SHA256 values in both corpora.

All 368 official validation/test CSV paths are unique; all actor labels agree with their filename pair (`masha_dima`: M/D, `masha_sveta`: M/S). These consistency checks cannot detect a publisher mislabelled voice. There is no independent listening audit in this task; no claim that metadata proves the physical identity of every recording.

Across [original provenance](../../../benchmark/eval/provenance.json) and [reserve provenance](../../../benchmark/eval-reserve/provenance.json), **1612 metadata/reference assertions passed, zero failed**:

- 137 selected source rows match every original CSV field verbatim; actors: M55, D41, S41.
- All 137 recorded raw hashes/sizes match the pinned publisher LFS index; source durations differ from recorded frames/rate by at most one source sample; resampled lengths follow the recorded sample-rate conversion.
- All 137 placements retain the complete source clip, correct actor identity and author text; reference milliseconds are the floor of the actual placement sample indices.
- All 23 reference JSONs match their provenance rows exactly. Unique actor count, first-appearance `speaker_1..N` mapping, manifest `expected_speakers`, manifest actor list and provenance speaker map agree for every case.
- The 137 paths, recorded raw content hashes and exact source texts are unique across the two corpora. The reserve also retains its separate [disjointness record](../../../benchmark/eval-reserve/disjointness.json), excluding the seven prior V1.5 whisper clips.

The [generator](../../../tools/eval/prepare_corpus.py) derives K from selected **author** actor labels; candidate ASR/VAD/diarization does not create those labels. It decodes, averages channels, resamples, places complete clips and encodes PCM16. It does not pitch-shift, replace voices, trim with candidate VAD or correct author text. All 23 saved montage/mono gains are 1.0. Artificial pauses and some 500 ms clip overlaps are intentional edits to conversational timing, not natural turn-taking gold. No metadata evidence of an actor collision, substituted actor or erroneous reference speaker renumbering was found.

## Per-file known K

Actor order is first occurrence; K is the distinct actor count, conditional on author metadata correctness. The three mono files are original utterance sanity cases, not multi-turn conversations.

| Corpus | Case | Actors | K | Source clips |
| --- | --- | --- | ---: | ---: |
| original | dev-01-two-clean | M,D | 2 | 8 |
| original | dev-02-three-clean | M,S,D | 3 | 9 |
| original | dev-03-short | M,S | 2 | 8 |
| original | dev-04-expressive | D,M,S | 3 | 6 |
| original | dev-05-whisper | M,D,S | 3 | 6 |
| original | dev-06-overlap | S,M,D | 3 | 6 |
| original | holdout-01-two-clean | D,M | 2 | 8 |
| original | holdout-02-three-clean | S,D,M | 3 | 9 |
| original | holdout-03-short | M,S,D | 3 | 8 |
| original | holdout-04-overlap-expressive | D,M,S | 3 | 6 |
| original | dev-mono-m | M | 1 | 1 |
| original | dev-mono-s | S | 1 | 1 |
| original | holdout-mono-d | D | 1 | 1 |
| reserve | reserve-01-two-clean | M,D | 2 | 6 |
| reserve | reserve-02-two-clean | M,S | 2 | 6 |
| reserve | reserve-03-three-clean | M,S,D | 3 | 6 |
| reserve | reserve-04-three-clean | S,D,M | 3 | 6 |
| reserve | reserve-05-short | M,S | 2 | 6 |
| reserve | reserve-06-short | S,M | 2 | 6 |
| reserve | reserve-07-expressive | D,M,S | 3 | 6 |
| reserve | reserve-08-expressive | M,D,S | 3 | 6 |
| reserve | reserve-09-overlap | D,M | 2 | 6 |
| reserve | reserve-10-overlap | S,M,D | 3 | 6 |

## Boundary between oracle, inference and scoring

[diar_sweep.py](../../../tools/eval/diar_sweep.py) passes manifest K only in the explicitly labelled `fixed` research mode; `auto` uses `-1`, and `overcluster` uses the global constant 8. Those latter modes must never use per-case expected K. Fixed-K results are oracle comparisons, not evidence that automatic K works. The runner explicitly records that an actual K=1 diarizer call differs from V1.6's production single-speaker bypass; the final fixed-V1.6 comparator must preserve that distinction.

[speaker_refiner.py](../../../tools/eval/speaker_refiner.py) accepts only native predicted turns, measured embedding windows, duration and global configuration. Native integer labels are prediction identities, not source actors M/S/D. There is no parameter for reference text, expected K, case ID, source actor or corpus split. Missing centroids stay explicit; a temporal small-fragment fallback is an optional labelled policy, not an acoustic identification result. Forced-cap, low-similarity, overlap-collapse and smoothing operations remain diagnostic evidence.

[refine_sweep.py](../../../tools/eval/refine_sweep.py) rejects fixed-K research sources and calls `refine(turns, windows, duration, global_config)` without the reference, words, K or case ID. Author references enter metric computation only; frozen D words are replayed for speaker assignment and cpWER after refinement. A raw-WER invariant checks that raw scoring remains unchanged; equal scores alone do not prove byte-identical hypotheses. Input hashes, incomplete source coverage and helper support are retained. `refiner_accepted` means computational support, not a dev/holdout or release gate. The sweep reports metrics and does not itself select a winner.

## Practical C gate and limits

The [plan](../../../docs/history/root/PLAN_19H.md) requires exact native speaker count on at least 80% of dev files and DER no more than 2 percentage points worse than fixed V1.6. With the current eight dev cases, 80% means **at least 7/8**, not 6/8. Count success is higher-is-better; DER and count absolute error are lower-is-better. Compare weighted DER as total miss+false alarm+confusion divided by total reference speaker time, using the same cases and collar as the fixed comparator. Preserve both collar0 and collar250 outputs; fix the primary collar/selection rule before holdout rather than choose whichever passes afterward. Baseline/candidate case coverage must be complete and identical.

Correct K alone can conceal merging different voices and assigning all their text incorrectly. A candidate therefore needs the paired native DER check, count error, cpWER and per-file failures alongside the raw-WER invariant. Short guests and overlaps require explicit inspection: the plan's small-cluster rule can erase a real short guest, while merging simultaneous source labels can lower K and destroy overlap. A temporal fallback must remain named as such; complete/partial acoustic support and unsupported cases cannot be silently discarded from the denominator.

These are **montage utterance-interval DER** measurements. Full source-clip intervals include edge/internal silence; placed clip overlap does not guarantee simultaneous voiced speech. A method can improve this proxy by fitting clip/pause structure without improving real speech-activity boundaries. Refiner endpoints come from native turns, which prevents gold-boundary rewriting, but does not make the gold acoustic speech-activity annotation.

All sets share the same three actors, and sessions may overlap. Original holdout and reserve have already been inspected in D; for C they remain separate regression validations, not new untouched tests. Same-actor expressive/whisper/session variation is useful for controlled comparisons, but the small actor pool and repeated development do not establish performance on unseen speakers, phone channels, natural interruptions or hidden jury audio. Any C promotion must remain scoped to the measured corpus/actual Android port; natural-dialogue DER, independent word timing and physical-device performance remain unproven.
