# REPLIKA V1.3 · состояние на 04.11.2026

**PARTIAL — кандидат с single-speaker bypass и улучшениями IO/чтения; automatic diarization и физический vivo не приняты.**

Продолжение `2f84a633f5c3b51accd99ac7510db70570f61dde`; существующие записи и schema 1 сохранены, push не выполнялся. Подробности: [TEST_REPORT_V1_3.md](TEST_REPORT_V1_3.md), [REAL_DEVICE_FINDINGS.md](REAL_DEVICE_FINDINGS.md), [PERFORMANCE_ANALYSIS.md](PERFORMANCE_ANALYSIS.md), [DIARIZATION_FIX_REPORT.md](DIARIZATION_FIX_REPORT.md), [VAD_BOUNDARY_REPORT.md](VAD_BOUNDARY_REPORT.md).

- All-in-One arm64: `release/REPLIKA-V1.3-AllInOne-arm64.apk`, versionCode 5, все 8 прежних файлов моделей включая Whisper; SHA-256 в соседнем `.sha256`.
- Три режима говорящих; single действительно не запускает Pyannote/embedding/clustering. У automatic нет универсального ограничения числа участников; новый estimator не принят.
- GigaAM default, Whisper tiny экспериментальный. CPU 2 threads по умолчанию, 1 в умеренном профиле; 4 только в диагностическом эксперименте.
- Блочное чтение PCM; 100 ms pre-roll сохранён, обработаны короткие края выравнивания. Жёсткие ASR-разрезы 20 s и отсутствие word alignment остаются риском.
- Диалог и чистое чтение из одной Room-модели, безопасные логические группы, копирование, синхронные ручные правки.
- Thermal API listener/polling, пауза SEVERE+, отмена ожидания, технические stage logs без audio/text. Уже начатый JNI не прерывается мгновенно.
- Android update 4→5 на эмуляторе: все 334 файла DB/files побайтово сохранены. Приватные backup/bundle/старый APK: `F:\ReplikaToolchain\v1.3-preservation`.
- Доступен только API35 x86_64 AVD; физический vivo, его исходная запись и независимый размеченный RU corpus отсутствуют. RTF/peak/thermal/качество на телефоне не установлены.

Проверки V1.3: 38 JVM, 60 разных Android методов прошли на API35/x86_64 без failures/skips. Single Worker на контролируемом повторе 247.589 s: 55.341 s, все ID 0. Automatic probe 247.590 s: 1 участник, но four-speaker fixture остаётся 7 вместо 4; automatic quality acceptance FAIL. Старый/новый GigaAM Worker 11.290 s: 21.455/12.809 s на AVD с неконтролируемыми кэшами/нагрузкой. Исходный vivo не проверен.

Ниже сохранено предыдущее состояние V1.2.1 для истории; его числа не являются свежими результатами V1.3.

---

# REPLIKA V1.2.1 · состояние на 02.11.2026

**Продукт PARTIAL. All-in-One работает в проверенной среде API35/x86_64; vivo X300/physicalarm64 BLOCKED.**

Ветка `feature/all-in-one-offline-apk`;база `ba81ad00d8808890b1418730559c60dada88a775`(исходное дерево чистое). Commit реализации `974ad6a1a027c0b5560c4e467df5546171de2ed3`;финальный HEAD включает последующие отчёты. Git bundle/прежние APK/app data сохранены в `F:\ReplikaToolchain\v1.2.1-preservation\20261102T171315Z`. Push не выполнялся.

|Возможность|Статус|Основание/предел|
|---|---|---|
|Один APK со всеми моделями|WORKING как артефакт|arm64-only377401829B,8 файлов моделей365008680B,все SHA|
|Zero-click offline provisioning|WORKING на AVD|чистая установка,airplane,WIFI/data off,29.437s,реальная Library|
|Повтор/закрытие/recovery|WORKING на AVD|.844s без extract;force-stop resume2+6→8;SHA/mtimes/PID|
|Защиты installer|WORKING в тестах|16Android fixtures,path/CRC/hash/space/partial publication;actualENOSPC PARTIAL|
|GigaAM/Whisper/VAD/diarization|WORKING на AVD|настоящие8weights из APK;оба полных mono Worker иlegacyMLregressions|
|Русский natural multispeaker|BLOCKED|нет допустимого размеченного диалога;mono иzh diarне заменяют|
|Room/правки/экспорт/плеер/review|WORKING на AVD|все старые assertion paths+5ProductUI+persistence;ML алгоритмы не менялись|
|Recording|PARTIAL|virtualAAC2756ms,pause/resume/background/save/decode PASS;phone microphone BLOCKED|
|V1.2→AIO upgrade|WORKING на AVD|sameId,code3→4;все значения9records/13segments/1speaker,11audio hashes,8model stats сохранены|
|Стандартный APK/manual import|WORKING на AVD|отдельная сборка,импорт сохранён,provisioning отключён,pack API tests PASS|
|Native16KiB|PARTIAL|ZIP+ELFLOAD+deps всех4arm64 .so PASS;runtime16KiB/API36 BLOCKED|
|Первоначальный ANR|PARTIAL|первая UX-попытка FAIL;coldreinstall того же APK PASS;корень причины не объявлен устранённым|
|Физический vivo/arm64|BLOCKED|нет телефона;никакой подмены эмулятором|
|Long audio/peakRAM/thermal/share receivers|PARTIAL/BLOCKED|переносятся ограничения V1.2;PSS snapshots не peak|
|Native immediate abort/wordtimes/overlap separation|NOT IMPLEMENTED|сегментные timestamps;отмена ждёт nativecall|

Проверки:25JVM;54uniqueAndroid/UI JUnit+1coldrepeat,0failed/skipped.2существующих Worker-метода вызваны внутри нового acceptance wrapper. [Отчёт](docs/ALL_IN_ONE_TEST_REPORT.md),[поимённые логи](docs/test-evidence/v1.2.1/test-summary.json).

APK:`F:\Hackathons\ReplikaAndroid\release\REPLIKA-V1.2.1-AllInOne-arm64.apk`.

SHA-256:`72fb824fc4356f72b22a57a1f7ac8a3221c29361d7feec35c0d1710cf2554aaa`.

Стандартный:`release/REPLIKA-V1.2.1-Standard.apk`;прежнийV1.2:`release/REPLIKA-V1.2-Standard-preserved.apk`. Модели/APK/audio/SDK не добавляются в Git. [Установка](docs/ALL_IN_ONE_INSTALL.md),[лицензии](docs/ALL_IN_ONE_LICENSE_AUDIT.md),[экраны](docs/human-review/v1.2.1/README.md),[пределы](docs/ALL_IN_ONE_KNOWN_ISSUES.md).

Три риска перед6ноября:1)нет приёмки физическогоarm64/API36/16KiB/микрофона и есть не до конца объяснённый ANR AVD;2)качество naturalRUдиалога/пересечений и дробление speaker IDs не подтверждены(zh auto7/fixed4,DER N/A);3)377MB APK+365MB weights,свободное место и native memory/нагрев длинных записей требуют проверки на телефоне.
