# Журнал выполнения

Все времена — фактические, с часовым поясом. Исторические результаты не заменяют новые прогоны.

## 2026-11-06T22:26:32+03:00 — начало пункта 0

- Прочитан PLAN_19H; принят порядок из вводной части и приоритет §0.4.
- План скопирован из внешнего корня в Git-проект без изменения содержимого.
- Сохранены локальный Git bundle и binary diff до фиксации рабочего дерева.
- Создана побайтово проверенная fallback-копия APK V1.6; evidence: `artifacts/test-results/step-00/preservation.json`.
- Созданы STATUS.md, UPDATES.md, DECISIONS.md. Новых ML-измерений пока нет.
- Проверены GitHub CLI и аккаунт XterrK; remote пока отсутствует.

## 2026-11-06T22:28:24+03:00 — окружение и GitHub

- Создан приватный репозиторий https://github.com/XterrK/ReplikaAndroid через GitHub CLI: подключённый GitHub-инструмент не предоставляет создание репозитория.
- На новой машине JDK17/SDK отсутствуют; готовится отдельное Linux-окружение в пользовательском каталоге вне Git. Старый F:-toolchain недоступен.
- Состав публикации: около 2724 исходных/evidence файлов, 123 MB; нет отдельных файлов >40 MiB и credential-like filenames. Точечный скан содержимого выполняется отдельно.
- Модели, `.so`, APK/fallback и signing key подтверждены через git check-ignore.

## 2026-11-06T22:34:53+03:00 — снимок зафиксирован

Коммит `3aba648`: сохранено всё неигнорируемое рабочее дерево V1.6; 1784 изменённых/добавленных/перемещённых файлов относительно прежнего HEAD. Запущен push в приватный GitHub; JDK/SDK preflight и проверка 12 входов прошли. Первая JVM/All-in-One сборка ещё идёт; успешный результат пока не заявляется.

## 2026-11-06T22:38:59+03:00 — публикация подтверждена

`hack/final` опубликован в приватном XterrK/ReplikaAndroid. Fallback V1.6 доступен в prerelease `v1.6-preserved-20261106`; серверный SHA-256 GitHub совпадает с локальным, размер 306312754 байта. Свежая сборка и JVM-тесты ещё выполняются.

## 2026-11-06T22:41:45+03:00 — пункт 0 завершён, начат пункт 1

Исходная сборка на новой машине: BUILD SUCCESSFUL (10m44s), 80 JVM / 0 failures/errors/skips; All-in-One собран. Логи и XML сохранены в `artifacts/test-results/step-00/`. Приватный source push и SHA fallback на GitHub подтверждены. Начата отдельная ветка `hack/task-01-jury-json`. Свежего ML benchmark пока нет.

## 2026-11-06T22:45:09+03:00 — пункт 1 реализован, проверяется

- Добавлен `domain/JuryJson.kt` и 9 контрактных JVM-тестов (схема, порядок, IDs, unknown, пустые, Unicode/экранирование, Long timestamps, некорректные интервалы).
- Обычный JSON переключён на формат жюри; прежний формат доступен отдельно. Кодирование выполняется вне Main.
- Обновлены Android export/persistence assertions и исторический collector; added automatic-default UI test.
- Запущены JVM, All-in-One и сборка Android test APK. Прогоны UI и модельные сравнения ещё не выполнены.
- Независимое ревью выявило блокирование Main при большом экспорте и зависимость legacy collector от старого пути; оба замечания исправлены.

## 2026-11-06T22:46:19+03:00 — исправление первой проверки пункта 1

Первая сборка остановилась при compileDebugUnitTestKotlin: JSONObject.keySet() отсутствует в Android compile API. Контрактный тест переведён на совместимый keys().asSequence(); main/ML-код не менялся. Неудачный лог сохранён в `artifacts/test-results/step-01/build-attempt1.log`. Повторяется полный выбранный набор JVM/All-in-One/Android test APK. Старые 80 XML не выдаются за новый результат.

## 2026-11-06T22:50:17+03:00 — 89 JVM и All-in-One PASS

