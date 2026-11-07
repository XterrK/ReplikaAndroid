# Статус выполнения PLAN_19H

Начало: **2026-11-06 22:24:57 +03:00**. Новые коммиты имеют фактические даты; прежняя история сохраняется.

## Текущий этап

**PAUSED_BY_USER_AFTER_STEP05 — 2026-11-07T12:37:46+03:00.** Пользователь попросил
сохранить контрольный срез и передать работу другому агенту. Реализация пункта5
и текущие проверки завершены в указанном ниже объёме. Ветка
`hack/task-05-runtime-import` создана от merge `87f669a`. Проверены политика
потоков `auto_v1`, термоконтроль, URI → импорт → декодирование и системный выборщик.
Общая приёмка проекта и целевые показатели скорости этим статусом не объявляются.
Продолжение — только по новой команде пользователя; пункт6 не начинался.
Передача: [HANDOFF_NEXT_AGENT.md](HANDOFF_NEXT_AGENT.md).
Итоговый commit определяется по истории веток `hack/task-05-runtime-import` /
[`hack/final`](https://github.com/XterrK/ReplikaAndroid/tree/hack/final) и tag
[`hack-step05-20261107`](https://github.com/XterrK/ReplikaAndroid/releases/tag/hack-step05-20261107);
самоссылка на текущий HEAD и предполагаемый номер PR здесь не используются.
Стенд остановлен после терминального завершения всех NN: собственный эмулятор5558
и Windows ADB5038 выключены, live QEMU/listeners отсутствуют; Linux5037 не тронут.
[Команды остановки](artifacts/test-results/step-05/user-pause-test-service-stop-v1.json),
[финальная проверка](artifacts/test-results/step-05/user-pause-test-services-final-v1.json).
Данные AVD и приложения телефона не удалены, фоновых тестов не осталось.
Свежие host-варианты
2/1/4 завершили **39/39 файлов**, независимый аудит — **5731 PASS**. Каждый файл
точно совпал с C2 по Jury JSON, интервалам, реальным векторам, токенам/временам/словам
и основным метрикам. Dev raw71/533, normalized16/532, cpWER146/533, K7/8,
native DER18,2985%; holdout49/444,13/442,95/444,K4/5,DER13,8896%. Два отдельных
регрессионных гейта PASS; время исключено, ускорение не заявляется.
Сборка auto v2 — **192 JVM / 370 Python / APK / static ARM64 / подпись PASS**.
Кандидат сохранён: `release/REPLIKA-Hack-Step05-AutoCPU-AllInOne-arm64.apk`,
SHA256 `ca18309f626d431d0bd7bb4c649a2a3ae77f3ef3b75f7f1bcb47c83bf449e15e`.
[Сборка](artifacts/test-results/step-05/build-auto-v2/summary.json).

В настоящем Android-запуске все **6 импортных методов PASS**, включая все 13
кодековых примеров, повторный URI, ошибки, обрезанный WAV и отмену после реальных
байтов/кадров с удалением только своих частичных файлов. **Весь запуск: 7 тестов,
1 FAIL** — thermal-класс не инициализировался из-за возвращаемого типа тестового
метода. В этой попытке термоконтроль не выполнялся, лог сохранён.
[Сводка и шесть device-отчётов](artifacts/test-results/step-05/android-import-thermal-v1/summary.json),
[исходный лог](artifacts/test-results/step-05/android-import-thermal-v1/instrumentation.log).

[Тестовый APK v3](artifacts/test-results/step-05/build-test-v3/summary.json) пересобран
успешно за 1 мин 11 с; main/debug не менялись. Thermal v2 — **1/1 PASS, 3,175 с**:
NONE без ожидания, SEVERE блокирует → MODERATE продолжает, CRITICAL сохраняет отмену,
статус сброшен в0. Runtime cores2 → requested0 → **1 поток** подтверждён без NN.
[PowerManager](artifacts/test-results/step-05/android-thermal-v2/actual-power-manager.json).
Настоящий DocumentsUI — **1/1 PASS, 17,674 с**: Back без новой записи, затем три
WAV/OGG-Opus/FLAC из Download. Предыдущие Room/аудио сохранены, три собственные строки
очищены, stay-on1 восстановлен.
[Отчёт picker](artifacts/test-results/step-05/android-picker-v1/device/picker-p19picker20261107T072016/report.json).

Полный **CPU-native control2 COMPLETE 10/10**, независимый аудит **917 PASS**:
dev raw70/533, normalized16/532, cpWER145/533, K7/8, native DER18,2984805764%;
все 11 условий нового nonregression-гейта PASS. Fixed5: native43/442 vs host44/442,
Δ−0,226244 п.п., port PASS; выброс dev01 сохранён. Все реальные векторы/токены/Jury
воспроизведены и пересчитаны, ресурсы освобождены.
[Аудит control2](artifacts/test-results/step-05/cpu-android-control2-v1/independent-cpu-audit-v1.json).
Сохранённые codec/thermal/picker-артефакты отдельно прошли
[311 non-NN проверок](artifacts/test-results/step-05/independent-non-nn-step5-audit.json).
Полный **automatic0 →1 COMPLETE 10/10**, независимый аудит **921 PASS**:
те же raw70/533, norm16/532, cp145/533, K7/8, DER18,2984805764% и fixed5 port PASS.
Во всех 10 файлах actual cores2/request0/ASR1/SD1/refiner1 подтверждены;
344 реальных вектора, 56 чанков, 2169 токенов и 767 слов воспроизведены.
[Аудит automatic](artifacts/test-results/step-05/cpu-android-auto1-v1/independent-cpu-audit-v2.json),
[запись до NN](artifacts/test-results/step-05/native-cpu-auto1-execution-receipt-v1.json).
Два прогона по тем же 10 файлам дали **1838 независимых проверок PASS**; качество
CPU1/2 принято в пределах API35/x86_64. **Android-регрессия 27/27 PASS за 12,598 с**:
15 MediaImport, 8 ImportJournal, 2 safe storage/decode и 2 Home UI Jury/default.
[Сводка](artifacts/test-results/step-05/android-regression-v1/summary.json).
Два compact QAfalse smoke COMPLETE: [auto2](artifacts/test-results/step-05/compact-smoke-v1/run.json)
и [legacy moderate1](artifacts/test-results/step-05/compact-legacy-moderate-one-v1/run.json).
Настоящие Worker SUCCEEDED, arrays отсутствуют, ресурсы сбалансированы; legacy
сохранил ASR1/SD2/refiner2/pin=true. Это контракт двух повторов короткого dev-файла,
без новой quality-группы или полного token/vector replay.

**Performance 2→4→4→2 FAILED**, driver exit1 в `08:28:55Z`:
[run](artifacts/test-results/step-05/perf-2-4-4-2-v1/run.json),
[запись до NN](artifacts/test-results/step-05/perf-execution-receipt-v1.json).
План был 12 Worker / 56 минут аудио. Первый пакет2threads: **3 driver-verified**
COMPLETE, Worker 67890 / 223039 / 854460 мс для файлов1/3/10мин, один PID8526.
Во втором пакете4threads первые2 имеют Android COMPLETE/SUCCEEDED — 130422 / 577404 мс,
но исходный драйвер не дошёл до их скоринга. Позднее отдельный
[partial-аудит пяти](artifacts/test-results/step-05/perf-2-4-4-2-v1/independent-partial-audit.json)
дал **2489 PASS** без нового NN; original driver-counter остаётся3 и experiment FAILED.
На третьем10мин тестовое ожидание
`withTimeout(20*60*1000L)` завершилось **TimeoutCancellationException1200000ms**.
Итого **5 завершённых native-отчётов, 3 driver-verified**, не12/12. Пакеты3/4 не запускались.
[Ошибка](artifacts/test-results/step-05/perf-2-4-4-2-v1/batch-02-threads4/instrumentation.log).
OOM не доказан; причина длительности JNI/SD не установлена. Файлы третьего case
содержат raw pull-errors, а не JSON-результаты. Root отдельно подтвердил отсутствие
app PID10346: [terminal receipt](artifacts/test-results/step-05/perf-process-terminal-observation-v1.json).
JNI исчезнувшего процесса больше не исполняется. Этот performance12 остаётся
**FAILED**, полный12-аудит не запускался; последующие ARM-результаты не меняют его.
В sampler отдельно зафиксирован
[скачок UTC относительно monotonic](artifacts/test-results/step-05/perf-wall-clock-observation-v1.json).
Это ограничение временной шкалы, без вывода о зависании; RTF берётся из Worker/SystemClock.
Источники и план:
[STEP_05_RUNTIME_IMPORT.md](docs/STEP_05_RUNTIME_IMPORT.md).

На физическом **vivo X300** выполнен первый короткий Worker: API37/arm64-v8a,
страница4096, cores8/request0 → ASR4/SD4/refiner4. Независимый saved-only аудит —
**79 PASS**: протокол до NN, APK/семь моделей, 4×512 реальных вектора, освобождение
ресурсов, 42 токена и 14 слов/Jury точно совпали с pure replay. Jury и семь основных
метрик равны host4: raw1/15, normalized0/14, cp1/15, K1, DER0 1,405337%.
Worker3185мс / audio6333мс — только описательный короткий RTF0,502921.
[Санитизированный аудит](artifacts/test-results/step-05/vivo-arm-one-audited-v1/independent-audit.json).
Это один повтор известного dev-файла, отдельный от последующего полного прогона.

Последующий физический **ARM10/10 COMPLETE**, независимый аудит **942 PASS**:
dev raw71/533, normalized16/532, cp146/533, K7/8, native DER18,2984805764%;
fixed5 ARM44/442 = host4 44/442, gap0. Оба зафиксированных ARM-гейта PASS.
344 реальных вектора по512 компонент, 56 чанков, 2171 токен и767 слов проверены;
все10 Worker в одном PID15843, ресурсы освобождены, C2/Jury replay точен.
[Аудит и санитизированные outputs](artifacts/test-results/step-05/vivo-arm-full10-audited-v2/independent-audit.json).
Jury совпал с host4 в8/10 файлах; в двух других различаются времена токенов,
тексты/токены/turns совпали. Небольшие численные различия векторов сохранены.
Root отдельно подтвердил точное сохранение пяти прежних Room-таблиц:
[receipt](artifacts/test-results/step-05/vivo-prior-data-preservation-v1.json).
Личные DB/серийный номер/dumpsys/команды не экспортированы.

Физический **ARM1/3/10мин: 3/3 COMPLETE/SUCCEEDED**, независимый аудит **1004 PASS**.
Один PID24551, CPU0→4, ресурсные счётчики сбалансированы:621 embedding windows и
87 ASR-чанков. Full QA массивы не собирались: полного token/vector replay этих
трёх длинных файлов нет. Worker/RTF: **21429мс/0,357150**, **72287мс/0,401597**,
**443545мс/0,739243**. В10мин включены135127мс настоящего ожидания охлаждения;
наблюдались thermal2→3→4→3→2 и последующие колебания2/3.
[Аудит и результаты](artifacts/test-results/step-05/vivo-perf-one-audited-v2/independent-audit.json).
Наблюдённые RSS1034876KiB, periodic PSS830950KiB и stage PSS876591KiB — снимки,
не непрерывные пики.46 samples:45 с PID и1 ранняя JSON-ошибка; stage-log пуст,
причина неизвестна. Это один профиль на одном телефоне, без причинного сравнения
threads2/4. Цель плана RTF≤0,3 на флагмане не достигнута; ускорение не заявляется.
После трёх файлов root повторно сверил оба APK и все пять прежних Room-таблиц:
[точное сохранение](artifacts/test-results/step-05/vivo-prior-data-preservation-after-long3-v1.json).
Телефон освобождён, пользователь уведомлён.

На отдельном **ps16k API35/x86_64/PAGE_SIZE16384** выполнен один настоящий Worker:
независимый аудит **120 PASS**, CPU0→1, 4×512 вектора, 42 токена/14 слов/Jury
воспроизведены; Jury равен host1. Worker13980мс на6333мс аудио — только compatibility
smoke. [Аудит](artifacts/test-results/step-05/ps16k-android-one-v1/independent-compatibility-audit-v2.json).
Prepared-hash retry OK1 и все семь файлов проверены до NN; настройки восстановлены
по readback. Первый system_server crash сохранён, backcompat-off не доказан.

`auto_v1` включается явно. Число потоков выбирается из {1,2,4}: наибольшее значение
не выше `clamp(cores − 1, 1, 4)`. Отсутствующий ключ сохранённого задания означает
legacy. Для прежнего C2 диаризация и дополнительный вычислитель эмбеддингов
сохраняют 2 потока. Новая адаптивная политика требует свежей host-проверки качества
до продвижения в Android; эксперимент C не переносится на неё автоматически.

## Завершённый пункт C

C завершён **по зафиксированным экспериментальным критериям монтажного корпуса**:
commit `b619519`, [PR #4](https://github.com/XterrK/ReplikaAndroid/pull/4) объединён
как `87f669a`, [выпуск C2](https://github.com/XterrK/ReplikaAndroid/releases/tag/hack-step04-20261107)
опубликован. [Приёмка](artifacts/test-results/step-04/acceptance.json),
[проверенная публикация](artifacts/test-results/step-04/github-publication.json).

Настоящий Android-прогон **10/10 COMPLETE**, оба гейта PASS. Фиксированная пятёрка:
raw WER **43/442 = 9,7285%** против host **44/442 = 9,9548%**, разница **−0,226244 п.п.**
Dev: правильное K **7/8**, native DER0 **18,2984805764%** точно как host, ниже предела
**28,8851817043%**. Raw dev — 70/533, normalized — 16/532. Это доли ошибок, меньше лучше.
Все 10 QA-файлов полные: 344 реальных вектора по 512 компонент, 56 ASR-чанков,
2169 токенов, 767 слов; Python воспроизвёл интервалы и Jury JSON. Ресурсы освобождены,
экран восстановлен. Независимый native-аудит — **564 проверки PASS**.

Итог C: **173 JVM / 345 Python / All-in-One / static / подпись / 2 UI — PASS**.
APK v2 SHA256 `a83bfe95cf7db72ddb65177a33586fdc52074a92759aa721212cc335f6b2a496`.
Локальные и GitHub digest V1.6, D и C2 совпадают; предыдущий Jury JSON-APK сохранён.
Обычные defaults `v16`, старые WorkData и manual/single legacy остаются рабочими.
Семь моделей и pack 1.5 не менялись. [Полный отчёт C](docs/STEP_04_DIARIZATION.md).

Host dev/holdout/reserve: K 7/8, 4/5, 5/10; native DER 18,2985/13,8896/22,4396%.
Полный новый NN-прогон 23 файлов и аудит 3164 проверок — PASS. C1 с центроидами и
eigengap реализован в Python/Kotlin, 274 сравнения совпали; выбранный C2 — явная
измеренная оконная альтернатива, eigengap в её разбиении не применяется.
Дополнительные 32 dev-прогона SD и 902 вычисления эмбеддингов проверили minOff
0,25/1,0 и shift 0,25/0,5. Все четыре варианта ухудшили K/DER; контрольный C2
сохранён. Независимый аудит — 3648 проверок PASS. Старые отказы сохранены.

AMI: 9 реальных SD-прогонов и 6288 проверок целостности не означают хорошее качество.
Gold K 4/4/3, C2 K 6/8/5: 0/3 точных K; третий DER хуже базы на 2,2794 п.п.
Параметры по AMI не подбирались. Общая приёмка проекта, естественного диалога,
независимого времени слов, скорости и длительных телефонных сценариев остаётся открытой.

Последнее обновление: 2026-11-07T12:39:28+03:00.

| Пункт | Статус | Проверки / результат |
| --- | --- | --- |
| 0. Сохранение и GitHub | DONE | `artifacts/test-results/step-00/preservation.json` |
| 1. Jury JSON + default automatic | DONE | 89 JVM / All-in-One / static / 2 Android UI PASS; схема повторно проверена в C |
| 2. Стенд оценки + baseline | DONE | 13 host / 5 Android, 65 Python; корпусный port gate PASS |
| 3. ASR по VAD + словные speaker IDs | IMPLEMENTED · opt-in | ASR host/native-гейты PASS; независимая точность времени слов и скорость открыты |
| 4. Диаризация | DONE · experimental | Native 10/10, dev K7/8 / DER18,30%, fixed5 WER9,73%; PR4 и Release опубликованы |
| 5. CPU/thermal/импорт | PAUSED_BY_USER_AFTER_STEP05 | Контрольный срез: реализация/текущие проверки PASS, ARM10/942, ARMlong3/1004, ps16k120, hostCPU39/x86native20/import13/thermal/UI/legacy. Цель RTF≤0,3 и общая приёмка не достигнуты; финальная Git-привязка — ветка/tag выше |
| 6. Английский + стереозвонки | NOT STARTED | Следующая отдельная задача |
| 7. Сдача, презентация, лендинг | NOT STARTED | После проверок конвейера; ответственность Codex |
| 8. Опциональные задачи | NOT STARTED | LLM/Lite только при наличии времени и после конвейера |

## Ограничения и правила

- Приоритет плана: §0.4 > §0.3 > §0.2 > §0.1. Raw WER с пунктуацией — основной; GigaAM v3 E2E сохраняется.
- Одна задача за раз, отдельная ветка и коммит/PR. Общая ветка — `hack/final`.
- Изменения ML продвигаются в Android после измеренного выигрыша на dev и отсутствия регресса на отдельных holdout/reserve; никаких параметров под конкретный файл.
- GLM/Kimi недоступны. Ответственность за реализацию, проверку и отчётность — у Codex.
- Веса, native `.so`, APK и приватный ключ вне Git; APK публикуются отдельными Release assets.
- Исторические результаты C — исходная база пункта 5, а не свежая проверка новой runtime-политики.
- Новые ASR, LLM, Lite и лендинг не добавляются в критический путь до завершения проверок конвейера.
- Вопросы организаторам не отправлялись: доступа к чату и поручения на отправку нет.
- Физический vivo X300 проверен через отдельный Windows ADB37.0.1 loopback5038: smoke79, ARM10/942 и три длинных файла/1004 PASS в своих пределах. Телефон освобождён; сеть/системные настройки не менялись, прежние5 Room-таблиц и оба APK сохранены точно. Mac/M1 и ARM16KiB не проверялись.
- Отдельный ps16k AVD загрузился: API35, x86_64, фактический PAGE_SIZE **16384**. Изолированная QA-сборка успешно собрана за 5 мин 2 с; APK/static/install hashes PASS. [Привязки APK](artifacts/test-results/step-05/ps16k-environment-v1/installed-build-bindings.json), [среда](artifacts/test-results/step-05/ps16k-environment-v1/runtime-before-setup.json). Исходный AVD сохранён.
- На ps16k три этапа cold provisioning PASS: чистая офлайн-подготовка, повтор без извлечения, прерывание с восстановлением. [Сводка](artifacts/test-results/step-05/ps16k-cold-provision-v1/summary.json). Первый hash-test завершился `Process crashed`: SIGSEGV `system_server`/CachedAppOptimizer, без REPLIKA crash. [Лог](artifacts/test-results/step-05/ps16k-environment-v1/first-instrumentation-crash-buffer.log). После перезапуска системы retry OK1 и один фактический NN smoke/аудит120 PASS. Сбой не переписан как успех. Backcompat properties write denied: отключение режима не доказано.

Журналы: [UPDATES.md](UPDATES.md), [DECISIONS.md](DECISIONS.md). План: [PLAN_19H.md](PLAN_19H.md).

Следующий пункт — **6: английский/LID и стереозвонки, NOT STARTED**.
На паузе он не выполняется. Контекст, команды восстановления и ограничения —
в [передаче следующему агенту](HANDOFF_NEXT_AGENT.md).
Кандидат остаётся явным `auto_v1`/context600/C2; стабильный fallback V1.6
SHA256 `dec7523de9403248358a5b590f12069be47e821460cb6095af4c1424edb7febd`
сохранён, обычные defaults/старые задания legacy не заменены. LLM/Lite/лендинг
не добавляются до проверок конвейера; приоритет §0.4 остаётся прежним.
