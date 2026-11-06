# Evaluation protocols

`score.py` compares an independent reference with a saved hypothesis. It performs
no inference, never sends reference text into a model, and does not edit input
files. Its measurements describe this protocol; the organizers' exact scorer
remains unknown.

```bash
python3 tools/eval/score.py \
  --reference reference.json --hypothesis hypothesis.json \
  --duration-ms 60000 --processing-ms 12000 --output metrics.json
python3 -m unittest discover -s tools/eval/tests -v
```

The CLI requires a new output path and refuses to overwrite evidence. UTF-8
without BOM is used. `--processing-ms` is optional; absent timing yields `rtf:
null`. The Python API is `score(reference, hypothesis, duration_ms,
processing_ms=None)`. The reusable `der(reference_rows, hypothesis_rows,
duration_ms, collar_ms=0)` also accepts native diarization turns converted into
the four Jury row fields, with `text: ""` and arbitrary nonempty speaker labels.

Each input has exactly `{"transcript": [...]}`. Each row has exactly
`speaker_id`, `start_ms`, `end_ms`, `text`; timestamps are integers in
`[0, duration_ms]`, with end ≥ start. Invalid timestamps are rejected rather than
silently clipped. Speaker labels are opaque identifiers and need not match
across reference and hypothesis. Rows are sorted by start and then end; input
order is retained for complete ties. Blank text and zero-duration rows remain
visible in input counts. Positive-duration blank rows count for diarization and
timing. Zero-duration rows contribute their text but no temporal support.

All rates are **fractions**, not percentages. Undefined denominators produce
`null`, not an invented zero or perfect score. WER/DER may exceed 1. Counts and
denominators are retained for aggregation; aggregate WER is total errors divided
by total reference words, not an unweighted average of file WERs.

## Text

- `wer_raw` is primary: exact whitespace-delimited tokens. Case, attached signs,
  `ё/е`, Unicode spelling and numeric forms remain distinct. Only whitespace
  runs are separators. Segments are concatenated in chronological row order;
  overlapping speech is not given a special interleaving oracle.
- `wer_punctuation_tokens` preserves spelling/case but separates every
  punctuation/symbol codepoint. Letter/number/underscore/combining-mark runs form
  word tokens. This is a second, explicitly different tokenization.
- `wer_normalized` matches `domain/Benchmark.kt`: lowercase, NFC, `ё→е`, replace
  non-letter/non-number characters with spaces. `cer_normalized` uses the same
  text with spaces removed. Its `reference_tokens` counts characters.
- Unit-cost Levenshtein reports substitutions, deletions, insertions, correct
  matches, errors and both token counts. Equal-cost paths prefer diagonal
  match/substitution, then deletion, then insertion. This makes S/D/I reproducible
  but does not establish the causal source of an error (VAD versus ASR).
- `wer_number_normalized` is optional and explicitly unavailable if `num2words`
  is absent. If present, digit-only tokens after lexical normalization are
  expanded as cardinal integers on both sides. Cyrillic text selects Russian;
  otherwise English is used. This heuristic is not language identification.
  Dates, times, currency, percentage units and ordinals are not interpreted
  semantically; this diagnostic is not a claim of equivalence under the jury's
  unknown ITN conventions. Primary/raw text is never replaced by this result.

## Punctuation and case

`punctuation` reports micro precision/recall/F1 and counts for `. , ? ! — :`,
plus per-mark values. Signs are anchored to the preceding lexical word;
signs before the first word have a BEGIN anchor. Normalized lexical sequences
are aligned first, and a mark matches only at an equal aligned lexical anchor.
A comma after a substituted or inserted word is therefore not rewarded merely
because the other transcript contains a comma elsewhere. Multiplicity is
counted. Missing punctuation on both sides gives undefined F1.

This protocol is sensitive to ambiguous repeated-word alignment and lexical
errors. It does not infer syntactic sentence boundaries or distinguish a colon
inside a time from a grammatical colon. Quotes and marks outside the six listed
classes are excluded from this diagnostic; raw WER still sees them.

`initial_case.accuracy` evaluates the first cased letter of each reference
segment at its aligned equal lexical word, even if hypothesis segmentation
differs. Missing/unmatched reference initials count incorrect.
`conditional_accuracy` excludes unmatched initials and reports its denominator
separately. Caseless scripts and digit-only rows have no eligible cased initial.

## Diarization

`der_collar_0ms` and `der_collar_250ms` evaluate the complete recording, including
overlap and nonspeech. A Hungarian assignment maximizes overlapping speaker time
globally; it is recomputed after collar exclusion. For each atomic interval:

```text
miss = max(0, reference speaker count - hypothesis speaker count)
false alarm = max(0, hypothesis speaker count - reference speaker count)
confusion = min(reference count, hypothesis count) - correctly mapped count
DER = (miss time + false-alarm time + confusion time) / reference speaker time
```

Repeated overlapping intervals of one label represent that label's temporal
union, rather than multiple simultaneous copies of the speaker. The zero-collar
formula follows the project's `Benchmark.kt` implementation.

The collar convention matches [pyannote-metrics' primary implementation](https://github.com/pyannote/pyannote-metrics/blob/develop/src/pyannote/metrics/utils.py):
`collar_ms=250` is the **total width**, excluding ±125 ms around each reference
segment boundary from both sides. It is not ±250 ms. Short reference segments
can disappear entirely, leaving an undefined DER. `excluded_duration_ms` and
`reference_speaker_ms` show this explicitly. Use `der(..., collar_ms=500)` if a
separate protocol requires ±250 ms; label it accordingly.

`speakers` counts distinct labels with positive temporal support, including
blank-text native turns; it reports signed and absolute count error. The count
is not a DER substitute.

Jury-export segment spans reflect text-assignment intervals, not necessarily
raw native diarization turns. Score raw native turns separately via `der()` to
evaluate the actual diarizer before export-side unknown-speaker projection.
Do not present export-derived DER as an isolated embedding/clustering result.

## Speaker-attributed text and timestamps

`cpwer_raw` and `cpwer_normalized` concatenate each speaker's words in time order.
They minimize total Levenshtein errors over all one-to-one speaker assignments;
unequal speaker counts are padded with empty streams. Missing streams contribute
deletions; extra streams contribute insertions. The denominator is the total
reference word count. The optimal cpWER assignment can differ from the DER
assignment. Empty-text labels have no word stream, but still count for DER.

`timing` performs a global one-to-one assignment that maximizes summed temporal
intersection-over-union (IoU). Only positive-overlap pairs are accepted. Text
and speaker identity are not used. It reports mean/median absolute start/end
errors, pair coverage on both sides, unmatched interval counts, and the fraction
of matched pairs whose start **or** end error exceeds 250 ms. A separate
`reference_fraction_over_250ms_or_unmatched` treats missing reference matches as
failures. No pairs means undefined mean errors, not zero.

This timestamp diagnostic depends on segment granularity; a split or merged
utterance cannot receive multiple one-to-one matches. It is not word alignment
accuracy and is not known to match the jury's timestamp criterion. Always report
coverage beside mean error so dropped speech cannot look artificially precise.

`rtf = processing_ms / duration_ms`. The caller must label whether processing
time includes loading, decoding, persistence and cold/warm caches, and whether it
was measured on host, emulator or physical device. The scorer does not infer
those conditions or convert host timing into phone timing.
