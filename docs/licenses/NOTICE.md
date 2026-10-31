# Third-party notices

REPLIKA bundles sherpa-onnx v2.0.1 (Apache-2.0), ONNX Runtime (MIT), whisper.cpp v1.7.6 / ggml (MIT), and AndroidX components (Apache-2.0). Source notices are retained in vendor Kotlin files; principal license texts are in this directory. The native runtime is obtained without modification from the official sherpa Android release.

Model packs carry independently licensed weights. GigaAM v2, Silero VAD, Pyannote segmentation-3.0 and Whisper GGML weights are MIT; 3D-Speaker is Apache-2.0. Model identity is recorded by exact file SHA-256 in the built-in manifest. See MODEL_RESEARCH.md for upstream references and limitations. Licenses are not inferred merely from the runtime library license.

Android SDK, emulator, JDK and NDK are build/test tools outside this repository, not model weights and not app source. Their upstream licenses continue to apply.
