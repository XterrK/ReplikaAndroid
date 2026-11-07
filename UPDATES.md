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

## 2026-11-07T02:36:02+03:00 — пункт3 опубликован, начат пунктC

D commit60b6743, PR3 merged6e6a35a; prerelease hack-step03-20261107 иGitHubdigest APK048c42fd… проверены. Обычныйsource-defaultv16, full_pipeline_accepted=false. Теперь веткаC: officialembeddingcatalog/weights внеGit, fixed-K исследование затемauto иrefiner. КодAndroid пока прежний. Baseline/scorer/decoder/ASRwordpolicy frozen; реальныеrefs/hypotheses сохраняются.


## 2026-11-07T02:49:18+03:00 — C: шесть моделей доступны, fixed-K идёт

Все6точных ONNX проверены SHA/размером и загрузкой в sherpa2.0.1;227082991B новых весов внеGit. CAM++LM имеет явный нерешённый конфликт лицензий источников. Новый refiner:30тестов+360случайных инвариантных проверок PASS, без model inference. Проекция13сохранённых token outputs воспроизводит JuryJSON иrawWERпобайтово/по метрикам. Первые2preflight failures (нет reference_sha256 в исходном manifest) сохранены доNN; runner использует независимый ref hash из зафиксированногоASRrun. Fixeddev8 ERes: nativeDER0proxy27,469%, exactcount4/8;ResNet34:30,210%,5/8. Это oracle-исследование, не автоматическая приёмка. Следующие4эмбеддера выполняются максимум2процессами; всеactual turns/refs/hyps/metrics/CSV сохраняются.


## 2026-11-07T03:00:33+03:00 — C: fixed6/dev8 завершён, auto/refinement идут

48 actual fixedSD cases сохранены. DER0proxy: ERes27,469%, ResNet34 30,210%, CAMPPlus46,860%, CAM++LM50,206%, TitaSmall29,845%, TitaLarge40,269%. Derived fixedV1.6 comparison с настоящим mono bypass26,885% (не новый inference); devgate максимум28,885% и>=7/8 точных counts. 187 Python contracts/scorer/refiner tests PASS, summary/log в step-04/python-checks. Auto-grid двух первых моделей реально выполняется; остальные4следом, полныйgrid672case-profile pairs. Дополнительно краткий1thread embedding-only collector извлёк232реальных clean-window vectors из сохранённых Dturns: SD/ASRне повторялись, nullRTF и originalsource-metrics сохранены. Его временный третийпроцесс при2SDworkers использовал измеренный RAM reserve~2,5GB; скорость алгоритма по этим concurrenttimes не сравнивается. Full dev14tau×2missingpolicies baseline-refiner выполняется; первый singlecase smoke явнонеgate. APK/sourceAndroid/скорер/ASR/decoder прежние; никаких LLM/Lite/landing. Рабочая веткаC пока без новогоcommit, HEAD6e6a35a.


## 2026-11-07T03:01:52+03:00 — C: первая полная refiner-проверка dev8 не принята

Из232реальных clean-window embeddings базовых Dturns проверены14tau×2missing-policy, каждый вариант на всех8dev. Все224refined case projections сохранилиrawWER71/533; failures0, NN SD/ASRне повторялся. Лучший DER0retain27,689% (tau0,35, exactK2/8), temporal27,213% (tau0,35, exactK3/8); baseline43,157%. Максимум exactcount по всемуgrid4/8retain,5/8temporal, меньшеобязательных7/8. GateFAIL, Androidнепереносится. Исходные turns/refined turns/refs/hypotheses/diagnostics/CSV и метаданные source→D связей сохранены в refine-baseline-retain/temporal. Настоящие SDautomaticgrids продолжаются, в том числе низкийdistance threshold для overclustering; промежуточный singlecase успех не выдаётся заобщуюприёмку.


## 2026-11-07T03:30:01+03:00 — C: первый devgatePASS, независимые validations идут

ResNet34LM SDthreshold0,50/shift0,1 +centroidrefinerτ0,70/minsmallcos0,70/temporalpolicy прошёл independent dev8 audit:7/8count(87,5%), nativeDER026,550360% vsfixedV1.6 26,885182%, cpWER227/533=42,5891%, rawWER71/533безизменений. Аудит `acceptance-resnet34-050-temporal-guard0p7/tau-0p7.json`, sourceintegrityerrors0. Provisionalcandidate зафиксирован ДО новойконтрольнойпроверки в candidate-c1-validation-freeze.json; это не Android/finalpipeline acceptance. ActualnewSD+embeddingwindowinference наoriginalholdout5завершилась: nativeDER020,299685%, count3/5, raw49/444 (ASRсохранённыйD). Reserve10ещёидёт; policyнеподбираетсяпоholdout.

ВсеC1CAMP/CAM.30/.50 refinements(896cases) FAIL: пример count-onlyложноговывода CAMP7/8приDER49,38% не проходит28,89%. WindowC2 matrices(включая1232ownedcaseoutputs+baseline448+ResNet030112) тожеjointgateFAIL: лучшийnearERes030average-smallτ0,35 —6/8,DER23,72%,cpWER38,65%; используетсякакresearch, неAndroid. ERes/ResNetnativeautomaticgridsCOMPLETE112каждый; CAMP/CAM/TitaSmallтожеCOMPLETE, TitaLargeещёсчитает. ВсеNNиsavedпроекции, refs/hyps/metrics/CSV сохранены. Готовится отдельный fullactualhostpipelineC, базовыеpipeline.py/pipeline_words.py/скорер/decoderиAndroidпока неизменны.


## 2026-11-07T03:39:40+03:00 — C: nativegrid6×14 завершён, validations numericPASS

Все672actualSDcase-profile pairs (6моделей×14порогов×8dev) COMPLETE. Independentnativeaudit84profiles: integrity/full8/raw71/533PASSвезде; ни одинplainnativeprofile не проходитсовместныеCcriteria. C1refinerResNetguard0,7 остаётсяпервымdevPASS7/8/DER26,55%. Actualoldholdout5 иreserve10 SD+cleanvectors COMPLETE; послеfrozenrefiner nativeDER20,299685%/29,235934%, exact3/5и3/10 противV1.6 2/5и1/10; nativebaselineDER51,545723%/47,659076%. Raw49/444и83/743сохранённыеD, противbaseline73/444и135/743. Формальныйsource/replay/cohortaudit ещёготовится, fullactualASRpipelineC ещёнепрогонялся.