Повторная сборка успешна (2m4s): 89 JVM / 0 failures/errors/skips, All-in-One и Android test APK. Статическая проверка APK PASS, SHA256 cc71c0a811d1d35efdc4186638898234a21171e21bebb1d8df75e67a454c53e5. XML/логи сохранены. ML-код и model lock совпадают со снимком V1.6. Дополнен UI-тест обоих форматов, отдельно собираются стандартный debug APK и обновлённый test APK; новый x86_64 AVD загружается.

## 2026-11-06T22:53:18+03:00 — пункт 1 принят

89 JVM, All-in-One/debug/test APK и static arm64 checks PASS. Два UI-метода на API35/x86_64 прошли за20.036s: экспорт обоих JSON через интерфейс, сохранение strict jury bytes, default automatic и ручной выбор. Фактические JSON и scope сохранены; это controlled fixture, не модельная транскрибация. APK кандидата сохранён отдельно от fallback, SHA256 `cc71c0a811d1d35efdc4186638898234a21171e21bebb1d8df75e67a454c53e5`. Подготовлен отчёт `docs/STEP_01_JURY_JSON.md`; далее commit/PR, затем пункт2.

## 2026-11-06T22:58:34+03:00 — пункт 1 опубликован, начат пункт 2

Commit `763253c` с проверенным Jury JSON опубликован; PR1 слит в `hack/final`, merge `d95c18b` (фактические даты06.11.2026 22:54/22:56+03). APK шага1 доступен в prerelease `hack-step01-20261106`; старый fallback сохранён. Начата ветка `hack/task-02-evaluation`. Параметры/веса не меняются: сначала независимые reference/hypothesis и baseline.

## 2026-11-06T23:28:27+03:00 — baseline host завершён, Android идёт

Все13 файлов прогнаны через модели с независимыми author refs. RawWERdev124/533=23.26%,holdout73/444=16.44%; normalized7.33%/5.43%. Native count exact2/8 и2/5; DER0proxy43.16%/51.55%. Это исходный уровень, улучшение не заявляется. HostRTF0.365/0.357, процессRSS437.2MiB, не phone. Пять matched AndroidWorker cases выполняются offline на AVD; три уже завершены. Создан `docs/TEST_RESULTS.md` со ссылками на сырые JSON/CSV и определениями метрик.

## 2026-11-06T23:35:40+03:00 — Android5 завершён, gate не принят

5actual Worker cases прошли offline (airplane1/Wi-Fi0).4файла exactWER parity; holdout02 отличается одним словом:hostSkeleton/nativeскелетон, rawWER23/148 против22/148, delta−0.6757п.п. Порог0.5не ослабляется; `baseline-v16-android/run.json` честно содержитPORT_PARITY_FAIL. ВсеJSON и исходные outputs сохранены. До inference есть различие peak0.510559082/0.5105543, при одинаковых VAD/turns/slices: исследуется hostidentityPCM против численного interpolation AudioDecoder16k. Добавлен test-only capture actualPCM, mainAndroid/модели не менялись; новый testAPK собирается. Пункт2 не закрыт, пункт3 не начат.

## 2026-11-06T23:43:57+03:00 — численный decoder mismatch доказан, причина слова ещё исследуется

Actual AndroidFloat32PCM захвачен test-only методом (1testPASS,.496s). Generic эмуляция AudioDecoder совпала побитово на всех1190678 samples; directPCM отличается на756167 samples,maxabs7.90e-6. СырыеPCM остаются внеGit, hashes/сравнение сохранены в step-02/decoder-parity. Causal probe на одномhostrecognizer далSkeleton и наdirect, и наactualAndroidPCM, и наgenericemulation: один decoder mismatch не объясняет script flip. Обнаружены разныеCPUtiers:hostFMA/AVX2/VNNI,guestтолькоAVX. Исследуется обратимый process-only qemuuser probe; productionмодели/параметры не меняются. Corpus baseline и исходный PORT_PARITY_FAIL не переписываются.

## 2026-11-07T00:02:35+03:00 — пункт2 принят

