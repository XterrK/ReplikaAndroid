# Приватные локальные smoke fixtures

Копии существовавших тестовых файлов из `F:\ReplikaToolchain`, перенесены внутрь рабочей папки для `tools/stage_android.py`.

- Russian WAV: `test_wavs/example.wav` из `sherpa-onnx-nemo-transducer-giga-am-v2-russian-2025-04-19.tar.bz2`; MP3/M4A — ранее подготовленные перекодировки этого WAV.
- `four-speakers-zh.wav`: официальный smoke sample из Sherpa speaker-segmentation-models, `0-four-speakers-zh.wav`.

Оригинальные provenance/ограничения описаны в `../corpus/README.md`. Это существующие локальные тестовые входы, они не включены в Git, APK или публичную поставку. Не являются новым русским многоголосным benchmark V1.6. Для новых UI-тестов V1.6 используется собственная запись виртуального рекордера; эти файлы нужны прежним regression-тестам.