ShiftA/Bactual16cases завершён:0,25 tinyDERregress+0,067747п.п.,0,5count6/8; обанеpromoted. Кандидатshift0,1 неизменён. ВсеNNсейчасзавершены; идутpure Tita refinements, новыеhostpipeline/tests иexternalKotlindraft. MainAndroidкод/lock/пакеты/рабочийAPK не менялись, веткаCнезакоммичена до полногоэтапа.


## 2026-11-07T04:41:43+03:00 — C2 выбран и проверен на host, Android-сборка идёт

Fine dev protocol21tau0,25..0,45 был заморожен до результатов. C2 EResSD0,30/shift0,1 +windowHC averageτ0,36/reassign-small прошёлdev7/8, nativeDER018,298481%, cpWER146/533; выбран один глобальный профиль без per-file параметров. Формальные separate holdout/reserve gates PASS: K4/5 и5/10, nativeDER013,889566% и22,439619%, raw49/444 и83/743. candidate-c2-validation-freeze.json и configs/eval/c2-window-selected-* фиксируют выбор; прежние C1/неудачные C2 trials сохранены.

Новый полный actual VAD/SD/clean-embedding/HC/GigaAM C2 прогон COMPLETE13+10: original raw120/977, reserve83/743; dev71/533 иnormalized16/532. CachedASR не подставлялся в full run. Независимый full23 equivalence audit дополняется. C1 full23 иего3321checksPASS тоже сохранены как исследование/fallback, ноResNetвеса вAndroid не добавляются: C2 использует прежний семифайловый pack1.5.

PureKotlinC2:157differential(включая23actualcases), exactturn/IDs/accepted безрасхождений; C1helper274parity, adapter10, QAencoder14 изолированных JVMtestsPASS. SciPyBSDlicense включена для faithful NN-chain tie handling. Исправлен найденный до APK интеграционный дефект BigInteger JSON с тестом реального refinerdiagnostic. WorkerпередASR проверяет release native resources; оригинальный PCM безgain/padding; полныеvectors толькоboundedQA-sidecar внеRoom. C2/context600 opt-in Gradle JVM/All-in-One/debug/test сборка выполняется, instrumentation дополнен явным evalDiarPlan/sidecar SHA+size+identity/count checks. Android inference/приёмка ещё не выполнены; обычныеdefaults/историческиеmanualзадания и сохранённыеV1.6/DAPK сохранены. НизкийWER~3% означает ошибки, неуспех; резервныйcount5/10 остаётся реальным ограничением.


## 2026-11-07T04:49:21+03:00 — C2 APK собран, 170 JVM + UI2 PASS

Gradle завершён за5m14s:170JVM/0fail/0skip, All-in-One/debug/androidTest собраны. StaticARM64 pack/7models/ELF/ZIP alignmentPASS, signer прежнийf4039935… . Новыйcandidate APK305476189B, SHA6a73427638ccd3e1e04e725d1080d604c5941d571e796544c1fa2733f4f965fd сохранён отдельно вrelease/REPLIKA-Hack-Step04-C2-AllInOne-arm64.apk, пока runtimeAccepted=false. V1.6fallback иD APK зановоSHAпроверены. Сборки/JVMXML/logs/SHA/sourcefingerprint: step-04/build-c2-v1; Gradledaemonостановлен передAndroid.

Наexplicit emulator-5556 установленC2debug/test поверхпрежнего безwipe. UIattempt1:2FAIL«NoCompose»; dumpsys подтвердилmWakefulness=Asleep/isSleeping=true. Послеwake+temporary-stayon безизмененияAPK повтор2/2PASS10,327s: JuryJSONиdiagnosticJSON черезUI, automaticdefault/manualchoices; исходнаяdisplaysettingвосстановлена. Обаattemptсохранены(ui-v1/ui-v2). Это controlledUIfixture безNN, некачествоC2.

НезависимыйfullC2audit3164checks/23casesPASS: exactJuryJSON/ASRtokens+timestamps/turns/749actualvectors/refinerdiag/coremetrics;23SD,130ASRforwards,4681tokens,1685wordproxies,749embeddingforwards. Векторные иwordsidecars дляactualAndroid10caseunion(DEV8+fixed5, пересечение3) сейчас готовятся строгимcollector. Ошибку первоначального подсчёта11 исправилидо запуска; фиксированнаяпятёркаиgateнеизменны. C2actualAndroidNN ещёне запускался.


## 2026-11-07T05:12:55+03:00 — actualAndroid C2 smoke: NN/ASR READY, QA publication FAIL

Однокейсовый explicit dev-mono-s smoke запущендляпроверкиSDK/QAпередfull10. Globalautomatic−1/context600/C2, noGTondevice. Workerполучил READY за10259ms,4actual512dimembeddings, streams4created/4released, extractor1, ресурсыдоrefiner/ASRосвобождены; C2получил1speaker. Однако Files.createLink QApublication упал AccessDeniedException; logcatподтвердил SELinuxEnforcing avcdenied{link}app_data_file. Инструментацияправильноотклонила truncated/missingQA настроке190. Стенограммаполезна/сохранена, quality/portgate этимsmokeнепройден. Полныеlogs/diag/hyp/failure вnative-c2-smoke-v1; отсутствующиеcase/sidecar pullerrors сохраненыraw, невалидируютсякакJSON.

Меняем QAhelper наprivatecooperatingwritersmutex +persistentFileChannellock +targetNOFOLLOWrecheck +same-directoryATOMIC_MOVE, сохраняяfd.sync/budget/null/BigInt/nooverwrite; дополнительныйJNI не нужен. MLweights/thresholds/ASR/Workerне меняются. НовыйAPK/re-smoke/full10послеhelpertests.

