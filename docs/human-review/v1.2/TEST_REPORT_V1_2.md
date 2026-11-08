# TEST REPORT · REPLIKA V1.2 · 02.11.2026

**Эмуляторная приёмка WORKING; продукт PARTIAL.** Проверен существующий Android-проект, не новый скелет. Русский многоголосный natural end-to-end и физический arm64 остаются BLOCKED. Внешнее Human Review ещё не проведено.

## Исходное состояние и артефакт

База: `validation/v1.1`, `6e3c8abcd885345b185c2a9131f69eb02e4eb029`, чистое рабочее дерево. Создана `feature/replika-v1.2-product`. Git bundle, APK/test APK, V1.1 ZIP и app-owned QA data сохранены вне Git в `F:\ReplikaToolchain\v1.2-preservation\20261031T130006Z`. Промежуточные проверенные APK 5ff/f25 также сохранены. Подробности: [preservation](../../test-evidence/v1.2/preservation.json). Модели, прежние доказательства и история не удалялись; push не выполнялся.

Проверенный commit реализации: `e4233e19c39170508d76c3450355ea4becf413a6`. Финальный commit документов фиксируется в `REVIEW_MANIFEST.json` Human Review ZIP и в итоговом отчёте Git.

APK: `F:\Hackathons\ReplikaAndroid\app\build\outputs\apk\debug\app-debug.apk`; version1.2.0/code3, arm64-v8a+x86_64, 129032636 bytes.

SHA-256: `5d06dc98cb4f896f2640e1d76c5821462dad8e26ec8a275991c8828d3cd5141c`.

DEX хранится без сжатия. Это увеличило debug APK относительно V1.1, но устранило наблюдавшуюся распаковку DEX на пути startup instrumentation. Веса в APK отсутствуют; release shrink отдельно не выполнялся.

## Точная среда

Android15/API35 x86_64, AVD Replika35v11, Windows WHPX, emulator37.2.12.0, AMD Ryzen5 3600 host,2 virtual CPU / 3072 MB RAM, 4096-byte pages, swiftshader, `-no-audio`. Основной профиль 432×936px/180dpi/384dp/font1.0; compact360×640px/160dpi/font1.3. Настройки возвращены к исходным. [Environment](../../test-evidence/v1.2/environment.json), [offline](../../test-evidence/v1.2/offline-network.json): wifi0/mobile_data0, active default network none.

Build: WSL2/JDK17.0.17, Gradle8.13, AGP8.9.2, Kotlin2.1.20, SDK35, NDK27.2.12479018, CMake3.22.1. Физический телефон не подключён; API36 image/SDK и 16KiB runtime отсутствуют.

## Реально выполненные проверки

| Проверка | Фактический результат | Доказательство |
|---|---|---|
| Clean APK+test APK+JVM | PASS,81/81executed tasks,BUILD SUCCESSFUL | [clean-build.log](../../test-evidence/v1.2/clean-build.log) |
| JVM |25 passed,0fail/errors/skips: Domain18+Presentation4+ProductErrors3 | [build artifacts/XML](../../test-evidence/v1.2/clean-artifacts.json) |
| Основной Android suite |27 passed,0fail/skips; содержит 1Compose navigation | [instrumentation](../../test-evidence/v1.2/android-instrumentation.txt) |
| Review/редактирование/экспорт UI |3 passed | [Compose](../../test-evidence/v1.2/android-compose-ui.txt) |
| Product UI |5 passed: no eager corrupt playback,seek/speed/background/свежий JSON export,corrupt Worker,data-safe delete,editor/save/Undo/draft/discard | [Product UI](../../test-evidence/v1.2/android-product-ui.txt) |
| Compact+font1.3+light IME |7 повторных сценариев passed,0fail/skips | [compact](../../test-evidence/v1.2/android-compact130.txt) |
| Отдельный process-relaunch |1 passed после force-stop; Room соответствует свежему UI JSON export | [relaunch](../../test-evidence/v1.2/android-process-relaunch.txt),[proof](../../test-evidence/v1.2/edit-persistence.json) |
| Три холодных UI-запуска |3 разных PID; исправленный текст и имя видны после каждого force-stop | [cold UI](../../test-evidence/v1.2/cold-ui-relaunch.json) |
| Offline pack |реальный ZIP+SHA-256; отдельный import test PASS и проверки damaged pack в основном suite | [pack](../../test-evidence/v1.2/android-pack-install.txt) |
| WAV/MP3/M4A |реальный platform decoder,PCM/durations/peaks PASS | [formats](../../test-evidence/v1.2/media-formats.json) |
| ZIP+ELF16KiB |PASS для 8 .so обеих ABI; PT_LOAD alignment/congruence и DT_NEEDED проверены отдельно | [static report](../../test-evidence/v1.2/apk-static-clean.json) |

Итого 36 уникальных Android/instrumentation/UI/process tests; ещё 7 повторов compact и 1 повтор pack import. Всего 44 выполнения JUnit в финальной последовательности. В 8 отдельных UI-сценариев не включён повторно уже учтённый NavigationTest. APK и tests устанавливались с `-r`, app data не очищались.

## Что изменено и проверено

Library: компактная шапка, записи сразу под действиями/поиском, реактивный поиск без false empty во время загрузки, rename/delete menu. Удаление требует подтверждения; собственная копия audio удаляется транзакционно со связанными строками, shared/external/symlink-out файлы сохраняются. Staged recovery проверен; искусственный сбой SQLite commit после staging отдельно не инжектировался.

