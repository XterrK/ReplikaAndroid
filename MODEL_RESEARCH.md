# Модели и подтверждённая интеграция

Исследование выполнено 28.10.2026 по официальным исходникам. Выбран sherpa-onnx **v2.0.1**: Kotlin API и Android JNI взяты из одной версии. Kotlin bindings находятся в `app/src/main/java/com/k2fsa/sherpa/onnx`; runtime для arm64/x86_64 устанавливается `tools/prepare_runtime.py`.

| Назначение | Выбранные веса | Лицензия | Основание совместимости |
|---|---|---|---|
| Основной ASR | sherpa-onnx-nemo-transducer-giga-am-v2-russian-2025-04-19: encoder.int8.onnx, decoder.onnx, joiner.onnx, tokens.txt | MIT | Официальный `getOfflineModelConfig(28)` в v2.0.1, modelType=nemo_transducer |
| Segmentation | sherpa-onnx-pyannote-segmentation-3-0 / model.onnx | MIT, copyright CNRS | Официальный Android SpeakerDiarizationObject; LICENSE внутри conversion archive |
| Embeddings | 3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx | Apache-2.0 | Точная модель из официального Android примера; лицензия 3D-Speaker |
| VAD | silero_vad.onnx из asr-models | MIT | Официальный Kotlin Vad.kt; окно 512, 16 kHz |
| Альтернативный ASR | ggml-tiny.bin, multilingual | MIT | whisper.cpp v1.7.6, собственный JNI над официальным whisper.h; CPU, два потока, язык ru |

Точные размеры и SHA-256 находятся в [models-lock.json](app/src/main/assets/models-lock.json). Хеши моделей sherpa измерены после загрузки release assets, а не выданы за подписанные производителем значения. Для Whisper model card публикует SHA-1; локальный SHA-256 дополнительно фиксирует точный бинарный файл. Неполные/изменённые файлы блокируют inference.

## Источники

- [sherpa-onnx v2.0.1](https://github.com/k2-fsa/sherpa-onnx/tree/v2.0.1), Apache-2.0.
- [Официальный Kotlin OfflineRecognizer](https://github.com/k2-fsa/sherpa-onnx/blob/v2.0.1/sherpa-onnx/kotlin-api/OfflineRecognizer.kt).
- [Официальный Android пример диаризации](https://github.com/k2-fsa/sherpa-onnx/tree/v2.0.1/android/SherpaOnnxSpeakerDiarization).
- [Документация диаризации](https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/index.html).
- [GigaAM, исходный проект и лицензия](https://github.com/salute-developers/GigaAM).
- [Pyannote segmentation-3.0 model card](https://huggingface.co/pyannote/segmentation-3.0): MIT; оригинальный Hugging Face checkpoint gated. Приложение использует опубликованную sherpa ONNX-конверсию с включённой лицензией, не обращается к gated checkpoint.
- [3D-Speaker](https://github.com/modelscope/3D-Speaker), Apache-2.0.
- [Silero VAD](https://github.com/snakers4/silero-vad), MIT.
- [whisper.cpp v1.7.6](https://github.com/ggml-org/whisper.cpp/tree/v1.7.6), MIT.
- [Официальные GGML conversions](https://huggingface.co/ggerganov/whisper.cpp), MIT.

Файлы лицензий сохранены в `docs/licenses`. AndroidX, Room, Compose, Media3 и WorkManager — Apache-2.0; Kotlin и coroutines — Apache-2.0; ONNX Runtime — MIT; Commons Compress — Apache-2.0. При внешнем распространении сборки необходимо включать соответствующие notices, включая транзитивные native-компоненты.

## Ограничения

GigaAM v2 — русский акустический ASR; автоматическая пунктуация не добавлена. Совместимость произвольных ONNX не предполагается. INT8 применяется только к официальному encoder. Segmentation и embedding оставлены в конфигурации официального Android примера. Embedding обучался преимущественно на китайском корпусе; перенос на русскую речь требует измерения DER на собственном корпусе.

Whisper tiny использует float GGML-веса, а не INT8; это маленькая multilingual модель, которая может уступать GigaAM на русской речи. Её результат никогда не выдаётся за результат GigaAM. Переключение выполняется явно до обработки.

Автоматическое число участников использует clustering numClusters=-1, threshold=0.5; пользователь может задать 1–20. Разделения одновременно произнесённых слов нет. Модель может не вернуть все пересечения. Реальное качество без размеченного корпуса не заявляется.

Локальный ZIP включает модели, а APK — только код и native runtime. Огромные веса не увеличивают APK. Для установки через интернет требуется место на архив и распакованные файлы. Offline pack удобнее подготовить до хакатона и проверить в авиарежиме на конкретном телефоне.