Collectorv1/v2mocks былиPASS, ноindependentreviewпоймал fullQA↔compactRoom иKotlinDouble2000.0↔JSONObjectinteger2000. Collectorv3исправляеттолькограницудиагностики: одинточныйnumericallowlistpathsmall_cluster_cutoff_ms, всеpolicy/clocks/countersстрогие. Добавлены4semanticcodeSHA иrawpull приnonzeroinstrumentexit. v3:36tests/read-onlyactualpreflight/reviewPASS, NNэтимcollectorещёнезапускался. IntegratedPythonv2:332PASS, artifactsretained; finalv3suitepending.

NaturalAMI v2выполнил9actualSDcalls(3frozenprofiles×3relatedcrops) безASR/VAD/LID. BaselineDER67,6455/60,6465/57,9461%,counts10/13/6; C1DER43,6296/66,6114/54,8480%,K5/1/3; C2DER42,9352/49,8849/60,2255%,K6/8/5 противgold4/4/3. Это реальныеплохиеабсолютныерезультаты/третийC2regress+2,2794п.п.; онинеусредняютсясRUgate, невыдаютсязабольшуюточность, параметрыпоAMIнетюним. Pairedmic/общиеparticipants/trainingoverlapunknown сохранены. Полныйrun/refs/hyps/vectors/NNcounts/source/runtimes/CSV:natural-ami-diar-only-v2. ПервоначальныйSciPyprivateimportfail доNN0неудалён.


## 2026-11-07T05:26:32+03:00 — APKv2 и настоящий C2 smoke PASS; full10 launcher исправляется

Повторнаясборказа4m4s:173JVM/0fail/0skip,335Python, staticARM64pack/signaturePASS. Единственныйruntime-source deltaкAPKv1 — DiarizationEvidence.kt, то естьQApublication, ML/7weights/configunchanged. APK305478017B SHAa83bfe95cf7db72ddb65177a33586fdc52074a92759aa721212cc335f6b2a496 сохранён вrelease/REPLIKA-Hack-Step04-C2-v2-AllInOne-arm64.apk. Debug eec64359… установленповерхбезwipe, testAPK270692… прежний; Gradledaemonостановлен. UI2/2PASS10,812s наэтомAPK.

Actualnativeonefilesmokev2PASS:6333msaudio,8331msWorker,4real512vectors, counts/releasescomplete, sidecar70224B SHAa4b4171d0350b1b347a7a1fdf6378ff7852703b70fe24ae7b08ad2985cb3750e; atomicrename+fcntl разрешеныAndroidSELinux. Независимыйfrozenv3validator воспроизвёлturn[31,6275,0]и42tokens/42timestamps→14words→literalJuryJSON exact, actualDouble2000.0/Room2000boundaryPASS. Полныйproof native-c2-smoke-v2/pure-validation.json; этоfunctional, неcorpus/quality/speed/ARMacceptance.

ПервыйFULL10collector стартовалвcontext600-c2-android-v1, ноошибочнообратилсякru.replika.offline.MainActivity вместоactualru.replika.MainActivity. ОтказдоNN(inference_requested=false),installedAPKshaверифицированы,screenrestoreуспешен. ЭтоошибкаlauncherвCLI, APKне меняется; ownerправитпакетноограниченныйLAUNCHERintent. Старыйrun/log/semanticversionсохранены, повтортольковfreshv2. НеотмечаемСпринятым/Gitcommitдоactualfullgate.


## 2026-11-07T05:33:51+03:00 — полный Android C2 действительно выполняется

ПоследвухCLIlauncherfailдоNNзапускпровереннепосредственночерезexplicit ru.replika.offline/ru.replika.MainActivity(Statusok). CLIv5SHA7cc15015…/policy82af9dd… прошёл38focusedtests/read-onlyactualpreflight. Fresh Androidrun context600-c2-android-v3/session13311 RUNNING, instrumentationreportRUNNING, completed2/10. Первыйdev01получилCOMPLETE/полныйsidecar за101306мс; данныхвсегокорпусаещёнет, gatedoneнеобъявлен. APKv2/ML/refs/codefrozen, никакогоhostNN/Gradleпараллельно. SourceWIPbackup70files355098Bготов /home/egor/replika-safety/20261107T053157+0300-source; предыдущийfullWIP44306files250703620Bтакжеготов. Этоbackup,неGitcommit/acceptance. СледующаяфиксацияCтолькопослепроверкиполныхрезультатов.


## 2026-11-07T05:45:46+03:00 — полный native10 PASS, готовится фиксация C

context600-c2-android-v3 завершёнexit0/COMPLETE. ОбаgatePASS: weightedfixed5raw43/442vs44/442, Δ−0,226244п.п.≤0,5; devnativeK7/8 иDER0=0,18298480576441103 точноhost,нижеfixedV1.6+0,02. NativeDevraw70/533(однимсловомлучшеhost71), normalized16/532; perfiledev01−0,714286п.п. сохранён. Все10sidecars/wordpayloadполные,344real512vectors/56ASRchunks/2169tokens/767words,Pythonpure/word/JuryreplayPASS, allresourcesreleased/powerrestore1, inferenceoffline. Total10Worker527281ms, dev356169ms/270480audio=RTF1,3168; uncontrolledx86scope, causalускорение/ARM/phoneнеобъявляем.

FinalPython337testsPASS12,011s, codehashesduringtestsunchanged; JVM173/staticARM64/signature/UI2остаютсяPASS. Nativeindependentaudit ещёпересчитывается,requirementsauditготовится. Natural9independentaudit6288checksPASS подтвердилвключаяплохиеK0/3/thirdDERregress, неqualityPASS. Gitstaging45000+source/artifactpathsидёт, бинарныевеса/APK/.so/keyвuntracked/modifiedспискенеобнаружены. Ccommit/PR/releaseтолькопослепроверкиаудитов; HEADпока6e6a35a.


## 2026-11-07T06:14:46+03:00 — C завершил измерения и финальные проверки

