# REPLIKA V1.2 — акт продуктовой приёмки

V1.2 продолжает существующий проект от `6e3c8abcd885345b185c2a9131f69eb02e4eb029`. Продукт имеет статус **PARTIAL**: основные сценарии подтверждены на Android API 35 / x86_64, но физический arm64 и полноценный русский многоголосный сценарий не приняты.

Ниже разделены фактическое исполнение и статический разбор. WORKING относится только к указанной среде и данным. Последняя полная приёмка относится к APK SHA-256 `5d06dc98cb4f896f2640e1d76c5821462dad8e26ec8a275991c8828d3cd5141c`. Окончательный commit и рабочее дерево фиксируются в TEST_REPORT_V1_2.md и манифесте Review ZIP; SHA V1.1 не используется вместо V1.2.

## Фактически выполненные проверки

| Набор | Результат | Доказательство |
|---|---|---|
| Clean APK arm64-v8a + x86_64, JVM | WORKING: 25 JVM, 0 failures/errors/skipped | [Clean build](../../test-evidence/v1.2/clean-build.log), [Domain 18](../../test-evidence/v1.2/TEST-ru.replika.DomainTest.xml), [Presentation 4](../../test-evidence/v1.2/TEST-ru.replika.PresentationTest.xml), [Errors 3](../../test-evidence/v1.2/TEST-ru.replika.ProductErrorsTest.xml) |
| Основной Android набор | WORKING: 27 tests | [Instrumentation](../../test-evidence/v1.2/android-instrumentation.txt) |
| Review и основные screenshots | WORKING: 3 Compose tests | [Review UI](../../test-evidence/v1.2/android-compose-ui.txt) |
| Редактор, Undo, delete, player, corrupted Worker | WORKING: 5 Compose tests | [Product UI](../../test-evidence/v1.2/android-product-ui.txt) |
| Компактный профиль 360×640 / font scale 1.3 | WORKING: 7 повторных UI tests; это не 7 новых независимых ML-корпусов | [Compact](../../test-evidence/v1.2/android-compact130.txt) |
| Исправления после force-stop и отдельного процесса | WORKING: 1 test, Room совпадает с UI export | [Process relaunch](../../test-evidence/v1.2/android-process-relaunch.txt), [JSON](../../test-evidence/v1.2/edit-persistence.json) |
| ZIP + ELF LOAD alignment нативных библиотек | WORKING статически: 8 .so, обе ABI | [APK static](../../test-evidence/v1.2/apk-static-clean.json); это не arm64/16 KiB runtime validation |
| ML-регрессии относительно V1.1 | WORKING на сохранённых actual outputs: 6 проверок PASS | [Comparator](../../test-evidence/v1.2/ml-regression.json); качество без reference не измерено |

Эти результаты получены после последних исправлений: светлых status bar icons в тёмных sheet, адаптивного заголовка Review и ограничения playhead длительностью аудио. Исправления подтверждены [новым Review UI прогоном](../../test-evidence/v1.2/android-compose-ui.txt), [compact прогоном](../../test-evidence/v1.2/android-compact130.txt), [кадром picker с IME](29-product-speaker-picker-keyboard-compact130-360x640.png) и [UI JSON с `subsecondClockClamped=true`](../../test-evidence/v1.2/v12-review-queue-ui.json). Пропусков в итоговых наборах нет. Исходные неудачные пилоты и компактный промежуточный assert сохранены в [attempts](../../test-evidence/v1.2/attempts/) и отдельных pilot logs.

## Продуктовые сценарии

