> **ВОЗОБНОВЛЕНО пользователем 07.11.2026 ~15:00.** Пауза ниже снята. Главный разработчик и интегратор — основная сессия Claude Code в `C:\R\ReplikaAndroid` (ветка `hack/final`): только она собирает APK, работает с телефоном/ADB, сливает ветки и пушит. Вспомогательные сессии работают в своих git worktree и ветках по заданиям из `C:\R\PROMPTS_PARALLEL.md`, коммитят только локально. Новый конвейер (context600 + C2 + auto CPU) теперь включён по умолчанию (коммит `4648db2`). Stop coding — вс 08.11 09:00.

# Передача следующему агенту: пауза после пункта 5

**PAUSED BY USER. Пользователь явно потребовал сохранить всё в Git/GitHub и приостановить работу.**
Продолжать эксперименты, сборки, инференс или пункт 6 без нового указания пользователя нельзя.
Фиксация среза: commit → push → PR/merge в `hack/final` → отдельный Release → пауза.
Итоговую фиксацию проверять по истории ветки и тегу `hack-step05-20261107`, а не по предположению о номере PR.
Проверенная реализация пункта 5 не означает полной приёмки проекта или достижения всех целей.
Все запущенные NN-задания завершены; фоновых NN-прогонов для продолжения нет.

## С чего восстановить контекст

Читайте [PLAN_19H.md](PLAN_19H.md), [STATUS.md](STATUS.md),
[PROJECT_OVERVIEW.md](../../PROJECT_OVERVIEW.md), [UPDATES.md](UPDATES.md), [DECISIONS.md](DECISIONS.md).
Затем [отчёт пункта 5](../../STEP_05_RUNTIME_IMPORT.md) и его исходные JSON-доказательства.
При противоречии плана: **§0.4 > §0.3 > §0.2 > §0.1 > ранние разделы**.
Остаётся GigaAM v3 E2E; основная метрика — raw WER с регистром и пунктуацией.
WER/DER — ошибки, меньше лучше; правильное число говорящих K — успех, больше лучше.
GLM/Kimi недоступны. Ответственность за цикл остаётся у основного агента Codex.
Не полагайтесь на предполагаемый остаток контекста или память прежнего AI: проверяйте файлы и хеши.

## Git, публикация и граница checkpoint

