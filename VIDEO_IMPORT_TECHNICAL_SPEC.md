# REPLIKA V1.5 — video import and GigaAM-only product

The user's direct instruction removes Whisper and adds local transcription of video audio. The original document remains unchanged. Recognition starts from the normal speaker-selection screen after import; import never starts automatic diarization by itself.

## Import contract

`MediaImporter.importMedia(uri, directory, id, progress)` returns an app-owned, audio-only `Result`. `AppViewModel.importAudio(uri)` remains the compatible picker entry point and accepts both audio and video. `importProgress: StateFlow<String?>` is null when idle; `cancelImport()` cancels the active import. On commit the ordinary Room `Recording` is inserted and `selected` changes. Existing playback, processing, edits, persistence and export use the same artifact as audio recordings.

Android's `MediaExtractor` reads the content URI directly. Video frames are never sent to a decoder, and the original video is never copied into app storage. A seekable content provider / Android-supported container and audio codec are required; cloud providers may first download their own document before granting access. No network fetch is initiated by REPLIKA.

Track policy: choose the first audio track marked `is-default` by the platform, otherwise the first audio track. Import only that track and show a notice for multiple audio tracks. The API returns its index and total track count. There is no automatic language or mix selection.

For AAC whose first sample has PTS zero, copy compressed audio packets into M4A with `MediaMuxer`. Preserve timestamps, decoder configuration and original compressed audio. No audio re-encoding is used. Muxer incompatibility falls back to the platform audio decoder.

Other supported audio codecs and non-zero initial timestamps use `MediaCodec` to decode audio only into mono 16-bit WAV at the source sample rate. Leading silence and timestamp gaps are inserted; negative/overlapping frames are trimmed. This keeps transcript times relative to the original video clock, including a delayed audio start. The existing `AudioDecoder` performs its normal single final resampling to 16 kHz for ML. Import does not change VAD, diarization, thermal control or the ASR pipeline.

Streaming uses bounded packet/PCM buffers and checks cancellation and available storage. Eight MiB is reserved beyond the written artifact. PCM fallback can use more disk space than compressed audio; RIFF's 4 GiB bound is enforced. Codec input/output buffers are always released; stalled decoders time out. Errors explain missing audio, lost permission, protected content, unsupported/corrupt media and insufficient storage. Failed/cancelled partial outputs are deleted. The ViewModel also handles cancellation at dispatcher/Room commit boundaries, preserving any artifact referenced by Room.

## Whisper retirement

The current manifest has one GigaAM family, VAD and diarization (seven files). `ModelManager.asrId` derives the current Giga family from the manifest and `resolveBackend` maps stale preferences/jobs to that family. Model choice is an active model row. Historical `whisper-tiny` Room attribution and display names remain readable and exportable; there is no historical-data rewrite.

The custom `WhisperEngine`, JNI bridge, CMake build and `libreplika-whisper.so` are removed. The removed GGML model is absent from the current manifest and separate V1.5 pack. Only the exact app-owned retired weight `files/models/whisper-tiny/ggml-tiny.bin` is deleted on upgrade; old external packs, APKs, recordings and transcripts are preserved. Generic upstream sherpa JNI ABI configuration types are retained, including optional Whisper structs; no Whisper model/engine is selected by the product.

`tools/prepare_current_pack.py` streams and verifies current manifest-pinned local files into `model-pack/replika-offline-pack-v1.5.zip`. It refuses to overwrite `replika-offline-pack.zip`. The embedded pack generator re-verifies every size and SHA-256. The final APK verifier rejects a packaged custom Whisper runtime and unexpected pack members. Switching between supported Giga families requires a new pinned manifest/local pack and measured acceptance, not an architecture change.

## Verification scope

`MediaImportV15Test` covers real Android AAC remux, no video tracks in artifacts, delayed-track silence/timecodes, Opus decoding fallback, declared-default/first-track policy, bit-identical ordinary audio copy, corrupt/no-audio/empty/missing-document errors, real content-provider URIs, pre-import and mid-copy storage exhaustion, cancellation cleanup (including dispatch-boundary ownership), collisions/path safety, unchanged sources and narrowly scoped retired-weight cleanup. Tiny original generated tones/color-video fixtures are Android-test assets only; `tools/create_media_import_fixtures.py` records their hashes. They contain no speech and establish no recognition-quality claim.

`VideoPipelineV15Test` uses a separate 99 KB video generated from the exact public Russian GigaAM sample (SHA-256 and command recorded in `docs/test-evidence/v1.5/video-pipeline-fixture.json`). It runs actual extraction, the production offline Worker, a second Room connection and JSON/TXT/SRT file readback. It is staged externally as `files/integration-video-v15.mp4`, never packaged as an app asset.

Host pack verification and Python syntax checks are separate from Android codec/runtime tests. The final test report must record actual instrumentation results; this specification is not evidence that tests passed on a physical phone. The user's vivo X300 is disconnected, so phone microphone/performance/thermal acceptance remains unavailable.

Platform references: [MediaExtractor](https://developer.android.com/reference/android/media/MediaExtractor), [MediaMuxer](https://developer.android.com/reference/android/media/MediaMuxer), [supported formats](https://developer.android.com/media/platform/supported-formats).

## Interrupted-import journal (V1.5 final)

Before extraction, `ImportJournal` atomically publishes a short versioned marker at `files/audio/.pending-imports/<UUID>.pending`. Only then may the importer create `<UUID>.audio`, `.m4a` or `.wav`. `ReplikaApp.importGate` serializes all live import actions through Room insertion with startup recovery, including recovery initiated by another ViewModel. Failed marker creation or an existing output/marker never authorizes deletion.

Recovery examines only valid UUID markers and three fixed candidate names, with bounded marker reads and at most 128 entries per startup pass. It does not scan the audio directory for general orphans. A targeted Room `EXISTS` query checks all candidate paths and canonical aliases, including references from a different recording ID. Referenced audio is preserved and its marker retired. An unreferenced, safely owned output can be removed; database lookup failures retain marker and files for a later retry. Invalid/oversized markers, redirected paths and symbolic links never authorize deletion. Cancellation after Room commit preserves the recording, and cancellation before commit removes owned partial outputs. Original source documents are outside journal ownership.

`ImportJournalV15Test` uses isolated files, actual in-memory Room references, a shared coroutine gate and persisted interrupted-state fixtures. It covers uncommitted/committed imports, shared references, database failure and retry, cancellation after commit, failed begin/collisions, live import versus recovery, invalid markers and redirected paths. Re-instantiating the helper models startup recovery; the suite does not claim a physical OS hard-kill experiment.
