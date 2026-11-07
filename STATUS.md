# Статус выполнения PLAN_19H

Начало: **2026-11-06 22:24:57 +03:00**. Даты новых коммитов — фактические, без backdating. Прежняя история сохраняется.

## Текущий этап

**Пункт 4 (C): реализован за флагом, все C-проверки завершены; готовится Git/Release.** Ветка `hack/task-04-diarization`, HEAD `6e6a35a`; изменения C пока не закоммичены. Все 48 fixed-K и 672 automatic SD-прогона сохранены. Выбран C2 на исходном ERes2Net: native threshold0,30/shift0,1, averageHCτ0,36 по чистым окнам с переназначением малых кластеров. Семь моделей и pack1.5 прежние.

**Настоящий Android-прогон 10/10 COMPLETE, оба числовых gate PASS.** Фиксированная пятёрка: rawWER43/442=9,7285% против host44/442=9,9548%, Δ−0,226244п.п. Dev8: K7/8, nativeDER0=18,2984805764% точно как host; порог fixedV1.6+2п.п.=28,8851817043%. Rawdev70/533=13,1332%, normalized16/532=3,0075%. Это ошибки↓, не доля успеха. Все10полныхQAфайлов:344реальных512dimвектора,56ASRчанков/2169токенов/767слов, точный Pythonreplay/JuryJSON; ресурсы освобождены, экран восстановлен. Androidscope:API35/x86_64/2cores, неARM/телефон. Независимый аудит native10:564проверкиPASS.

**173 JVM /345 Python /All-in-One/static/signature/UI2 PASS.** APKv2 SHA `a83bfe95cf7db72ddb65177a33586fdc52074a92759aa721212cc335f6b2a496` сохранён отдельно; V1.6/D/первыйC2APK сохранены. Обычный defaultv16 и исторические WorkData/manual/singlelegacy остаются рабочими. Source/model/code заморожены; первичный Git staging завершён, добавляются финальные отчёты.

Hostdev/holdout/reserve C2: K7/8,4/5,5/10; nativeDER18,2985/13,8896/22,4396%. FullnewNN23cases/audit3164PASS. C1centroid/eigengap реализован/ported/274parity; выбранный C2 — измеренная альтернатива, eigengap не применяет. Все неудачные trials и AndroidQA/launcher отказы сохранены. Дополнительно32новыхdevSDи902embeddingcalls проверилиminOff0,25/1,0 иC2shift0,25/0,5:все4вариантаухудшилиcount/DER, контрольныйC2неизменён; независимыйаудит3648PASS.

NaturalAMI:9actualSDcalls/6288independentauditchecksPASS означает целостность данных, не качество. GoldK4/4/3, C2K6/8/5(0/3), DER42,94/49,88/60,23%; третий хужеbaseline на2,2794п.п. Общая точность естественного диалога не принята, параметры по AMI не подбираются. Word-time/speed/ARM иполныйпроектacceptance открыты; LLM/Lite/лендинг не начинались.

Последнее обновление: 2026-11-07T06:14:46+03:00.

| Пункт | Статус | Проверки / результат |
| --- | --- | --- |
| 0. Сохранение и GitHub | DONE | `artifacts/test-results/step-00/preservation.json` |
| 1. Jury JSON + default automatic | DONE | 89 JVM / All-in-One / static / 2 Android UI PASS |
| 2. Стенд оценки + baseline | DONE | 13host/5Android,65Python; corpusportgatePASS |
| 3. ASR по VAD + словные speaker IDs | IMPLEMENTED · opt-in | ASR host/native gates PASS; full timing/diarization/speed acceptance open |
| 4. Диаризация | IN PROGRESS | Native10/10 gates PASS; devK7/8/DER18,30%; fixed5WER9,73%;173JVM/345Py;Git/Releaseготовятся |
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