- Приватный репозиторий: <https://github.com/XterrK/ReplikaAndroid>.
- Рабочая ветка пункта 5: `hack/task-05-runtime-import`, база — merge `87f669a`.
- Интеграционная ветка — `hack/final`; root сохраняет и объединяет туда пункт 5.
- Пункт C уже опубликован: commit `b619519`, [PR #4](https://github.com/XterrK/ReplikaAndroid/pull/4).
- Не считайте номер PR пункта 5 известным: этот документ не выдумывает будущие идентификаторы.
- Для пункта 5 root использует отдельный Release/tag `hack-step05-20261107`.
- Проверяйте фактическое завершение публикации по Git/GitHub и актуальному STATUS, не по ожиданию.
- Опубликованный артефакт не заменять новым APK с тем же именем/tag; исправления — новый checkpoint.
- Старые даты/история, FAIL-прогоны, исходные outputs и снимки исходников сохраняются.

После сохранения фактический HEAD/tag можно установить такими read-only командами:

```sh
git branch --show-current
git rev-parse HEAD
git show --no-patch --format=fuller HEAD
git show --no-patch --format=fuller hack-step05-20261107
gh release view hack-step05-20261107 --repo XterrK/ReplikaAndroid
gh pr list --repo XterrK/ReplikaAndroid --state all --head hack/task-05-runtime-import
```

Если tag ещё не доступен локально, это не разрешение пересоздать его: сверить публикацию у root.
Финальный hash этого checkpoint намеренно не вписан в собственный коммит документа.

## APK и точные флаги

Стабильный fallback V1.6/code8 сохранён в `release/REPLIKA-V1.6-AllInOne-arm64.apk`
и `release/fallback/REPLIKA-V1.6-AllInOne-arm64.apk`, размер **306312754 байта**.
SHA256: `dec7523de9403248358a5b590f12069be47e821460cb6095af4c1424edb7febd`.
Его исходный снимок — `3aba648`; [preservation](../../../artifacts/test-results/step-00/preservation.json).
Семь исходных моделей и pack V1.5 не менялись; обычные build-defaults остаются `v16`.
Профили context600, C2 и CPU-auto включаются явно, не продвигаются в defaults автоматически.

Проверенный кандидат пункта 5: `release/REPLIKA-Hack-Step05-AutoCPU-AllInOne-arm64.apk`.
Размер **306315573 байта**, SHA256:
`ca18309f626d431d0bd7bb4c649a2a3ae77f3ef3b75f7f1bcb47c83bf449e15e`.
Сертификат прежний, SHA256:
`f40399356577bcd0a5c220818ba13e9686768a02830a7f6e3af81d5a487947ab`.
ApplicationId — `ru.replika.offline`, Activity — `ru.replika.MainActivity`.
Тестовый APK v3 SHA256: `ce4851c681962e8489bd9d8bc0edc0a229d245307b88fdfa9c19d0ef1f1df051`.
Обычный `app-debug.apk` имеет другой SHA `0a03b2f1…`; не подставлять его вместо ARM-кандидата.

Точные три флага кандидата:

```text
-PreplikaAsrPlan=vad_words_context600
-PreplikaDiarPlan=eres2net_window_v1
-PreplikaCpuPlan=auto_v1
```

ARM build-type — `allInOne`, задача `:app:assembleAllInOne`.
Для x86 QA build-type — `allInOneQa`, задача `:app:assembleAllInOneQa`.
По умолчанию QA applicationId — `ru.replika.offline.aioqa`; тестовый build-type выбирается
флагом `-PreplikaTestBuildType=allInOneQa`, задача `:app:assembleAllInOneQaAndroidTest`.
`-PreplikaAioQaSameId=true` снимает QA suffix только для заранее согласованной проверки обновления.
Текущий debug AndroidTest собирается задачей `:app:assembleDebugAndroidTest`; это другой вариант.
Эти команды описывают воспроизведение после разрешённого возобновления, сейчас их не выполнять.

## Что делает проверенный конвейер

Нативный Kotlin/Compose, Room schema1, WorkManager, системные MediaExtractor/MediaCodec.
Строгий Jury JSON содержит только `transcript` и speaker_id/start_ms/end_ms/text.
Диагностический JSON существует отдельно; unknown-проекция экспорта не доказывает качество SD.
Профиль D: ASR один раз на VAD-чанк, не на пересечение с turns; максимум 20 секунд.
Разрез длинного чанка — минимум энергии в последних 4 секундах, контекст 600 мс.
Слова собираются из настоящих RNNT tokens/timestamps; границы — emission proxies, не word-gold.
VAD: Silero threshold .5/minSpeech .25/minSilence .25; модель ASR — GigaAM v3 E2E greedy CPU.
C2: ERes2Net из прежнего pack, native threshold .30, shift .1, minOn .2/minOff .5.
Чистые окна эмбеддингов 1.5 с/шаг .75 с/minIsland 1 с; затем window average HC τ=.36.
Grid125мс/max8/reassignSmall=true; точная конфигурация — DiarizationPlan и frozen configs/eval.
SD освобождается до дополнительного extractor, extractor/streams — до GigaAM; глобального NN-кэша нет.
Manual/fixed/single K не превращается в C2: `forExpectedSpeakers` возвращает legacy-диаризацию.
CPU `auto_v1`: максимум из {1,2,4}, не выше `clamp(availableCores−1,1,4)`; request0 означает auto.
Отсутствующий CPU-key старой WorkData означает legacy; прежний C2 SD/refiner остаётся CPU2.
На физическом cores8 фактически request0→ASR4/SD4/refiner4; на x86 cores2 — auto1.

## Основные доказательства пункта 5

| Проверка | Результат | Сохранённое основание |
| --- | --- | --- |
| JVM, сборка, static, подпись | 192 JVM PASS | [build-auto-v2](../../../artifacts/test-results/step-05/build-auto-v2/summary.json) |
| Полный Python-набор | 370 PASS | [Python](../../../artifacts/test-results/step-05/python-cpu-collector/summary.json) |
| Host CPU2/1/4 | 39 case-runs, 5731 audit PASS | [2](../../../artifacts/test-results/step-05/independent-cpu-threads2-v1.json), [1](../../../artifacts/test-results/step-05/independent-cpu-threads1-v1.json), [4](../../../artifacts/test-results/step-05/independent-cpu-threads4-v1.json) |
| x86 native CPU2/auto1 | 20 case-runs, 1838 audit PASS | [control2](../../../artifacts/test-results/step-05/cpu-android-control2-v1/independent-cpu-audit-v1.json), [auto1](../../../artifacts/test-results/step-05/cpu-android-auto1-v1/independent-cpu-audit-v2.json) |
| Импорт/thermal/picker | 311 saved-only checks PASS | [non-NN audit](../../../artifacts/test-results/step-05/independent-non-nn-step5-audit.json) |
| Android import/journal/storage/UI | 27/27 PASS | [regression](../../../artifacts/test-results/step-05/android-regression-v1/summary.json) |
| ARM короткий full-QA | 79 audit PASS | [short](../../../artifacts/test-results/step-05/vivo-arm-one-audited-v1/independent-audit.json) |
| ARM полный union10 | 942 audit PASS, версия v2 | [full10](../../../artifacts/test-results/step-05/vivo-arm-full10-audited-v2/independent-audit.json) |
| ARM 1/3/10мин | 3/3 SUCCEEDED, 1004 audit PASS, версия v2 | [long3](../../../artifacts/test-results/step-05/vivo-perf-one-audited-v2/independent-audit.json) |
| x86 runtime 16KiB | один настоящий Worker, 120 audit PASS | [ps16k](../../../artifacts/test-results/step-05/ps16k-android-one-v1/independent-compatibility-audit-v2.json) |

Это повторы известных регрессионных входов, не 39/20/10 новых независимых записей.
Host CPU-профили совпали с C2 по каждому файлу, векторам/словам/Jury и метрикам; время исключено.
ARM dev: raw71/533, normalized16/532, cp146/533, правильное K7/8, native DER0 18.2984805764%.
ARM fixed5: raw44/442 = host4 44/442; корпусный WER-gap0, допуск 0.5 п.п. пройден.
Fixed5 и dev8 имеют разные гейты; нельзя объединять их в удобный общий знаменатель10.
Различия отдельных времён токенов/векторов между платформами сохранены; exact NN-bit parity не заявлена.
Примерно 3% normalized WER — доля ошибок, а не 3% успеха.

## Длинный ARM-прогон и сохранённый отрицательный опыт

| Файл | Actual audio, мс | Worker, мс | RTF | Raw / normalized WER |
| --- | ---: | ---: | ---: | --- |
| 1мин | 60000 | 21429 | .357150 | 10/108 · 2/106 |
| 3мин | 179999 | 72287 | .401597 | 30/324 · 6/318 |
| 10мин | 599999 | 443545 | .739243 | 88/1080 · 20/1060 |

Один instrumentation PID, три уникальных Work/record UUID; 621 реальное окно и 87 ASR-чанков.
QA=false: массивы tokens/words/vectors не собирались, полного replay этих массивов нет.
10мин включает **135127 мс фактического cooling wait**, с thermal2→3→4→3→2 и далее2/3.
Native SD181148мс, refiner77770мс, ASR inference23962мс; таймеры вложенные, не складывать все поля.
RSS max1034876KiB, periodic PSS830950KiB, diagnostic stage PSS876591KiB — снимки, не continuous peaks.
46 samples:45 с own PID и1 ранняя JSON-ошибка без PID; stage-logcat пуст, причина не установлена.
Это один профиль на одном телефоне: ни причинного threads2/4, ни x86/ARM speedup из этого нет.
**Цель RTF≤.3 на флагмане не достигнута.** Кэш, зарядка, температура и overhead не контролировались.

Прежний x86 план2→4→4→2 на12 Worker **FAILED**, не превращать его в PASS после ARM.
Только3 driver-verified и ещё2 native COMPLETE; третий case второго batch истёк по1200000мс.
[Частичный аудит5](../../../artifacts/test-results/step-05/perf-2-4-4-2-v1/independent-partial-audit.json):2489 PASS, без пересчёта статуса FAILED.
У отсутствующего результата raw pull-errors `cat: No such file`, это не JSON и не нулевая ошибка.
OOM/codec hang не доказаны; дальнейшие batch3/4 не запускались, app PID того прогона исчез.

## Что остаётся непроверенным или не принято

Монтажные refs имеют независимые авторские тексты/интервалы, но не независимый word-gold.
[AMI](../../../artifacts/test-results/step-04/natural-ami-diar-only-v2/independent-audit.json): C2 K6/8/5 против gold4/4/3, точных K0/3.
Третий AMI DER хуже legacy на2.2794п.п.; integrity6288 PASS не означает хорошее natural-качество.
По AMI не тюнили; это связанные crops и участники, не отдельный новый acceptance corpus.
Физический ARM API37/4KiB проверен отдельно от x86 API35/16KiB; **ARM16KiB и M1 не доказаны**.
ps16k первоначальный system_server crash сохранён; backcompat-off не доказан (write denied).
RTF≤.3, батарея, длительный continuous memory peak, natural dialogue и независимые границы слов открыты.
Пункт6 (английский ASR/LID и стерео-звонки) **не начат**; пункт7 (итоговая сдача) **не начат**.
LLM/Lite/лендинг/презентация не начинать автоматически; это пониженный приоритет после конвейера.
Общая приёмка проекта не объявлена; завершённая реализация пункта5 не отменяет этих ограничений.

## Телефон, приватность и сохранность данных

На пользовательском vivo V2515/X300: ARM64 MT6993, Android17/API37, page4096, cores0–7.
Кандидат `ca183…` установлен через install-r с прежней подписью; приложение не удаляли, данные не чистили.
Root дважды сверил все пять прежних Room-таблиц: полное совпадение строк/count/hash.
[После10](../../../artifacts/test-results/step-05/vivo-prior-data-preservation-v1.json),
[послеlong3 и повторные APK SHA](../../../artifacts/test-results/step-05/vivo-prior-data-preservation-after-long3-v1.json).
Телефон освобождён; пользователь уведомлён и может пользоваться REPLIKA и другими приложениями.
Серийный номер, личная DB/WAL, dumpsys, /proc, сенсоры и команды — **только вне Git**.
Указатель приватного before-backup: `/home/egor/replika-toolchain/evidence/step05-vivo-before-backup-location.txt`.
Приватный full10: `/home/egor/replika-toolchain/evidence/step05-vivo-cpu-auto4-native-v1`.
Приватный long3: `/home/egor/replika-toolchain/evidence/step05-vivo-perf-one-PRIVATE-v1`.
Публичные sanitized exports лежат в `artifacts/test-results/step-05/vivo-*-audited-v*`.
Не публиковать серийный номер/ключи/DB и не копировать приватные raw-каталоги в репозиторий.
Не менять airplane/Wi-Fi/mobile data на личном телефоне без отдельного явного согласия.
Instrumentation перезапускает target app и открывает Activity: нужен согласованный idle-период.
Отмена WorkManager не означает мгновенное прерывание текущего JNI; сначала доказать terminal state.
Root завершил остановку своего ps16k emulator5558 и отдельного Windows ADB5038; QEMU/listener5038 отсутствуют.
[Подтверждение](../../../artifacts/test-results/step-05/user-pause-test-services-final-v1.json),
[процедура](../../../artifacts/test-results/step-05/user-pause-test-service-stop-v1.json); Linux5037 не останавливали.
Не убивать общий Linux/default ADB5037, чужие процессы/эмуляторы, не wipe/uninstall приложение.

## Перенос окружения и возобновление

Рабочая папка: `/mnt/d/ReplikaAndroid/ReplikaAndroid`; clone сам по себе **недостаточен**.
Переносить приватно всю папку с `.git`, `model-pack/`, `app/src/main/jniLibs/`, `local-dev/debug.keystore`.
Это локальные ignored build inputs; ключ подписи и веса в Git не добавлять, старые APK сохранять.
См. [PORTABILITY.md](../../PORTABILITY.md), [HANDOFF.md](HANDOFF.md), `tools/build_portable.py`.
Внешний toolchain `/home/egor/replika-toolchain`: `jdk17`, `android-sdk`, `gradle-cache`, `host-venv`.
Host Python: `/home/egor/replika-toolchain/host-venv/bin/python`, sherpa-onnx2.0.1/ORT1.28.2.
Canonical corpus вне Git — `eval-audio/`, controlled repeats — `plan19-perf/` внутри toolchain.
Сохранить external evidence/source snapshots и dataset/cache metadata при передаче на другую машину.
Windows phone wrapper — `/home/egor/replika-toolchain/windows-adb/adb-phone`, изолированный port5038.
Сам wrapper не даёт разрешения подключаться к устройству; serial берётся только из приватного receipt.
При разрешённом возобновлении root сначала запускает Windows server5038 отдельным adb.exe **без `-H`**.
Только child-env: `ADB_LOCAL_TRANSPORT_MAX_PORT=0`, `ADB_MDNS_AUTO_CONNECT=0`, без системных изменений.
Запускать лишь при отсутствии активного emulator NN: у AOSP первичного scan есть startup race даже с max0.
Wrapper с фиксированным `-H127.0.0.1 -P5038` использует уже поднятый сервер и отвергает emulator serial.
Не запускать `adb devices`/server/сборку/NN в рамках чтения этого handoff.

После **явного возобновления пользователем** сверить Git HEAD/tag, STATUS и hashes сохранённых APK.
Проверить реальные незавершённые пункты плана; не повторять уже прошедшие тесты без нового изменения/сбоя.
Если нужен новый эксперимент — заранее protocol/config/cohort/source pins, fresh output, refs только scoring.
Не использовать просмотренные holdout/reserve как новый blind cohort и не подгонять отдельные файлы.
Root — единственный владелец Git/GitHub, ADB, Gradle и NN-запусков; другие агенты работают read-only по поручению.
Не запускать параллельно два драйвера на устройстве; согласовать ресурсный бюджет и источник истины.
Не делать reset/clean или массовую уборку: игнорируемые модели, ключи, private backups нужны для продолжения.
До нового разрешения пользователя сохранять **PAUSED**, никаких автоматических следующих задач.