Дополнительныйdev-onlyпротокол43a817… доNN закрылminDurationOffиselectedC2shift.32actualSD/902cleanembeddingcalls,ASRявныйcachedD71/533. Все4вариантаполные,ноFAILquality:off0,25 K6/8 DER21,6134%;off1,0 K4/8 DER19,7999%;shift0,25 K5/8 DER18,9807%;shift0,5 K4/8 DER24,2211%. ОстаётсяC2shift0,1/off0,5/K7/8/DER18,2985%. Независимыйаудит3648checksPASSданных/replay/метрик. Ни новаяAndroidмодель,нипересборка,ниповторныйAndroidдляотвергнутыхвариантовненужны. ФинальныйPython345/0fail иcodehashstable, JVM173/UI2/build/staticостаютсяPASS.

C1реализуетназванныевпланецентроиды/eigengap/малые/сглаживание,ported274parity; C2честноназванизмереннойwindowHCальтернативой,неNME-SC.32probe-followupзакрываетrecommendationcoverage,неослабляячисловыеgates. acceptance.json=PASS_FOR_EXPERIMENTAL_C2_PROFILE; full_project_accepted=false. Native10independentaudit564PASS,hostfull23audit3164PASS,natural9audit6288PASSцелостностиприK0/3. ПоследниеотчётыготовятсякодномуCcommit/PR/Release; GitHubstateпубликациибудетзафиксированотдельно,нетложногозаявленияофинальнойсдаче.


## 2026-11-07T06:50:13+03:00 — C опубликован, начат пункт 5

Публикация C подтверждена `artifacts/test-results/step-04/github-publication.json`:
feature `b619519`, PR #4 MERGED, merge `87f669a`, prerelease `hack-step04-20261107`.
Серверный digest C2 v2 совпадает с локальным SHA `a83bfe95…`; V1.6 `dec7523d…` и
D `048c42fd…` также проверены и сохранены. Пункт C завершён по экспериментальным
монтажным и native-гейтам: 10/10, dev K7/8 / DER18,2985%, fixed5 raw43/442,
независимый аудит564, JVM173/Python345/UI2 PASS. Общая приёмка проекта, естественного
диалога, времени слов, ARM и скорости остаётся открытой. Исторические FAIL сохранены.

Новая ветка `hack/task-05-runtime-import` от `87f669a` ограничена пунктом 5.
Готовится `auto_v1` за явным флагом: floor по {1,2,4} от clamp(cores−1,1,4).
Отсутствующий ключ задания сохраняет legacy; прежний C2 SD/refiner остаётся на2 потоках.
Адаптивное поведение не наследует C-приёмку: до продвижения в Android нужна свежая
host-проверка качества. Другой агент готовит13 кодековых примеров и проверку
URI→импорт→decode/системного выбора. На момент этой записи проверки пункта5 ещё
не выполнялись; в `docs/STEP_05_RUNTIME_IMPORT.md` сохранены план и PENDING.
Обновлены только документы; production-код, стенд, модели, NN/ADB/Gradle и Git
этой документальной работой не затронуты.


## 2026-11-07T07:02:51+03:00 — host CPU 2/1/4: 39/39, независимый аудит PASS

Три последовательных полных варианта по протоколу `cpu-auto-v1-protocol.json`
завершены: каждый выполнил 13 новых SD-прогонов, 428 чистых эмбеддингов и 69 новых
ASR-чанков без replay или известного K. Все файлы точно совпали с опубликованным
C2 по Jury JSON, raw/stable/refined turns, реальным векторам, диагностике refiner,
токенам/времени/словам и основным метрикам. Время исключено из равенства.

Внешний независимый аудитор заново проверил source/config/model/runtime/audio/ref
SHA, SDK num_threads, чистые окна, C2 из actual vectors, слова из actual tokens,
Jury JSON и WER/cpWER/DER0/250/K. Control2 — 1919, вариант1 — 1906, вариант4 —
1906 проверок PASS; суммарно 5731. Оба зафиксированных cohort gates пройдены отдельно:
dev raw71/533, normalized16/532, cpWER146/533, K7/8, native DER18,2984805764%;
holdout49/444,13/442,95/444,K4/5,DER13,8895661248%. Это уже просмотренные
регрессионные группы, не слепая проверка. Reserve заново не запускался.

Доказательства: `artifacts/test-results/step-05/independent-cpu-threads{2,1,4}-v1.json`
и `.md`; внешний скрипт и immutable snapshot SHA `11fc1e516a2a0663ce950e755833b1cb9c9fd86b9c07ffba45a795239772b929`.
Guard self-test10 и отказ перезаписи существующего отчёта сохранены отдельно.
Аудитор не запускал модели и не менял исходные результаты. Скорость, формула выбора
потоков на Android, thermal, импорт и полная приёмка новой runtime-политики пока
не подтверждены; пункт 5 остаётся IN PROGRESS.


## 2026-11-07T07:10:11.545962+03:00 — пункт5: hostCPU39 PASS; первая Android-сборка остановилась на QA-import

Все39 actualhostcase(13×threads1/2/4) COMPLETE; независимые5731checksPASS, тексты/векторы/интервалы/метрики EXACT C2. Python370PASS19,125s. Gradleattempt1 остановился на compileDebugAndroidTestKotlin: root пропустил import CpuPlan в EvaluationBatchTest. Main APK не устанавливался и не объявляется принятым; лог сохранён build-auto-v1-failed. Импорт исправлен после terminalexit1; готовится повтор с optionalperfQAfalse, defaultполногоQAtrue сохраняется. V1.6/D/C2 release APK неизменны.


## 2026-11-07T07:17:14+03:00 — сборка auto v2 и настоящий импорт; thermal не выполнялся

Сборка auto v2 завершилась за 1 мин 31 с: 192 JVM без ошибок/пропусков, полный
Python-набор 370 PASS. All-in-One/debug/test APK, семь весов, ARM64 static alignment
и прежний signer f4039935… проверены. APK сохранён как
`release/REPLIKA-Hack-Step05-AutoCPU-AllInOne-arm64.apk`, 306315573 байта,
SHA256 `ca18309f626d431d0bd7bb4c649a2a3ae77f3ef3b75f7f1bcb47c83bf449e15e`.
Debug/test установлены -r без wipe. Доказательства: step-05/build-auto-v2 и
python-cpu-collector/summary.json. Это сборка/статические проверки, не ARM runtime.

