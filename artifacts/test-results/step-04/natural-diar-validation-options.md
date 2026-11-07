# C: small natural-dialogue validation options

Research checked 2026-11-07 00:11–00:15 UTC, bounded to five minutes. **No audio body was downloaded, no model ran, and no corpus/gate was changed.** Requests read source documentation, Git metadata and RTTM/UEM text; audio requests were HEAD only. This concerns diarization, not English ASR task E.

## Feasible first choice: AMI naturally occurring meetings

AMI explicitly distinguishes naturally occurring **N** meetings from scenario **S** and elicited **B** meetings. EN2002a/c are MSc project discussions; they are not scripted utterance montages. [Official ID definitions](https://groups.inf.ed.ac.uk/ami/corpus/meetingids.shtml), [non-scenario meeting descriptions](https://groups.inf.ed.ac.uk/ami/corpus/nonscenariomeetings.shtml).

The benchmark RTTMs are the [BUT Speech@FIT setup](https://github.com/BUTSpeechFIT/AMI-diarization-setup), derived from AMI **manual annotations v1.6.2**, using word speech intervals and preserving pauses/overlap. They are benchmark-author derivatives of official manual annotation, rather than original AMI-format RTTM releases. Prefer `only_words`; do not mix the alternative words+vocal-sounds policy. [Setup documentation](https://github.com/pyannote/AMI-diarization-setup#ami-diarization-setup).

| Proposed diagnostic input | Direct official audio URL | HEAD result | First60s reference |
| --- | --- | --- | --- |
| EN2002a headset mix, crop [0,60) | [EN2002a.Mix-Headset.wav](https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/EN2002a/audio/EN2002a.Mix-Headset.wav) | 200, 68,566,744 bytes, `Accept-Ranges: bytes` | Four speakers; 15.74/27.19/17.97/12.11 speaker-seconds |
| EN2002a single distant mic, same crop | [EN2002a.Array1-01.wav](https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/EN2002a/audio/EN2002a.Array1-01.wav) | 200, 68,566,744 bytes, `Accept-Ranges: bytes` | Same meeting/RTTM; harder microphone condition, not an independent speaker sample |
| EN2002c headset mix, crop [0,60) | [EN2002c.Mix-Headset.wav](https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/EN2002c/audio/EN2002c.Mix-Headset.wav) | 200, 95,112,236 bytes, `Accept-Ranges: bytes` | Three speakers; 3.29/12.25/4.86 speaker-seconds |

EN2002a RTTM labels are FEO070/FEO072/MEE071/MEE073; EN2002c uses FEO072/MEE071/MEE073. Speaker-seconds above are computed from clipped RTTM intervals, not audio/VAD. These sessions share participants and cannot be called speaker-disjoint. Both meetings are in the benchmark test partition. The official signal catalogue also identifies their participants. [AMI signal documentation](https://groups.inf.ed.ac.uk/ami/corpus/signals.shtml).

Immutable annotation URLs and checks:

- Upstream BUT commit **`2509d8933721023fab4def2618aabd5c28eb82e9`**, [EN2002a RTTM](https://raw.githubusercontent.com/BUTSpeechFIT/AMI-diarization-setup/2509d8933721023fab4def2618aabd5c28eb82e9/only_words/rttms/test/EN2002a.rttm): 42,817 bytes, SHA256 `a93919ae5f18e476614b7e5a2713c4dc6bba23e95149fba18dbe68602b13ee40`.
- Pyannote fork commit **`67c2d539286e89f68952d5dcf83912bd9f01dfae`**, [EN2002c RTTM](https://raw.githubusercontent.com/pyannote/AMI-diarization-setup/67c2d539286e89f68952d5dcf83912bd9f01dfae/only_words/rttms/test/EN2002c.rttm): 36,557 bytes, SHA256 `e595fa5953a923cbd62ffc881bd9725df98a6587bc14730dd279937773953bca`.
- Same fork's [EN2002a UEM](https://raw.githubusercontent.com/pyannote/AMI-diarization-setup/67c2d539286e89f68952d5dcf83912bd9f01dfae/uems/test/EN2002a.uem): interval [0,2142.709375), SHA256 `3126782a9c64efc2ed2919b8c9e1666a6254b1abedf6279de9512829472244d1`. Its EN2002a RTTM was also read and has the same bytes/hash as upstream.

**Download size:** one complete meeting WAV is ~65–91MiB, not a multi-GB corpus archive. For a later bounded fetch, the server advertises byte ranges; a 60s16kHz mono PCM16 payload would be ~1.92MB **if the actual WAV header confirms that format**. HTTP206 behavior and RIFF/data offsets have not been tested here, because no audio bytes were authorized. Later parse the real WAV chunks/format, then fetch exact frame ranges; never assume a44-byte header. If Range is ignored, abort the bounded request or explicitly choose the single-file download. Current audio URLs are not immutable revisions: preserve ETag/Last-Modified and measure source/crop SHA256 during the later authorized preparation; these headers are not content-hash proof.

**License scope:** the current official AMI download page says signals and manual annotation v1.6.2 are **CC BY4.0**, including the2017 license update. The older OpenSLR16 listing describes an earlier modified NC/SA license; use the actual current source release/notice, not that mirror summary. The setup repository has a separate **Apache2.0** license. Retain AMI/benchmark attribution and applicable notices; research audio should remain outside APK/Git. [Current AMI release/licensing page](https://groups.inf.ed.ac.uk/ami/download/), [pinned setup license](https://raw.githubusercontent.com/pyannote/AMI-diarization-setup/67c2d539286e89f68952d5dcf83912bd9f01dfae/LICENSE).

EN2003a is another naturally occurring three-person meeting with a public71,688,920-byte headset WAV and readable RTTM, but belongs to the benchmark **train** partition. It is a weaker independent-validation choice, especially with AMI-trained segmentation; prefer the test meetings above. Neither AMI test membership nor a new corpus proves disjointness from every candidate model's training data.

## Conditional fallback: VoxConverse v0.3

The [authors' repository](https://github.com/joonson/voxconverse) provides human-speech broadcast/debate clips and RTTM labels, and warns that v0.3 corrects older test labels. Current annotation commit: **`24bf60be297701cd7e4ef18550c6d390c1b87365`**. Its stated scope is research download under CC BY4.0, with video copyright remaining with original owners.

Official [dev ZIP](https://www.robots.ox.ac.uk/~vgg/data/voxconverse/data/voxconverse_dev_wav.zip) returned **HTTP401 to HEAD** in this session. No official individual-WAV route was verified. This is therefore **not a currently verified small-download option**. Do not substitute an unaudited HF mirror or scrape YouTube. A future archive-range approach would need confirmed public access, ZIP central-directory/member checks and matching v0.3 IDs before claiming feasibility. No such fetch happened here.

## Later preparation and evaluation boundary

After root freezes a candidate, freeze meeting/channel/crop selection from metadata before any new hypotheses. The first60s option avoids searching for a segment where one model looks good; it also gives60s of actual neural context, beyond sherpa's short single-window exception.

For crop [a,b), intersect each RTTM speech interval with [a,b), drop empty intersections, then subtract a from **both** endpoints. Preserve overlaps and the original speaker IDs; crop K counts only speakers with positive retained speech. Crop the UEM identically and score the entire crop, including its silence, not just reference speech. Parse decimal seconds consistently and record a single millisecond conversion rule. Keep the same crop/sample clock for headset and distant-mic variants; verify the signal/header mapping before comparison.

Run automatic/native diarization and optional refiner only: no known K enters inference, no GigaAM English transcript is required. Report native DER0/250, miss/false alarm/confusion, count error, overlap and exact preprocessing/model hashes. Keep this as a separate natural-dialogue diagnostic, with declared word-derived manual annotation scope. A small shared-speaker AMI crop can expose a proxy failure; it cannot establish general natural-dialogue accuracy, Russian ASR, hidden-jury performance or replace the existing eight-dev/holdout gates.
