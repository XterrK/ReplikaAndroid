# REPLIKA V1.5 — отчёт проверки

Дата обновления: 6 ноября 2026. **Source11: 80/80 JVM, 97/97 уникальных Android-проверок на API 35 и 33/33 на API 28 — PASS. Финальная heavy ML-фаза завершена.** Два первоначальных таймаута сохранены в истории; изолированные повторы прошли без изменений приложения. Видео, UI-доказательства, эмуляторные измерения и повторная QA галереи source11 завершены; их ограничения приведены ниже. Семь аудиофайлов внутри одного JUnit-теста не считаются семью Android-тестами.

Физический vivo X300 сейчас недоступен. Пользователь подтвердил историческую работу V1.3 на нём и примерно 30 секунд для своей конкретной четырёхминутной записи в соответствующем режиме GigaAM. Это свидетельство о V1.3, а не измерение V1.5.

## Сборка, артефакт и границы проверки

| Объект | Подтверждённый текущий результат |
|---|---|
| Production source11 | **BUILD SUCCESSFUL**, 5 минут 1 секунда. [Журнал](docs/human-review/v1.5/evidence/build11-final.log) |
| JVM source11 | **80/80 PASS**, 0 failures/errors/skipped: прежние 65 + 8 detector-rescue policy + 7 frame-cadence. [XML](docs/human-review/v1.5/evidence/jvm-build11/) |
| Основной API 35 / x86_64 | **97 уникальных PASS, 0 FAIL, 0 SKIP**, 112 test invocations с повторами. [Канонический case summary](docs/human-review/v1.5/evidence/android-tests-build11/case-summary.json) |
| Настоящий RU studio whisper через Android Worker | **1/1 JUnit PASS, все 7 аудиофайлов**, 73.92 с внешнего запуска; WER **9/84 = 10.714%**, CER **39/500 = 7.8%**. [Acceptance](docs/human-review/v1.5/evidence/whisper-native11/acceptance.json), [лог](docs/human-review/v1.5/evidence/android-tests-build11/WhisperPipelineV15Test-20261106T023158.log) |
| Вторичный API 28 / x86_64, исходный native-профиль | **33/33 PASS:** 32 UI/core и 1 настоящий Worker-тест на всех 7 whisper-файлах. [Core/UI](docs/human-review/v1.5/evidence/api28/build11/ui32-summary.json), [whisper](docs/human-review/v1.5/evidence/api28/build11/whisper1-summary.json) |
| Arm64 All-in-One APK | **304 997 087 байт**, SHA-256 `ea5495998e97339194932b8cfa75aaf66823c7dd3a10e821bfda2e3234beaffc`. [APK](release/REPLIKA-V1.5-AllInOne-arm64.apk), [checksum](release/REPLIKA-V1.5-AllInOne-arm64.apk.sha256) |
| Статический аудит / подпись | **PASS**, ABI только arm64-v8a, прежний сертификат; [аудит](docs/human-review/v1.5/evidence/arm64-static.json), [apksigner](docs/human-review/v1.5/evidence/apksigner-arm64.txt) |
| Физический микрофон, arm64 runtime, батарея/нагрев/FPS на vivo | **Не проверены:** телефон не подключён |

Конфигурация: versionName 1.5, versionCode 7, minSdk 26, targetSdk 35; GigaAM v3 E2E RNNT INT8, sherpa-onnx 2.0.1, Silero VAD и прежние модели диаризации. Automatic diarization не объявлена исправленной. Эмуляторы исполняют QA-вариант x86_64 с тем же кодом продукта; статический аудит arm64 не заменяет выполнение на физическом arm64.

Источник сборки: [build11-source-sha256.json](docs/human-review/v1.5/evidence/build11-source-sha256.json); SHA-256 самого манифеста — `2bc16f4baddb30c63e96bafa8ae521bb92fac03db300afc8ae9e312274d5fc8c`.

