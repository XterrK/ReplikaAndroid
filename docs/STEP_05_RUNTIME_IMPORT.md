# Пункт 5: CPU, термоконтроль и импорт

**PAUSED_BY_USER_AFTER_STEP05 — 2026-11-07T12:37:46+03:00.** Реализация и текущие
проверки пункта5 завершены; пользователь попросил сохранить контрольный срез и
передать его другому агенту. [Передача](../HANDOFF_NEXT_AGENT.md). Пункт6 не начат;
новые работы — только по новой команде пользователя.
После терминального завершения всех NN root остановил собственный эмулятор5558
и Windows ADB5038; [команды](../artifacts/test-results/step-05/user-pause-test-service-stop-v1.json)
и [финальная проверка](../artifacts/test-results/step-05/user-pause-test-services-final-v1.json)
подтверждают отсутствие live owned test services. Linux5037 не тронут; AVD-данные
и установленные приложения телефона не удалены. Фоновые тесты не оставлены.
Ветка `hack/task-05-runtime-import` создана от merge `87f669a`. В этом пункте
добавлена явная политика потоков `auto_v1` с диагностикой фактических стадий;
проверены ожидание охлаждения и отмена, настоящий путь URI → локальный файл → PCM,
системный выборщик и сохранение прежних данных. Это позволяет использовать
поддерживаемое число потоков на разных устройствах и проверять его влияние на
качество, сохраняя старые задания и legacy-поведение.

Текущий результат: **192 JVM / 370 Python / APK/static/signature PASS**,39 host CPU
case-runs,20 x86 native case-runs, ARM10/10 и942 независимые проверки, три длинных
ARM Worker и1004 проверки, ps16k one120 PASS; импорт13 форматов, thermal/UI/picker/
регрессия/legacy/compact подтверждены ниже. Это повторные регрессионные входы,
не39/20 новых независимых записей. Источники, APK и семь моделей после проверок
не менялись. Цель RTF≤0,3 на флагмане не достигнута; прежний x86 performance12
остаётся FAILED. Готовность контрольного среза не означает приёмку всего проекта, естественного
диалога, word-gold, ARM16KiB/M1 или причинного ускорения.

Приоритет [PLAN_19H.md](../PLAN_19H.md): **§0.4 > §0.3 > §0.2 > §0.1**.
Основная метрика — raw WER с пунктуацией и регистром; GigaAM v3 E2E сохраняется.
LLM, Lite и лендинг не входят в этот пункт и не добавляются в критический путь до
завершения проверок конвейера. GLM/Kimi недоступны; ответственность остаётся у Codex.

## Проверенная исходная база

