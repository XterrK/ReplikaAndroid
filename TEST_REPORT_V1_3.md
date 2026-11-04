# REPLIKA V1.3 — отчёт проверки

Дата: 4 ноября 2026. Исходный commit `2f84a633f5c3b51accd99ac7510db70570f61dde`. Итоговый статус — **PARTIAL / кандидат для физической приёмки**, а не закрытие всех дефектов vivo. Физического телефона через ADB нет, оригинальная запись пользователя отсутствует. Публикация и git push не выполнялись.

## Подтверждённая область исправлений

| Изменение | Основание | Ограничение |
|---|---|---|
| Один говорящий пропускает тяжёлую диаризацию | Отдельная ветка Worker, нулевые diarization timings, Android Worker 247.589 s / 42 физических фрагмента, ID только 0 | Контролируемый повтор публичного примера, не запись пользователя |
| Блочное чтение PCM | Android sample-for-sample equality 320000 значений; чтение через границу блока и EOF | Порядок чтения legacy→new, кэши не контролируются |
| Потеря pre-roll на коротких diarization margins | Новые planner-инварианты, реальный публичный prefix-тест GigaAM | Жёсткие 20 s cuts и настоящие пять границ vivo не закрыты |
| Паузы не создают отдельные логические абзацы одного голоса в пределах политики | JVM source-ID/clock/unknown/overlap tests и UI-группа | Порог чтения 1200 ms — эвристика, не понимание законченной мысли |
| Диалог/Чтение/копирование/правки | Android UI с контролируемыми данными, сохранение после recreate, одна Room-модель | Synthetic UI-текст не считается результатом ASR |
| Thermal wait, resume и отмена | Реальный PowerManager эмулятора с emulator-only override SEVERE/CRITICAL и reset в finally | OEM vivo не проверен; уже начатый JNI не прерывается мгновенно |
| Обновление без изменения существующих файлов | install -r code4→5, 334 файла DB/files побайтово совпали | Эмулятор x86_64; обновление arm64 на телефоне не выполнено |

## Что не исправлено / не доказано

- Автоматический estimator числа участников не заменён. Проблема 11 участников не воспроизведена и не закрыта. Китайский four-speaker пример по-прежнему показывает overclustering; повышение порога не принято как глобальный fix.
- Нет гарантии отсутствия потерянных/повторённых слов на произвольной записи. Word alignment не реализован; lexical dedup без аудиодоказательств не применяется. Ошибки на жёстких 20 s границах возможны.
- Нет arm64 RTF, непрерывного peak RAM, температуры/энергопотребления vivo, физического microphone QA, runtime 16 KiB/API36 QA. Никакой AVD или WSL результат их не заменяет.
- Нет независимого размеченного natural Russian multi-speaker corpus; WER/CER/DER без эталона не объявляются.
- Подготовка моделей после чистой установки на V1.3 отдельно не повторялась с очисткой данных. Прежние V1.2.1 evidence сохранены; V1.3 проверяет восстановление в isolated installer fixtures и reuse/hash готовых моделей.

## Сохранность

До изменений рабочее дерево было чистым, HEAD совпадал с переданным commit. Старый arm64 APK не перезаписан: `release/REPLIKA-V1.2.1-AllInOne-arm64.apk`, SHA-256 `72fb824fc4356f72b22a57a1f7ac8a3221c29361d7feec35c0d1710cf2554aaa`.

Приватные копии находятся вне репозитория: `F:\ReplikaToolchain\v1.3-preservation`. Там Git bundle, дополнительная копия старого APK, полный tar базы и files эмулятора до тестовых изменений и snapshot непосредственно перед обновлением. Эти данные не включаются в публичный review ZIP. Room schema остаётся version 1; destructive migration, clear data и uninstall обычного приложения не использованы.

## Выполненные проверки

JVM: **38 passed**, четыре test suites: прежние DomainTest 18, PresentationTest 4, ProductErrorsTest 3 и новые RecoveryV13Test 13. XML сохранены в `docs/test-evidence/v1.3/jvm`. Первые candidate-сборки выявили конфликт импорта SystemClock, затем overflow в interval splitting; оба исправлены, последующие JVM-прогоны прошли. Неудачные исходные логи сохранены отдельно, не считаются passing evidence.

Первый Android Debug-прогон: **5 passed**, `RecoveryV13InstrumentedTest` (4) и `TranscriptModesV13Test` (1). Лог `android-new-debug.log`; собственные новые результаты в `initial-debug/`. В эту папку не копировались старые ML outputs как результаты свежего теста. Fresh baseline V1.2.1 — ещё один отдельно обозначенный успешный Worker-тест, не V1.3 acceptance.

Финальный All-in-One QA: **59 passed** в семи упорядоченных группах, затем отдельный новый long automatic JNI тест — **1 passed**, итого **60 различных Android методов, 0 failures/skips**. Дополнительно оба существующих complete Worker метода вызываются внутри bundle acceptance wrapper. Поимённый индекс: `docs/test-evidence/v1.3/test-summary.json`; сырые instrumentation status коды: `final-qa/*.log`. Это реальные запуски API35/x86_64 с прежними weights, не замена inference mock-результатом.

| Группа финального QA | Passed |
|---|---:|
| Bundled acceptance, оба ASR Worker | 2 |
| Model pack, storage/audio, Room edits, recovery/cancel, installer guards, diarization, Whisper direct | 36 |
| ASR/VAD/clustering comparisons | 3 |
| Реальная короткая речь / warning pipeline | 1 |
| Новые IO/threads/thermal/long single/UI modes | 5 |
| Navigation, All-in-One UI, product UX, review/virtual recording | 11 |
| Ручные исправления после отдельного force-stop/relaunch | 1 |
| Дополнительная automatic диаризация long mono | 1 |

