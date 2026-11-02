# REPLIKA V1.2.1 · All-in-One · 02.11.2026

**WORKING на API35/x86_64 после восстановления среды; продукт PARTIAL. Физический vivo X300/arm64 BLOCKED.**

База `ba81ad00d8808890b1418730559c60dada88a775`; ветка `feature/all-in-one-offline-apk`; проверенный commit реализации `974ad6a1a027c0b5560c4e467df5546171de2ed3`. Последующий commit содержит отчёты и доказательства. Push не выполнялся. Git bundle, исходные APK, исходные документы и app data сохранены в `F:\ReplikaToolchain\v1.2.1-preservation\20261102T171315Z`.

## APK и состав

Основной файл: `F:\Hackathons\ReplikaAndroid\release\REPLIKA-V1.2.1-AllInOne-arm64.apk`.

377401829 байт; SHA-256 `72fb824fc4356f72b22a57a1f7ac8a3221c29361d7feec35c0d1710cf2554aaa`.

Стандартный APK: `release/REPLIKA-V1.2.1-Standard.apk`,129392247 байт; SHA-256 `3c4412b29cf0e7d94e5283658d2feb9da96e356bf9df05325cae7aa18195d92f`.

Исходный V1.2 сохранён отдельно: `release/REPLIKA-V1.2-Standard-preserved.apk`, SHA-256 `5d06dc98cb4f896f2640e1d76c5821462dad8e26ec8a275991c8828d3cd5141c`.

Version1.2.1/code4, minSdk26/target35, прежний applicationId и debug signing. Основной APK содержит только arm64-v8a, один stored asset ZIP281336043B. Внутри восемь файлов365008680B: GigaAM encoder INT8+decoder+joiner+tokens, Silero VAD, Pyannote segmentation, 3D-Speaker embeddings, Whisper tiny multilingual. Все восемь исходных SHA-256 сохранены, повторных загрузок/квантования не было. DEFLATE сжимает контейнер; DEX остаётся ZIP_STORED. В APK проверены25 license/notice assets. [Состав и SHA](test-evidence/v1.2.1/generated-pack-verification.json),[лицензии](ALL_IN_ONE_LICENSE_AUDIT.md),[установка](ALL_IN_ONE_INSTALL.md).

## Фактическая среда

Windows WHPX AVD Replika35v11, Android15/API35/x86_64,2vCPU/3072MiB,4096-byte pages,432×936px/180dpi, font1.0, SwiftShader,-no-audio,-no-snapshot. QA package `ru.replika.offline.aioqa` изолирован от исходной REPLIKA. [Среда](test-evidence/v1.2.1/environment.json),[ADB обеих служб](test-evidence/v1.2.1/final-adb-devices.json). Физического телефона нет. SDK/imageAPI36 и16KiB runtime отсутствуют.

JDK17.0.17,Gradle8.13,AGP8.9.2,Kotlin2.1.20,SDK35,NDK27.2.12479018,CMake3.22.1. Clean Gradle-проход84tasks успешен; после интеграционных исправлений выполнена актуальная multi-variant сборка156tasks. Финальный APK относится к актуальной сборке. Отдельно пересобран QA test APK после адаптации ожиданий advanced controls. Логи сохранены в test-evidence/v1.2.1/. Обычный task graph не включает prepareEmbeddedModelPack; стандартный APK не содержит ZIP моделей.

## Первый запуск без сети

Чистая повторная установка QA APK после cold boot. Ни модели, ни внешний ZIP перед этой приёмкой в QA не копировались. Включён авиарежим; Wi-Fi/mobile data выключены, IP route пуст. Для автоматизации заранее выдано только разрешение уведомлений; микрофон не использовался при подготовке.

|Сценарий|Результат|Фактические данные|
|---|---|---|
|Чистый первый запуск|PASS|29437ms installer;8 extracted/8 published;SHA проверены;доступная Library|
|Force-stop→повторный запуск|PASS|844ms;8 validSkipped,0 extracted/0 published;времена файлов неизменны|
|Прерывание в PREPARING|PASS|Процесс принудительно остановлен;live models ещё отсутствовали;verified staging сохранён|
|Повтор после прерывания|PASS|23541ms;2 reusedStage/6 extracted/8 published;Library открылась|
|Новый процесс после inference|PASS|Повторно проверены SHA всех8 файлов,mtime и другой PID;без распаковки|

Время installer отделено от установки APK, первого кадра и UI-автоматизации. [JSON/PNG/XML успешного прохода](test-evidence/v1.2.1/first-launch-after-cold/),[полные SHA после cold restart](test-evidence/v1.2.1/qa-cold-prepared-models.json). Подготовка выполняется на IO, память ограничена потоковыми буферами; все staged файлы проверяются до публикации. Gate и Worker.awaitReady препятствуют загрузке промежуточного комплекта.

**Первая попытка FAIL по UX:** модели8/8 прошли проверку за89178ms, но появился ANR и доступная Library не была подтверждена. [Исходные снимки/trace](test-evidence/v1.2.1/first-launch/). Главный поток ожидал RenderThread/ART; CPU pressure≈86%, ANR системных приложений появились ранее. После cold boot тот же APK заново установлен с нулевыми QA данными и прошёл сценарий. Код приложения ради этого повтора не менялся. Причина полностью не установлена; успешный повтор не объявляется исправлением ANR.

## Автоматические проверки

