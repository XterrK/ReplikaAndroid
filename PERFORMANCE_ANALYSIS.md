# REPLIKA V1.3 — производительность

## Методика

Разделены свежий Android baseline V1.2.1, новая Android instrumentation, Linux host-проба и неподтверждённый vivo. Никакой RTF эмулятора не объявляется RTF телефона. Кэши и температура хоста не контролируются; во время части проверок на хосте работал Gradle. PSS — снимки, а не истинный непрерывный peak RAM. Замеры вложенных стадий пересекаются: их нельзя просто суммировать.

Свежий baseline запущен установленным V1.2.1 APK и существующим `PipelineTest#completeRealGigaPipeline`: `docs/test-evidence/v1.3/android-baseline-v121.log`. Вход — публичный русский WAV из прежнего набора, SHA-256 `d8aaaa18a5098d7c6de0595ae7ac1e64cacd0d4022af3595213bdaf23be77e69`, 11 290 ms. Все baseline-поля сохранены в `baseline-v121/android-pipeline-diagnostics.json`.

| Стадия V1.2.1 | ms на эмуляторе |
|---|---:|
| Проверка моделей | 411 |
| Декодирование | 2254 |
| VAD load / VAD с загрузкой | 173 / 642 |
| Диаризация load / чтение / inference | 894 / 4259 / 2012 |
| Диаризация всего | 7195 |
| ASR load / чтение / inference | 2303 / 3466 / 5010 |
| ASR stage | 10922 |
| Всего до финального Room commit | 21455 |

Старый scope VAD включал load; новый `vadMs` измеряет проход после отдельного `vadLoadMs`. Старый `asrMs` включал load; в новом load вынесен. Сравнивать эти поля без поправки нельзя. Старый scope не включал alignment и final Room отдельно.

## Изменения

1. PCM читается FileChannel блоками по 64 KiB вместо одного RandomAccessFile.readFloat на сэмпл. Сохраняются big-endian Float PCM, исходный clock и точные значения, добавлена проверка выхода за EOF. Сравнение старого/нового reader выполняется на Android с одинаковыми 320 000 сэмплами и смещением через границу блока. Порядок legacy → buffered даёт преимущество кэша новому reader; результат не считается cold-cache сравнением.
2. Один говорящий: не загружаются segmentation/embeddings, не создаётся FloatArray всей записи. GigaAM работает с ограниченными физическими срезами. Максимальная длина ASR остаётся 20 s.
3. Исключено повторное хеширование всего набора моделей только ради диагностического modelBytes. Проверка SHA перед inference и проверки установщика сохранены. В single проверяются ASR+VAD; для fixed/auto нужны также diar-модели.
4. Короткие неизвестные края диаризации объединяются с однозначным соседом до ASR. Это также уменьшает число дорогостоящих tiny-ASR вызовов. Количество вызовов и фактический текст проверяются отдельно от IO.
5. ML остаётся последовательным под mutex. Эксперимент 1/2/4 CPU threads создаёт и освобождает каждый движок последовательно; два прохода 1→2→4 и 4→2→1 сравнивают гипотезы на одном входе. В UI доступны 1 и 2; default 2 сохранён без необоснованной оптимизации под vivo.

## Новая диагностика

`ReplikaPerf` Logcat содержит только allowlisted технический JSON: случайный run ID, имя стадии, время, PSS/Java used bytes, thermal status; отдельно validated backend, threads, audio duration, mode. Не передаются названия, recordingId, пути пользовательского аудио, PCM или ASR text. Установщик логирует стадии проверки/распаковки/публикации с числом байт и временем. Его отдельные времена и ожидание gate сохраняются в private provisioning JSON.

Worker измеряет provisioning wait, native gate wait, validation, decode, metadata Room commit, VAD load/inference, diarization load/read/inference/release scope, alignment, ASR load/read/inference, thermal wait и финальный Room commit. Room diagnostics содержат гипотезы ASR только в private storage, как ранее; технические Logcat сообщения их не содержат. Финальная диагностическая запись обновляет только колонку diagnostics под native gate и не перезаписывает ручные изменения.

`totalMs` остаётся сопоставимым scope validation→ASR release, persistenceMs указан отдельно; `telemetry.elapsedMs` дополнительно охватывает ожидания и commit, но не завершающий diagnostics-only commit и close. `observedMaxPssKb` — максимум снимков на границах стадий, не peak между ними. Логи measure пишутся также при прерывании стадии.

## Thermal API

