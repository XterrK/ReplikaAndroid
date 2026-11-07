# Handoff 08.11 ~02:25 — финальный отрезок до сдачи (stop coding 09:00)

**Ветка:** `hack/final` (origin `XterrK/ReplikaAndroid`), HEAD `91f33ad5` (видео). Сборка 1.7 / code 9.

## Сделано
- Видео: `artifacts/demo/demo.mp4` (2:05, 1080p, тихая CC BY музыка, −25,5 LUFS) + `demo-poster.jpg`, README с таймкодами.
  Исходник HyperFrames: `C:\R\replika-video` (`build_comp.py` → `composition/`, `npx hyperframes@0.9.20 render --quality delivery`).
- Шум/GTCRN (шаг 15), ближайший говорящий (шаг 13), FP32 отклонён — в `docs/STEP_1x_*.md`, `docs/DEFENSE_UPDATE.md`.
- Ветка `claude/gallant-khorana-199242`, коммит `2abc667b` (шаг 14, ASR параллельно с диаризацией):
  JSON побитно совпадает, −11…−15% времени, +250–430 МБ пикового PSS (есть откат на последовательный путь).
  **Слита 08.11 ~02:30 с согласия пользователя: merge `72dffbf8`.** Тесты/сборка после слияния — см. ниже.

## Дальше (по порядку)
1. После слияния шага 14: JVM-тесты + чистая сборка APK (логи `C:\R\logs\step14-*.log`); установить на телефон в 04:30.
2. ~04:30 проверка на телефоне (пользователь подключает, экран разблокирован, stay-awake):
   `scratchpad\run_batch.ps1` / `EvaluationBatchTest#stagedCanonicalInputsThroughProductionWorker`, RU+EN, 13 мин.
   Гонять через подагента/рабочую сессию на Sonnet, отчёт ≤20 строк.
3. 06:00 заморозка кода → чистая сборка → GitHub Release (APK + sha256 + demo.mp4), README: убрать TBD про имя релиза.
4. 07:00–08:30: XterrK делает репозиторий публичным и включает Pages = GitHub Actions; добавить
   `.github/workflows/pages.yml` по `site/README.md`, проверить ссылку без входа. Ссылку отправить до 09:00.
5. По желанию: скриншоты V1.7 для слайдов 1 и 6 (см. `docs/DEFENSE_UPDATE.md`).

## Риски
- Не публиковать `local-dev/debug.keystore`, серийник телефона, приватную БД. Без force-push.
- Залоченный телефон замораживает приложение во время прогонов.
- Частицы на экране записи в видео не попали (на эмуляторе нет микрофона) — честно сказано в README.
- Правила экономии: `memory/token-economy-rules.md` (≤180k контекста, сборки/adb — на Sonnet/Haiku).