| Сценарий | Приёмка и практический предел |
|---|---|
| Library / поиск / меню | WORKING на обоих профилях. [Основной кадр](01-library.png), [compact](compact130-01-library.png). Тысячи записей отдельно не измерялись |
| Удаление записи и её копии аудио | WORKING: cancel сохраняет всё; confirm удаляет только owned audio/строки/подписи. Shared/external/symlink и busy запись защищены; staging recovery проверен. [UI proof](../../test-evidence/v1.2/product-experience-v12-base-384x832-delete.json) |
| Workspace / настоящие сегменты / active row | WORKING по реальному состоянию плеера и Room. [Workspace](04-transcript-workspace.png), [seek/speed/background proof](../../test-evidence/v1.2/product-experience-v12-base-384x832-player.json). Слышимый тракт телефона не проверен |
| Редактор с IME и длинными именами | WORKING: text/speaker/reviewed сохраняются; поиск участника 12 доступен с открытой клавиатурой. [Compact picker](29-product-speaker-picker-keyboard-compact130-360x640.png), [compact editor](23-product-editor-keyboard-compact130-360x640.png) |
| Черновик / discard / Undo | WORKING: черновик переживает Activity recreation; Back требует подтверждения; continue сохраняет draft, discard не пишет в Room; точный Undo возвращает предыдущую строку. [Proof](../../test-evidence/v1.2/product-experience-v12-compact130-360x640-editor.json). История Undo после process death не обещается |
| Исправление имени и экспорт | WORKING: ручные text/speaker/name/reviewed присутствуют в свежем [UI JSON export](../../test-evidence/v1.2/ui-corrected-transcript.json) и после отдельного process relaunch. Sheet открывается полностью и допускает прокрутку: [обычный профиль](36-product-export-options-base-384x832.png), [compact](36-product-export-options-compact130-360x640.png). Оба [base proof](../../test-evidence/v1.2/product-experience-v12-base-384x832-player.json) и [compact proof](../../test-evidence/v1.2/product-experience-v12-compact130-360x640-player.json) фиксируют `allExportFormatsVisible=true` и `freshUiExportMatchesSavedRows=true`. Открытие Share chooser не доказывает приём файла сторонним приложением |
| Smart Review с настоящим предупреждением | WORKING: неизменённый Worker получил непустую реплику «ничьих не» из реального 650 ms excerpt, создал объективный short flag; listen/editor/done и сохранение reviewed проверены. [Raw pipeline](../../test-evidence/v1.2/v12-warning-pipeline.json), [UI](../../test-evidence/v1.2/v12-review-queue-ui.json), [кадр](14-smart-review-real-warning.png) |
| Пустой Review | WORKING как объяснение и навигация: [кадр](06-smart-review.png). Пустая очередь не свидетельствует о правильном ASR |
| Recording | PARTIAL: AVD -no-audio; реальные виртуальные уровни, timer/pause/resume/background/save дали декодируемый M4A. [Proof](../../test-evidence/v1.2/v12-recording-ui-1.0.json), [ранние отсчёты](32-recording-early-levels.png), [setup после Save](33-recording-saved-setup.png). Микрофон телефона не использован |
| Processing / duplicate / cancel / recovery | WORKING в API35 тестах. Фазы фактические, проценты и ETA не выдумываются; текущий JNI нельзя немедленно прервать. [Processing](03-processing.png) |
| Models / offline pack / human diagnostics | WORKING: настоящий pack проверен, SHA/размеры видны, малый VAD 629 КБ, JSON отдельно. [Summary](12-models-diagnostics-details.png), [details](30-models-technical-details.png), [pack test](../../test-evidence/v1.2/android-pack-install.txt). Числа PSS — снимки, не peak |
| Loading / пустой результат | WORKING в проверенных переходах: готовые строки не выдавались за отсутствие речи до загрузки; данные связаны с recordingId. В быстрых прогонах loading может не попасть на кадр: `observedLoadingTag=false` не превращается в доказательство отсутствия состояния |
| Повреждённое аудио | WORKING: IMPORTED не готовит скрытый player; production Worker приходит в ERROR, сохраняет предыдущую строку, показывает русскую причину и хранит raw exception. [Proof](../../test-evidence/v1.2/product-experience-v12-base-384x832-corrupt-worker.json), [error](34-product-corrupt-worker-recovery-base-384x832.png) |
| Стресс памяти, ENOSPC, долгий download/resume, внешние Share receivers | PARTIAL: полная приёмка этой итерацией не подтверждена; PSS и небольшой public fixture их не заменяют |

Дополнительный ручной интеграционный прогон: системный DocumentsUI Downloads → импорт публичного AAC/M4A → fixed speaker count 1 в UI → настоящий GigaAM Worker → Room → UI → JSON Share chooser. Получены две реплики, speaker ID 0, границы проверены. [Доказательство](../../test-evidence/v1.2/saf-m4a-fixed1-proof.json) относится к предыдущему APK `5cc933fe…4909`, до отдельной правки export sheet, и учитывается как **SUPPLEMENTARY**, а не как новый ручной прогон финального APK. Это mono-конверсия публичного WAV, не русский многоголосный диалог; файл внешнему receiver не отправлялся.

## Что подтверждает ML-часть

GigaAM и Whisper прошли настоящий mono Worker → Room → UI → экспорт; VAD, диаризация, pre-roll 100 ms и временная шкала сохранены. Comparator сопоставляет тексты, временные границы, ID и параметры, игнорируя случайные UUID и несопоставимые timing/PSS. Равные гипотезы означают отсутствие обнаруженной регрессии на данном входе, а не доказательство точности всех записей.

Реальный short-warning input — контролируемый crop исходной публичной речи с сохранёнными SHA и offset. Это не демонстрационный текст, не естественный диалог и не независимый эталон качества. UI-данные с 12 длинными ручными именами копируют настоящую стенограмму и помечены `uiOnlyCopyOfActualInference`; число подписей не равно числу обнаруженных голосов.

Происхождение старых native speaker labels и новых последовательных ID разобрано в [SPEAKER_ID_PROVENANCE.md](SPEAKER_ID_PROVENANCE.md). Новые цвета/имена не являются переписыванием диаризации. Сопоставимое качество GigaAM и Whisper по WER/CER без ручного reference не оценено; автоматическое второе мнение Whisper не интегрировано.

## Ограничения внешней приёмки

- **BLOCKED:** полный русский многоголосный end-to-end, включая natural turn-taking/overlap и независимую ручную разметку. Mono, crop и отдельная китайская диаризация его не заменяют.
- **BLOCKED:** физический arm64, API36 и Android с 16 KiB страницами. Статический alignment не означает успешное исполнение.
- **PARTIAL:** компактные сценарии прошли, но длинный текст с IME требует прокрутки, длинные имена Workspace сокращаются после двух строк, Retry ошибки находится ниже первого экрана. См. [самостоятельную UX-критику](UX_BEFORE_AFTER.md).
- **PARTIAL:** настоящая работа одной рукой и TalkBack не проверены. Верхние действия требуют перемещения руки; emulator pointer не имитирует thumb reach.
- **PARTIAL:** длительные записи, peak RAM, нагрев, батарея, нехватка места и сторонние media/Share providers требуют отдельного устройства и данных.
- **NOT IMPLEMENTED:** мгновенный abort JNI, word timestamps, разделение одновременно произнесённых слов, voice identity, постоянная история ручных изменений и optional ASR second opinion.

Это внутренняя приёмка и пакет для независимого Human Review. Внешняя пользовательская оценка не проведена. Перед хакатоном 6 ноября главные задачи — допустимый русский диалог с разметкой, физический offline arm64 и проверка длительных записей/памяти/нагрева.