Пункт C завершён для экспериментального C2 по зафиксированным монтажным критериям:
[acceptance.json](../artifacts/test-results/step-04/acceptance.json),
[отчёт C](STEP_04_DIARIZATION.md). Commit `b619519`,
[PR #4](https://github.com/XterrK/ReplikaAndroid/pull/4) объединён как `87f669a`;
[Release C2](https://github.com/XterrK/ReplikaAndroid/releases/tag/hack-step04-20261107)
и локальные/серверные digest V1.6, D и C2 проверены в
[записи публикации](../artifacts/test-results/step-04/github-publication.json).

| Проверенная база C | Результат | Граница доказательства |
| --- | --- | --- |
| Полный Android-пакет | 10/10 COMPLETE; независимый аудит 564 PASS | API35, x86_64, два ядра; без вывода о скорости ARM/телефона |
| Dev | Правильное K 7/8; native DER0 18,2984805764% | Авторский монтажный корпус; предел fixed V1.6 + 2 п.п. — 28,8851817043% |
| Фиксированная пятёрка | Raw WER 43/442 против host 44/442; Δ−0,226244 п.п. | Взвешенный корпусный допуск 0,5 п.п.; отдельный выброс сохранён |
| Сборка и тесты | 173 JVM / 345 Python / All-in-One / static / подпись / 2 UI — PASS | Это результаты C, а не новой runtime-политики |
| Jury JSON | Строгая схема и native-восстановление всех 10 файлов подтверждены | Диагностический JSON остаётся отдельным форматом |
| Веса и defaults | Семь исходных файлов, pack1.5; обычный `v16` | C2 остаётся явным экспериментальным профилем |

APK C2 v2: **305 478 017 байт**, SHA256
`a83bfe95cf7db72ddb65177a33586fdc52074a92759aa721212cc335f6b2a496`.
Новая политика потоков не наследует эти результаты автоматически. Общая приёмка
естественного диалога, независимого времени слов, целевой скорости и всего проекта
остаётся открытой; отрицательные результаты AMI сохраняются в отчёте C.

## Первые результаты пункта 5

До первого NN-вызова зафиксирован
[протокол CPU](../configs/eval/cpu-auto-v1-protocol.json): последовательные полные
варианты 2/1/4 потока на восьми dev и пяти уже просмотренных holdout-записях.
Каждая группа отдельно должна сохранить raw/normalized WER, cpWER и native DER0
относительно C2; число записей с правильным K не должно уменьшиться. Это
регрессионная проверка, не слепой holdout. В инференс передавался только automatic −1.

Все три варианта завершили по 13 новых SD/GigaAM-прогонов и отдельное измерение
чистых окон. Независимый аудитор не запускал NN: он повторно проверил хеши,
параметры стадий, C2 из реальных векторов, слова из токенов и все метрики по
отдельным эталонам.

| Потоки | Полнота | Проверок аудита | Dev: raw / normalized / cpWER | Holdout: raw / normalized / cpWER | Качество |
| ---: | ---: | ---: | --- | --- | --- |
| [2, контроль](../artifacts/test-results/step-05/independent-cpu-threads2-v1.json) | 13/13 | 1919 | 71/533 · 16/532 · 146/533 | 49/444 · 13/442 · 95/444 | PASS |
| [1](../artifacts/test-results/step-05/independent-cpu-threads1-v1.json) | 13/13 | 1906 | 71/533 · 16/532 · 146/533 | 49/444 · 13/442 · 95/444 | PASS |
| [4](../artifacts/test-results/step-05/independent-cpu-threads4-v1.json) | 13/13 | 1906 | 71/533 · 16/532 · 146/533 | 49/444 · 13/442 · 95/444 | PASS |

Во всех вариантах native DER0 — **18,2984805764% / 13,8895661248%**, правильное K —
**7/8 / 4/5**. Каждый файл точно совпал с C2 по Jury JSON, исходным/стабильным/
уточнённым интервалам, всем измеренным векторам, диагностике refiner, токенам,
временным меткам, словам и основным метрикам. На вариант сохранены 428 реальных
векторов по 512 компонент, 69 ASR-чанков, 2682 токена и 957 словных оценок.
Время исключено из равенства; это не доказательство ускорения.

Суммарно **5731 проверка PASS**, внешний аудитор и неизменяемый снимок имеют SHA256
`11fc1e516a2a0663ce950e755833b1cb9c9fd86b9c07ffba45a795239772b929`.
[Проверки отказа при регрессе и запрета перезаписи](../artifacts/test-results/step-05/independent-cpu-audit-self-test-v1.json)
сохранены отдельно. В Android подтверждено cores2 → auto1 и затем пройден полный
Worker-контроль; подробности ниже. Эти три host-прогона не проверяли reserve заново.

## Android: сборка и первый запуск проверок импорта

[Сборка auto v2](../artifacts/test-results/step-05/build-auto-v2/summary.json)
завершилась успешно за **1 мин 31 с**: **192 JVM-теста**, без ошибок и пропусков;
[полный Python-набор](../artifacts/test-results/step-05/python-cpu-collector/summary.json)
— **370 PASS**. All-in-One, debug и androidTest APK собраны. ARM64-пакет, семь весов,
ZIP/ELF alignment и прежняя подпись проверены
[статически](../artifacts/test-results/step-05/build-auto-v2/all-in-one-static.json).
Реальный ARM и Android runtime с 16 KiB страницами этим не проверены.

Сохранён `release/REPLIKA-Hack-Step05-AutoCPU-AllInOne-arm64.apk`:
**306 315 573 байта**, SHA256
`ca18309f626d431d0bd7bb4c649a2a3ae77f3ef3b75f7f1bcb47c83bf449e15e`.
Сертификат прежний: `f40399356577bcd0a5c220818ba13e9686768a02830a7f6e3af81d5a487947ab`.
Debug и тестовый APK установлены поверх существующих данных, без wipe.
Это локально сохранённый кандидат; публикация нового Release пока не заявляется.

[Первый Android-прогон](../artifacts/test-results/step-05/android-import-thermal-v1/instrumentation.log)
дал **6 PASS и 1 FAIL из 7**. Все шесть методов `Plan19ImportFormatsTest` прошли:
реальный Content URI → MediaImporter → системный декодер → PCM для всех 13 файлов,
повторный URI с независимыми UUID-файлами, пустой/повреждённый/отсутствующий источник,
обрезанный WAV, отмена после фактических байтов копирования и после кадров декодера.
Проверялись сохранность источника и чужого файла, удаление собственного частичного
результата, каналы, частота, временная шкала, конечность PCM и спектральные признаки.
Это headless-проверка Android-компонентов, не прохождение системного выборщика.
[Сводка PARTIAL_FAILURE](../artifacts/test-results/step-05/android-import-thermal-v1/summary.json)
и [шесть отчётов с устройства](../artifacts/test-results/step-05/android-import-thermal-v1/device/plan19-import-evidence)
сохранены: каждый импортный метод COMPLETE, временные каталоги удалены.

Отказ относится к `CpuThermalPlan19Test.initializationError`: AndroidJUnit4 отклонил
метод `actualPowerManagerNoneSevereResumeCancellationAndReset`, поскольку его
возвращаемый тип был не `void`. **Термоконтроль в этом запуске не выполнялся**.
Первоначальный лог сохранён. После явного `: Unit` у двух тестовых методов
[тестовый APK v3](../artifacts/test-results/step-05/build-test-v3/summary.json)
успешно пересобран за **1 мин 11 с**. Его SHA256 —
`ce4851c681962e8489bd9d8bc0edc0a229d245307b88fdfa9c19d0ef1f1df051`;
основной All-in-One `ca18309f…` и debug `0a03b2f1…` остались побайтно прежними.

Первая попытка сборки до v2 остановилась на отсутствующем импорте `CpuPlan` в QA;
она также сохранена в `artifacts/test-results/step-05/build-auto-v1-failed/`.
Технические отказы не удаляются и не выдаются за неудачу или успех NN-качества.

## Настоящие thermal- и picker-проверки

[Thermal v2](../artifacts/test-results/step-05/android-thermal-v2/summary.json):
**1/1 PASS за 3,175 с** на API35/x86_64. Через настоящий PowerManager проверены:
NONE — ожидание **0 мс**; при SEVERE выполнение блокируется, переход к MODERATE
разрешает продолжение; CRITICAL сохраняет отмену. Тестовый override сброшен,
`thermalAfterReset=0`. [Данные PowerManager](../artifacts/test-results/step-05/android-thermal-v2/actual-power-manager.json),
[лог](../artifacts/test-results/step-05/android-thermal-v2/instrumentation.log).
Фактический Runtime сообщил **2 ядра**; requested0 по `auto_v1` дал **1 поток** для
ASR, SD и дополнительных эмбеддингов. Модели не запускались. Это работа Android API
при управляемом thermal-статусе эмулятора, без вывода о нагреве/батарее телефона или
поведении старых API.

[Системный выборщик](../artifacts/test-results/step-05/android-picker-v1/summary.json):
**1/1 PASS за 17,674 с**. Back из DocumentsUI не создал запись. Затем из Download
последовательно выбраны WAV 8 кГц mono, OGG/Opus 48 кГц stereo и FLAC 44,1 кГц mono;
все три импортированы и декодированы системным путём. Предыдущие строки Room,
исправления и аудио сохранены, удалены только три собственные импортные записи.
`priorRowsAndAudioPreserved=true`, `ownedImportedRowsCleaned=3`.
[Отчёт и снимки экранов](../artifacts/test-results/step-05/android-picker-v1/device/picker-p19picker20261107T072016/report.json),
[PNG выборщика](../artifacts/test-results/step-05/android-picker-v1/device/picker-p19picker20261107T072016/picker-1.png),
[лог](../artifacts/test-results/step-05/android-picker-v1/instrumentation.log).
Исходное stay-on **1 восстановлено**. NN не запускался; это не проверка микрофона,
речевого качества или трёх длинных распознаваний.

[Независимый аудит сохранённых non-NN доказательств](../artifacts/test-results/step-05/independent-non-nn-step5-audit.json)
дал **311/311 PASS**: source/APK/fixture-хеши, исходные отчёты, кодековые допуски,
thermal-override/reset, настоящие URI и последовательность picker связаны между
собой. Аудитор не запускал декодер или ADB заново. Удалённый тестовый PCM и снимки
предыдущей Room не экспортированы: их сохранность и очистка подтверждаются
зафиксированными assertions, успешным JUnit и device-отчётами. Список decoder names
означает доступные возможности, а не захваченное имя реально выбранного codec.
Эта проверка целостности не является NN-, телефонной или полной приёмкой пункта 5.

## Протокол CPU-native до запуска моделей

[Отдельный протокол](../artifacts/test-results/step-05/cpu-native-before-nn-protocol-v1.json)
зафиксирован до нового native NN, SHA256
`129f4fb4e147af26345c3a80e9d8bfe0d48d7a60c34def4627f4c672c0551ed0`.
База — настоящий завершённый C2 Android-прогон с run SHA `488f4f192a4547e579e9fce46634eb7613e3261dc1df1d8c525e539560fa6686`;
её JSON и интервалы повторно пересчитаны по отдельным эталонам.
Новый dev8 должен сохранить **raw ≤70/533, normalized ≤16/532, cpWER ≤145/533,
native DER0 ≤18,2984805764%, K не меньше 7/8**; числовой EPS — `1e-12`, целые
счётчики и знаменатели точные. Отдельно сохраняется port-гейт фиксированной пятёрки:
абсолютная корпусная разница с парным host ≤0,5 п.п., все пофайловые выбросы видны.

Полный контроль с явными двумя потоками **COMPLETE 10/10; независимый аудит PASS**:
[`cpu-android-control2-v1`](../artifacts/test-results/step-05/cpu-android-control2-v1/run.json).
[Запись до первого NN](../artifacts/test-results/step-05/native-cpu-execution-receipt-v1.json)
и [preflight](../artifacts/test-results/step-05/preflight-cpu-control2-v3.json) связывают
протокол с точными APK, исходниками и парным host.
[Независимый аудит — 917 PASS](../artifacts/test-results/step-05/cpu-android-control2-v1/independent-cpu-audit-v1.json):
все 11 условий нового dev-гейта соблюдены — **raw70/533, normalized16/532,
cpWER145/533, K7/8, native DER0 18,2984805764%**. Фиксированная пятёрка отдельно:
**native43/442 против host44/442, Δ−0,226244 п.п.**, port PASS. Отдельное расхождение
dev01 −0,714286 п.п. сохранено и не меняет зафиксированный корпусный критерий.

Все 10 QA-файлов полные: 344 реальных вектора по 512 компонент, 56 ASR-чанков,
2169 токенов и 767 словных оценок; C2 и Jury JSON воспроизведены, метрики нового
прогона и исходной C2-native базы пересчитаны по отдельным эталонам. Ресурсы
освобождены, исходное состояние экрана восстановлено. SHA256 аудита —
`4877922df64e098b95aef4ec9cb0a122b96963761d6229f1ed18847af1f91dd9`.
Аудитор не запускал NN/ADB/сборку и не менял сохранённые выходы.

Этот результат принимает **контроль explicit2**, а не всю автоматическую политику.
Полный automatic-request0 **COMPLETE 10/10; независимый аудит PASS**:
[`cpu-android-auto1-v1`](../artifacts/test-results/step-05/cpu-android-auto1-v1/run.json),
[собственная запись до NN с host1](../artifacts/test-results/step-05/native-cpu-auto1-execution-receipt-v1.json).
Все 10 Worker/QA-диагностик подтвердили **Runtime cores2 / requested0 / ASR1 / SD1 /
refiner1**, без pin2 в этом явном `auto_v1`-профиле. Строгий
[аудит v2 — 921 PASS](../artifacts/test-results/step-05/cpu-android-auto1-v1/independent-cpu-audit-v2.json)
связал exact automatic receipt с принятым control2 и неизменным протоколом.
Все 11 условий nonregression и отдельный fixed-five port PASS: **raw70/533,
normalized16/532, cpWER145/533, K7/8, DER0 18,2984805764%; fixed5 43/442 против
host44/442, Δ−0,226244 п.п.** Воспроизведены все 344 реальных вектора, 56 чанков,
2169 токенов и 767 слов; метрики пересчитаны, ресурсы и состояние экрана восстановлены.
SHA256 аудита — `d03d61f41855422b46d5421f73ef9567073d9162a8176ccf0cda3197221a3ce4`.

Итого выполнены **два новых прогона по тем же 10 файлам**, независимые аудиты —
**1838 PASS**. Это приёмка CPU nonregression на API35/x86_64 для explicit2 и automatic1;
четыре потока проверены на host; отдельный последующий native ARM/4 описан ниже. Время начальных
quality-прогонов не доказывает ускорение. Обычные defaults и модельные байты сохраняются.
Исторический legacy moderate1
(ASR1 / SD2 / refiner2) подтверждён отдельным smoke ниже. Старый `collector.gate_pass`
с критерием fixed V1.6+2 п.п. не заменяет новый CPU nonregression-гейт. Перед NN
сохранены точные APK/source/protocol pins отдельного запуска. Последующий
1/3/10-минутный ARM-профиль описывает наблюдённое время, без причинного сравнения потоков.

## Регрессии UI/импорта и настоящий compact QA

[Android-регрессия](../artifacts/test-results/step-05/android-regression-v1/summary.json)
прошла **27/27 за 12,598 с**: 15 MediaImport, 8 ImportJournal, 2 проверки безопасного
хранения/декодирования и 2 Home UI — Jury/diagnostic JSON, automatic default и ручные
режимы. Это выбранные тесты без NN; исходное stay-on1 восстановлено.
[Лог](../artifacts/test-results/step-05/android-regression-v1/instrumentation.log).

Затем выполнены два отдельных настоящих Worker-smoke на том же коротком
`dev-mono-s` с **collectEvidence=false**:

| Smoke | Фактические потоки | Результат и граница |
| --- | --- | --- |
| [Compact auto-two](../artifacts/test-results/step-05/compact-smoke-v1/run.json) | auto_v1/request2: ASR2 / SD2 / refiner2 | COMPLETE, WorkInfo SUCCEEDED; по одному настоящему Worker |
| [Legacy moderate-one](../artifacts/test-results/step-05/compact-legacy-moderate-one-v1/run.json) | v16/request1: ASR1 / SD2 / refiner2, оба pin=true | COMPLETE, исторический путь подтверждён; строгий full-C gate к этому узкому smoke не применяется |

В обоих случаях полные tokens/timestamps/word/vector массивы отсутствуют, компактные
счётчики и настоящий текст сохраняются, ресурсы сбалансированы. Сохранены отдельные
reference/hypothesis/diagnostics/case/metrics, APK/source pins и хеши всех семи моделей
до и после. Процедура зафиксирована SHA256
`442367b8c14acb20914b290926684488cfdfbaf16dec6f9eccdbdb92583090ce`.
Это проверка compact-контракта и legacy-совместимости на дубликате dev-файла,
без новой независимой группы качества и без полного replay скрытых массивов.
Она не заменяет два полных native10 QA-прогона выше и не измеряет скорость.

## Performance-прогон: частичный результат и timeout

[Протокол](../benchmark/eval-perf/protocol.json) зафиксирован до NN, SHA256
`aef12832afdd97eef5e301e1515402535e01fbbbe7ce0414bdefda0b3419196a`:
порядок потоков **2→4→4→2**, в каждом из четырёх пакетов файлы **1/3/10 минут**.
Запланированы **12 Worker-запусков, 56 минут аудио суммарно**. Входы — связанные
контролируемые повторы с отдельными author references и
[происхождением](../benchmark/eval-perf/provenance.json); это не новые независимые
диалоги. Reference/известное K на устройство не передаются, automatic speakers −1,
context600/C2, compact QAfalse.

[Драйвер](../artifacts/test-results/step-05/perf-driver-contract-v2/summary-final.json)
прошёл 11 проверок и локальный preflight без NN/ADB. Его SHA256 —
`a910dd990505175d031312e1dc0ed8848cb5caabcc64434dde19d367c2a4747c`.
[Запись до первого performance NN](../artifacts/test-results/step-05/perf-execution-receipt-v1.json)
связывает протокол, preflight и оба завершённых compact-smoke.
Настоящий [`perf-2-4-4-2-v1`](../artifacts/test-results/step-05/perf-2-4-4-2-v1/run.json)
завершился **FAILED, driver exit1** в `2026-11-07T08:28:55.191944Z`.
Из 12 запланированных Worker только **3 полностью проверены и пересчитаны драйвером**.
Ещё **2 имеют настоящие Android COMPLETE/SUCCEEDED**, но драйвер не дошёл до их
независимого скоринга. Позднейший отдельный
[partial-аудит всех пяти — 2489 PASS](../artifacts/test-results/step-05/perf-2-4-4-2-v1/independent-partial-audit.json)
пересчитал эти данные без нового NN. Raw driver-counter остаётся **3**;
эксперимент остаётся **FAILED**, не успешный performance12.

| Пакет / потоки | Файл | Audio ms | Worker ms | Состояние |
| --- | --- | ---: | ---: | --- |
| 1 / 2 | 1 мин | 60000 | 67890 | COMPLETE, driver verified |
| 1 / 2 | 3 мин | 179999 | 223039 | COMPLETE, driver verified |
| 1 / 2 | 10 мин | 599999 | 854460 | COMPLETE, driver verified |
| 2 / 4 | 1 мин | 60000 | 130422 | Android COMPLETE/SUCCEEDED; отдельный partial-аудит PASS |
| 2 / 4 | 3 мин | 179999 | 577404 | Android COMPLETE/SUCCEEDED; отдельный partial-аудит PASS |
| 2 / 4 | 10 мин | — | — | Ожидание прервано timeout; валидных case/diagnostics/hypothesis нет |

Пакеты 3 и 4 не запускались. Все три завершённых файла пакета1 имеют один PID8526;
первые два файла пакета2 — PID10346. Значения таблицы — наблюдаемые времена Worker
на x86_64; у завершённых файлов они больше длительности аудио. Полного двухстороннего
сравнения 2→4 и 4→2 нет, ускорение и телефонный RTF не установлены.

Точная ошибка — **`TimeoutCancellationException: Timed out waiting for 1200000 ms`**
в тестовом ожидании `withTimeout(20*60*1000L)`:
[снимок EvaluationBatchTest.kt этого запуска](../artifacts/test-results/step-05/perf-2-4-4-2-v1/source-snapshots/app/src/androidTest/java/ru/replika/EvaluationBatchTest.kt),
[лог второго пакета](../artifacts/test-results/step-05/perf-2-4-4-2-v1/batch-02-threads4/instrumentation.log),
[частичный Android-report](../artifacts/test-results/step-05/perf-2-4-4-2-v1/batch-02-threads4/instrumentation-report.json).
Это 20-минутный guard на ожидание третьего Worker, не host subprocess timeout5400с.
OOM в этих данных не доказан. Последняя stage-запись незавершённого Worker —
`diarizationReadMs`; завершения SD/ASR в сохранённом логе нет. Причина длительности
самого JNI/SD-вызова этим не установлена.

Три файла `perf-10m.{case,diagnostics,hypothesis}.json` второго пакета содержат
буквальный `cat: ... No such file or directory`: это сохранённые pull-errors,
**не валидные JSON и не результаты**. Они не исправляются и не учитываются как PASS.
В raw run остались консервативные `inference_may_still_be_running=true` и statusRUNNING
у прерванного пакета. Позднее root отдельно проверил терминальность:
[receipt](../artifacts/test-results/step-05/perf-process-terminal-observation-v1.json)
подтверждает отсутствие app PID10346, остаётся только тестовый процесс. JNI этого
исчезнувшего процесса больше не исполняется. Это не отчёт об успешном завершении
10-минутного Worker или его штатном освобождении ресурсов.

Исходное stay-on1 восстановлено. Полный12-аудитор не запускался как завершённый
аудит; partial-аудит пяти native-результатов имеет SHA256
`ee8af7f27a866f53b31fab7a0eed3157e7c8b5ae1238beae7187967a27794926`.
Критерии и исходные данные не меняются из-за отказа. Полный12-Worker протокол и
причинное ускорение этим FAILED-экспериментом не подтверждены. Последующие
физические ARM-проверки приведены отдельно ниже.

Внутри тройки не планируется перезапуск приложения; между пакетами — отдельные
instrumentation-вызовы. Сохраняются PID, stage timings/PSS, периодические RSS/PSS/thermal
снимки и исходники. Это наблюдаемые значения с накладными расходами sampler/QA;
кеши и температура полностью не контролируются. Два направления порядка нужны
для сравнения, но сами по себе не доказывают причину изменения скорости.
Телефонный ARM, реальный нагрев и непрерывный пик памяти этим не подтверждаются.

Во время первого пакета обнаружено и отдельно сохранено
[расхождение UTC и монотонного времени](../artifacts/test-results/step-05/perf-wall-clock-observation-v1.json):
в одном интервале wall clock вырос на 9958,94 с, monotonic — на 10,48 с.
Причина неизвестна. Наблюдение сделано во время первого пакета, без вывода о зависании.
RTF вычисляется по Worker/SystemClock, а разности ISO timestamp не используются как
длительность обработки; скачок часов должен остаться в итоговых ограничениях.

## Дизайн `auto_v1` за флагом

Новый режим выбирается явно. Отсутствующий ключ сохранённого WorkManager-задания
означает **legacy**, даже если будущая сборка изменит defaults. Старое задание
не должно незаметно получить новую политику после обновления APK.

Для `auto_v1` обозначим `cores = availableProcessors()`,
`target = clamp(cores − 1, 1, 4)`. Число потоков — наибольшее значение из
**{1,2,4}**, не превышающее `target`:

| Доступные ядра | target | Выбранные потоки |
| ---: | ---: | ---: |
| 1 | 1 | 1 |
| 2 | 1 | 1 |
| 3 | 2 | 2 |
| 4 | 3 | 2 |
| 5 | 4 | 4 |
| 8 | 4 | 4 |

Это дискретная политика под поддерживаемые значения, поэтому при четырёх ядрах
выбираются два потока. Политика одна для всех аудиофайлов и не использует эталон,
число известных участников или текст распознавания.

В прежнем пути C2 SD и дополнительный вычислитель эмбеддингов остаются на **двух
потоках**, как в опубликованной политике. Запрошенный runtime-режим, число ядер и
фактические потоки ASR, SD и дополнительных эмбеддингов должны записываться отдельно.
Применение адаптивного числа потоков к каждой стадии определяется реализацией и
замороженным протоколом кандидата; его качество проверяется заново.

До продвижения нового поведения в Android нужны свежие host-проверки качества.
Сравнение проводится с legacy-контролем на тех же входах и версиях. Для этого
CPU-эксперимента протокол фиксирует отдельные dev8/holdout5; старые reserve-результаты
C не выдаются за новую CPU-проверку. Изменения по конкретной записи и подбор по AMI запрещены.
Успех на старом APK или чистая компиляция не заменяют эту проверку.

## План реальных проверок

| Область | Что необходимо проверить | Состояние пункта 5 |
| --- | --- | --- |
| Чистая политика CPU | Границы числа ядер, дискретное округление, допустимые 1/2/4, явное поведение неизвестных ID/недопустимых настроек | JVM6 PASS; actual cores2 → auto1 и полные explicit2/automatic1 Worker PASS |
| Сохранённые задания | Нет ключа → legacy; явный `auto_v1` не подменяет прежние задания; фактические потоки стадий диагностируются | JVM fallback missing→legacy PASS; actual v16/request1 stage pins PASS; восстановление старой незавершённой очереди отдельно не испытывалось |
| Старый C2 | SD/refiner pin2, прежние модели и алгоритм, manual/single обход C2, отсутствие скрытого изменения ASR-плана | Actual legacy moderate1 ASR1/SD2/refiner2 smoke PASS; отдельный automatic/manual UI PASS; полный legacy-quality гейт не заявлен |
| Host-качество кандидата | Новые реальные вычисления с зафиксированной runtime-политикой; raw WER/S/D/I, cpWER, native DER0/250 и K против контроля; отдельные dev8/holdout5 | 2/1/4: 39/39, независимый аудит 5731 PASS; каждый файл совпал с C2 |
| Термоконтроль | NONE или недоступный API не вызывают ожидания; SEVERE+ и отмена обрабатываются явно; физическая защита не отключается безусловно | JVM10 PASS; actual API35 NONE0/SEVERE→MODERATE/CRITICAL-cancel/reset PASS; старые API/физический нагрев не проверены |
| URI → импорт → PCM | Все 13 кодековых примеров проходят реальный ContentResolver/MediaImporter/AudioDecoder, а не прямое чтение тестового WAV | PASS: настоящий Android, все 13 |
| Системный выборщик | Файлы видны из Download; настоящий выбор даёт читаемый URI и запускает импорт; отмена не публикует запись | PASS: Back без записи, три формата последовательно, предыдущие данные сохранены |
| Сохранность и ошибка | Источник не меняется; ошибка/отмена удаляет только собственный частичный результат, не библиотеку пользователя; повторный импорт работает | Импортные методы PASS, включая отмену реального копирования и декодирования |
| Сборка и регрессия | JVM, All-in-One/debug/test APK, подпись, static ABI; повторные native UI/Jury JSON на новом APK | JVM192 / Python370 / APK/static/signature PASS; test APK v3 PASS; два Worker/Jury10, regression27 и compact2 PASS |
| Android и измерение | Явно выбранное устройство, legacy/кандидат с одинаковыми QA-настройками, свежие гейты переноса и времена | x86 explicit2/auto1:20 case-runs/аудит1838 PASS; ARM10/942 PASS. Физические1/3/10мин измерены, цель RTF≤0,3 не достигнута |
| Устойчивость | Три длинные записи подряд без перезапуска, данные загрузки/освобождения моделей, PSS и отмены | ARM3/3 SUCCEEDED в одном PID, ресурсы сбалансированы,1004 PASS; реальное охлаждение135127мс. Старый x86 performance12 FAILED, без вывода об общей устойчивости |
| ARM/16 KiB/телефон | Фактическая проверка там, где доступна; отсутствие среды указывается явно | vivo X300 API37/4KiB: ARM10/942 и long3/1004 PASS в своих пределах. ps16k API35/x86_64: cold3/retry/one NN/120 PASS; первый system_server crash сохранён, backcompat-off не доказан. ARM16KiB/M1 не проверены |

Для новых качественных сравнений используются действующие методики C/D и
[скоринга](../tools/eval/SCORING.md), без заднего ослабления допуска. Native WER
сравнивается с host на фиксированной пятёрке; dev8 не расширяет её знаменатель.
Все отдельные расхождения сохраняются. Условие C о K/DER и раздельные проверки
качества не заменяются одним средним RTF.

## Матрица импорта: 13 примеров

Фиксированная матрица **13 кодековых примеров** подготовлена до прогона и прошла
настоящий Android-импорт/декодирование. Имена, формат, каналы, частота, длительность,
происхождение, SHA и допуски сохранены в
[fixtures.json](../app/src/androidTest/assets/plan19-import/fixtures.json).
Это собственные математические сигналы по CC0-1.0 без речи и чужих записей.

Покрытие по плану: WAV, MP3, M4A/AAC, OGG/Opus и FLAC; моно/стерео;
8/16/44,1/48 кГц; отдельно AAC ADTS. Тринадцать файлов проверяют выбранные комбинации, а не полный
декартов набор форматов, каналов и частот. Синтетические сигналы допускаются как
проверка контейнера и временной шкалы; они не являются измерением микрофона или
качеством распознавания естественного разговора.

Для каждого файла нужно сохранить исходные metadata/хеш, фактический URI/MIME,
результат импорта, metadata и SHA декодированного PCM, проверку исходника после
операции и время. Длительность, задержка кодека и временные допуски определяются
протоколом до оценки; их нельзя получать из гипотезы ASR. Проверка системного
выборщика и чтение Content URI отмечаются отдельно от самого декодирования.

## Методика времени и памяти

Измерения скорости выполняются последовательно, с версией APK/моделей, числом
ядер и потоков каждой стадии, ABI/API, состоянием экрана, thermal API и условиями
прогона. Загрузка и проверка моделей, decode, VAD, SD, дополнительные эмбеддинги,
ASR, освобождение ресурсов, QA-запись и persistence должны быть различимы.
Одинаковые настройки QA нужны, чтобы размер доказательств не менял смысл сравнения.

Времена параллельных quality-исследований не выдаются за ускорение. PSS в точках
стадий не называется непрерывным пиком памяти. Эмулятор x86_64 подтверждает свою
функциональность; из его RTF не выводится скорость физического ARM-телефона.
Общего лимита 4 ГБ от организаторов нет; устойчивость и отсутствие OOM проверяются
фактически. Физический замер ниже выполнен, но целевой RTF≤0,3 на флагмане
не достигнут; результаты одного профиля не доказывают причинное ускорение.

## Доказательства и завершение пункта

После завершения failed-процесса root установил официальный API35/ext13
**google_apis_ps16k x86_64 revision5** и создал отдельный AVD; исходный сохранён.
[Фактический снимок](../artifacts/test-results/step-05/ps16k-environment-v1/runtime-before-setup.json)
подтверждает загрузку API35/x86_64 с PAGE_SIZE **16384**. Изолированная QA-сборка
успешна за **5 мин 2 с**, static-проверка и установленные APK-хеши совпадают:
[привязки app/test](../artifacts/test-results/step-05/ps16k-environment-v1/installed-build-bindings.json),
[ZIP/ELF](../artifacts/test-results/step-05/ps16k-environment-v1/aioqa-static.json).
App SHA256 `8a1edbc98c7f32a1a34c002a93b7447bff93f4993c3f4fd37884b82b411928c5`,
test `afa1fb5a6a116094e3106ffa9c8b8f04bf219df9a6b8147989298b6bbbae994f`.

Все три проверки подготовки моделей **PASS**: чистая офлайн-подготовка семи файлов,
повторный запуск без повторного извлечения и реальное прерывание с восстановлением.
[Cold-provision summary](../artifacts/test-results/step-05/ps16k-cold-provision-v1/summary.json).
Первый отдельный `preparedBundleHashesAndNoExtractionOnRepeatedLaunch` завершился
`Process crashed`: [instrumentation](../artifacts/test-results/step-05/ps16k-environment-v1/prepared-bundle-first.log).
[Crash buffer](../artifacts/test-results/step-05/ps16k-environment-v1/first-instrumentation-crash-buffer.log)
показывает SIGSEGV `system_server` PID571 в CachedAppOptimizer, перед ним — два
сбоя Google-процессов; записи о падении REPLIKA нет. Android перезапустил
system_server. Это сохранённая неудачная проверка среды **до NN**; причина не
приписывается приложению и не превращается в PASS. Обе попытки записи backcompat
properties получили permission denied: [raw setup](../artifacts/test-results/step-05/ps16k-environment-v1/runtime-setup.json).
Отключение режима не доказано. После перезапуска системы выполнен один свежий
hash-test retry: **OK1**, все семь SHA/размеров и сохранение mtime подтверждены
до NN. Затем production Worker **COMPLETE/OK1**, independent saved-only аудит
**120 PASS**: API35/primary x86_64/PAGE_SIZE16384, cores2/request0→ASR1/SD1/refiner1.
Полный sidecar:4×512 вектора, освобождение ресурсов, C2 replay,42 токена и14 слов
точно воспроизвели Jury; Jury равен host1. Raw1/15, normalized0/14, cp1/15,
K1, DER0 89/6333. Worker13980мс на6333мс аудио — compatibility smoke, не скорость.
[Аудит](../artifacts/test-results/step-05/ps16k-android-one-v1/independent-compatibility-audit-v2.json),
[фактический prepared proof](../artifacts/test-results/step-05/ps16k-android-one-v1/prepared-models.json),
[execution receipt](../artifacts/test-results/step-05/ps16k-android-one-v1/execution-receipt.json),
[final settings readback](../artifacts/test-results/step-05/ps16k-android-one-v1/final-settings-readback.json).
Airplane0/wifi1/data1/stay1 восстановлены точно. Первоначальный system_server
crash и обе denied setprop попытки остаются ограничениями среды. Протокол одного
smoke не подменяет полный quality-гейт и не доказывает ARM16KiB или скорость.

Пользователь подключил **vivo X300 / Dimensity9500** по USB; ADB transport теперь
подтверждён. Root запустил
отдельный Windows ADB37.0.1 на loopback5038 с child-only
`ADB_LOCAL_TRANSPORT_MAX_PORT=0` и `ADB_MDNS_AUTO_CONNECT=0`; Linux5037 не затронут.
Первый `-H 127.0.0.1 -P 5038 start-server` был отклонён как remote-host startup;
успешный запуск — `-P 5038 start-server` без `-H`. Wrapper с `-H` обращается к уже
живому серверу и не используется для его запуска.

AOSP принимает max-port0 и тем самым оставляет цикл emulator scan пустым;
mDNS0 очищает auto-connect allowedlist. Эти настройки нужны окружению именно
создаваемого server-процесса, не глобальному SDK:
[emulator scanner](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/client/transport_emulator.cpp),
[mDNS policy](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/adb_mdns.cpp).
Начальный сервер запущен root, когда эмуляторы были остановлены; доступность
USB/PnP и ADB transport отделены от полной ARM-приёмки.

На физическом устройстве завершён **один dev-mono-s** через production Worker:
API37/arm64-v8a, PAGE_SIZE4096, фактические cores8/request0 → ASR4/SD4/refiner4,
без pin. [Протокол до NN](../artifacts/test-results/step-05/vivo-arm-one-protocol-v1.json),
[предварительные APK/модели](../artifacts/test-results/step-05/vivo-arm-preflight-v1.json),
[execution receipt](../artifacts/test-results/step-05/vivo-arm-one-execution-receipt-v1.json).
На телефон переданы только batch и канонический авторский WAV, без эталона или K.

Независимый **saved-only аудит79 PASS**:
[JSON](../artifacts/test-results/step-05/vivo-arm-one-audited-v1/independent-audit.json),
[читаемый отчёт](../artifacts/test-results/step-05/vivo-arm-one-audited-v1/independent-audit.md).
Связаны источники, APK, все семь фактических remote model hashes и paired host4.
Полный sidecar содержит **4×512** реальных вектора; ресурсный цикл и C2 replay
совпали. **42 токена/времени, 14 слов** точно воспроизвели фактический Jury JSON.
Jury и семь основных метрик точно равны независимо пересчитанному host4:
raw1/15, normalized0/14, cpWER1/15, K1, native DER0 **1,405337123%** (miss89мс).
Worker **3185мс** на аудио6333мс, описательный короткий RTF **0,502921**.
Это повтор известного короткого файла, без нового quality-гейта или приёмки
скорости/длинных записей/нагрева/батареи. Это отдельный первый smoke. В public
артефакты скопированы только известные author dev outputs, эталон и метрики;
серийный номер, команды, dumpsys и DB сохранены приватно.

Последующий полный физический **ARM10/10 COMPLETE**, независимый аудит **942 PASS**:
[JSON](../artifacts/test-results/step-05/vivo-arm-full10-audited-v2/independent-audit.json),
[отчёт](../artifacts/test-results/step-05/vivo-arm-full10-audited-v2/independent-audit.md),
[протокол до NN](../artifacts/test-results/step-05/arm-cpu-protocol-v1.json),
[execution receipt](../artifacts/test-results/step-05/vivo-arm-full10-execution-receipt-v1.json).
Фактический PID15843 один для всех10, cores8/request0→4 во всех стадиях.
APK/семь моделей/референсы/source fingerprints повторно проверены;344 реальных
512-компонентных вектора,56 чанков,2171 токен/время и767 слов прошли pure replay.
Все ресурсы освобождены. Dev raw **71/533**, normalized **16/532**, cpWER **146/533**,
правильное K **7/8**, native DER0 **18,2984805764%**. На fixed5 ARM **44/442** равно
host4 **44/442**, gap **0п.п.** Оба заранее зафиксированных ARM-гейта PASS.

Этот протокол требует fixed-five port≤0,5п.п., K≥7/8 и native DER0≤28,88518%.
Он **не переносит** отдельный x86 CPU-порог raw≤70 на ARM и не требует битового
совпадения нейросетевых вычислений между архитектурами. Все10 raw/stable/refined
turns, ASR-тексты и token strings совпали с host4. Jury совпал в8/10 файлах:
в dev02 и holdout04 есть только изменения token timestamps. Векторы имеют одинаковые
окна, максимальная разница компонент **3,027915955×10⁻⁵**; исходные значения сохранены.
Отдельный v1-аудит сохранён (счётчик JSON отставал на1 от последней privacy-проверки);
v2 исправляет только счётчик и заново проверяет те же неизменённые источники.

Root отдельно сверил все пять прежних Room-таблиц по count и ordered row SHA:
[preservation receipt](../artifacts/test-results/step-05/vivo-prior-data-preservation-v1.json).
Личные строки/DB не публиковались и независимый аудитор их не читал; это точное
сохранение таблиц в этих снимках, не общий Android backup. Публичный пакет состоит
из allowlisted author refs/hyps/диагностики/векторов/scored cases/CSV, без serial,
команд, dumpsys или DB.

## Физические ARM1/3/10 минут: завершённые результаты

Три production Worker **COMPLETE/SUCCEEDED**, один PID24551, automatic0/cores8→4.
Независимый saved-only аудит — **1004 PASS**:
[JSON](../artifacts/test-results/step-05/vivo-perf-one-audited-v2/independent-audit.json),
[отчёт](../artifacts/test-results/step-05/vivo-perf-one-audited-v2/independent-audit.md).
SHA256 аудита `f1a53d67c48a99353674d7dc61928c2045103ca92cd65b26af93688b9530ffa3`.
Корпус — связанные повторы знакомых авторских реплик, без новой blind quality-группы.

| Аудио | Worker, мс | RTF | Охлаждение, мс | Raw WER | Stage PSS, KiB |
| --- | ---: | ---: | ---: | --- | ---: |
| 1мин /60000мс | 21429 | 0,357150 | 0 | 10/108 | 793605 |
| 3мин /179999мс | 72287 | 0,401597 | 0 | 30/324 | 864721 |
| 10мин /599999мс | 443545 | 0,739243 | 135127 | 88/1080 | 876591 |

Время10мин включает реальное ожидание охлаждения, не вычтенное из RTF.
В telemetry наблюдалось thermal2→3→4→3→2 и затем повторные колебания2/3.
Native SD181148мс, refiner77770мс, ASR inference23962мс; таймеры вложенные,
их нельзя суммировать с родительскими стадиями как независимые слагаемые.
Ресурсные счётчики подтверждают621 измеренное embedding window и87 ASR-чанков,
создание/освобождение сбалансированы. `collectEvidence=false`: полных токеновых
и векторных массивов нет, полный replay этих трёх файлов не выполнялся.

Sampler сохранил46 записей:45 снимков собственного PID и1 раннюю JSON-ошибку.
Максимальные наблюдённые RSS **1034876KiB**, periodic PSS **830950KiB**, stage PSS
**876591KiB** относятся к разным снимкам, не непрерывным пикам. Stage-logcat пуст;
причина неизвестна. Стадии/PSS/thermal взяты из настоящих диагностических снимков,
а не восстановлены из отсутствующего журнала. Численные sensor dumpsys значения
не выдаются за температуру конкретных CPU-ядер или измерение батареи.

Один профиль на одном телефоне не даёт причинного сравнения threads2/4 или x86/ARM.
Цель плана **RTF≤0,3 на флагмане** не достигнута;10мин RTF0,739243 превышает и
ориентир0,6 для среднего телефона. Результат подтверждает завершение трёх файлов
и фактическую работу охлаждения в этом прогоне, без общей гарантии скорости/нагрева.
Предыдущий x86 FAILED12, partial2489 и его timeout сохранены без изменений.

После группы root повторно проверил оба установленных APK и все5 прежних
Room-таблиц по полным строкам:
[receipt](../artifacts/test-results/step-05/vivo-prior-data-preservation-after-long3-v1.json).
SHA app/test не изменились, prior tables EXACT; личная DB/serial/raw dumpsys
не публиковались. Процесс приложения завершён, телефон освобождён и пользователь
уведомлён. Независимый аудит ограничен тремя сохранёнными Worker и не принимает
самостоятельно весь пункт5; готовность реализации основана на совокупности проверок.

Новые входы, конфиги, версии исходников, команды, реальные JSON/CSV, логи и
независимые пересчёты сохраняются под `artifacts/test-results/step-05/`.
Имена будущих файлов не являются доказательством выполненного теста. Каждая строка
обновляется только по фактическим результатам; таблицы C не перезаписываются.

Контрольный срез сохраняется в ветках `hack/task-05-runtime-import` /
[`hack/final`](https://github.com/XterrK/ReplikaAndroid/tree/hack/final).
Финальная commit/tag-привязка определяется по Git history и
[выпуску `hack-step05-20261107`](https://github.com/XterrK/ReplikaAndroid/releases/tag/hack-step05-20261107),
без self-HEAD или заранее предполагаемого номера PR. Пользовательская пауза
зафиксирована в [STATUS.md](../STATUS.md); продолжение — по
[HANDOFF_NEXT_AGENT.md](../HANDOFF_NEXT_AGENT.md) после новой команды пользователя.
Кандидат `ca18309f…` сохранён локально, подпись `f4039935…` прежняя. Стабильный
V1.6 fallback SHA256 `dec7523de9403248358a5b590f12069be47e821460cb6095af4c1424edb7febd`
и `release/CURRENT.json` сохранены; ordinary defaults/старые задания остаются legacy,
новый профиль включается явно. Общая приёмка проекта, натуральная диаризация
(отрицательные AMI-результаты C), независимый word-gold D, целевая скорость,
ARM16KiB и Mac/M1 не объявляются. Следующий пункт6 — английский/LID и стереозвонки,
**NOT STARTED**, на паузе не выполняется. Приоритет §0.4 и отложенные LLM/Lite/лендинг сохраняются.
