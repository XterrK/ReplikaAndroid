# MP4 audio timeline compatibility — V1.5

2026-11-06. Fix scope: local video/audio import, without changes to ML, ASR configuration or UI.

## Regression and evidence

Android 28 exposed the first AAC sample at0 for `aac-offset.mp4`, although its audio track contains an `elst` initial empty edit of18176 movie ticks at48000 Hz: approximately378.667 ms. The old zero-PTS remux gate consequently discarded the video-clock delay. This also bypassed the PCM preparation callback used by the cancellation regression.

The [actual API28 format probe](../../human-review/v1.5/evidence/api28/mediaextractor-format-probe-api28.txt) identifies audio `track-id=2`, extractor index1, first PTS0. The [read-only box dump](../../human-review/v1.5/evidence/api28/aac-offset-boxes.json) confirms the separate movie/media clocks and two edits. The source fixture is a synthetic tone with an original flat-color video, not a microphone or speech-quality test.

AOSP Android9 explicitly handles only a single `elst` entry for gapless playback and ignores multi-entry lists; AOSP Android15 handles the initial empty edit and shifts presentation timestamps. [Android9 extractor](https://android.googlesource.com/platform/frameworks/av/+/android-9.0.0_r1/media/extractors/mp4/MPEG4Extractor.cpp), [Android15 extractor](https://android.googlesource.com/platform/frameworks/av/+/android-15.0.0_r1/media/module/extractors/mp4/MPEG4Extractor.cpp). Edit lists map movie time to media time; their clocks must not be mixed. [Apple format documentation](https://developer.apple.com/documentation/quicktime-file-format/playing_with_edit_lists), [W3C ISO-BMFF note](https://www.w3.org/TR/mse-byte-stream-format-isobmff/).

## Implementation

[IsoBmffAudioTimeline.kt](../../../app/src/main/java/ru/replika/ml/IsoBmffAudioTimeline.kt) reads only checked box headers and small metadata fields using bounded positional seeks. It reads `moov/trak`, `tkhd.track_ID`, `mvhd/mdhd` clocks, `edts/elst`, and the first composition-time offset when present. Track matching uses the actual [MediaFormat track ID](https://developer.android.com/reference/android/media/MediaFormat#KEY_TRACK_ID), not the extractor track index. Missing IDs can fall back only to a unique audio track.

For an initial empty edit followed by untrimmed audio at rate1, two observed cases are accepted:

- First PTS≈the expected empty-edit duration: the platform already applied it; additional offset0.
- First PTS0: recover the missing edit duration once, in decoded PCM presentation timestamps.

Known delayed tracks always use PCM output, retaining actual leading silence instead of trusting a muxer to preserve a non-zero start. Unexplained timestamp mappings fail with an actionable message. No offset is inferred from video duration minus audio duration; longer trailing video remains a zero-offset audio import.

A single positive `media_time`, including the common AAC priming value1024, remains platform/codec gapless metadata. The fix does not subtract it again or alter codec delay/padding. The new `aac-priming.mp4` fixture explicitly contains this case.

Unsupported mappings include multiple media edits, non-unit/dwell rates, an empty edit combined with a start trim, delayed fragmented audio, non-zero initial composition offset, ambiguous track identity, and delayed end trims/extensions beyond small clock rounding. One movie tick plus one media tick is allowed for end rounding, with a2 ms cap. Unsupported or malformed mappings fail instead of producing plausible but incorrect timecodes.

The reader permits32/64-bit box lengths and `elst` versions0/1; handles provider descriptor subranges; never reads `mdat` payload; caps metadata reads at256 KiB, box count4096, tracks64, edits16; and checks cancellation during traversal. Each individual metadata allocation is at most256 bytes. Video frames are never decoded, and the original video is not copied or modified. URI descriptors are duplicated and owned through `AutoCloseInputStream`; source offsets/lengths are retained. Partial-output cleanup remains in `MediaImporter`; cancellation after the PCM progress callback is checked before starting the codec.

## Validation status

Pure helper tests were compiled with Kotlin2.1.20 and run with JUnit4.13.2 outside Gradle; see [standalone evidence](../../test-evidence/v1.5/iso-bmff-source8-host.log). Cases cover missing/already-applied delay, real delayed and priming fixtures, version1/extended boxes, movie/media clock rounding, correct track identity, unsupported edits, malformed bounds, cancellation, provider subranges, unknown top-level boxes and a virtual file with `mdat` larger than4 GiB without reading its payload.

Android coverage is in [MediaImportV15Test.kt](../../../app/src/androidTest/java/ru/replika/MediaImportV15Test.kt): the existing delayed-clock/cancellation checks plus delayed content-URI, normal AAC priming and unsupported-rate cleanup cases. Actual API28/API35 post-fix execution and the full real-speech `VideoPipelineV15Test` must be recorded after source8 is built. A host parser pass does not establish Android codec or physical-device behavior.

No new runtime library, FFmpeg executable, native media engine, model, VAD parameter, transcription timestamp policy or Room schema was added.
