# Историческое доказательство Kotlin parity

Это сохранённый результат изолированной проверки внешнего черновика до подключения к
Android-проекту, а не самостоятельный каталог сборки. Проверено 157 differential cases;
точная область и входные SHA находятся в `differential-report.json`.

Текущий интегрированный helper: `app/src/main/java/ru/replika/domain/WindowSpeakerRefiner.kt`,
SHA256 `69498c73d0489a8381ef2a00dd53afde6c3c4fb02e54a348d63beae89c3e4d67`.
Интегрированный JVM test: `app/src/test/java/ru/replika/domain/WindowSpeakerRefinerTest.kt`.
Текущую компиляцию и JVM-тесты воспроизводит из корня проекта:

```sh
python3 tools/build_portable.py :app:testDebugUnitTest
```

Сохранённые standalone logs/скрипты относятся к первоначальному внешнему staging:
их локальные compiler/cache/draft пути — сведения об исполнении. Они не запускаются
из этого каталога без восстановления того staging и могут перезаписать старые proofs.
Для новых прогонов нужно отдельное выходное место; сохранённые результаты не менять.
Python-алгоритмы и все исходные реальные model outputs находятся в репозитории.
Изолированная parity не доказывает Android inference или качество голоса/таймкодов.
