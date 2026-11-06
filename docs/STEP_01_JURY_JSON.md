# Пункт 1 — JSON жюри и режим говорящих

Реализация: ветка `hack/task-01-jury-json`, основание `3aba648` (сохранённая V1.6). ML-конвейер, модели, VAD, quiet gain и схема Room не менялись.

## Поведение

«JSON» с главной или из стенограммы экспортирует только:

```json
{"transcript":[{"speaker_id":"speaker_1","start_ms":1250,"end_ms":4380,"text":"Добрый день!"}]}
```

Это пример контракта, не результат модельного прогона. Текст сохраняется буквально, включая регистр и пунктуацию. Пустые тексты исключаются. Реплики сортируются по началу/концу; идентификаторы — 1-based по первому появлению после назначения неизвестных. Неизвестный получает ближайшего по времени известного участника; при равенстве выбирается более ранний интервал. Без известных участников используется один условный speaker_1. Эти назначения не записываются в Room и не означают исправления диаризации.

Файл `replika-<id>.json` записывается явно в UTF-8 без BOM и передаётся как application/json. «Диагностический JSON» сохраняет прежнюю схему, исходные speakerId, имена, правки, warnings и diagnostics; путь `replika-<id>.diagnostic.json`, тот же MIME. TXT/SRT сохраняют прежнее поведение. Кодирование выполняется на Dispatchers.Default после транзакционного чтения сохранённых данных.

Новые импортированные и записанные файлы уже имели expectedSpeakers=-1. Automatic остаётся default; single и fixed доступны, ранее выбранные значения записи сохраняются. Миграции БД и замены модели нет.

## Проверки

9 новых JVM-сценариев: строгие ключи, порядок/нумерация, nearest-interval assignment и unknown до первого известного, равные расстояния/overlap, полностью unknown и пустой ввод, пустые строки, Unicode/кавычки/переносы/BOM, Long timestamps, отклонение некорректных интервалов. Legacy Exporter.json тесты сохранены. Android assertions и collector переведены на нужный формат; добавлена проверка default automatic и ручного выбора.

**Итог:** 89 JVM / 0 failures/errors/skips; All-in-One, debug и Android test APK собраны; статическая проверка arm64 APK PASS. Два native UI-теста прошли на отдельном API35/x86_64 AOSP AVD (20.036 s): оба формата экспортированы через Home UI, strict keys/текст/время/ID проверены, jury-файл не перезаписан, default automatic и manual modes работают.

Фактические UI JSON, scope, среда, XML и логи — в [artifacts/test-results/step-01](../artifacts/test-results/step-01). Это controlled UI fixture без нового inference, не оценка ASR. Первоначальный compile-failure теста из-за keySet() исправлен; failed log сохранён.

APK: `release/REPLIKA-Hack-Step01-AllInOne-arm64.apk`; SHA256 `cc71c0a811d1d35efdc4186638898234a21171e21bebb1d8df75e67a454c53e5`. Старый fallback V1.6 не изменён. ML-код и manifest совпадают со снимком V1.6. ARM/16KiB runtime, физический микрофон и качество моделей не проверялись этим этапом. Evaluation baseline с независимыми эталонами — отдельный пункт 2.
