# Russian evaluation corpus v1

This corpus accompanies the host evaluation harness. It contains **six dev and
four holdout simulated conversations**, plus **three original mono utterance
sanity files**. Audio is downloaded/generated outside Git and is never packaged
in the app. References retain the author's punctuation and case.

## Source and independent reference text

Source: [Langswap Dialogs](https://huggingface.co/datasets/langswap/dialogs-ru-emotional-conversations),
pinned revision `a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd`.
The [authors' paper](https://arxiv.org/abs/2607.14310) describes acted studio
dialogues segmented/aligned with transcripts. These are recordings of three
actors, not generated voices. Dialogue scripts were written before recording;
our reference strings are taken verbatim from the supplied CSV `text` column.
REPLIKA/candidate ASR hypotheses, VAD and forced alignment are **not** used to
create or correct these references. We have not independently audited every word
against the recording. Possible overlap with model pretraining is unknown.

The complete pinned source metadata and license are retained in `sources/`.
`provenance.json` records each selected row, source URL, raw WAV SHA-256 and the
placement of every utterance. Raw WAVs are verified against publisher LFS SHA-256
and sizes from the pinned Git tree. These identify bytes, not publisher signatures.

## Frozen selection and separation

`selection.json` was written before inference. The preparer has fixed recipes
and duration/emotion/actor constraints; eligible unused CSV rows are ordered by
SHA-256 of a fixed seed plus `audio_path`. Selection does not depend on recognizer
output, measured WER or model confidence. `sources/audio-index.json` freezes the
published paths and LFS hashes: 58 of the 368 CSV paths are not published in the
pinned audio tree and are excluded before selection. The initial unavailable
attempt is retained as `selection-attempt-01-unavailable.json`; it was abandoned
before inference and supplies no final evaluation cases. The fixed actor order
was adjusted to the available whisper/short pools before the final selection.

- All dev sources come from the official `val.csv`; all holdout sources come
  from the official `test.csv`.
- All **77 source clips** have unique paths and raw content hashes. No source
  clip is reused, even within a split. Exact reference strings are also not
  repeated across cases.
- The seven official test whisper clips used in the V1.5 study are excluded
  from this corpus. The holdout therefore does **not** provide a new whisper
  acceptance set. The dev whisper case uses previously unused validation clips.
- Three actor identities are shared across dev and holdout. These splits are
  utterance-disjoint, **not actor-disjoint or session-disjoint**. This small
  studio corpus cannot establish general speaker-embedding performance.
- Short cases use author utterances of at most 3.5 s and eight whitespace words.
  Short dev uses the two female actors: there is no eligible male validation
  utterance under those fixed constraints. Short holdout includes three actors.
- The three mono sanity files retain a single source utterance, with no montage
  padding or inserted gaps; only format conversion/resampling is applied.

The manifest has schema version 1 and `files[]` entries with `id`, `split`,
`language`, `audio`, `reference`, `duration_ms`, `audio_sha256`,
`expected_speakers`, `kind`, `source`, `conditions` and explicit timing scope.
`audio` is relative to the external audio root; `reference` is relative to this
directory. Each reference uses exactly the jury JSON `transcript` schema, with
speaker IDs numbered by first occurrence in its own file.

## Timing and DER scope

**Montage DER is an utterance-interval proxy, not natural-dialogue DER.**

Sources are author-segmented utterance WAVs. Their full clip intervals include
internal pauses and any silence at the edges. We place those intervals onto a
constructed timeline and insert fixed silence gaps; overlap cases deliberately
overlap some clip regions by 500 ms. An overlap of file regions does not prove
that both actors are acoustically speaking at that instant. These boundaries
are not independently annotated speech-activity or word timestamps. The mono
cases likewise provide author utterance bounds, not speech-activity gold.

Thus WER against author text is useful evidence on the declared corpus. Speaker
count, cpWER and timing/DER proxy results can detect changes under controlled
conditions, but cannot alone establish acceptance on natural dialogue, real
overlap, phone audio or the hidden jury set. Do not present the proxy DER as
human-annotated natural-dialogue DER or tune a VAD-generated gold reference.

An accessible source with the desired natural-dialogue properties was sought.
[DAI-ASR-I18N](https://huggingface.co/datasets/davidai-labs/DAI-ASR-I18N) has natural
Russian conversations and human-verified text, but requires an approved custom
gated agreement and prohibits redistribution/training. Access was not attempted.
The openly listed `ivkond/synthetic-speech-diarization-ru` is synthetic and does
not establish independent author punctuation; it was not selected.

## Audio preparation and reproducibility

Use Python 3.12+ with the versions recorded in `provenance.json` (the prepared
environment has NumPy 2.5.4, SciPy 1.18.1 and SoundFile 0.14.0). The source
metadata is verified against pinned SHA-256. Only selected individual WAVs are
downloaded, not the full dataset or a parquet archive.

```bash
# Set this to an external directory; do not put research audio under the repo.
export REPLIKA_EVAL_AUDIO_ROOT=/path/outside/repository/eval-audio

# Freeze the same deterministic row selection without audio/model inference.
python tools/eval/prepare_corpus.py --audio-root "$REPLIKA_EVAL_AUDIO_ROOT" --select-only

# Download only the selected source clips, convert and construct the cases.
python tools/eval/prepare_corpus.py --audio-root "$REPLIKA_EVAL_AUDIO_ROOT"

# Rebuild in memory from the cache and require all frozen output bytes to match.
python tools/eval/prepare_corpus.py --audio-root "$REPLIKA_EVAL_AUDIO_ROOT" --offline
```

The preparer refuses to overwrite different metadata, references or audio.
Changes to the selection or encoding should use a new corpus version/directory,
not silently replace the baseline. `--metadata-dir` can select that directory.

Processing: decode using libsndfile to float64; average channels; resample to
16 kHz with `scipy.signal.resample_poly`, reduced integer rate ratio, Kaiser
window beta 5.0 and constant padding. Do not trim with VAD or ASR. Montages add
250 ms of outer silence and fixed gaps; mono files add none. A constant
whole-file gain is used only when the mixed peak would exceed 0.999, preventing
introduced PCM16 clipping. Each actual gain is recorded. Finally encode mono
16 kHz PCM16 WAV. This resampling is a corpus preparation step, **not** a claim
of bit identity with Android's MediaCodec/FIR decoder.

## License and distribution

The source uses the authors' custom **OpenRAIL** responsible-use license. Retain
[the full license](sources/LICENSE.md), its use restrictions and notices when
distributing these metadata or derived audio; the preparer also copies it into
the external audio root. Audio must stay outside APK/source archives. This
dataset license is independent of the application/model licenses. No special
model access token is required for the selected public WAVs.