Android-import-thermal-v1: все 6 методов Plan19ImportFormatsTest PASS. Все 13
исходных CC0-сигналов прошли реальный Content URI→MediaImporter→системный decoder→PCM;
прошли повторный URI, пустой/повреждённый/отсутствующий источник, обрезанный WAV,
отмена после фактических байтов копирования и кадров декодирования. Источники и
чужие файлы сохраняются, собственные частичные файлы убираются. Системный DocumentsUI
этим не проверялся; synthetic tone не является качеством микрофона или ASR.

Общий запуск: 7 тестов, 1 FAIL. CpuThermalPlan19Test получил initializationError:
метод actualPowerManagerNoneSevereResumeCancellationAndReset should be void.
Термоконтроль не запускался и не отмечается PASS. Raw instrumentation.log сохранён;
root добавил явный : Unit у двух тестовых методов, пересобирается только test APK.
Main APK неизменен. CPU-native10, thermal-повтор, picker, скорость, ARM и общая
приёмка остаются PENDING.

До нового NN зафиксирован cpu-native-before-nn-protocol-v1.json SHA129f4fb4…:
новый dev nonregression относительно фактического C2 native70/16/145/K7/DER.1829848
проверяется отдельно от исторического collector gate и fixed-five port≤0.5п.п.
Исходная база независимо пересчитана; baseline run SHA488f4f19… . Ни моделей,
ни source, ни NN/ADB/Gradle/Git эта документальная запись не меняла.


## 2026-11-07T07:22:35+03:00 — thermal и DocumentsUI PASS; CPU-native control2 выполняется

Test-only v3 собран за 1 мин 11 с, SHA `ce4851c681962e8489bd9d8bc0edc0a229d245307b88fdfa9c19d0ef1f1df051`.
Main All-in-One ca18309f… и debug0a03b2f1… побайтно прежние. Первый thermal
initializationError сохранён как историческая неудача тестового запуска.

Actual API35/x86_64 thermal v2: 1/1 PASS за 3,175 с. NONE wait 0, блокировка SEVERE и
продолжение MODERATE, CRITICAL-cancel, reset до0 подтверждены через настоящий
PowerManager с управляемым override. Runtime cores 2 / auto0→1 подтверждён; NN=0.
Доказательства step-05/android-thermal-v2/{summary,actual-power-manager,instrumentation}.
Это поведение API эмулятора, не измерение физического нагрева/батареи телефона.

Actual DocumentsUI picker: 1/1 PASS за 17,674 с. Back не создал запись; из Download
последовательно выбраны WAV 8 кГц mono, OGG/Opus 48 кГц stereo, FLAC 44,1 кГц mono. Все импортированы
и декодированы, priorRowsAndAudioPreserved=true, ownedImportedRowsCleaned=3.
Сохранены report.json и PNG под android-picker-v1/device/picker-p19picker20261107T072016;
исходный stay-on 1 восстановлен. Старые данные не очищались, модели не запускались.

Root запустил настоящий full10 CPU explicit2-контроль: cpu-android-control2-v1
RUNNING. До NN сохранены receipt-v1/preflight-v3 с protocolSHA129f4f… и точными APK/
source/host pins. Итог всех 10 ещё не получен; CPU nonregression не объявляется.
Automatic-контроль, historical moderate1 smoke, скорость 1/3/10 мин и ARM остаются
отдельными проверками. Документы обновлены без source/NN/ADB/Gradle/Git действий.


## 2026-11-07T07:34:56+03:00 — native control2 принят; automatic0 выполняется

Настоящий control2 завершил 10/10, collector exit0/COMPLETE. Независимый сохранённый
аудит — 917 PASS: protocol129f4f…, отдельные эталоны, реальная C2-native база,
APK/source/model/CPU/receipt pins, actual vectors→C2 и tokens→words→Jury replay,
полный WER/cpWER/DER0/250/K пересчёт. Дополнительный новый CPU-гейт прошёл все
11 условий: raw70/533, normalized16/532, cpWER145/533, K7/8, DER0=0.18298480576441103.
Fixed5 отдельно43/442 vs host44/442, Δ−0,226244 п.п., port PASS; dev01−0,714286 п.п.
сохранён. 344 реальных512-векторов, 56 ASR-чанков, 2169 токенов, 767 слов; ресурсы
и экран восстановлены. Выход: cpu-android-control2-v1/independent-cpu-audit-v1.json,
SHA `4877922df64e098b95aef4ec9cb0a122b96963761d6229f1ed18847af1f91dd9`.

Независимый non-NN аудит codec/thermal/picker — 311/311 PASS. Он связывает source/
APK/fixtures/device receipts и assertions; не пересоздаёт удалённый PCM и не делает
новую ADB-проверку. First thermal-init FAIL сохранён, абсолютное качество речи,
телефонный нагрев, ARM и скорость этим не подтверждены.

После control2 и отдельного before-NN receipt root запустил automatic request0,
paired host1, out cpu-android-auto1-v1: RUNNING. Новый receipt имеет точный статус
READY_BEFORE_FIRST_NATIVE_AUTOMATIC_CPU_NN, timestamp до запуска и hash control2.
Внешний auditor v2 принимает этот известный status только для request0/effective1/
host1; старый9dc7 и его control2-proof сохранены. Полный automatic audit до
подтверждённого terminal10 не выполняется. Итог всей CPU-политики и пункта5 открыт.


## 2026-11-07T07:43:13+03:00 — automatic CPU1: full10 и строгий независимый аудит PASS

Auto request0 завершил 10/10, session13304 закрыт exit0. V2-аудитор independently
проверил точный automatic receipt до NN, preflight/host1, связь с принятым control2,
APK/source/runtime/model/audio/ref pins, реальные sidecar vectors и токены, метрики
и исходную C2-native базу. 921 PASS; protocol129f4f…/все11 nonregression условий PASS:
raw70/533, norm16/532, cpWER145/533, K7/8, native DER0=0.18298480576441103.
Fixed5 отдельно: native43/442 vs host44/442, Δ−0,226244 п.п., port PASS; каждый
пофайловый выброс сохранён. Все10 CPU maps: cores2/request0/ASR1/SD1/refiner1.
344 реальных512-векторов, 56 чанков, 2169 токенов, 767 слов, release/replay/Jury PASS;
состояние экрана восстановлено. Аудитор не запускал NN/ADB/Gradle/Git.

