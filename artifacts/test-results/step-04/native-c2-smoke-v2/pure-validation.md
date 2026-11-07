# C2 Android smoke v2: pure validation

PASS on the actual `dev-mono-s` payload using the unchanged frozen v3 validator. No NN, ADB or build was run by this validation.

- Sidecar: 70,224 bytes; SHA-256 `a4b4171d0350b1b347a7a1fdf6378ff7852703b70fe24ae7b08ad2985cb3750e`.
- Four complete real 512-dimensional Float32 embedding windows; extractor loads 1; reads/streams/releases/attempts/forward calls/measured windows all 4. Native resources released.
- Source audio hash/6,333ms clock, legacy ERes model pin, C2 policy and paired `vad_words_context600` match. Canonical work UUID/record and sidecar SHA/size match.
- Exact replayed turn: `[31,6275,speaker0]`; computational status `PARTIAL_TEMPORAL`, preserving the explicit selected temporal-voting policy. Full sidecar trace independently replays; compact Room projection matches. Actual QA cutoff `2000.0` versus Room `2000` validates through the single exact numeric allowlist.
- 42 realtokens/42 timestamps reconstruct 14 words; actual exported JuryJSON matches exactly, including text, punctuation, case, speaker and timestamps.

This is one functional mono smoke. It is not the fixed-five weighted WER gate, the dev8 count/DER gate, natural-dialogue validation, phone/ARM performance or release acceptance. No new decoded-PCM SHA is claimed.

Source hashes, all counters, strict-schema checks and limitations are recorded in `pure-validation.json`.
