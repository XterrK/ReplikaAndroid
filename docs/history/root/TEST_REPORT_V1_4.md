# REPLIKA V1.4 — проверка реализации

Дата: 2026-11-05. Направление утверждено непосредственно пользователем: C+B / Editorial Intelligence; окончательная палитра — холодная Light и нейтральная Graphite.

**Физический телефон недоступен.** Все новые Android runtime проверки выполняются на Android SDK x86_64 emulator API 35. Ни реакция на настоящий микрофон телефона, ни FPS/батарея/нагрев vivo X300 не подтверждаются этим отчётом. Пользовательский результат V1.3 (~30 s на конкретной 4-min записи) не переименовывается в новый benchmark.

## Реализация и сохранность

Kotlin/Compose, две самостоятельные темы и DataStore SYSTEM/LIGHT/DARK. Onest для основного текста и controls, serif для editorial headings. Самостоятельные реплики Dialogue, отдельное Reading с чистым копированием, уменьшенный transport в Reading, компактный Editor и модели с расширенной диагностикой. Duration-only warnings исключены из Review, persisted ML reasons остаются в Room/JSON.

Liquid Voice Orb: 72-точечный Bézier контур, общий damped spring и пять локальных мод, AGSL volume surface на API 33+ и Canvas fallback. Сигнал — maxAmplitude существующего MediaRecorder каждые 50 ms, adaptive floor / logarithmic compression / attack-release smoothing. Нативного simulation slider нет. Обновляется только Canvas, есть lifecycle/reduced-motion/thermal/power-save ограничения.

18 файлов ML/domain/Room/ProductStorage/C++/model manifest совпадают с V1.3 побайтно (evidence/ml-source-integrity.json). Automatic diarization остаётся известным дефектом.

V1.3 APK не перезаписан. Исходный HEAD ce345569377f0d7b60b383296f00f58b417986e0 сохранён Git bundle в review/v1.4-baseline/. Архив прежней лаборатории и preservation.json лежат рядом. Ранее существовавшая video-production-fi-20261105/ не изменялась. Git push не выполнялся.

Приложение обновлено install -r. При сравнении старых файлов БД и аудио не изменились; AndroidX profileInstalled обновился при первом запуске. Первый запуск пересёкся с длительным сбором post-install файлов, поэтому это не строгая no-launch byte-identity проверка; подробности в evidence/upgrade.json. Приватная резервная копия не включена в review ZIP.

## Автоматические проверки

- JVM: 44 теста, включая устойчивость динамики, ограничение расширения, шум/quiet/loud/release, reduced motion и legacy warning provenance.
- Browser prototype: 53 проверки: восемь экранов, Light/Dark, 392×852 и 360×640, крупный шрифт, тихий/громкий/нулевой тестовый уровень, pause/resume/stop, reduced motion. Browser plugin not available; использован установленный Playwright/Chromium. evidence/prototype/report.json содержит результаты и отсутствие runtime/console ошибок. Амплитуда явно помечена как симуляция.
- ML regression: 6/6 сравнений PASS с исходными V1.3 outputs: GigaAM Worker, Whisper Worker, direct ASR, VAD, automatic/fixed diarization, native-label export provenance. Нормализованные тексты, границы, assignments, flags и параметры совпали. Timings/PSS — отдельные наблюдения, не обещание ускорения.
- Android core: реальные модели, WAV/MP3/M4A, storage/edit/Undo, recovery/cancellation, bundle installer, diarization, оба Worker backends, warning pipeline, thermal gate и контролируемая четырёхминутная повторённая запись. Это публичные/контролируемые fixtures, не новая естественная четырёхминутная запись с телефона.

## Нативная матрица

Итог: 44 JVM, 69 различных Android методов PASS, 53 browser проверок; неустранённых тестовых отказов нет. 87 актуальных Android captures, включая renderer fixtures. Финальные результаты — evidence/validation-summary.json; указатель основных экранов — SCREENSHOTS.md. Полные instrumentation логи — evidence/android-tests/, JVM XML — evidence/jvm/. Android screenshots — evidence/android/, browser captures — evidence/prototype/. Renderer fixtures отдельно помечены.

Проверяются Light/Dark на Library, Recording, Processing, Dialogue, Reading, Review, Editor с IME, Models; настройки, ошибки, AGSL и принудительный Canvas fallback; 360×640 и увеличенный системный шрифт; Back, pause/resume, stop/save, decode и повторное открытие.

Первый UI прогон выявил ошибку тестового поиска третьей кнопки Back-диалога (нужен unmerged semantics tree); тест исправлен. Один ранний screenshot захватил предыдущий compositor frame: добавлена синхронизация frame commit. Clipboard-preview исключён из визуальной матрицы, копирование продолжает проверяться отдельной регрессией. На 360×640 / font 130% визуальная проверка обнаружила вытеснение editor-text панелью предупреждения при открытой IME. Исправлено отдельным компактным режимом: текст, воспроизведение в header и footer сохранения, подробности после закрытия клавиатуры. Добавлена проверка видимости поля.

Старый acceptance-marker моделей имел mtime до явного импорта pack в ModelPackTest и был устаревшим ещё до V1.4. Исторический marker сохранён, затем две отдельные свежие acceptance-сессии подтвердили неизменность всех моделей без импорта между ними. Устаревший test APK с прежней строкой Models дал timeout; актуальная пересборка и 2/2 AllInOneUiTest прошли.

Ранний PersistedEditsTest был запущен до повторного UI исправления после PipelineTest: он требует порядок «pipeline → UI edit/export → отдельный процесс persistence». Исходные неудачные логи сохранены; финальный прогон использует правильный порядок.

## Практические ограничения приёмки

- Виртуальный MediaRecorder проверяет Android сессию/паузы/контейнер/Room; это не физическая тихая/громкая речь. Envelope/dynamics tests используют явные тестовые значения и не заменяют микрофонную приёмку.
- AOSP keyboard может иметь светлую тему внутри вручную выбранной Dark REPLIKA. Это отдельное IME-приложение; insets/footer/scroll проверяются. REPLIKA не меняет глобальную тему устройства.
- Canvas fallback на API 35 не подтверждает полный runtime прогон API 26–32.
- Первый gfxinfo захват во время screenrecord/UIAutomator и параллельной сборки: 478 frames, 160 janky (33.47%), p50 32 ms. Он не проходит как свидетельство плавных 60 FPS; прогретый изолированный замер: 461 frames / 8 s, 26 janky (5.64%), p50 24 ms, p90 32 ms. Это также не гарантия стабильных 60 FPS. В Idle после settling — 0 frames за 3 s; пустые histogram percentiles не интерпретируются как задержка. Полные данные в performance-warm.json. Gfxinfo/thermal emulator observations не измеряют энергопотребление и тепловое поведение arm64 телефона. Thermal gate регрессия проверяет реальные PowerManager transitions эмулятора.
- Static ZIP/ELF alignment не заменяет запуск на 16 KiB устройстве.
- Accessibility проверяется через semantics, отдельные подписи, увеличенный шрифт и видимость действий; полноценная ручная TalkBack-сессия на физическом телефоне остаётся для приёмки.

Код сопоставлен с утверждённым направлением: evidence и FIDELITY_LEDGER.md. Цветовые/типографические отклонения от старого C обусловлены прямым уточнением пользователя; отличия shader/fallback и idle motion описаны в LIQUID_ORB_TECHNICAL_SPEC.md.
