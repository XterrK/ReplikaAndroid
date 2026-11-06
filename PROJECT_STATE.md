# REPLIKA V1.6 — UI и перенос проекта · 06.11.2026

Продолжение пользовательских тестов V1.5: пользователь подтвердил улучшение распознавания, включая шёпот. В этом цикле ML-модели, усиление тихой речи, VAD, диаризация и схема Room не менялись.

Главная переработана: шар строго по центру, новая внутренняя опаловая поверхность AGSL с мягкими потоками и отражениями, согласованный Canvas fallback; голосовая шкала — отдельный слой из правой кромки на 88% высоты главной. Касания шара не подмешиваются в микрофонный уровень. Спокойная внутренняя анимация работает и до записи, останавливается вне RESUMED; reduced motion и thermal/power caps сохранены.

«Назад», видимая стрелка выхода и «Завершить» открывают одну нижнюю панель «Сохранить запись» / «Удалить запись». Запись на время выбора на паузе; закрытие панели восстанавливает только ранее работающую запись. Панель прокручивается на коротких экранах. Сохранение не доступно до завершения старта микрофона. После сохранения/удаления elapsed очищается; на главной старый таймер не показывается. Длительность сохранённого файла остаётся в библиотеке.

Текущие точки входа: [README](README.md), [передача на ноутбук](HANDOFF.md), [переносимая сборка](PORTABILITY.md), [отчёт V1.6](TEST_REPORT_V1_6.md), [визуальное исследование](docs/ui-v1.6/DESIGN.md). APK versionCode 8 / 1.6 использует прежние applicationId и сертификат подписи. Архив APK: `release/archive/`; прежний видеоэксперимент: `archive/video-production-fi-20261105/`. Корневые версионные отчёты и review evidence сохранены как история.

Финальные результаты и ограничения приведены в отчёте V1.6. Windows/ноутбук и физический GPU/энергопотребление пока не проверены в этом цикле; эмуляторные проверки не заменяют приёмку нового UI на телефоне. Automatic diarization остаётся прежним ограничением.

---

# REPLIKA V1.5 — состояние на 06.11.2026

Продолжение прямого пользовательского ревью C+B: холодная Light и нейтральная Graphite Dark, стартовая запись с интерактивным Liquid Voice Orb, отдельная библиотека и экспорт на главной. Перестроены waveform/transport и компактный Review; большие цели касания и самостоятельные реплики сохранены. Пузырь получает уровень из существующего рекордера, tap/drag действует только на упругую форму; правые шкалы независимо отображают реальный уровень микрофона.

Добавлен локальный импорт видео: извлекается только звуковая дорожка, исходное видео не изменяется. Проверяется временная шкала MP4, включая потерянную Android 9 начальную задержку. Журнал незавершённого импорта защищает локальные файлы при перезапуске. Whisper удалён из движка, интерфейса, JNI и нового комплекта моделей; старые стенограммы остаются читаемыми. Основная модель — GigaAM v3 E2E RNNT INT8 с greedy decoding. Ограниченное усиление тихого входа применяется только к временным ML-буферам. Room schema 1, VAD, диаризация, offline runtime и thermal gating сохранены; automatic diarization остаётся известным дефектом.

Проверки source11:80 JVM,97 уникальных Android-методов на API35 и33 на API28 прошли; первоначальные таймауты захвата/очереди сохранены, изолированные повторы успешны. На7 авторских студийных RU whisper test-записях Android Worker получил9/84 ошибок (WER10,714%,CER7,80%): выборочный RMS/headroom повтор VAD восстановил21 из23 слов фрагмента, полностью пропущенного первым проходом. Другие6 не входят в retry; ASR gain/оригинальные WAV/PCM/диаризация не меняются. Это небольшая студийная выборка, не физическая приёмка vivo. В спокойной записи cadence ограничивается30fps; речь и касания используют прежний максимум60 с сохранением thermal/power caps.

Финальная поставка и фактические результаты проверок описаны в [TEST_REPORT_V1_5.md](TEST_REPORT_V1_5.md), [ASR_QUALITY_V1_5.md](ASR_QUALITY_V1_5.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md) и [Human Review](docs/human-review/v1.5/REVIEW_GUIDE.md). Предыдущие V1.3/V1.4 APK, review ZIP и исходный HEAD ce345569377f0d7b60b383296f00f58b417986e0 сохранены; push не выполнялся. Прежние untracked video-production материалы не изменены.

Доступны эмуляторы API35 и API28; vivo X300 не подключён. Физическая реакция микрофона, скорость, батарея и нагрев телефона не подтверждены. Ослабленная обычная речь не заменяет проверку настоящего шёпота. Ниже сохранена история прежних версий; её числа не являются новыми измерениями V1.5.

---

# REPLIKA V1.4 — состояние на 05.11.2026

Editorial Intelligence (C+B) утверждён напрямую пользователем, включая Final Visual Direction Update. Реализованы две темы, локальный выбор оформления, Liquid Voice Orb (Compose Path / AGSL / Canvas) из существующего MediaRecorder, самостоятельные реплики и чистое Reading. Подробности: [TEST_REPORT_V1_4.md](TEST_REPORT_V1_4.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md), [Human Review](docs/human-review/v1.4/REVIEW_GUIDE.md).

Нативные ML/domain/Room/storage/C++ и models-lock совпадают с V1.3. Automatic diarization остаётся дефектом. Новый arm64 All-in-One — versionCode 6 / 1.4; V1.3 APK сохранён, исходный HEAD ce34556 и прежняя лаборатория архивированы в review/v1.4-baseline/. Изменения V1.4 оставлены reviewable в рабочем дереве, push не выполнялся. Прежние untracked video-production материалы не изменены.

Доступен API35 x86_64 эмулятор. Физическая микрофонная реакция на тихую/громкую речь и производительность/батарея/нагрев vivo X300 в V1.4 не подтверждены. Все итоговые проверки, APK SHA и ограничения перечислены в отчёте V1.4; ниже сохранена история V1.3 без переименования её чисел в новые измерения.

---

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