65Python tests,89JVM/All-in-One/testAPK checks PASS;13hostcases повторены сgenericAndroid-math decoder. Все reference/hypothesis/metrics/diagnostics/CSV сохранены.5actualWorker cases прошли offline; дополнительно decoder/freshASR probesPASS. По явному уточнению пользователя corpusgate0.226244<0.5п.п.PASS; per-filewordoutlier и первоначальныйgateFAIL сохранены. Обновлён `docs/TEST_RESULTS.md`,добавлен `tools/eval/README.md`,подготовлен immutablebaseline для пункта3. Commit/PR готовится; пункт3 ещё не начат.

## 2026-11-07T00:27:12+03:00 — начат пункт3

PR2 merged `beeaff5`; создана `hack/task-03-vad-word-asr`. Разрабатываются отдельные hostword-pipeline и pureKotlin helpers, baselinepipeline.py/scorer/corpusзаморожены. Подтверждёнframe40ms поencoder subsampling4 иsherpa feature10ms. AsrEngine получил неиспользуемый detailed API; существующий recognize и Worker legacy не изменены. Runner принимает только явную experimentalконфигурацию сpunctuation_mode/energy_split. Нет выборановыхweights/VADparams. Ранние кандидаты проверяются толькоdev; итоговыйwinner — затемdev+holdout.

## 2026-11-07T00:33:49+03:00 — пункт 3: первый dev-эксперимент

Все 8 dev-файлов обработаны. ASR по VAD без правки пунктуации: raw WER 93/533 = 17,448% (baseline 124/533 = 23,265%), normalized 26/532 = 4,887% (39/532 = 7,331%). Fallback словных таймингов: 0. Native DER прежний; DER по экспортным интервалам вырос, что фиксируется отдельно. Короткий dev-кейс всё ещё имеет 2 удаления; цель −30% не достигнута. Медианы границ по coarse clip gold не подтверждают целевые 200 мс. Holdout пока не запускался. Добавляются предусмотренный планом VAD-sweep и отдельный A/B пунктуации. Найден защитный дефект на невероятном Float timestamp: исправляется с регрессией; исходный эксперимент и source snapshot сохраняются.

## 2026-11-07T00:49:44+03:00 — пункт 3: промежуточный VAD-sweep

Повтор default word-пути воспроизвёл 93 raw / 26 normalized ошибок на dev. Ранний глобальный seam дал 116 / 26 и не принимается. VAD 0,15/0,20 с: 92 / 22, короткие удаления 2. VAD 0,10/0,12 с: 99 / 20, короткие удаления 0 (baseline 124 / 39 и 2 удаления). Веса/диаризация прежние. Идут sensitive threshold 0,35 и seam-v3, ограниченный реально разделёнными чанками; v2 source snapshot сохранён до изменения. Все эталоны/гипотезы/метрики в step-03, индекс results.csv обновляется. 282 pure Kotlin/Python cases v2 совпали, v3 проверяется отдельно. Android Worker ещё не переключён.

## 2026-11-07T00:56:50+03:00 — пункт 3: dev-выбор заморожен

Последние два interaction checks завершены: short10+seam дал 119 raw / 20 normalized; sensitive+short10 — 96 / 18 и 0 коротких удалений. Последний выбран по зафиксированным условиям D до открытия candidate holdout (`candidate-selection.json`). Порог/минимум речи/минимум тишины: 0,35 / 0,10 / 0,12 с; punctuation_mode=none. Запущен свежий одиночный selected-host на всех 13 файлах. До его gate ML-параметры Android не меняются, port готовится вне working tree. 114 Python tests PASS, 20 focused JVM PASS и 282 pure v3 differential cases без различий. Цель <200 мс остаётся неподтверждённой: независимой словной разметки нет.

## 2026-11-07T01:06:23+03:00 — пункт 3: selected holdout FAIL, Android не переключён

