# Проверка REPLIKA V1.1 — 31.10.2026

Итог: **эмуляторная интеграция WORKING; продукт PARTIAL**. Полный русский многоголосный сценарий и физический arm64 **BLOCKED**. Доказательства V1.1 находятся в `docs/test-evidence/v1.1/`; прежние файлы и промежуточный неудачный UI-прогон сохранены отдельно.

## Среда и APK

Windows 10.0.26200.9711 + WHPX, Android Emulator 37.2.12.0, отдельный AVD Replika35v11: Android15/API35, x86_64, 2 CPU, 3072 MB, 432×936, 180 dpi, страницы 4096 bytes. Эмулятор запущен с -no-audio; физического микрофона и звукового тракта телефона нет. Build: WSL2, Microsoft JDK17.0.17, Gradle8.13, AGP8.9.2, Kotlin2.1.20, SDK35, NDK27.2.12479018, CMake3.22.1. Windows ADB на порту5038 исключает конфликт с Linux ADB. Точный fingerprint/CPU — `environment.json`.

APK 83157436 bytes, arm64-v8a + x86_64, version1.1.0/code2. SHA-256: `9728e09fe8f6b0d66b4c038f5a71752c21602db5c72e7013e3b80d0ea6668b6a`. Контрольная clean-сборка после Android тестов дала побайтово тот же APK; повторный inference того же бинарника не требовался.

## Реально выполнено

| Проверка | Результат | Доказательство |
|---|---|---|
| clean :app:assembleDebug :app:testDebugUnitTest :app:assembleDebugAndroidTest | PASS, 81 задача выполнена, 5m28s | clean-build.log |
| Все JVM tests | PASS 18, 0 failures/errors/skipped | jvm-domain-tests.xml |
| Main Android instrumentation | PASS 19, без Assume/ignore skips | android-instrumentation.txt |
| Compose ReviewScreenshotsTest | PASS 2, без пропусков | android-compose-ui.txt |
| Compose NavigationTest | PASS, включён в main19 | android-instrumentation.txt |
| Отдельный процесс после force-stop | PASS 1 | android-process-relaunch.txt, edit-persistence.json |
| Дополнительный первоначальный pack install | PASS 1; повтор метода из main19 | android-pack-install.txt |
| Offline pack + испорченный pack + incomplete weights | PASS на настоящем ZIP/manifest | ModelPackTest; все четыре группы SHA-256 |
| WAV / MP3 / M4A + stereo48→16k | PASS MediaExtractor/MediaCodec/PCM | media-formats.json, StorageAudioTest |
| Повреждённый файл и Worker | PASS: ERROR без падения, прежний edited segment сохранён | StorageAudioTest |
| Настоящие GigaAM/Silero/Pyannote/3D-Speaker | PASS русский mono полный Worker | android-transcript.json, android-pipeline-diagnostics.json |
| Настоящий Whisper tiny | PASS прямой inference и полный Worker | android-whisper*.json/txt |
| Отдельная многоголосная zh диаризация | PASS как запуск, не качество DER | android-diarization.json, ml-diarization-comparison.json |
| VAD/границы | PASS сравнительные вызовы и regression | ml-vad-comparison.json, JVM + PipelineTest |
| Duplicate processing / queued cancel / orphan recovery | PASS, прежние правки не удалены | ProcessingRecoveryTest (2 tests) |
| Editor открытие, прокрутка, IME, text/speaker/name/reviewed | PASS с сохранением, Activity recreate, export | UI2 + edit-persistence.json, реальные кадры05/09/10/11 |
| Cold UI reopening после force-stop | PASS: правки и подпись видны в fresh hierarchy | cold-ui-relaunch.json, кадр04 |
| Player segment tap / active row | PASS по состоянию Media3/Compose | UI2 |
| Player stop/seek | PASS actual adb taps: пауза у8.485s, clamp11s, назад1s | player-manual.json; физический звук N/A |
| Recording pause/resume/background | PASS только виртуальный AVD | UI2; не проверка настоящего микрофона |
| Offline execution | PASS без default network и IP route | offline-network.json: wifi=0, mobile=0, Active default network:none |
| 16KiB ZIP + ELF | PASS всех8 .so / обе ABI | apk-static-acceptance.json |

Уникальных Android test methods: **22** (19 main +2 UI +1 fresh-process); первоначальный импорт pack повторяет один из этих методов. Всего Compose tests3: Navigation1 внутри main19 и Review2. Проценты confidence не используются. Неудачные ранние попытки сборки/JVM cache и UI с ошибкой сохранения/Assume не засчитаны как PASS; финальная серия прошла без пропусков.

## ML и корректность данных

