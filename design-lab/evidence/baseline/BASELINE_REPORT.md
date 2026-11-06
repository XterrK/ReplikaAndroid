# V1.3 baseline перед нативными изменениями V1.4

Дата: 2026-11-05. Git HEAD: `ce345569377f0d7b60b383296f00f58b417986e0`. Исходная ветка `feature/all-in-one-offline-apk`, создана `feature/replika-v1.4-visual`. До работы единственный untracked путь — `video-production-fi-20261105/`; он не менялся. Новые артефакты находятся только в `design-lab/` и отдельном concept ZIP. Native tracked source diff отсутствует. Push/reset/uninstall/clear data не выполнялись.

**Статус: PARTIAL baseline: 38/38 JVM, 59/60 различных Android методов подтверждены; один старый cross-launch mtime fixture не проходит. Это не финальная приёмка V1.4.**

## Сохранность

- V1.3 APK не перезаписан: `release/REPLIKA-V1.3-AllInOne-arm64.apk`, 377500137 bytes, SHA-256 `80f39d54d1d2b18e299c3820f4f21fee03aedbebd0a766bdf74cf171ff5a2fc2`. Хеш вычислен заново и совпадает с прежним `.sha256`.
- 102 ранее доступных screenshots проиндексированы с SHA-256: `screenshots-inventory.json`.
- Приватный snapshot до Android-тестов: `/mnt/f/ReplikaToolchain/v1.4-preservation/baseline-20261105/upgrade-before-private.tar`; 399 файлов DB/files, ~722 MiB. Он находится вне проекта и ZIP. `preservation.json` содержит только количество и version5/1.3. Перед snapshot пакет остановлен штатным force-stop, не очищен.
- Существующие instrumentation tests работают с QA fixtures в подготовленном AVD; они могут переписывать собственные QA-строки и установленные тестовыми сценариями модели. Это не проверка побайтового сохранения всех файлов вокруг upgrade; upgrade не выполнялся.

## Build и JVM

Команда: `REPLIKA_REUSE_RAM_CACHE=1 REPLIKA_BUILD_OFFLINE=1 python3 tools/build_local.py :app:assembleDebug :app:testDebugUnitTest :app:assembleDebugAndroidTest --rerun-tasks`.

**BUILD SUCCESSFUL, 78/78 задач executed, 12m1s.** Это принудительная повторная сборка, не удаление build cache через clean. Compiler warnings о deprecated icon/clipboard APIs сохранены. Финальная clean build V1.4 остаётся этапом после выбора и native implementation.

JVM: Domain18 + Presentation4 + ProductErrors3 + RecoveryV13 13 = **38 passed, 0 failures/errors/skips**. Свежие XML и summary в `jvm/`, полный build.log рядом.

## Android 15, существующая V1.3 All-in-One QA

Эмулятор `Replika35v11`, API35/x86_64, serial emulator-5556. Запуск сохранённым Windows emulator script без wipe-data/snapshot reset; старые app data сохранены. Использован существующий установленный V1.3 QA пакет с bundled weights и его instrumentation; свежий debug APK собран, но не установлен поверх него, чтобы не менять вариант provisioning до baseline.

Первый упорядоченный `tools/run_android_v13.py`: **60 разных методов, 50 passed, 10 failed**. Группы core36, ml3, warning1 прошли. Bundle real GigaAM+Whisper Worker прошёл. Recovery/PCM/threads/thermal/long single/automatic методы прошли; отдельный UI modes метод упал на clipboard. Затем UI-группа дала ошибки. Снятый настоящий Android screenshot показывает системный **System UI isn't responding**, перекрывающий UI; `android-system-ui-anr.png`, `system-anr-events.log`, `runtime-errors.log` сохранены. ANR не объявлен исправленным дизайном.

После штатного reboot без удаления данных адресно повторены восемь затронутых UI-методов и persistence: 6/8 UI и persistence прошли, два теста упали на setup/library timeouts при холодном старте. После прогретого запуска отдельно повторены эти два метода: **2 passed**. Clipboard, edit/recreate, отсутствие повторного inference при переключении, player seek/speed, export, correction save/undo/discard и persistence после process restart в итоге подтверждены прежними tests. Неудачные попытки не удалены и не переименованы в passing evidence.

Общий учёт: **71 execution, 60 различных методов; последний результат 59 passed / 1 failed / 0 skipped**. Поимённый индекс с попытками — `android-final-summary.json`. Первые логи — `android/`; адресные повторы — `android-ui-retry/`. Дополнительный полный ML-прогон после UI reboot не выполнялся: соответствующие методы уже прошли.

## Единственный остающийся fail

`AllInOneAcceptanceTest.preparedBundleHashesAndNoExtractionOnRepeatedLaunch` сравнивает current model lastModified с `files/all-in-one-prepared-models.json`, оставшимся от прошлой приёмки. Expected1793636363744, actual1793816630780. Приватный tar, снятый **до** тестов этой сессии, уже содержит encoder с mtime1793816630 seconds; старый expectation в том же snapshot отличается. Это доказывает stale cross-launch assumption до настоящего запуска, но не объясняет причину исторического изменения моделей. Evidence: `provisioning-stale-mtime.json`.

Старый fixture не удалялся, test assertion не ослаблялся, provisioning code не менялся ради зелёного отчёта. Повторное awaitReady без переписывания в процессе и ModelPack/installer tests не эквивалентны новому чистому offline provisioning. Его fresh isolated QA-проверка запланирована после native implementation.

## UI evidence и ограничения

`native-v13-reading-controlled.png` извлечён из app-private evidence после успешного warm UI-mode теста и просмотрен: настоящий Reading с controlled text и clipboard toast. Второй свежий файл при просмотре оказался предыдущим кадром Library/loading, хотя test проверил Dialogue semantics; он сохранён как `native-v13-dialogue-capture-race.png` и не выдаётся за Dialogue. Для исходного Dialogue сохранён честно обозначенный архивный `archived-v13-dialogue-controlled.png` из прежней V1.3 evidence. Это настоящие Android renders контролируемых fixtures, не ASR-результат записи vivo. Race screenshot acquisition требует отдельного исправления при native visual acceptance. Imagegen и browser captures находятся отдельно.

В конце thermal status0, overridefalse; native pipeline/policies не менялись. Реальный GigaAM/Whisper smoke на публичном WAV подтверждён, natural Russian multi-speaker quality и физический vivo не проверены. Пользовательский ~4min→~30s результат сохраняется как наблюдение, не измеренный здесь benchmark. Peak RAM/FPS/jank/energy/physical microphone не измерялись. Automatic diarization quality остаётся известной отдельной проблемой.

## Воспроизведение UX-дефекта без изменения production

`design-lab/probes/WarningProvenance.java` вызывает compiled production Kotlin classes. VAD[0,6000], diarization[200,6000]speaker0 → один slice[0,6000] с причиной «Короткая граница диаризации…» → UI «Фрагмент короче 700 мс». `warning-provenance-reproduction.json` расположен уровнем выше baseline. Это воспроизведение механизма, не исходной записи vivo.
