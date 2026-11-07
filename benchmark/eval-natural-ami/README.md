# AMI: separate natural-meeting diarization diagnostic

Prepared 2026-11-07, after the metadata-only selection freeze and before any
model inference on these crops. This adds three diagnostic inputs; it changes
neither the existing corpora nor their dev/validation gates. English ASR task E
is outside scope. See [attribution and licensing](ATTRIBUTION.md).

| Input | Source clock | Reference intervals | Reference speakers |
| --- | --- | --- | --- |
| EN2002a Mix-Headset | [0,60) seconds | 25 | 4 |
| EN2002a Array1-01 | [0,60) seconds | 25 | 4 |
| EN2002c Mix-Headset | [0,60) seconds | 8 | 3 |

The two EN2002a channels share one conversation and byte-identical gold. The
EN2002a/c meetings share participants. These are 180 seconds of channel audio,
120 seconds of distinct meeting time, and not three independent conversations.
Candidate training overlap is unknown. Reference speaker counts are for
scoring only; automatic inference must receive `expected_speakers=-1` and no
reference labels, count, speech activity or transcript.

[manifest.json](manifest.json) uses relative audio paths beneath the separately
provided audio root, and reference paths beneath this directory. Audio stays
outside Git/APK at the machine-specific root recorded in
[preparation-audit.json](preparation-audit.json). Each WAV contains exactly
960,000 PCM16 mono16kHz frames. No resampling, gain, VAD or ASR was performed.

The [preparer](../../tools/eval/prepare_natural_ami.py) required HTTP206,
exact requested `Content-Range`, frozen full-source length/ETag/Last-Modified,
identity encoding and bounded reads. It parsed actual RIFF chunks and verified
the PCM format before reading the crop. All 15 audio requests satisfied those
checks; total audio body bytes were 5,760,132. No complete source was fetched.
[provenance.json](provenance.json) retains each partial response's headers and
SHA256; whole-source audio SHA256 remains `null`. Canonical crop SHA256 values
are separately measured, not presented as full-source hashes.

Pinned `only_words` RTTMs in [sources](sources) derive from AMI manual annotation.
Conversion uses Decimal source seconds, intersection with [0,60), subtraction of
the crop start, then half-up integer milliseconds. It preserves original IDs,
overlap and whole-crop silence; every reference text is blank. The crop is scored
over its entire60seconds, including silence. Paired channels use the same clock.

The original [metadata freeze](../../artifacts/test-results/step-04/natural-probe-freeze.json)
was left byte-identical; [selection-freeze.json](selection-freeze.json) copies it.
Preparation passed 14 mocked tests for Range refusals, bounds, RIFF chunks,
PCM format, exact frames, RTTM clipping/rounding, source pins and fresh-output
rules, followed by the 36-check saved-artifact audit. No model inference or
diarization quality result is claimed here.