История source10 сохранена отдельно: её первая packaging-попытка дала Failed to read chunk; очищен только сгенерированный каталог arm64 packaging, повтор завершился успешно. Это не отказ source11. [Исходный лог](docs/human-review/v1.5/evidence/build10-incremental-package-failure.log), [успешный повтор](docs/human-review/v1.5/evidence/build10-final.log).

## Android source11: окончательные regressions

[Case summary](docs/human-review/v1.5/evidence/android-tests-build11/case-summary.json) считает каждый class#method один раз по последнему результату: **97 PASS / 0 FAIL / 0 SKIP**, всего 112 invocations, незавершённых логов нет. Compact/normal/reduced-motion и другие повторы не увеличивают число уникальных методов.

| Область | Подтверждённый результат | Доказательство |
|---|---|---|
| Импорт медиа и восстановление незавершённого импорта | **15/15 + 8/8 PASS**: AAC/edit-list/priming, timestamps, fallback, URI, tracks, место, отмена, journal/Room/gate | [Media](docs/human-review/v1.5/evidence/android-tests-build11/MediaImportV15Test-20261106T023409.log), [journal](docs/human-review/v1.5/evidence/android-tests-build11/ImportJournalV15Test-20261106T023416.log) |
| Home/library/export, player, Dialogue/Reading, models, installer/storage | Все включённые в 97 методы PASS; подготовка пакета, модели и сохранённые записи проверены | [Все журналы](docs/human-review/v1.5/evidence/android-tests-build11/), [product artifacts](docs/human-review/v1.5/evidence/product-native11/) |
| UI, обе темы, IME/editor/Undo | Compact 360×640 / font 1.3 **4/4**, normal 384×832 / font 1.0 **4/4**; recorder/font2.0 PASS | [Compact](docs/human-review/v1.5/evidence/android-tests-build11/EditorialV14UiTest-20261106T023504.log), [normal](docs/human-review/v1.5/evidence/android-tests-build11/EditorialV14UiTest-20261106T023957.log), [200%](docs/human-review/v1.5/evidence/android-tests-build11/EditorialV14UiTest-virtualRecorderPauseBackSaveDecodeReopen-20261106T024059.log) |
| Запрещённый микрофон, отказ notifications, reduced motion, virtual recorder | Все соответствующие случаи и повторы PASS; виртуальный вход не выдан за микрофон vivo | [Mic denied](docs/human-review/v1.5/evidence/android-tests-build11/RecordingPermissionV14Test-20261106T024925.log), [Home denied](docs/human-review/v1.5/evidence/android-tests-build11/HomeExperienceV15Test-launcherOpensOrbLibraryHasOwnTabAndHomeExportsRoomText-20261106T024933.log), [orb reduced](docs/human-review/v1.5/evidence/android-tests-build11/OrbInteractionV15Test-20261106T024946.log), [recorder reduced](docs/human-review/v1.5/evidence/android-tests-build11/EditorialV14UiTest-virtualRecorderPauseBackSaveDecodeReopen-20261106T024951.log) |
| AGSL/Canvas и recovery | **2/2 + 2/2 PASS** после изолированных повторов; история двух таймаутов сохранена ниже | [Renderer repeat](docs/human-review/v1.5/evidence/android-tests-build11/OrbRendererV14Test-20261106T024141.log), [recovery repeat](docs/human-review/v1.5/evidence/android-tests-build11/ProcessingRecoveryTest-20261106T024153.log) |
| Heavy ML/product regressions | **21/21 PASS**, включая actual GigaAM Worker, quiet/silence, video, ML comparisons, long/thermal/thread, product/review и persisted edits | [Native artifacts](docs/human-review/v1.5/evidence/native-regressions11/), [product](docs/human-review/v1.5/evidence/product-native11/) |
| Cold готовность All-in-One в двух процессах | **PASS**, PID 10968→11117; SHA всех 7 моделей совпадают, mtime не меняются | [Первый](docs/human-review/v1.5/evidence/bundle-final11/first-process.json), [второй](docs/human-review/v1.5/evidence/bundle-final11/second-process.json) |