Выход: step-05/cpu-android-auto1-v1/independent-cpu-audit-v2.json и .md, SHA
`d03d61f41855422b46d5421f73ef9567073d9162a8176ccf0cda3197221a3ce4`.
Вместе с control2 — 1838 проверок на двух прогонах тех же10 файлов. Это проверка
качества CPU1/2 на API35/x86_64, не 20 независимых записей и не доказательство скорости.
Root далее проверяет legacy27/UI2 и compact QA; результаты пока не объявляются.
Скорость1/3/10мин, три длинных распознавания и ARM остаются открытыми.

Root также сохранил неатомарный WIP-снимок Linux
`/home/egor/replika-safety/20261107T073911+0300-step05-wip`: 678 файлов, 12496779 байт,
SHA `23c3034cf7f8059813ce27f1db92dd6d5273382240dc0c69f9a7f56b1b6c4e8b`;
пофайловые tar-хеши проверены. Это промежуточная страховочная копия, не коммит
или финальная приёмка пункта5.


## 2026-11-07T07:52:28+03:00 — regression27 и compact2 PASS; performance12 выполняется

Actual Android-регрессия27/27 PASS за12,598с: 15 MediaImport,8 ImportJournal,
2 безопасных storage/decode,2 Home UI Jury/default/manual. NN не выбирался, stay-on1
восстановлен; summary/instrumentation сохранены в android-regression-v1.

Два настоящих compact smoke COMPLETE: compact-smoke-v1 и compact-legacy-moderate-one-v1.
В каждом один Worker на повторе dev-mono-s, collectEvidence=false, WorkInfoSUCCEEDED;
full token/timestamp/word/vector arrays отсутствуют, counters/text сохранены, ресурсы
сбалансированы. Legacy v16/request1 фактически сохранил ASR1/SD2/refiner2 и pin=true.
Сохранены reference/hypothesis/diagnostics/case/scoring, точные source/APK и все7model
SHA до/после. Procedure SHA442367b8… . Это narrow compact/legacy контракт, не новый
quality-корпус и не ослабление strict full-C native gate; полного replay скрытых
массивов здесь нет. Исходные качественные native20-прогоны остаются отдельно.

Root запустил performance perf-2-4-4-2-v1 --execute: RUNNING. До NN зафиксированы
protocolSHAaef12832… и perf-execution-receipt-v1.json; driver SHAa910dd99…/11 tests PASS.
Порядок explicit threads2/4/4/2, в каждом пакете1/3/10min: 12 Worker,56min audio total,
compact QAfalse, source frozen. Входы — связанные контролируемые повторы, не новая
независимая группа. До полного результата не называются RTF, выигрыш скорости,
устойчивость длинных запусков или ARM PASS. Stage/PSS и периодические RSS/thermal
— снимки с overhead; физический телефон/непрерывный пик памяти не измерены.
Документы обновлены без source/ADB/NN/Gradle/Git действий.


## 2026-11-07T10:49:49+03:00 — подготовлен perf-аудитор; сохранён clock-step

Внешний saved-only perf-аудитор подготовлен, полный12 run ещё не проверялся как
завершённый. V1 SHA1f07e501… сохранён; V2 SHA2a707b31… добавляет только явный
UTC/monotonic anomaly report. AST parse,14 synthetic guards и запрет перезаписи
готового отчёта проверены; source snapshot/preparation-v2 сохранены. Проверяются
порядок2/4/4/2, все12 Worker/PID/UUID, source/APK/model/input/reference SHA, compact
контракт, независимые метрики/RTF/парные descriptive ratios и raw RSS/PSS snapshots.
QAfalse не позволяет full token/vector replay; такого заявления не будет.

Read-only sampler observation: строки20→21 дают wallΔ9958,936162с, monotonicΔ10,478699с,
расхождение9948,457463с. Точные строки и их SHA сохранены в perf-wall-clock-observation-v1.json.
Причина скачка UTC неизвестна; по нему нельзя объявлять NN зависшим или считать
ISO-разницу временем обработки. Пакет продолжает оставлять ресурсные снимки,
счётчик verified обновляется после проверки целой тройки. Worker/SystemClock и
host monotonic остаются отдельными источниками времени. Итог RTF/скорости/ARM
по выполняющемуся прогону не заявлен; ADB/NN/Gradle/source/Git агент не трогал.


## 2026-11-07T11:32:06+03:00 — performance FAILED: 3 driver-verified и 2 дополнительных native COMPLETE

Драйвер завершился exit1 в08:28:55.191944Z. Точная причина в batch2/threads4/perf-10m:
TimeoutCancellationException «Timed out waiting for1200000ms» из20-минутного
withTimeout в EvaluationBatchTest.kt:170. Это instrumentation guard ожидания
третьего Worker, не host subprocess5400s timeout; OOM данными не установлен.
Последний stage неоконченного Worker — diarizationReadMs, завершения SD/ASR нет.
Причина длительного JNI/SD самим этим логом не доказана.

Batch1/threads2 COMPLETE,3 driver-scored/verified, одинPID8526: Worker67890/223039/
854460мс для audio60000/179999/599999мс. Batch2/threads4 Androidreport содержит ещё
2 COMPLETE/SUCCEEDED:130422/577404мс для1/3мин, одинPID10346. Драйвер не дошёл до
их независимого скоринга; они не добавляются к verified3. Третьего валидного
case/diagnostics/hypothesis нет: .json-файлы содержат raw cat No-such-file errors.
Batch3/4 не запускались. Итого5 завершённых native-отчётов,3 driver-verified,
не12/12 и не законченный двунаправленный benchmark. Raw run/логи/частичные ошибки
сохранены, полный12-аудитор не запускался как успешный.