Свежий all13 selected-host завершён. Dev воспроизведён: 96/533 raw (18,011%), 18/532 normalized (3,383%), short D=0. Holdout: 78/444 raw (17,568%) против baseline 73/444 (16,441%); normalized 16/442 (3,620%) против 24/442 (5,430%). Raw — главный по §0.4, поэтому gate FAIL; ни VD-параметры, ни новый Worker не перенесены в Android. Внешний port независимо проверен двумя агентами, но не применялся/не компилировался. Исходный trial и v3 source snapshot сохраняются. Продолжается только D: dev-эксперимент с исходным VAD и увеличенным реальным pre-roll; отдельно фиксируется резерв новых disjoint клипов без model/hypothesis input для будущей финальной проверки. Старый holdout-gate остаётся обязательным.

## 2026-11-07T01:13:42+03:00 — пункт 3: context600 выбран на dev

Context300: 84/533 raw, 21/532 normalized, short D=0. Context600: 71/533 raw (13,321%), 16/532 normalized (3,008%), short D=0. Меняется только реальный pre-roll при исходном VAD .5/.25/.25; frame40/слова/диаризация/веса прежние. Во второй selection JSON зафиксированы dev-результаты и уже замороженный reserve selection hash. Свежий all13 context600-selected-host идёт; далее отдельная проверка на reserve. Ни один candidate пока не перенесён в Worker.

## 2026-11-07T01:30:21+03:00 — пункт 3: host quality PASS, начат нативный port

Context600 прошёл primary quality gates: original dev71/533 raw и16/532 normalized, original holdout49/444 raw и13/442 normalized; reserve83/743 raw и24/744 normalized против baseline135/743 и42/744. Все23файла имеют supported word projection без fallback. host-quality-gate.json сохраняет отдельные условия и null для недоказанной word timing acceptance. После этого применён независимо проверенный draft Worker/AsrPlan; default обычной сборки v16, кандидат только через -PreplikaAsrPlan=vad_words_context600 и явный WorkData plan. Full JVM111/0fail и Python125PASS, All-in-One собран; debug/test APK ещё собираются. APK не опубликован/не объявлен принятым. Следом actual offline Worker fixed-five и прежние export UI checks. Аудит host2131/2131PASS, отчёт host-audit.json сохраняет также ухудшения timing coverage/DER.

## 2026-11-07T01:55:17+03:00 — пункт 3: native fixed-five PASS

5actualWorker cases завершены offline наAPI35/x86_64. Raw43/442=9,729% против host44/442=9,955%; разница−0,226244п.п., corpusgatePASS. Единственный per-file outlier dev01: native10 vs host11 на140словах (−0,714286п.п.); все расхождения сохранены в native-port-differences.json. Пять QA payloads полные, fallback0/truncationfalse. Предыдущий Android baseline на той же пятёрке75/442=16,968%; user3%-вопрос уточнён: WER — ошибки↓, доля верного числа спикеров — успех↑, platformgap — отдельная проверка. Нативный RTF3,616–4,911 плохой; неизменённая SD стадия наdev01 217471ms против прежних50710ms, поэтому начат отдельный legacy current-environment control, causal slowdown не объявляется исправленным/объяснённым. Обычный build-default всё ещёv16.

## 2026-11-07T02:21:22+03:00 — пункт 3: проверки завершены, готовится Git

ASR opt-in delivery: host-quality и native quality/port PASS,125Python/111JVM, All-in-One/debug/test APK/static PASS, UI2/2 за18,633s после test-only ожидания появления второго chooser перед Back. Attempt1 (1/2) сохранён, mainAPK побайтово прежний353147c… . UI-export обеих JSON-схем, automatic/manual и фактический nativeJury5 contractPASS. Legacy текущегоAPK наdev01RTF4,739 vsword4,605, обеSD~219/217с vsисторические50,7с; причина не установлена, ускорение не заявляется. acceptance.json допускает opt-in ASR, но full_pipeline_accepted=false; defaultv16, targets diar/time/speed открыты. НовыйAPK305347754B SHA048c42fd1ad6f48db10c90583baae3a94ad389ef4e6a9dbb50535879b442ae9d, прежниеAPK и signer сохранены. Веса/скорер/decoder/baseline helper не изменились. Новая исходная поставка содержит все dev-trials, отдельный reserve, refs/hypotheses/metrics/CSV; secrets/weights/native/APK внеGit. C не начинался.