**История двух первоначальных отказов сохранена.** Renderer capture сначала получил Failed waiting for PixelCopy — callback timeout 1 с; compile AGSL и orb interaction уже проходили. Queued cancellation сначала не завершила ожидание за 10 с. Повтор обоих полных классов изолированно дал 2/2 PASS без изменений приложения. Это не «112 запусков без единого отказа»: canonical latest-case result 97/97 отделён от двух historical failed invocations. [PixelCopy failure](docs/human-review/v1.5/evidence/android-tests-build11/OrbRendererV14Test-20261106T023439.log), [queued cancellation failure](docs/human-review/v1.5/evidence/android-tests-build11/ProcessingRecoveryTest-20261106T023757.log). Причина таймаутов не установлена; ошибки AGSL/app crash в PixelCopy-стеке нет, пороги качества изображения не ослаблялись.

### Что проверила heavy ML-фаза

21 случай: автоматически подготовленный комплект→GigaAM Worker 1, QuietPipeline 2, VideoPipeline 1, MLComparison 3, RecoveryV13Instrumented 5, ProductExperience 5, ReviewScreenshots 3 и PersistedEdits 1. Это настоящие native inference/Room/export пути, текст не подставляется.

- **Тихая речь/тишина:** ослабленный публичный PCM16 (-40 dB) даёт текст и Room readback; exact silence даёт 0 segments и **asrLoadMs=0/asrInferenceMs=0**. [Quiet](docs/human-review/v1.5/evidence/quiet-native11/quiet-pcm16-minus40db.json), [silence](docs/human-review/v1.5/evidence/quiet-native11/silence.json). Это отдельная проверка цифрового уровня, не настоящий шёпот.
- **Видео:** реальный AAC remux→offline Worker→повторное открытие Room→прочитанные TXT/JSON/SRT. Source SHA сохранён, video decoder не используется. [Acceptance](docs/human-review/v1.5/evidence/video-native11/acceptance.json), [три exports](docs/human-review/v1.5/evidence/video-native11/).
- **Длинный pipeline и диаризация:** single и automatic отработали около 247.59 с **контролируемого повтора** публичного fixture. Это не независимый длинный русский диалог и не доказательство исправления automatic diarization. [Single](docs/human-review/v1.5/evidence/native-regressions11/v13-long-single-diagnostics.json), [auto](docs/human-review/v1.5/evidence/native-regressions11/v13-long-auto-diarization.json).
- **Threads/thermal:** последовательные 1/2/4 CPU threads сохранили одинаковую гипотезу на одном fixture; severe блокирует, moderate продолжает, critical отменяет через **emulator-only override**. Это не нагрев телефона. [Threads](docs/human-review/v1.5/evidence/native-regressions11/v13-thread-comparison.json), [thermal](docs/human-review/v1.5/evidence/native-regressions11/v13-thermal.json).
- **Ручные изменения:** text/speaker/name пережили отдельный process invocation и совпали в Room/UI/export. [Persisted edits](docs/human-review/v1.5/evidence/native-regressions11/edit-persistence.json). Product/review дополнительно покрывают editing/player/delete/corrupt import/Worker/review flows; старые артефакты с похожими именами хранятся отдельно от [source11 scope](docs/human-review/v1.5/evidence/product-native11/SCOPE.md).

ModelPack 3 намеренно импортирует комплект до новой cold-baseline; сравнение mtime не делается с изменённым этим тестом состоянием. Чистые снимки двух текущих процессов подтверждают отсутствие повторной распаковки.

Source11 также вводит cadence: тишина после settling около 30 fps, речь/переходы/касания — максимум 60 fps, при этом onset слушается на каждом vsync. Семь JVM-тестов проверяют scheduling; завершённые измерения эмулятора приведены ниже и не являются измерением телефона.