|Группа|Результат|
|---|---|
|JVM|25 passed,0 failed/errors/skipped|
|AIO safety+real ML+UI|26 passed|
|Legacy storage/media/model/ML|23 passed|
|Compose navigation/review/virtual recording|4 passed|
|Правки после отдельного force-stop|1 passed|
|Повтор cold file hashes|1 passed повторно|

Итого54 уникальных JUnit Android/UI метода,55 запусков,0 failures/0 skipped. Два существующих полных Worker-метода PipelineTest выполняются внутри AIO wrapper и не посчитаны вторично как самостоятельные JUnit cases. Все старые assertion paths выполнены. [Поимённая сводка](test-evidence/v1.2.1/test-summary.json),[логи](test-evidence/v1.2.1/).

16 installer tests используют явно обозначенные маленькие ZIP fixtures, не ML-заглушки продукта: hash/CRC corruption, missing/duplicate/unsafe paths, oversized metadata, нехватка места через availableSpace, interrupted extraction/publication, stage reuse, неизменность валидных моделей. Это проверка реального установщика на Android, но не физическое заполнение диска до ENOSPC. ERROR screen/font1.3/retry дополнительно проверен как явно помеченный UI fixture; он не выдаётся за настоящий сбой большого APK.

Проверены реальные WAV/MP3/M4A decoder, corrupted import/Worker с сохранением предыдущих строк, редактор/Undo/long speaker names/keyboard, seek/speed/background pause, удаление owned audio, исправленный экспорт, Smart Review на реальном коротком speech crop. Виртуальный MediaRecorder прошёл pause/resume/background/save/decode(2756ms); это не микрофон телефона. [Регрессионные JSON](test-evidence/v1.2.1/regression/files/),[правки==экспорт после restart](test-evidence/v1.2.1/regression/files/edit-persistence.json).

## Настоящий ML после подготовки из APK

Полный русский **mono** вход11290ms → Silero → Pyannote/3D-Speaker → GigaAM либо Whisper → Alignment → Room → Workspace → JSON. Оба backend дали READY и2 непустых сегмента с корректными границами. Внешнего model pack в QA в момент этих Worker-прогонов не было. [Доказательство обоих Worker](test-evidence/v1.2.1/acceptance/files/all-in-one-real-worker-acceptance.json),[GigaAM JSON](test-evidence/v1.2.1/acceptance/files/android-transcript.json),[Whisper JSON](test-evidence/v1.2.1/acceptance/files/android-whisper-transcript.json).

GigaAM:ASR load1820ms,pure inference3559ms,pipeline15969ms,конечныйPSS181341KiB. Whisper:126ms/32350ms/40060ms/PSS177148KiB. Pipeline scope — validation→ASR release; финальный Room commit и UI/export исключены из этого таймера и подтверждены отдельно. Это не peak RAM и не контролируемые cold/warm runs. WER/CER N/A; вывод о качестве моделей не делается. [Методика и отдельные показатели](../BENCHMARKS.md).

Отдельный zh diarization regression:automatic7/fixed4,DER N/A. Это не доказательство русского многоголосного end-to-end. Pre-roll100ms/post0 сохранён; настоящий GigaAM Worker вновь начинается с «ничьих». В экспериментальном JSON вариант current означает контроль pre0, а не текущую настройку Worker. Глобальные timestamps/веса/алгоритмы не менялись. Естественного русского многоголосного диалога с согласием участников и reference нет: **BLOCKED**.

## Обновление и стандартная сборка

Same-ID x86_64 AIO QA APK установлен поверх исходной V1.2/code3 без clear/uninstall: **все значения**9 Room recordings,13 segments,1 speaker и11 owned audio hashes сохранены.8 model file stats остались прежними;report8 validSkipped/0 extracted. Подпись совпадает с V1.2. [Точное сравнение](test-evidence/v1.2.1/upgrade-preserves-data.json).

Затем установлен отдельный стандартный code4 APK: импорт виден без advanced, bundled banner отсутствует, provisioning job не запускается;Room/audio/model stats также неизменны. [Стандартная совместимость](test-evidence/v1.2.1/standard-compatibility.json). Ранний uiautomator dump вернул null root; после ожидания фактическая Library/Models подтверждены. Все разрушительные fixture-тесты выполнялись только в изолированном QA package. Физическое arm64-обновление не проверялось.

## Native и ограничения

**PASS статически**:все4 arm64 .so и4 x86 .so в соответствующих AIO APK,ZIP16KiB alignment,ELF LOAD alignment,ABI иDT_NEEDED. ZIP alignment сам по себе не считается полным доказательством. [arm64](test-evidence/v1.2.1/arm64-static.json),[QA](test-evidence/v1.2.1/qa-static.json),[стандартный APK](test-evidence/v1.2.1/standard-static.json),[подпись](test-evidence/v1.2.1/signature.json),[25 notices](test-evidence/v1.2.1/packaged-notices.json).

BLOCKED:physical arm64/vivo/API36/16KiB runtime,физический микрофон и естественный русский multispeaker. PARTIAL:первоначальный ANR,реальный ENOSPC,long audio/peak RAM/thermal/vendor background policy/external Share receiver. NOT IMPLEMENTED:немедленный native abort,word timestamps,overlap separation,автоматический второй ASR для каждой реплики. Это прежние ограничения, не новые обещания All-in-One. [Проблемы](ALL_IN_ONE_KNOWN_ISSUES.md),[реальные экраны](human-review/v1.2.1/README.md).