Используются `getCurrentThermalStatus()` и listener API 29+. SEVERE=3, CRITICAL=4, EMERGENCY=5, SHUTDOWN=6 блокируют следующий ML-вызов; MODERATE=2 разрешает продолжение. Для API 26–28 статус -1 означает отсутствие API, а не измеренное отсутствие нагрева. Доступна отмена во время ожидания.

Защита действует перед проверкой/декодированием, загрузкой и запуском ML и примерно раз в секунду обрабатываемого VAD-аудио. Уже выполняющийся непрерываемый JNI-вызов может закончиться после изменения статуса. Не введены forced cooldown bypass, отключение throttling или автоматические горячие повторы. Синтетический thermal override допускается тестом только на ranchu/goldfish, сбрасывается в finally; на телефоне он не запускается.

Первичный источник API: [Android PowerManager](https://developer.android.com/reference/android/os/PowerManager). Возвращаемое severity не является градусами температуры CPU и не доказывает причину конкретного OEM-состояния.

## arm64 GigaAM

Сохранён CPU provider, существующий INT8 encoder, FP decoder/joiner и все SHA. На доступном Android x86_64 сравниваются потоки, но нет измерения arm64. NNAPI/QNN, дополнительная квантизация, изменение precision, смена encoder и aggressive windowShift не включаются без сравнения качества на corpus и устройствах. Без физического vivo нельзя обещать снижение нагрева или конкретное ускорение.

Фактические новые числа и файлы evidence перечислены в [TEST_REPORT_V1_3.md](TEST_REPORT_V1_3.md).

## Итоговые свежие измерения V1.3

Финальная QA-сборка проверена на том же API35/x86_64 AVD. На 11 290 ms публичного русского WAV, automatic, 2 потока: **12809 ms** validation→ASR release против **21455 ms** старого APK. Это два наблюдения с неконтролируемыми кэшами/нагрузкой хоста, не универсальный процент ускорения.

| Стадия V1.3 | ms |
|---|---:|
| Validation / decode | 396 / 1745 |
| VAD load / проход | 93 / 501 |
| Diar load / read / inference | 1053 / 17 / 2169 |
| Diar scope | 3442 |
| Alignment | 20 |
| ASR load / read / inference | 1938 / 2 / 3832 |
| ASR scope без load | 4173 |
| Metadata Room / final Room | 23 / 25 |
| Thermal wait | 0 |

На контролируемом PCM 20 s новый Android reader дал sample-for-sample equality. Первый Debug-проход: 4547→2 ms; финальный QA-проход: 4090→2 ms (`final-results/v13-pcm-read.json`). Это подтверждает чтение без потерь значений, не отсутствие ASR-ошибок слов.

Финальный single Worker: **247.589 s** аудио, **55.341 s** обработки (RTF **0.224**), 42 сегмента, участник 0, diarization load/inference 0. Максимум снимков PSS 589830 KiB, финальный PSS 184630 KiB; это не непрерывный peak. Первый Debug-проход того же сценария занял 79.346 s, что отдельно показывает вариативность среды. Ни один результат не является замером исходного монолога vivo.

Отдельный native automatic probe на повторённом decoded waveform 247.590 s: load 440 ms, inference 77531 ms, 1 участник / 42 turns. Это отдельная стадия, **не измерение полного automatic Worker**, и её время нельзя просто сложить с single Worker как будто выполнен один общий прогон.

| CPU threads | Первый inference, ms | Второй проход, ms | Hypotheses |
|---|---:|---:|---|
| 1 | 2402 | 2412 | совпали на этом fixture |
| 2 | 2128 | 2158 | совпали на этом fixture |
| 4 | 4585 | 4393 | совпали на этом fixture |

Два потока оказались быстрее 1/4 на этом двухъядерном AVD. Это не основание выбирать число потоков vivo; default 2 сохранён, профиль 1 доступен для контролируемого сравнения на телефоне. Пониженный thermal/energy от профиля 1 здесь не измерен.

Финальный Whisper полный pipeline на том же WAV выполнился за 41405 ms, ASR inference 37236 ms. Backend сохранён и фактически исполнялся; по одной записи нельзя объявлять его глобально непригодным. Fresh bundle readiness: 551 ms, 8 validSkipped, 0 extracted; стадии CHECKING 517 ms, COMPLETE 4 ms. Чистая распаковка V1.3 не измерялась.

Проверка 141 доступной финальной записи `ReplikaPerf` / 6 run IDs обнаружила только разрешённые поля. Первоначальный Debug log отдельно: 106 / 2, также без нарушений. Это проверка именно нашего технического logger, не аудит всех OEM/native журналов. Финальный thermal service: status 0, override false.
