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