Root отдельно подтвердил терминальность: app PID10346 отсутствует, pidof app exit1,
остался только test PID6434; WM-Processor reschedule=false.
perf-process-terminal-observation-v1.json SHA164600d9c600ca01042753909d3d10fe8d57e54ad9132d6defbfe5f19b999484.
JNI исчезнувшего процесса больше не выполняется; это не отчёт об успешном окончании
10мин Worker или его штатном release. Stay-on1 восстановлен. Другой агент root
проверяет5 сохранённых завершённых результатов отдельно без нового NN.

Скорость/полный performance12/ARM не приняты. Пользователь имеет ARM-телефон,
но сейчас подключить его не может; Mac нет. Это не пауза всей работы: доступные
x86-проверки продолжаются без повторного запроса подключения. ps16k x86 SDK-образ
есть в официальном каталоге, но не установлен; фактический16KiB runtime PENDING.
Во время performance основной SDK не менялся. Агент выполнял только saved-file
анализ и правки owned-документов: без ADB/NN/Gradle/Git/production изменений.


## 2026-11-07T11:40:06+03:00 — partial2489 PASS; подготовлены ps16k и отдельный Windows ADB

Partial-аудит всех5 сохранённых native COMPLETE дал2489 PASS без нового NN:
perf-2-4-4-2-v1/independent-partial-audit.json,
SHA `ee8af7f27a866f53b31fab7a0eed3157e7c8b5ae1238beae7187967a27794926`.
Исходный driver verified-counter остаётся3, experiment FAILED, полного12/12/
speed/ARM acceptance нет. Missing10min не оценивается нулём и не заменяется
поддельной гипотезой; non-JSON pull-errors сохранены.

После терминальности failedJNI root установил официальный SDK ps16k x86_64
API35/ext13/revision5 и создал отдельный AVD, старый сохранён. Pre-boot receipt
ps16k-environment-v1/pre-boot.json фиксирует подготовку; boot/page-size/NN runtime
ещё не приняты. QA-buildv2 выполняется, успешная сборка пока не заявлена.

Пользователь подключил vivo X300 (Dimensity9500) USB: Windows PnP StatusOK,
ADB pending/devices пуст. Root запустил WindowsADB37.0.1 loopback5038 с
childenv max-emulator-port0/mDNS-autoconnect0. Попытка -H127.0.0.1 start-server
отклонена cannot-start-on-remote-host; успешна -P5038 start-server без-H.
Wrapper-H127/P5038 работает с уже живым сервером, его автостарт safe-fail.
Linux5037 и Windows5037 wslrelay PID22324 не тронуты. Телефонный NN/RTF не выполнялся.
Агент только прочитал primary AOSP flags и бинарные строки подготовленного
Google-signed37.0.1, не запускал ADB/server/USBIP/driver и не менял source/SDK.

## 2026-11-07T11:54:44+03:00 — ps16k загружен; cold3 PASS, первый hash-test прерван системой

Отдельный AVD revision5 фактически загрузился с PAGE_SIZE16384/API35/x86_64.
QA build SUCCESS за 5 мин 2 с, static/install hashes PASS; привязки сохранены в
`ps16k-environment-v1/installed-build-bindings.json`. Три cold-provision проверки
PASS: clean offline, повтор без извлечения и interruption/resume.

Первый отдельный prepared-model hash-test завершился `Process crashed`.
Сохранённый crash buffer показывает SIGSEGV system_server PID571 в
CachedAppOptimizer и более ранние Google crashes; REPLIKA crash не установлен.
Android перезапустил system_server. NN ещё не запускался: этот сбой не считается
ни product failure, ни доказательством совместимости JNI. Обе backcompat-записи
получили permission denied, отключение режима не заявляется. Повтор hash-test,
один настоящий короткий Worker и независимый аудит пока PENDING. Скрипт аудита
готовится отдельно, без ADB/NN/Gradle/Git и без изменения полного10-case гейта.

## 2026-11-07T12:01:14+03:00 — первый физический ARM Worker, независимый аудит79 PASS

ADB телефона vivo X300 подтверждён; root завершил один production Worker на
авторском dev-mono-s: API37/arm64-v8a/PAGE_SIZE4096, cores8/request0→4 во всех
трёх стадиях, PID12952. Протокол и preflight двух APK/семи моделей сохранены до NN.
Saved-only аудит79 PASS: 4×512 вектора/C2 replay/resources closed, 42 токена и
14 слов/Jury exact; Jury и семь основных метрик равны host4. Raw1/15, norm0/14,
cp1/15, native DER0 89/6333, K1. Worker3185мс на6333мс аудио — только короткий
описательный RTF0,502921. Полный ARM-корпус/скорость не приняты.

Санитизированные файлы: `vivo-arm-one-audited-v1/independent-audit.json`,
SHA `872ee23d85132eea3a5bbe55e2b152b957b6713e1c340c000525289f7ef361d6`;
аудитор `ebf99f345c05ddc00ffa0288a9112ecddbce009d14d092541369baf23c5f6e3b`.
Серийный номер/commands/dumpsys/DB не экспортировались. Аудитор не запускал
ADB/NN/Gradle/Git. PS16k остаётся на подготовке: NN там ещё не было.

## 2026-11-07T12:13:14+03:00 — ARM10/10 и ps16k NN проверены независимо

Физический vivo X300/API37/ARM/4KiB: полный collector COMPLETE10/10 в одном
PID15843, automatic0/cores8→4. Независимый saved-only аудит **942 PASS**, все
зафиксированные ARM-условия выполнены. Dev raw71/533, norm16/532, cp146/533,
K7/8, DER0 18,2984805764%; fixed5 44/442=host4, gap0. Проверены344×512 реальных
вектора,56 чанков,2171 токен/время и767 слов; ресурсы/C2/Jury replay PASS.
Raw/stable/refined turns и token strings совпали с host4; Jury8/10 exact, в двух
других изменились только timestamps. Численные различия векторов сохранены.
Root отдельным private count/row-SHA сравнением подтвердил сохранность5 прежних
Room-таблиц; личные DB/serial/dumpsys/команды не экспортированы.

