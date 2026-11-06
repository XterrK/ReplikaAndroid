# Статус выполнения PLAN_19H

Начало: **2026-11-06 22:24:57 +03:00**. Даты новых коммитов — фактические, без backdating. Прежняя история сохраняется.

## Текущий этап

**Пункт 3 (D) — реализация и ASR-гейты готовы; профиль opt-in.** Реализация в `hack/task-03-vad-word-asr`, база `beeaff5`. Host dev raw13,321%, прежний holdout11,036%, reserve11,171%; Android5 raw43/442=9,729% против75/442 baseline, portgap0,226п.п.PASS. 125 Python /111 JVM /All-in-One/debug/test APK/static /2UI PASS. Обычная сборка сохраняет `v16`, кандидат включается явным флагом. Полная приёмка конвейера НЕ достигнута: automatic speaker count, word timing <200мс и скорость остаются открытыми. Legacy current-APK controlRTF4,739 и word4,605; причина отличия от исторического1,185 не установлена. C ещё не начат.

Последнее обновление: 2026-11-07T02:21:22+03:00.

| Пункт | Статус | Проверки / результат |
| --- | --- | --- |
| 0. Сохранение и GitHub | DONE | `artifacts/test-results/step-00/preservation.json` |
| 1. Jury JSON + default automatic | DONE | 89 JVM / All-in-One / static / 2 Android UI PASS |
| 2. Стенд оценки + baseline | DONE | 13host/5Android,65Python; corpusportgatePASS |
| 3. ASR по VAD + словные speaker IDs | IMPLEMENTED · opt-in | ASR host/native gates PASS; full timing/diarization/speed acceptance open |
| 4. Диаризация | NOT STARTED | Только после dev/holdout |
| 5. CPU/thermal/импорт | NOT STARTED | Отдельная задача |
| 6. Английский + стереозвонки | NOT STARTED | Отдельная задача |
| 7. Сдача, презентация, лендинг | NOT STARTED | Ответственность Codex; GLM/Kimi недоступны |
| 8. Опциональные задачи | NOT STARTED | Только при наличии времени |

## Ограничения и правила

- Одна задача за раз; отдельная ветка и коммит/PR. Общая ветка — `hack/final`.
- Сохраняем рабочее поведение V1.6; ML-параметры не меняем без измеренного выигрыша на dev и отсутствия регресса на holdout.
- GLM/Kimi нет; ответственность за выполнение, проверку и отчётность — у Codex.
- Свежий baseline пункта 2: 13 host-файлов и 5 файлов через Android Worker; гипотезы и независимые эталоны сохранены. Исторические цифры отдельно от результатов этого цикла.
- Веса, native `.so`, APK и приватный ключ не коммитятся; APK публикуются отдельно как release assets.
- GitHub-публикация выполняется по прямому поручению пользователя; репозиторий приватный.
- Вопросы организаторам не отправлялись: доступ к их чату и поручение на отправку отсутствуют.
- Сборочное окружение проверено в пунктах 0–2; после каждой задачи заново выполняются нужные проверки.

Журналы: [UPDATES.md](UPDATES.md), [DECISIONS.md](DECISIONS.md). План: [PLAN_19H.md](PLAN_19H.md).