38 JVM плюс 60 final Android — число проверенных разных методов, а не независимых аудиозаписей. Первые 5 Debug Android executions и baseline V1.2.1 считаются отдельно. Вывод продукта остаётся PARTIAL: тесты smoke/configuration не требуют от automatic ошибочного семикластерного примера искусственно проходить quality acceptance.

Скриншоты `final-results/01-dialogue-controlled.png`, `02-reading-controlled.png` просмотрены: сохраняется читаемость, один короткий логический абзац в чтении, отдельный ответ другого участника. Это явно обозначенный UI fixture; системный clipboard toast может быть виден внизу reading screenshot.

APK static: **PASS**, errors=[], arm64-only, один embedded ZIP, восемь совпавших файлов моделей, зависимости и ZIP/ELF LOAD alignment проверены. Runtime arm64/16 KiB не проверен. Отдельный QA x86_64 static также PASS. Подпись совпала со старым arm64 APK; оба сертификатных SHA совпадают в `signature-comparison.json`.

В финальных логах проверено 141 техническое событие / 6 run IDs: только allowlisted поля. После thermal override-теста `dumpsys thermalservice`: status 0, override false. Bundle readiness 551 ms, 8 validSkipped / 0 extracted; старые файлы моделей не переподготовлены.

## Воспроизведение

```bash
REPLIKA_REUSE_RAM_CACHE=1 REPLIKA_BUILD_OFFLINE=1 python3 tools/build_local.py :app:assembleDebug :app:testDebugUnitTest :app:assembleDebugAndroidTest
REPLIKA_REUSE_RAM_CACHE=1 REPLIKA_BUILD_OFFLINE=1 python3 tools/build_local.py :app:assembleAllInOne :app:assembleAllInOneQa :app:assembleAllInOneQaAndroidTest -PreplikaTestBuildType=allInOneQa -PreplikaAioQaSameId=true
# Только на подготовленном эмуляторе, после install -r app/test QA и staging прежних публичных fixtures:
ADB=/mnt/f/ReplikaToolchain/v13-adb.exe python3 tools/run_android_v13.py --output docs/test-evidence/v1.3/new-run
```

Не запускайте прежние destructive clean-launch helpers на основном приложении или на телефоне. В All-in-One QA same-ID варианте используются существующие данные основного **эмуляторного** пакета; перед повтором сначала сделайте приватный snapshot. Инструментальные UI-тесты редактируют только специальные QA-строки и сохраняют evidence; микрофонный тест использует виртуальный ввод эмулятора.

## Обновление телефона без потери записей

1. Сохраните важные экспорты и убедитесь, что телефон остыл. Не удаляйте REPLIKA и не очищайте её данные.
2. Передайте `release/REPLIKA-V1.3-AllInOne-arm64.apk`, сверьте SHA-256 и установите поверх V1.2.1. С ADB: `adb install -r REPLIKA-V1.3-AllInOne-arm64.apk`. applicationId прежний, versionCode 5; подпись проверяется относительно прежнего APK.
3. Если Android отклоняет обновление по подписи, не обходите это удалением приложения с записями: требуется APK с исходной подписью.
4. Откройте существующие записи, проверьте ручные правки, плеер и оба представления. Обновление само не пересчитывает сохранённые стенограммы и не исправляет задним числом 11 участников.
5. Для нового сравнения импортируйте копию исходного монолога, оставив старую запись; выберите GigaAM и «Один говорящий». Для известного состава — fixed; automatic пока требует проверки результата. В обычном профиле 2 потока, в умеренном 1; режим 4 доступен только диагностическому тесту.
6. Технический JSON доступен в «Модели → Диагностика → Технические данные → Поделиться JSON». Он может содержать private ASR hypotheses и название; передавайте его осознанно. Системные `ReplikaPerf` логи содержат только технические метрики.

Связанные отчёты: [физические наблюдения](REAL_DEVICE_FINDINGS.md), [производительность](PERFORMANCE_ANALYSIS.md), [диаризация](DIARIZATION_FIX_REPORT.md), [VAD](VAD_BOUNDARY_REPORT.md).

## Артефакты передачи

- All-in-One arm64: [REPLIKA-V1.3-AllInOne-arm64.apk](release/REPLIKA-V1.3-AllInOne-arm64.apk), **377500137 bytes**.
- SHA-256: `80f39d54d1d2b18e299c3820f4f21fee03aedbebd0a766bdf74cf171ff5a2fc2`; [checksum](release/REPLIKA-V1.3-AllInOne-arm64.apk.sha256).
- [HUMAN_REVIEW_V1_3.zip](review/HUMAN_REVIEW_V1_3.zip): этот APK, пять отчётов, публичные/контролируемые evidence, исходники для ревью, guide и `v1.3-delivery.json` с точным Git commit. Приватные backup/DB/audio не включаются.
- До выдачи ZIP проверяется CRC всех его файлов; упаковщик требует чистое рабочее дерево и совпадение APK SHA со статическим отчётом.
- Точный окончательный commit выдаётся вместе с архивом и записывается в его manifest после фиксации отчётов; здесь не используется самоссылочный hash будущего commit. Состояние дерева проверяется `git status --short`; push не выполняется.
