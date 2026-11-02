# All-in-One model and runtime redistribution audit

Date: 2026-11-02. Scope: existing local model-pack/replika-offline-pack.zip, assets/models-lock.json, native runtime and notices for the V1.2.1 APK. No model weights were downloaded, converted or changed during this audit. This is a source and notice audit, not a legal opinion or a certification of ownership of the training data.

**WORKING — model license basis.** The five selected model families have official permissive weight-license evidence allowing copying and distribution subject to their notices. No model-license prohibition on bundling these files in an offline APK was found. **PARTIAL — full provenance / supply chain.** Exact file hashes are local integrity records, not publisher signatures. In particular, the 3D-Speaker conversion input revision and a bit-for-bit export recipe were not reconstructed. No claim of an exhaustive SBOM or independent legal clearance is made.

| Model actually selected | Weight license and primary evidence | APK notices |
|---|---|---|
| GigaAM v2, sherpa ONNX INT8 release 2025-04-19; encoder, decoder, joiner, tokens | MIT, GigaChat Team. [Official repository/license](https://github.com/salute-developers/GigaAM/blob/main/LICENSE); [authors' paper](https://arxiv.org/abs/2506.01192) identifies model and code release under MIT. | giga-LICENSE.txt; exact source URLs, hashes and sizes in models-lock.json |
| Silero VAD, existing sherpa silero_vad.onnx | MIT, Silero Team. [Official license](https://github.com/snakers4/silero-vad/blob/master/LICENSE). Exact training/checkpoint version is not encoded in the local filename; identify this binary by SHA-256. | vad-LICENSE.txt |
| pyannote segmentation-3.0, existing sherpa ONNX conversion | MIT. [Official weight model card](https://huggingface.co/pyannote/segmentation-3.0) states MIT; the local sherpa conversion includes Copyright (c) 2022 CNRS. | pyannote-LICENSE.txt |
| 3D-Speaker ERes2Net base, iic/speech_eres2net_base_sv_zh-cn_3dspeaker_16k | Apache-2.0. [Official exact model card](https://modelscope.cn/models/iic/speech_eres2net_base_sv_zh-cn_3dspeaker_16k/summary), [project license](https://github.com/modelscope/3D-Speaker/blob/main/LICENSE), [collaborator's weight-specific clarification](https://github.com/modelscope/3D-Speaker/issues/268). | 3d-LICENSE.txt; 3d-weights-modelcard.md; provenance caveat below |
| Whisper tiny multilingual ggml-tiny.bin | MIT, OpenAI weights, independently of the runtime license. [Official README/license](https://github.com/openai/whisper#license); [GGML model card](https://huggingface.co/ggerganov/whisper.cpp/blob/main/README.md) identifies converted OpenAI weights. | NEW whisper-model-LICENSE.txt (OpenAI); retained whisper-LICENSE.txt (ggml authors) |

The machine-readable model-license-provenance.json in docs/licenses and APK assets/licenses maps every exact manifest member to its license and upstream source. It does not replace the signed-off manifest or rerun model validation.

## Access conditions and provenance limits

The original pyannote Hugging Face checkpoint requires accepting access conditions and sharing contact information. The same primary model card specifies MIT and describes the gate as access/user information collection. This audit distinguishes that gate from the weight copyright license: it does not infer a noncommercial restriction or a requirement that recipients of an already published sherpa ONNX file log in at runtime. REPLIKA uses the existing local sherpa conversion. It neither downloads nor bypasses the gated checkpoint.

The exact existing embedding ONNX SHA-256 is 1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b. Its embedded metadata contains framework=3d-speaker, the official ModelScope model URL, and a comment identifying the exact model family above. The retained model card specifies Apache-2.0 and model_revision v1.0.1. In upstream issue #268, collaborator yfchenlucky confirms Apache-2.0 for that checkpoint's pretrained weights and permits conversion and public/commercial deployment. The issue mentions the same ONNX hash, but the collaborator does **not** assert the exact checkpoint-to-ONNX byte lineage. We retain that qualification and do not treat availability of an ONNX download as its license. No model switch or re-export was performed.

## Native runtime and application dependencies

The application uses sherpa-onnx v2.0.1 (Apache-2.0) and whisper.cpp v1.7.6 / ggml (MIT). The local arm64 libonnxruntime.so contains version string 1.28.2; this matches [sherpa's pinned Android aarch64 dependency](https://github.com/k2-fsa/sherpa-onnx/blob/v2.0.1/cmake/onnxruntime-android-aarch64.cmake). ORT is MIT and carries additional [v1.28.2 ThirdPartyNotices](https://github.com/microsoft/onnxruntime/blob/v1.28.2/ThirdPartyNotices.txt), now retained unchanged in APK assets and docs.

Additional small upstream notices were retrieved for native dependencies selected in [sherpa v2.0.1 CMake](https://github.com/k2-fsa/sherpa-onnx/blob/v2.0.1/CMakeLists.txt): kaldi-native-fbank, kaldi-decoder, kaldifst/OpenFst, simple-sentencepiece, utf8proc, hclust-cpp, KISS FFT and nlohmann/json. The source URL, version/tag, retrieved SHA-256 and length for these notice files are in license-sources.json. This records declared dependencies and preserves their texts; it is not a symbol-level inventory of every optional feature or a reproducible native build. In particular, broad ORT notices are retained as upstream provided, rather than claiming that all of its optional execution providers ship on Android.

Sherpa v2.0.0 removed in-tree espeak-ng and piper-phonemize ([upstream change](https://github.com/k2-fsa/sherpa-onnx/pull/4055)); the selected v2.0.1 source no longer links those components. No conclusion about older sherpa releases is transferred to this binary.

AndroidX, Compose, Room, Media3, WorkManager, Kotlin, coroutines and Commons Compress use Apache-2.0. Commons Compress's v1.27.1 NOTICE is included. This pass does not claim a full Gradle/transitive dependency legal review; the existing dependency graph was not changed for packaging.

## Redistribution obligations and changes made

- Retain MIT authorship, permission and disclaimer text for all MIT weights and runtimes. A runtime license alone is insufficient attribution for independently licensed pretrained weights.
- Retain Apache-2.0 text and relevant upstream copyright/NOTICE material, including notices for distributed object forms. Preserve modification notices where present; REPLIKA has not modified model files. No trademark endorsement is granted.
- Retain BSD / Unicode notices for the native dependencies carrying those conditions.
- Preserve the original ZIP. Its old whisper-LICENSE.txt remains the ggml runtime text; the APK now also contains the distinct OpenAI weight license outside that ZIP. This avoids silently changing a previously validated pack.

Changes in this pass: added the missing OpenAI weight MIT text; added pinned ORT third-party notices and declared native dependency notices; retained the exact 3D model card in APK assets; updated NOTICE and added model provenance metadata. No APK was published or pushed. The integration owner must verify that these assets are present in the final built APK; source inclusion alone does not prove final packaging or model operation.
