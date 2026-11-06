# Unused-source reserve v1

This is an **additional future holdout**, frozen from independent author metadata.
It does not replace the original corpus or relax its acceptance gate. A future
candidate must still satisfy the original holdout requirement as well as any
reserve check. No candidate/baseline hypotheses, model metrics, model outputs or
old reference files are inputs to this preparation.

Seed: `plan19h-reserve-v1-20261107`. Exact recipes and selected source rows are
committed in `recipes.json` and `selection.json`. All ten cases have
`split="holdout"`. Five cases have two actors and five have three; two cases
contain short utterances and two have intentionally overlapping clip placements.
Each case uses six distinct source clips. Short cases use M/S because the
available unused short pool has no D clips under the fixed constraints.

The source is the same pinned author corpus:
[Langswap Dialogs](https://huggingface.co/datasets/langswap/dialogs-ru-emotional-conversations/tree/a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd).
Only unused clips are eligible. Every source path, publisher LFS audio SHA-256
and exact author text is disjoint from the original77 source clips and the
previously evaluated7 whisper clips. Clips are also not repeated within the
reserve. The source actors and recording sessions can still overlap with the
original corpus; this is not a speaker/session-disjoint test.

The initial metadata-only dry selection used a 9s ordinary upper bound and a
10s expressive bound. The available ordinary D pool was too narrow after earlier
selections. Before any reserve audio/reference creation or inference, both upper
bounds were uniformly expanded to12s; actor order, clip count, seed and conditions
stayed fixed. `construction-attempt-01.json` records that availability failure.
Final `selection.json` is immutable and includes its actual freeze timestamp.

References are **verbatim author CSV text**, retaining case and punctuation.
Intervals are deterministic placements of entire author utterance clips,
including any internal/edge silence. They are **not** human word/speech-activity
gold, VAD-derived labels or natural-dialogue timing annotations. Placed clip
overlap does not guarantee simultaneous voiced activity. DER/timing scores must
be described as montage utterance-interval proxies. No ASR, VAD or forced
alignment is used to build gold.

Audio is mono16kHz PCM16 WAV, using the unchanged helper from
`tools/eval/prepare_corpus.py`: float64 channel averaging, SciPy polyphase
resampling with Kaiser beta5.0 and constant padding, fixed gaps/500ms overlap,
250ms outer silence, gain only if needed for0.999 headroom, floor-converted
millisecond bounds. Exact helper hash, dependency versions, original source
URL/SHA/size, placement frames and each applied gain are in `provenance.json`.

```bash
# Keep research WAVs outside the repository.
export REPLIKA_RESERVE_AUDIO_ROOT=/path/outside/repository/eval-reserve-audio

python tools/eval/prepare_reserve.py --audio-root "$REPLIKA_RESERVE_AUDIO_ROOT" --select-only
python tools/eval/prepare_reserve.py --audio-root "$REPLIKA_RESERVE_AUDIO_ROOT"
python tools/eval/prepare_reserve.py --audio-root "$REPLIKA_RESERVE_AUDIO_ROOT" --offline
```

Existing different metadata, references or audio are never overwritten.
`summary.json` reports counts/duration/hash only. `disjointness.json` proves the
explicit source exclusions. `validation.json` records preparation checks, not
recognition quality. No inference is part of these commands.

The custom author OpenRAIL [license](sources/LICENSE.md) and source notices are
retained here and copied into the external audio root. Keep the license/use
restrictions with research derivatives. Raw source and constructed audio do not
belong in the APK, Git or public source archives.