Public `vivo-arm-full10-audited-v2/independent-audit.json`,
SHA `64d6d82d427991906e6af2cc3d1907dd879be44b4fbc8831183d097d1c5a2867`;
аудитор `e8e89fed0f3bf211b7f7b5a67997938edf2682a6a34e7065c71eedda9ff046b1`.
V1 не перезаписан: исправлена только запаздывавшая на1 метка счётчика, затем fresh
v2 повторил весь saved-only аудит. Это не новая NN-попытка и не изменение данных.

Ps16k API35/primary x86_64/страница16384: после system_server restart свежий
prepared-hash retry OK1, затем один настоящий6333мс Worker COMPLETE/OK1.
Независимый аудит **120 PASS**: CPU0→1,4×512/resources/C2,42tokens/14words/Jury
exact, Jury=host1. Worker13980мс — описание короткого compatibility smoke.
Настройки airplane0/wifi1/data1/stay1 RESTORED_EXACTLY по readback.
`ps16k-android-one-v1/independent-compatibility-audit-v2.json`,
SHA `7db6ad7ed8eba52c7184d477f2880b1212a3d954aa5a33c8c5eb963ed7db54d3`;
аудитор `ae893867a3fe8d0f464e31cf3d8c20e0988b0c43bcbb4bd48896d8d525441b48`.
Первый Google/system_server crash сохранён; backcompat-off не доказан (write denied).
ARM performance1/3/10мин root запустил отдельно, сейчас RUNNING; скорости/нагрева/
батареи/натуральной диаризации/word-gold/общей приёмки ещё нет. Аудиторы выполняли
только чтение и пересчёт сохранённых данных: без ADB/NN/Gradle/Git/source изменений.

## 2026-11-07T12:29:58+03:00 — пункт5 READY_TO_COMMIT, три длинных ARM-файла завершены

ARM1/3/10мин **3/3 COMPLETE/SUCCEEDED**, один PID24551, CPUautomatic0→4.
Worker/RTF:21429мс/0,357150;72287мс/0,401597;443545мс/0,739243.
В10мин включены135127мс настоящего ожидания охлаждения: thermal2→3→4→3→2,
далее колебания2/3. Счётчики621 окон/87 ASR-чанков сбалансированы; QAfalse,
полного token/vector replay этих длинных файлов нет. Аудит **1004 PASS**:
`vivo-perf-one-audited-v2/independent-audit.json`,
SHA `f1a53d67c48a99353674d7dc61928c2045103ca92cd65b26af93688b9530ffa3`.

46 sampler records:45 собственных PID samples и1 ранняя JSON-ошибка.
RSS1034876KiB, periodic PSS830950KiB, stage PSS876591KiB — разные снимки,
не непрерывные пики. Stage-log пуст, причина неизвестна. SD/refiner/ASR timings
берутся из actual diagnostics; вложенные таймеры не суммируются повторно.
Это один профиль и связанные повторные реплики, без причинного2/4-сравнения.
Цель RTF≤0,3 на флагмане не достигнута; старый FAILED x86perf12 сохранён.

Root после группы проверил оба APK и все5 прежних Room-таблиц: EXACT,
`vivo-prior-data-preservation-after-long3-v1.json`. Личные данные не опубликованы;
телефон освобождён, пользователь уведомлён. Исходники/семь моделей/кандидат
`ca18309f…` и testAPK `ce4851c…` не изменились;192 JVM/370 Python остаются
проверками текущей сборки. Подпись прежняя, стабильный fallback V1.6 `dec7523d…`
сохранён. Совокупность CPUhost39/x86native20/ARM10/long3/ps16k/import13/thermal/
picker/UI/legacy/compact позволяет готовить отдельный commit/PR пункта5.
**READY_TO_COMMIT**, Git/PR ещё PENDING; это не полная приёмка проекта, естественной
диаризации, word-gold, ARM16KiB/M1, батареи или целевой скорости.
Следующий пункт6 — английский/LID и стереозвонки, NOT STARTED. §0.4 сохраняет
приоритет; LLM/Lite/лендинг не добавляются до проверок конвейера.

## 2026-11-07T12:37:46+03:00 — пользовательская пауза после контрольного среза пункта5

Пользователь явно попросил закончить checkpoint, сохранить всё в Git/GitHub и
передать работу другому ИИ. Текущий статус — **PAUSED_BY_USER_AFTER_STEP05**.
Реализация и текущие проверки пункта5 подтверждены; исходники/APK/модели после
проверок не менялись, повторные тесты не запускались. Завершение сохранения и
публикации входит в запрошенный checkpoint, новых задач после него не выполняем.

Финальная commit/tag-привязка — история веток `hack/task-05-runtime-import` /
`hack/final`, [выпуск/tag `hack-step05-20261107`](https://github.com/XterrK/ReplikaAndroid/releases/tag/hack-step05-20261107).
Хеш текущего коммита и номер PR заранее не придумываются. Передача следующему
агенту: [HANDOFF_NEXT_AGENT.md](HANDOFF_NEXT_AGENT.md).

Пункт6 EN/LID+стереозвонки **NOT STARTED**, продолжать только по новой команде
пользователя. Телефон освобождён, кандидат `ca18309f…` и прежние5 Room-таблиц
сохранены; стабильный fallback V1.6 `dec7523d…` остаётся. Старые FAILED-прогоны,
цель RTF≤0,3 (не достигнута), natural C/word-gold D и ARM16KiB/M1 ограничения
не отменяются паузой или checkpoint. Общая приёмка проекта не объявляется.

## 2026-11-07T12:39:28+03:00 — тестовые сервисы остановлены и проверены

После терминальности всех NN root завершил собственный эмулятор5558 и Windows
ADB5038: обе команды exit0. Финальная read-only проверка показала live QEMU[],
Windows5038 listeners отсутствуют, `no_live_owned_test_services=true`.
[Команды](artifacts/test-results/step-05/user-pause-test-service-stop-v1.json),
[финальный receipt](artifacts/test-results/step-05/user-pause-test-services-final-v1.json).
Linux5037 не завершался; данные AVD, приложения телефона и прежние пользовательские
записи сохранены. Фоновых тестов нет. Остаётся только запрошенное сохранение
checkpoint/передача; пункт6 не начат и на пользовательской паузе не запускается.