## Настоящий русский шёпот: host и Android разделены

Получены **все 7 официальных whisper test rows**, 50.299 с / 84 слова / 500 символов / 3 актёра из [Langswap, pinned revision](https://huggingface.co/datasets/langswap/dialogs-ru-emotional-conversations/tree/a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd). Whisper label и текст взяты из авторского CSV; это scripted studio speech, а не запись vivo или проблемный файл пользователя. Пользователь такого файла не предоставил. Источники, SHA, лицензия и ограничения: [provenance](docs/test-evidence/v1.5/ru-whisper-dialogs-provenance.json), [fixtures](docs/test-evidence/v1.5/ru-whisper-dialogs-fixtures.json), [host report](docs/test-evidence/v1.5/ru-whisper-dialogs-report.md). Аудио не включено в APK/review ZIP.

Host whole-clip E2E дал 2/84 word errors, но прежние production VAD/context пропустили один целый 13.123-секундный файл / 23 слова: всего **31/84 ошибок**. Принятая политика C повторяет **только VAD**, если первый проход пуст: ограниченный RMS/headroom gain применяется к отдельному detector input. На host она уменьшила число ошибок до **10/84 (WER 11.90%, CER 44/500 = 8.8%)**. Этот малый набор применялся при выборе rescue-policy и больше не является независимой оценкой этой настройки. Снижение threshold до 0.35/0.2, fixed 4× и post-roll 150 не выбраны. [Host summary](docs/test-evidence/v1.5/ru-whisper-dialogs-summary.json).

В source11 настоящий Android Worker на API 35 выполнил все 7 файлов: **9/84 word errors = 10.714% WER**, **39/500 char errors = 7.8% CER**. Ранее потерянный в host default файл распознан с **2/23 word errors**; detector-only gain **9.273613**, ASR gain **1**. Остальные шесть файлов не использовали rescue. SHA исходников до/после совпали; проверены Room-перечитывание и TXT/JSON/SRT exports. **Один JUnit-тест содержит семь file cases**; внешнее время запуска 73.92 с, внутренний JUnit log 70.001 с. [Acceptance](docs/human-review/v1.5/evidence/whisper-native11/acceptance.json), [run metadata](docs/human-review/v1.5/evidence/android-tests-build11/run-20261106T023158.json), [лог](docs/human-review/v1.5/evidence/android-tests-build11/WhisperPipelineV15Test-20261106T023158.log).

Отдельный API 28 source11 Worker на тех же семи файлах также дал **9/84 и 39/500**, один rescue и неизменённые исходники: **1/1 PASS**, внешнее время 55.59 с. [API 28 acceptance](docs/human-review/v1.5/evidence/api28/build11/real-whisper-worker/acceptance.json), [run](docs/human-review/v1.5/evidence/api28/build11/whisper1-summary.json). Эти x86_64 проверки не подтверждают акустику телефонного микрофона или arm64 скорость. Host 31→10 и Android 9 — результаты разных платформ, их нельзя выдавать за парный Android before/after 31→9.

Сохраняются VAD threshold 0.5, context 100/0 ms, прежний ASR input/model, исходные PCM, playback и вход диаризации. У семи studio-файлов ASR gain всегда 1. Detector rescue отдельно ограничивает RMS/headroom; восемь новых JVM-тестов проверяют guards/bounds. Предыдущий low-peak gain остаётся отдельной политикой временных VAD/ASR массивов при global peak <0.01, максимум 20×. Полноценное решение русского телефонного шёпота не заявляется.

## Остальная ASR-оценка

На Linux CPU / sherpa-onnx 2.0.1, 96 фиксированных обычных FLEURS-файлах / 1859 слов v2 дал 139 ошибок (WER 7.48%), выбранный v3 E2E 89 (4.79%). На no-digit subset эффект меньше: 65 против 58/1446 слов; CER не доказывает универсальное преимущество. [Raw summary](docs/test-evidence/v1.5/asr-final-summary.json), [выбор модели](MODEL_SELECTION_V1_5.md).

Цифровое ослабление на 40 dB **не является настоящим шёпотом**: в PCM16 первых 32 файлов E2E без gain 149/670 ошибок, с bounded gain 39/670. Это проверка низкого цифрового уровня, а не плохого SNR или отсутствующего озвончения. Настоящий EN whisper использован только для VAD. Ранее найденный NCSpeech RU corpus оставался gated; новый доступный Langswap набор описан отдельно выше. [ASR_QUALITY_V1_5.md](ASR_QUALITY_V1_5.md) содержит методику и ограничения. Host WER не является WER всего Android video/recording pipeline.

## Вторичный API 28, размеры и UI-доказательства

На source11 API 28 / x86_64 завершены **33/33 PASS: 32 UI/core + 1 Worker-тест всех семи whisper-файлов**. UI/core: MediaImport 15, Canvas renderer 1, ImportJournal 8, Navigation 1, OrbInteraction 1, Home 2 и Editorial 4. Использован исходный native-профиль **432×936 px / density 180 / font 1.0**, конфигурация приложения 384×760 dp; без wm/density/font overrides. Home теперь проверяет действительный оконный фокус после chooser/Back; JSON export и возврат проходят. [UI32 summary](docs/human-review/v1.5/evidence/api28/build11/ui32-summary.json), [32 свежих PNG](docs/human-review/v1.5/evidence/api28/build11/ui/), [scope](docs/human-review/v1.5/evidence/api28/build11/ui/scope.json). На API 28 оба renderer requests исполняют Canvas, AGSL требует API 33+.

Ранние смещённые timestamps/edit-list исправлены и повторно проверены всеми 15 media случаями на API 28. Прежний wm override на старом AVD обрезал compositor/root surface; соответствующие [диагностические снимки](docs/human-review/v1.5/evidence/api28/build10-invalid-wm-override/) не приняты как компактная приёмка. Наблюдавшийся там ANR принадлежал **com.android.systemui**, а не REPLIKA; [recovery](docs/human-review/v1.5/evidence/api28/systemui-anr-recovery.json). Compact 360×640 / font 1.3 доказательства относятся к основному API 35 стенду. Тема внешнего IME управляется клавиатурой; проверка insets/Save не означает её перекраску приложением.

Свежие source11 LIGHT/DARK PNG двух основных API35 профилей, recording frames и API28 исходного профиля собраны. [Основной каталог](docs/human-review/v1.5/evidence/android/), [API28](docs/human-review/v1.5/evidence/api28/build11/ui/). Новое [native-video source11](docs/human-review/v1.5/evidence/native-demo/native-orb-emulator-touch.mp4) показывает orb start/tap/drag/release/pause/resume/stop/save; [scope](docs/human-review/v1.5/evidence/native-demo/video-scope.json) подтверждает host microphone Off, отсутствие synthetic speech и отсутствие performance measurements во время видео. Оно доказывает интерфейс и виртуальную запись, не физическую реакцию на голос.

Source10 PNG/video сохранены отдельно: [архив PNG](docs/human-review/v1.5/evidence/android-build10/), [архив video](docs/human-review/v1.5/evidence/native-demo-build10/). Предыдущая [gallery QA source10](docs/human-review/v1.5/evidence/review-gallery-build10/report.json) архивирована; свежая source11 проверка описана ниже.

## Системные панели: внешнее ограничение старого AVD

На source11 gesture mode прошёл **восемь checkpoints** manual LIGHT/DARK до/во время/после диалога и после recreation: [ThemeBars](docs/human-review/v1.5/evidence/android-tests-build11/ThemeBarsV15Test-20261106T023351.log). Прежняя проблема светлых фонов manual DARK устранена: фон #111214; ранее измеренный контраст часов 18.74, gesture indicator 15.875.

Строгая трёхкнопочная проверка старого AOSP AVD остаётся известным **FAIL**: Home glyph contrast **2.001**, ниже 3.0. App/SystemUI запрашивают светлые glyphs, но Launcher3 Taskbar применяет override системной LIGHT-темы. Воспроизведено вне JUnit, Launcher restart/cold boot не устранили override. [Исходный отказ](docs/human-review/v1.5/evidence/android-tests/ThemeBarsV15Test-20261106T002359.log). Порог не ослаблен, глобальная смена системной темы как workaround не добавлена. Это не доказанный дефект всех Android 15; vivo неизвестен. [Полная диагностика](docs/test-evidence/v1.5/SYSTEM_UI_AVD_LIMITATION.md).

## Измерения UI на эмуляторе

Сравнены отдельные **10-секундные окна тихой виртуальной записи** source10 и source11 после 5 с прогрева: API 35 / x86_64 AOSP, Skia OpenGL, host microphone отключён. Во время измерений не работали другой AVD, host ASR, Gradle, браузер и screenrecord. Кэши устройства и нагрузка host OS не контролировались; это небольшое сравнение на одном эмуляторе. [Performance summary](docs/human-review/v1.5/evidence/native-demo/performance-summary.json), [scope](docs/human-review/v1.5/evidence/native-demo/performance-scope.json).

| Метрика gfxinfo | Source10 | Source11 |
|---|---:|---:|
| Кадры за окно 10 с | 289 | 295 |
| Janky frames | 102 / 35.29% | 175 / 59.32% |
| Frame cost p50 | 31 мс | 19 мс |
| Frame cost p90 | 117 мс | 28 мс |
| Frame cost p95 | 150 мс | 38 мс |
| Кадры после успокоения idle за 4 с | 0 | 0 |

**Стоимость кадров по этим percentile ниже, но reported jank вырос с 35.29% до 59.32%.** Общего улучшения плавности или прохождения 60 fps эта выборка не доказывает. Тихий scheduler ориентирован на 30 fps; речь/касания имеют cap 60 fps, но не были отдельными performance samples в этом прогоне. GPU percentiles исключены как invalid/sentinel и не выдаются за реальную latency. Нулевые idle frames подтверждают отсутствие постоянной отрисовки на этих двух коротких settled-idle отрезках; батарея/нагрев/FPS vivo не измерялись. Видеодемонстрация записана отдельно от замера.

## Финальная нативная галерея

[Свежий browser QA report](docs/human-review/v1.5/evidence/review-gallery/report.json) — **PASS**. Все 48 оригинальных PNG (12 экранов × 2 темы × 2 профиля: 360×640 / font 1.3 и 384×832 / font 1.0) декодированы в точных исходных размерах; captions/alt и UI-fixture отметки совпадают. Переключатели темы/профиля меняют соответствующие 12 изображений. Supporting links существуют; APK/download и exports не открывались. Review-page на ширинах 320/360/392 px не имеет горизонтального переполнения; JavaScript/console errors отсутствуют. Новое source11 native-video иposter загружаются, muted playback продвигается: **360×640, 26.771989 с**. Scope подтверждает host mic Off/no synthetic speech и отсутствие performance measurements во время записи.

Browser plugin недоступен: использованы существующий Playwright 1.64.1 и изолированный headless Edge Chromium 156.0.4314.58, fileURL локальной галереи. Браузер закрыт после проверки. Скриншоты/metadata/script сохранены в [review-gallery](docs/human-review/v1.5/evidence/review-gallery/); это QA review-page, не проверка телефонного runtime. Все 48 source11 PNG имеют новые SHA относительно архивной source10 матрицы.

## Browser-прототип

После минимальной CSS-защиты однострочных подписей `verify-v15-orb.cjs` прошёл **15 групп сценариев**, ошибок консоли нет. Дополнительно LIGHT/DARK × ширины 320/360/392 px × 640 px при font 130% дали **24 валидных layout-состояния** idle/recording/paused/resumed: подписи целиком в одну строку, кнопки в viewport, горизонтального переполнения нет; start/pause/resume/stop работают. [Основной отчёт](docs/human-review/v1.5/evidence/orb-prototype/report.json), [font130](docs/human-review/v1.5/evidence/orb-prototype/controls-font130-report.json).

Browser plugin недоступен. Использован существующий Playwright 1.64.1 через Windows Node и отдельный headless Edge Chromium 156.0.4314.58 profile после зависания существующего Linux Chromium до CDP. Новых зависимостей не установлено. Амплитуда явно обозначена симуляцией; браузерный микрофон не используется. Эти результаты относятся к концептуальному прототипу, а не к Android runtime.

## Комплект, сохранение и подпись

Текущий набор содержит **7 model files / 3 группы** (`giga-v3`, `diar`, `vad`), 278 127 730 байт распакованных моделей; Whisper отсутствует в новом pack и продуктовых вариантах выбора. Исторические транскрипции Whisper остаются читаемыми с прежней атрибуцией. Прежний V1.3 APK и исходное Git-состояние сохранены; push не выполнялся.

Исходный новый pack `model-pack/replika-offline-pack-v1.5.zip`: **278 569 170 байт**, SHA-256 `5e064a64e7a2511b5b2cc8b51989a3bafac57719a3d9bb062fb60e10d2af73c6`. В APK упакована одна losslessly сжатая копия с теми же model hashes: **208 854 459 байт**, SHA-256 `2c12dfd8a000b2432cae606d6b849dd9b39ce205d50cc49c70a4f9a3253003d0`. Старый desktop ZIP сохранён отдельно; [inventory](docs/test-evidence/v1.5/current-model-pack-verification.json), [preservation checks](docs/test-evidence/v1.5/media-platform-host-checks.json).

Финальный APK: [REPLIKA-V1.5-AllInOne-arm64.apk](release/REPLIKA-V1.5-AllInOne-arm64.apk), **304 997 087 байта**, SHA-256 **`ea5495998e97339194932b8cfa75aaf66823c7dd3a10e821bfda2e3234beaffc`**. `tools/verify_all_in_one.py` — **PASS**: один встроенный pack, model hashes, только arm64-v8a, ZIP/ELF 16 KiB alignment и native dependencies; custom Whisper JNI не упакован. [Аудит](docs/human-review/v1.5/evidence/arm64-static.json). Работа на устройстве с 16 KiB страницами не проверена runtime-тестом.

`apksigner` подтвердил APK Signature Scheme v2; прежний локальный debug-сертификат SHA-256 `f40399356577bcd0a5c220818ba13e9686768a02830a7f6e3af81d5a487947ab` сохранён для совместимого обновления. [Подпись](docs/human-review/v1.5/evidence/apksigner-arm64.txt), [аудит лицензий](docs/ALL_IN_ONE_LICENSE_AUDIT.md). Совпадение подписи не заменяет отдельный сценарий upgrade реальных пользовательских данных на физическом телефоне.

## Границы приёмки

Все 97 основных и 33 вторичных Android-regression случая, 80 JVM, финальное видео, эмуляторные измерения и QA галереи завершены. Логи двух первоначальных таймаутов сохранены вместе с успешными изолированными повторами. Высокая доля jank на эмуляторе и ограничение трёхкнопочного Launcher AVD не скрыты итоговым PASS тестовых случаев.

Настоящий Worker на доступном RU studio whisper подтверждён на двух эмуляторах. **Реальный микрофон vivo, тихая/громкая речь и телефонный шёпот, UI FPS/GPU/батарея/нагрев на телефоне, физический arm64 и runtime 16 KiB нового APK не подтверждены.** Виртуальный вход эмулятора и browser simulation это не заменяют. Automatic diarization остаётся нерешённым дефектом. [Известные ограничения](KNOWN_ISSUES.md).
