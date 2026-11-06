# REPLIKA V1.5 — current model/runtime redistribution audit

Date: 2026-11-05. Current scope: `assets/models-lock.json`, the separate `model-pack/replika-offline-pack-v1.5.zip`, native libraries, current APK notice assets and source provenance. The [2026-11-02 / V1.2.1 audit](history/v1.2.1/ALL_IN_ONE_LICENSE_AUDIT.md) is preserved unchanged. Its Whisper/GigaAM v2 inventory describes that historical build.

The current manifest contains **seven files in three groups**: `giga-v3` (four), `vad` (one), `diar` (two). It identifies exact bytes with SHA-256. The model-license records support retaining these permissive licenses and notices in distribution. File hashes establish integrity against the local manifest; they are not publisher signatures or a reconstruction of training-data ownership. The embedding conversion's exact checkpoint-to-ONNX lineage remains partially documented.

## Current weight inventory

| Model / files | Primary license evidence | Current APK attribution |
|---|---|---|
| GigaAM v3 E2E RNNT punctuation-capable sherpa ONNX INT8 conversion, 2025-12-16: encoder, decoder, joiner, tokens | MIT, Copyright (c) 2024 GigaChat Team. The selected maintainer repository has an [immutable revision/license](https://huggingface.co/csukuangfj/sherpa-onnx-nemo-transducer-punct-giga-am-v3-russian-2025-12-16/blob/a6039be7cee829a9044a69ac0ebaf1c191217c97/LICENSE); [GigaAM upstream](https://github.com/salute-developers/GigaAM/blob/main/LICENSE) carries MIT. | `giga-LICENSE.txt`, NOTICE, manifest and per-file provenance |
| Silero VAD: silero_vad.onnx | [Official MIT license](https://github.com/snakers4/silero-vad/blob/master/LICENSE). Exact local binary is identified by manifest SHA-256; the short filename alone does not establish its training revision. | `vad-LICENSE.txt` |
| Pyannote segmentation-3.0: segmentation.onnx | [Official model card](https://huggingface.co/pyannote/segmentation-3.0) specifies MIT. The retained sherpa conversion license names Copyright (c) 2022 CNRS. | `pyannote-LICENSE.txt` |
| 3D-Speaker ERes2Net base: embedding.onnx | Apache-2.0. [Project license](https://github.com/modelscope/3D-Speaker/blob/main/LICENSE), retained exact model card and [maintainer's weight-specific clarification](https://github.com/modelscope/3D-Speaker/issues/268). | `3d-LICENSE.txt`, `3d-weights-modelcard.md`, explicit provenance qualification |

The current machine-readable mapping is [app/src/main/assets/licenses/model-license-provenance.json](../app/src/main/assets/licenses/model-license-provenance.json). `docs/licenses/model-license-provenance.json` remains the historical audit inventory; it is not the V1.5 packaging input.

GigaAM v3 source repository revision is `a6039be7cee829a9044a69ac0ebaf1c191217c97`. Each of its four model URLs resolves that exact revision. The included license has SHA-256 `f00de6715714c7a63d08639cdbfaa40224eefc407302614bd19f1a8b98c875aa`, 1,070 bytes. Source files are copied without modification; the pack and installer verify their manifest sizes and SHA-256. The current ASR choice follows separate measured quality/runtime review; a license inventory does not establish model quality.

## Provenance limits and access conditions

The Pyannote model card describes a gated original checkpoint and separately states MIT. REPLIKA uses the already obtained sherpa ONNX conversion and does not request or bypass access to that checkpoint. The APK adds no user token or runtime account for this model. This is a distinction between documented access conditions and the retained weight-license record.

The unchanged embedding hash is `1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b`. Its ONNX metadata identifies ModelScope's `iic/speech_eres2net_base_sv_zh-cn_3dspeaker_16k`. The retained card and collaborator clarification support Apache-2.0 for those pretrained checkpoint weights and conversion/public deployment. The collaborator recommends an official conversion tool; they do not certify the exact lineage of this particular ONNX hash. That remaining uncertainty has not been erased by the UI or ASR update. No embedding re-export or diarization-quality fix is claimed.

## Runtime and other notices

Current packaged native libraries are sherpa-onnx v2.0.1 JNI (Apache-2.0) and ONNX Runtime v1.28.2 (MIT plus its unchanged third-party notices). The ORT dependency is pinned in [sherpa's Android aarch64 configuration](https://github.com/k2-fsa/sherpa-onnx/blob/v2.0.1/cmake/onnxruntime-android-aarch64.cmake). `tools/native-lock.json` now retains the sherpa Android archive and build-tool integrity records; it has no Whisper source tar entry. The sherpa archive SHA-256 is `39003753ec293425ed56723ea9b972b98841a490af3311670c3060548d654330`, 45,300,379 bytes. The bootstrap no longer downloads or builds whisper.cpp.

The application retains upstream notices for declared native dependencies: kaldi-native-fbank, kaldi-decoder, kaldifst/OpenFst, simple-sentencepiece and its Darts-clone, utf8proc, hclust-cpp, KISS FFT and nlohmann/json. The current `assets/licenses/license-sources.json` records retrieved additional notice URLs/hashes. It is not a complete symbol-level inventory. Broad ORT third-party notices remain unchanged; their inclusion does not claim that every optional upstream execution provider is shipped.

AndroidX/Compose/Room/Media3/WorkManager, Kotlin/coroutines and Commons Compress retain Apache-2.0 notices, including Commons Compress's NOTICE. The UI font's `Onest-OFL.txt` is included. The pass does not claim an exhaustive transitive-dependency or training-data audit.

## Whisper retirement and historical records

The product removes the custom `WhisperEngine`, JNI bridge/CMake build, custom `libreplika-whisper.so`, GGML weight and current Whisper license entries. Current packaging excludes both the old weight and custom runtime. Generic upstream sherpa JNI configuration structs remain for ABI compatibility; optional symbol/string presence in a general upstream library is not a packaged Whisper model or a selectable product engine. Archived transcript attribution is retained so historical results remain honest.

The original eight-file `model-pack/replika-offline-pack.zip` and original `model-pack/giga-v2` directory are preserved outside the new APK. Original ZIP SHA-256 remains `1b547b033feb12208fe8365c4f08302457053f3e15fb31a7fe110ea5bfe47369`, matching V1.2.1 evidence. Its old notices stay with that historical distribution. New packs are built from current manifest members and `app/src/main/assets/licenses`, rather than copying old historical `docs/licenses` wholesale.

## Packaging evidence and distribution conditions

Retain MIT copyright, permission and disclaimer texts; Apache-2.0 license and applicable attribution/NOTICE material; BSD, Unicode and font notices. Preserve upstream modification notices where present. No model file is modified by REPLIKA's installer, and licenses do not grant trademark endorsement.

Current source ZIP: 278,569,170 bytes, SHA-256 `5e064a64e7a2511b5b2cc8b51989a3bafac57719a3d9bb062fb60e10d2af73c6`. Weights total 278,127,730 bytes. [Full host inventory](test-evidence/v1.5/current-model-pack-verification.json) and [historical/current pack checks](test-evidence/v1.5/media-platform-host-checks.json) verify all seven model hashes, removal of Whisper members and preservation of the historical ZIP. These are host file checks.

The integration owner runs `tools/verify_all_in_one.py` against the final APK to validate its nested pack, native libraries, ABI, alignment, required dependencies and absence of the removed custom runtime. Source inclusion and this document alone do not establish final APK packaging or Android execution. The final audit result belongs in [TEST_REPORT_V1_5.md](../TEST_REPORT_V1_5.md); physical vivo X300 microphone, arm64 performance and thermal behavior remain unverified while the device is disconnected.