Workspace: единый audio dock, настоящий waveform и speaker timeline, связанная палитра, непрерывные реплики, заметная active row, seek/±10s/pause/resume/speed/background pause. Субсекундные интервалы показывают ms; playhead ограничен длительностью. Сегментные timestamps не превращаются в word timestamps.

Editor: длинный текст и 12 ручных длинных имён, вертикальный поиск с открытой светлой IME, настоящий play/pause, отдельный save footer, dirty state и подтверждение discard. Черновик и исходный Room snapshot переживают Activity recreation. Save подтверждается после DAO; Undo восстанавливает точную строку и защищён от stale data. Постоянная история Undo и сохранение несохранённого черновика после force-stop не обещаются.

Smart Review: очередь с объективным типом/объяснением/интервалом/участником/listen/edit/reviewed. Реальный 650 ms crop дал «ничьих не»,31–650 ms, short flag; pipeline→Room→UI→reviewed→recreation проверены. Причины не вставлялись вручную. Пустая очередь прямо не гарантирует ASR; fake confidence нет.

Recording: фиксированная сетка ранних реальных отсчётов; нулевой вход не рисует выдуманную речь. Виртуальный MediaRecorder pause/resume/background/save дал декодируемый M4A. Это PARTIAL для настоящего микрофона/аудиотракта.

Models: выбор обоих ASR, реальные размеры включая Silero629 КБ, summary времени/RTF/PSS и отдельный raw JSON/Share. Ошибки codec/permission/storage имеют русское объяснение; исходная ошибка остаётся в диагностике. Corrupt Worker не уничтожил сохранённую строку.

## ML и пределы доказательства

ML/Worker/Alignment/native/model-lock не менялись. Оба настоящих русских mono Worker прошли; [6 групп сравнения с V1.1](../../test-evidence/v1.2/ml-regression.json) PASS по гипотезам, временным меткам сегментов, ID, предупреждениям, контекстам и параметрам. Pre100 ms/post0 сохранены, GigaAM «ничьих» и start31 ms подтверждены. Raw JSON отделён от [ручного UI export](../../test-evidence/v1.2/ui-corrected-transcript.json).

Automatic.5/.65 на zh fixture снова 7 кластеров; fixed4→4. Sparse native labels и first-appearance IDs объяснены [provenance](SPEAKER_ID_PROVENANCE.md), это не новая неисправность. Без reference нет DER/WER/CER и независимого tune/eval. Сопоставимые timings обоих ASR и двух полных Worker — [BENCHMARKS](../../history/root/BENCHMARKS.md); `totalMs` исключает final commit/diagnostics, PSS не peak.

Русский natural multispeaker audio не предоставлен: полный такой сценарий BLOCKED. Короткий mono crop и отдельная китайская diarization его не заменяют. Физический arm64, API36/16KiB runtime, реальный микрофон/звук, long audio/peak/thermal, ENOSPC и сторонние Share receivers не приняты. Мгновенный abort JNI, word timestamps и separation одновременных слов NOT IMPLEMENTED.

## История неудачных попыток

31.10 первый instrumentation startup завершился ANR в ART inflate до Application; retry Worker превысил 30s пилотный лимит. Сохранены stack/log/JSON. DEX packaging исправлен, лимит холодного QA-прогона увеличен; последующие полные прогоны прошли. Первый compact test имел ранний assert после системного Back; добавлено ожидание фактического отображения. Старые mid-fade/white screenshots сохранены в attempts; новые снимаются после native compositor settle. Эти неудачи не удалены и не выдаются за PASS.

## Открытая приёмка

См.[UX before/after](UX_BEFORE_AFTER.md),[product acceptance](PRODUCT_ACCEPTANCE.md),[known issues](KNOWN_ISSUES.md),[manual guide](MANUAL_TEST_GUIDE.md),[ML summary](ML_TEST_SUMMARY.md). Финальные кадры — в этом каталоге; все настоящие, получены на Android. Для телефона и добровольного русского диалога подготовлены инструкции V1.1. Human Review ZIP не содержит APK, SDK, модели, аудио или секреты.

## Дополнительный ручной путь SAF

На интеграционном APK `5cc933fe…ada4909` до последней правки только меню экспорта выполнены реальные действия системного DocumentsUI: public M4A → fixed1 → GigaAM Worker → Room → UI → JSON. Получены две непустые реплики,11306ms,expectedSpeakers1/clusteringMode fixed/thresholdApplied false. [JSON](../../test-evidence/v1.2/saf-m4a-fixed1-transcript.json),[происхождение и scope](../../test-evidence/v1.2/saf-m4a-fixed1-proof.json). Это mono, не русский диалог.

Через тот же picker импортирован55-byte некорректный MP3: import не упал, Worker завершился ERROR, UI объяснил восстановление, в технических подробностях сохранён `Failed to instantiate extractor.`. [Proof](../../test-evidence/v1.2/saf-corrupt-proof.json). Проверки других SAF providers и полного WAV/MP3 SAF-пути в V1.2 отдельно не выполнялись; все три decoder-формата проверены финальным suite.

Последняя ручная проверка обнаружила partially expanded меню экспорта на font1.3. В финальном APK оно раскрывается сразу и прокручивается, статус-иконки контрастны; [compact frame](36-product-export-options-compact130-360x640.png). Оба профиля прошли новые assert TXT/SRT/JSON visibility и fresh JSON==Room в ProductExperienceTest. Старые неудачные ручные попытки сохранены в attempts/manual.
