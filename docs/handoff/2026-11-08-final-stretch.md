# Handoff 08.11 ~04:00 — финальный отрезок до сдачи (stop coding 09:00, заморозка 06:00)

**Ветка:** `hack/final` (origin `XterrK/ReplikaAndroid`), HEAD `f9075a53`, запушено. Сборка 1.7 / code 9.
**Кандидат в релиз:** `app/build/outputs/apk/allInOne/app-allInOne.apk`, 839 901 555 Б,
sha256 `5e26ecc98d3090602dac6b0eacde1f378002660a3ede8d0d1406dbd8cad22fe3` (стоит на телефоне vivo).

## Сделано за ночь (после основного отчёта)
- Видео `artifacts/demo/demo.mp4` (2:05) + постер + README. Исходник HyperFrames: `C:\R\replika-video`.
- Шаг 14 (ASR параллельно с диаризацией) слит, но **выключен по умолчанию** (`ParallelAsrDiarPolicy.DEFAULT_ENABLED=false`):
  на ARM-телефоне выигрыша нет, на 13 мин перегрев (627 с ожидания). Итог — в `docs/STEP_14_PARALLEL_ASR_DIAR.md`.
- «Аналитика встречи» (кто сколько говорил) — чип на экране стенограммы, `domain/MeetingStats.kt`, тесты.
- JVM: 271 тест, 0 падений, 2 пропуска. Телефон: phoneFinal4/5 — транскрипты совпадают с phoneFinal3.
  RTF в phoneFinal5 (0,40/0,48) снят на горячем телефоне; для отчётов использовать phoneFinal3 (0,35/0,41/0,41).
- DER с допуском ±0,25 с — только измерение, в `docs/DEFENSE_UPDATE.md` (по итоговому JSON 15–23%, строго 18–28%).

## Дальше
1. GitHub Release: APK выше + sha256 + `demo.mp4`; в README убрать TBD про имя релиза. Запускать на Sonnet.
2. 07:00–08:30: XterrK делает репозиторий публичным + Pages = GitHub Actions; добавить `.github/workflows/pages.yml`
   по `site/README.md`, проверить ссылку без входа. Ссылку отправить до 09:00.
3. По желанию: скриншоты V1.7 (включая «Аналитику») для слайдов 1 и 6.

## Риски
- Не публиковать `local-dev/debug.keystore`, серийник телефона, приватную БД. Без force-push.
- Перед финальной сборкой удалять `app/build/outputs/apk` (иначе мёртвый хвост 208 МБ).
- Правила экономии: `memory/token-economy-rules.md`; все ответы пользователю — по-русски.
