# Установочная версия

Финальная сборка для Nuclear IT Hack — **REPLIKA 1.7 (versionCode 9)**.
APK и видео доступны в [релизе v1.7-hack-20261108](https://github.com/XterrK/ReplikaAndroid/releases/tag/v1.7-hack-20261108).

| Файл в релизе | Назначение |
| --- | --- |
| `REPLIKA-1.7-code9-AllInOne-arm64.apk` | Приложение для Android 8.0+; все модели внутри, 839 901 555 байт (≈ 840 МБ) |
| `REPLIKA-1.7-code9-AllInOne-arm64.apk.sha256` | Контрольная сумма APK |
| `demo.mp4` | Демонстрация на физическом телефоне, 1 минута |

SHA-256 APK (также в [SHA256SUMS](SHA256SUMS)):

```text
5e26ecc98d3090602dac6b0eacde1f378002660a3ede8d0d1406dbd8cad22fe3
```

Скачайте APK и файл `.sha256` в одну папку. Проверка на Linux / macOS:

```bash
# Linux
sha256sum -c REPLIKA-1.7-code9-AllInOne-arm64.apk.sha256
# macOS
shasum -a 256 -c REPLIKA-1.7-code9-AllInOne-arm64.apk.sha256
```

Откройте APK на телефоне и разрешите установку из этого источника либо установите
через компьютер:

```bash
adb install -r REPLIKA-1.7-code9-AllInOne-arm64.apk
```

При обновлении нашей сборки с той же подписью записи сохраняются. Первый запуск
распаковывает и проверяет модели; после этого приложение работает без сети.
Метрики и ограничения — в [TEST_RESULTS.md](../docs/TEST_RESULTS.md)
и [LIMITATIONS.md](../docs/LIMITATIONS.md).

## Прежние артефакты

[CURRENT.json](CURRENT.json) — сохранённые метаданные базовой **V1.6 (code 8)**,
используемые историческими отчётами. Этот файл не описывает релиз 1.7.
[SHA256SUMS](SHA256SUMS) содержит суммы релизной 1.7 и базовой 1.6.
Прежние метаданные и суммы сохранены в [archive/](archive/);
APK распространяются через GitHub Releases и локально не входят в Git.
Проверки экспериментального C2 сохранены в [отчёте этапа 4](../docs/STEP_04_DIARIZATION.md).