Русский mono fixture: 11290ms, официальный WAV GigaAM conversion; MP3/M4A получены из него. Отдельный zh файл: 56860ms. Хеши — fixtures.json. Аудио и модели не включены в Git/review ZIP.

На одном PCM сравнивались raw waveform, текущий VAD, pre100, post100, pre100+post100, threshold .35/minSpeech .1 и threshold .65/minSilence .4. Raw GigaAM дал «ничьих»; current/post/проверенные threshold варианты — «чьих». Pre100 восстановил слово в VAD-only и aligned output. Продукционный pre-roll100/post0 ограничен файлом, spans объединены, ASR slices не пересекаются. Полный GigaAM Worker подтвердил «ничьих», первый сегмент31–8485ms. Все slices, включая пустые, сохранены в диагностике. Это регрессия конкретного слова и согласованность гипотез, не WER и не обещание отсутствия ошибок на других границах.

Whisper Worker с тем же pre100 завершился. Четыре коротких unknown slices дали пустую строку за1–2ms, дополнительных реплик не возникло. Две длинные гипотезы сохранены как есть; качество текста не объявлено исправленным.

Automatic .5 и .65 дали одинаковые11 turns/7 ID на zh sample; fixed4 дал10 turns/4 ID. Нормализованные embeddings, cosine distance и complete linkage соответствуют upstream. При fixed k threshold не применяется. Нет независимого эталона — DER N/A; глобальный порог не меняли. Русский многоголосный E2E **не выполнен**. Протокол согласованной записи и ручной разметки — RUSSIAN_DIALOGUE_PROTOCOL.md.

Сравнение моделей измеряет одинаковый full-waveform FloatArray отдельно от Worker: GigaAM load1054ms, inference1953/2032/2004ms; Whisper load103ms, inference14691/15085/14063ms. Первый inference — new engine с неконтролируемым filesystem cache, два следующих warm. Это не reboot-cold. Core Worker time до diagnostics/Room commit: GigaAM16752ms/RTF1.484, Whisper48707ms/RTF4.314. Полное wall time с UI/export отдельно не измерено. Подробности и PSS — BENCHMARKS и ML_TEST_SUMMARY. WER/CER/DER **N/A**. Память измерена snapshots, не peak.

## Ограничения и открытые дефекты

Физический arm64 не подключён; API36 и 16KiB runtime отсутствуют. Статическое выравнивание ZIP/ELF не закрывает runtime/symbol/SoC compatibility. Реальные микрофон, динамик, нагрев, ENOSPC, прерывание загрузки, внешние Share receivers и SAF providers телефона не проверены. Immediate native abort не реализован; queued cancellation и recovery не доказывают прерывание уже выполняющегося JNI.

Найдены и оставлены для независимого UX-ревью: краткий ложный empty-state до загрузки Room Flow (кадр14), широкие круглые caps индикатора при первых отсчётах записи, размер Silero «0 МБ», громоздкая JSON-диагностика. Native diarization требует весь PCM; длинные записи и peak RAM не валидированы. Поперечные слова на смене участника, overlaps и 20s разрезах остаются риском.

Полный перечень — docs/human-review/v1.1/ISSUES_V1_1.md. Физическое подключение — docs/test-evidence/v1.1/PHYSICAL_DEVICE.md. Новые скриншоты — docs/human-review/v1.1, их происхождение — SCREENSHOTS.md. Модельные raw exports сохранены **до** QA-правок; новый speaker ID в исправленном mono Workspace — ручная проверка редактора, не доказательство нескольких настоящих голосов.

## Дополнительный живой SAF-сценарий

После основной серии выполнены реальные действия через системный AOSP Downloads picker. WAV импортирован, выбран режим «Указано пользователем» и число1, нажат запуск, получен настоящий GigaAM Worker/Room/UI/export. `saf-wav-transcript.json` содержит expectedSpeakers=1, clusteringMode=fixed и настоящий текст «ничьих…». MP3 и M4A прошли тот же путь с automatic mode: `saf-mp3-transcript.json`, `saf-m4a-transcript.json`. Это конверсии одной mono записи, не три независимых качественных примера.

Повреждённый 35-byte MP3 fixture импортирован через picker. Media3 показал обработанный диалог «Воспроизведение: Source error» без падения; после закрытия диалога Worker завершился фазой «Обработка прервана». Доказательство: saf-corrupt-ui.json, кадры17 и19. Английская общая формулировка ошибки оставлена как UX-замечание. Первые короткие polling-попытки adb не дождались окончания обработки/перекрывающего диалога и не засчитаны как успешные тесты; итог проверен по реальному UI и экспорту.

Эти ручные проверки дополняют22 уникальных instrumentation methods, не увеличивая их счётчик. APK не менялся. Проверенный коммит реализации: `d0ba1eb06db3d07e808237d33859b5e4e6bd35d7`.
