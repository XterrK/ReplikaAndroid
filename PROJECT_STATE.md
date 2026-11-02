# REPLIKA V1.2 · состояние на 02.11.2026

**Продукт PARTIAL; эмуляторная приёмка WORKING.** Продуктовый проход выполнен поверх существующей V1.1. Независимое Human Review ещё не получено; физический arm64 и русский natural многоголосный end-to-end BLOCKED.

База: `validation/v1.1` / `6e3c8abcd885345b185c2a9131f69eb02e4eb029`, исходное дерево было чистым. Текущая ветка: `feature/replika-v1.2-product`. Проверенный commit реализации: `e4233e19c39170508d76c3450355ea4becf413a6`; финальный commit отчётов указан в manifest ZIP. Git bundle/старые APK/QA app data и Review V1.1 сохранены в `F:\ReplikaToolchain\v1.2-preservation\`; история и модели сохранены. Push не выполнялся.

## Возможности и область проверки

| Возможность | Статус | Подтверждение / предел |
|---|---|---|
| Clean APK/JVM/native static |WORKING |25 JVM,81clean tasks,8 .so ZIP+ELF,обе ABI |
| Android API35 x86_64 |WORKING |36 уникальных Android/UI/process+7 compact-повторов,без skipped |
| GigaAM/Silero/sherpa/Whisper |WORKING на AVD |Настоящие weights,оба full mono Worker,6 групп regression PASS |
| Русский multispeaker natural pipeline |BLOCKED |Нет допустимого диалога/reference; protocol готов |
| Физический arm64 |BLOCKED |Телефон не подключён;эмулятор не заменяет |
| API36/16KiB runtime |BLOCKED |Доступен только API35/4096;staticalignment не runtime proof |
| Diarization automatic/fixed |WORKING как конфигурация |zh auto7/fixed4;нет DER и независимой русской оценки |
| VAD/timestamps/pre-roll |WORKING на fixture |100 ms pre/0post,clamp/merge/partition,«ничьих»,global31 ms |
| Library |WORKING на AVD |Компактная шапка,реактивный поиск,rename,без ложного initial empty |
| Удаление с audio |WORKING на AVD |Подтверждение,cancel,owned/shared/external/symlink,busy,restart recovery;forcedSQLrollback не инжектирован |
| Transcript/player |WORKING по состоянию AVD |Связанныеwaveform/timeline/rows,tap/seek/±10/speed/pause/background;реальный звук не проверен |
| Editor/Room/export |WORKING на AVD |12 ручных имён+IME,font1.3,save/Undo/stale guard/draft recreation,force-stop |
| Smart Review |WORKING как очередь |Реальный 650 ms crop дал short flag;не confidence/не доказательство ASR |
| Recording |PARTIAL |Виртуальный MediaRecorder,pause/resume/background/save/decode;микрофон телефона не проверен |
| Форматы/ошибки |WORKING в пределах тестов |WAV/MP3/M4A decoder,corrupt Worker/PCM cleanup/oldrows;SAF-провайдеры отдельно |
| Models/diagnostics |WORKING на AVD |Оба ASR,packSHA,629 КБ для VAD,summary+отдельный JSON |
| Длительные записи/нагрев/peak |PARTIAL/BLOCKED |Нет phone/long acceptance;PSS snapshots,неpeak |
| Нехватка места/download-resume/external Share |PARTIAL |Есть guards/errors/chooser;forcedENOSPC иreceivers не выполнены |
| Немедленный JNI abort/word timings/separation |NOT IMPLEMENTED |Отмена ждёт native call;timestamps сегментные |
| Second ASR opinion |NOT IMPLEMENTED |Полезность исследована,доказательств для фонового Whisper нет |
| Human Review package |WORKING как материалы |Реальные PNG,отчёты,rawJSON;внешнее UX-одобрение не заявлено |

## Артефакты и риски

APK: `app/build/outputs/apk/debug/app-debug.apk`,129032636 bytes,version1.2.0/code3.

SHA-256: `5d06dc98cb4f896f2640e1d76c5821462dad8e26ec8a275991c8828d3cd5141c`.

Review ZIP: `review/REPLIKA_V1_2_HUMAN_REVIEW.zip`; без APK/SDK/моделей/аудио/секретов. [TEST_REPORT](TEST_REPORT.md),[UX](docs/human-review/v1.2/UX_BEFORE_AFTER.md),[KNOWN_ISSUES](docs/human-review/v1.2/KNOWN_ISSUES.md),[ML timings](BENCHMARKS.md).

Три главных риска до 6 ноября: (1)нет приёмки русского многоголосного диалога и независимой разметки; (2)нет физического arm64/offline/audio/16KiB runtime подтверждения; (3)длинный PCM/native memory,нагрев и ожидание отмены ещё не проверены на телефоне. Нельзя выводить их готовность из clean build или эмуляторных скриншотов.
