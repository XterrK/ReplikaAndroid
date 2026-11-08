# Проверка REPLIKA V1.2.1 · 02.11.2026

**WORKING на API35/x86_64; продукт PARTIAL; physical vivo/arm64 BLOCKED.** [Полный отчёт](../../ALL_IN_ONE_TEST_REPORT.md).

Commit реализации `974ad6a1a027c0b5560c4e467df5546171de2ed3`,база `ba81ad00d8808890b1418730559c60dada88a775`;ветка `feature/all-in-one-offline-apk`. Итоговый HEAD после отчётов указан в Git. История, исходные APK, документы и app data сохранены;push не выполнялся.

25JVM passed;54 уникальных Android/UI JUnit метода,55 запусков включая cold-повтор,0 skipped/failures. Внутри AIO acceptance переиспользованы два настоящих full Worker-метода старого PipelineTest. Подготовка без сети29.437s;повтор.844s без распаковки;force-stop recovery2 reused/6 extracted/8 published. [Сводка](../../test-evidence/v1.2.1/test-summary.json).

Оба настоящих mono Worker прошли с моделями только из APK;VAD/diarization/ASR/Room/UI/export подтверждены. WAV/MP3/M4A,коррупция,редактор/Undo/seek/Smart Review/virtual recording и persistence прошли. Natural русский многоголосный pipeline **BLOCKED**. Native ZIP+ELF16KiB **PASS статически**,runtime16KiB/API36/physicalarm64 **BLOCKED**.

Обновление code3→AIOcode4 сохранило все значения9recordings/13segments/1speaker,11audio hashes и8model stats. Последующая стандартная сборка также сохранила данные и ручной импорт.

Первый запуск на деградировавшем AVD **FAIL/ANR**,сохранён. После cold boot и чистой переустановки того же APK сценарий прошёл;исправление причины в коде не заявляется. [Ограничения](../../ALL_IN_ONE_KNOWN_ISSUES.md).

APK:`release/REPLIKA-V1.2.1-AllInOne-arm64.apk`,377401829B.

SHA-256:`72fb824fc4356f72b22a57a1f7ac8a3221c29361d7feec35c0d1710cf2554aaa`.

[Установка одним файлом](../../ALL_IN_ONE_INSTALL.md),[экраны](../../human-review/v1.2.1/README.md),[ML timings](BENCHMARKS.md). Предыдущие V1.1/V1.2 доказательства не перезаписаны;[V1.2 report](../../human-review/v1.2/TEST_REPORT_V1_2.md) сохранён.
