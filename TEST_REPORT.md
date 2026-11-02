# Проверка REPLIKA V1.2 · 02.11.2026

Итог: **WORKING на API35/x86_64; продукт PARTIAL**. Полный отчёт — [TEST_REPORT_V1_2.md](docs/human-review/v1.2/TEST_REPORT_V1_2.md).

Проверенный commit реализации: `e4233e19c39170508d76c3450355ea4becf413a6`. Ветка `feature/replika-v1.2-product`, база `6e3c8abcd885345b185c2a9131f69eb02e4eb029`. Исходное состояние и прежние доказательства сохранены; push не выполнялся.

| Проверка | Результат |
|---|---|
| Clean debug APK+test APK |PASS,81 задача выполнена |
| JVM |25 passed,0 errors/failures/skipped |
| Android core |27 passed,включая Compose navigation |
| Review+Product Compose |3+5 passed |
| Compact360×640/font1.3/lightIME |7 повторных сценариев passed |
| Force-stop process persistence |1 passed |
| Холодный UI |3 новых PID,исправления и имя видны |
| ML regression |6 групп PASS,оба mono Worker на настоящих моделях |
| Pack+WAV/MP3/M4A+corrupt Worker |PASS в указанной среде |
|16KiB ZIP+ELF LOAD+dependencies |PASS статически для 8 .so; runtime не проверен |

Всего 36 уникальных Android/UI/process tests, ещё 7 compact-повторов и 1 повтор pack import; пропусков нет. [Логи/JSON](docs/test-evidence/v1.2/),[среда](docs/test-evidence/v1.2/environment.json). Эмулятор: Android15/API35/x86_64,4096-byte pages,2 CPU/3072MB,432×936@180dpi,-no-audio; сборка JDK17/SDK35/NDK27.2/AGP8.9.2/Kotlin2.1.20.

APK: `app/build/outputs/apk/debug/app-debug.apk`,129032636 bytes,1.2.0/code3,arm64-v8a+x86_64.

SHA-256: `5d06dc98cb4f896f2640e1d76c5821462dad8e26ec8a275991c8828d3cd5141c`.

BLOCKED: физический arm64, русский natural многоголосный end-to-end, API36/16KiB runtime. PARTIAL: реальный микрофон/звуковой тракт, длительные записи/peak RAM/thermal, ENOSPC и сторонний Share. Пустая Review очередь не доказывает правильность ASR; WER/CER/DER N/A. Native immediate abort/word timestamps/overlap separation NOT IMPLEMENTED.

UI/data/presentation изменены, ML/Alignment/Worker/native/model lock сохранены. Automatic/fixed zh clustering снова 7/4; pre100/post0 и «ничьих» сохранены. Скорость измерена сопоставимо в [BENCHMARKS](BENCHMARKS.md), без ранжирования качества моделей.

Первоначальные ANR,30s timeout,compact assert и transient screenshots сохранены в [attempts](docs/test-evidence/v1.2/attempts/). Финальный повтор после исправлений прошёл. V1.1 доказательства не перезаписаны.

Review ZIP: `review/REPLIKA_V1_2_HUMAN_REVIEW.zip`; его manifest содержит финальный Git SHA и хеши вложений. [UX сравнение](docs/human-review/v1.2/UX_BEFORE_AFTER.md),[проблемы](docs/human-review/v1.2/KNOWN_ISSUES.md),[ручная проверка](docs/human-review/v1.2/MANUAL_TEST_GUIDE.md).

Дополнительно: [ручной M4A/fixed1 SAF-проход](docs/test-evidence/v1.2/saf-m4a-fixed1-proof.json) и [corrupt MP3 SAF](docs/test-evidence/v1.2/saf-corrupt-proof.json) относятся к предыдущей 5cc до исправления только меню экспорта. Финальные Product UI tests проверили полностью видимые форматы и свежий JSON==Room в обоих профилях.
