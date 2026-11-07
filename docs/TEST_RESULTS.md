# Результаты тестирования — PLAN_19H

**WER / CER / cpWER / DER показывают ошибки — меньше лучше.** Например,
3,01% normalized WER = 16 исправлений на 532 слова, а не 3% успеха.
Главный raw WER сохраняет знаки и регистр; normalized — диагностика лексики.
Доля файлов с верным числом спикеров и punctuation F1 имеют обратное направление:
больше лучше. [Пояснения и формулы](../tools/eval/SCORING.md).

## Методика и независимые эталоны

Свежий baseline ML V1.6 / pack V1.5, без смены моделей и параметров: automatic−1 на всех файлах,CPU2threads,sherpa2.0.1/ORT1.28.2. Эталонный текст и число спикеров не передаются в recognizer/diarizer. Основная метрика — rawWER с регистром,пунктуацией,ё/е и числительными. NormalizedWER,CER,number-normalizedWER,punctuationF1,initial-case,cpWER,DER0/250,ошибки таймкодов/coverage и RTF считаются отдельно. [Полный протокол](../tools/eval/SCORING.md).

Корпус: [manifest](../benchmark/eval/manifest.json), [provenance](../benchmark/eval/provenance.json), [validation](../benchmark/eval/validation.json). Langswap Dialogs,pinned revision,77уникальных авторских клипов.13файлов/485.722s:6dev+4holdout монтажа разных актёров и3mono. Officialval→dev/test→holdout; исходники и точные авторские строки между split не повторяются; прежние7whisper-test исключены. Выбор зафиксирован до inference. PublisherLFS SHA/размеры проверены;404 отсутствующие исходники отфильтрованы по pinned publisher tree до распознавания. Тексты — независимые эталоны авторов, нами заново не размечены; training overlap неизвестен. Условия и лицензия сохранены.

**DER/timing scope:** gold — границы размещённых авторских utterance-клипов. Это montage/utterance-interval proxy, не независимая speech-activity разметка живого диалога и не word-level gold. В DER входят overlap/паузы; collar250ms означает общую ширину±125ms. Raw native turns и число кластеров оцениваются отдельно от проекции ID в Jury JSON. cpWER может превышать100% из-за лишних speaker streams.

## Принятый host baseline

| Split | Файлов | Raw WER | WER normalized | cpWER raw | Native DER0 proxy | Число native спикеров верно | Host RTF |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| dev | 8 | 124/533 = 23.26% | 7.33% | 82.93% | 43.16% | 2/8 | 0.369 |
| holdout | 5 | 73/444 = 16.44% | 5.43% | 100.45% | 51.55% | 2/5 | 0.360 |

Полные reference/hypothesis/diagnostics/metrics, config/manifest/code fingerprints и results.csv: [baseline-v16-host-android-decoder](../artifacts/test-results/step-02/baseline-v16-host-android-decoder). Первоначальный directPCM host baseline сохранён отдельно, не перезаписан.

HostRTF включает per-invocation SHA, WAV/Android-math emulation,VAD,diarization,planner,ASR release; без scorer/JSON/persistence. OS cache/температура/фоновые задачи не контролировались; это Linux/WSL CPU, не телефон/ARM. PeakRSS всего hostпроцесса, включая scoring:426.4MiB; не AndroidPSS/peakRAM.

## Android: пять actual Worker cases offline

Один instrumentation batch test выполнил5настоящих productionWorker cases на отдельном AOSP API35/x86_64 AVD,2048MB/2cores/SwiftShader. Airplane=1,Wi-Fi/data off. Эталоны/число участников не staged; толькоaudio/id/SHA, threads2, automatic−1. Фактические Jury JSON/diagnostics: [baseline-v16-android](../artifacts/test-results/step-02/baseline-v16-android). ВходныеSHA и авторские refs совпадают с host.

Пользователь уточнил, что порог0.5п.п. относится **ко всей фиксированной пятёрке**, при сохранении различий по файлам. На442эталонных rawсловах host76ошибок,Android75: delta−0.226244п.п., **corpus gate PASS**. [Сводка и CSV](../artifacts/test-results/step-02/port-comparison-user-gate). Четыре файла имеют exactWER parity; holdout02 отличается одним словом `Skeleton`/`скелетон`,23/148 против22/148,−0.675676п.п. Оно не исправлялось и не скрывалось. Прежний более строгий per-file PORT_PARITY_FAIL сохранён как исходное evidence; новая сводка только пересчитывает уже сохранённые outputs по уточнённому правилу, не выдавая её за новый inference.

RTF настоящего Worker на этих5файлах1.185–1.410. Это x86_64 functional proxy, не ARM/physical acceptance; статическое16KiB alignment не заменяет16KiB runtime.

## Decoder fidelity и ограничение межплатформенного совпадения

Даже canonical16k WAV проходит через инкрементальныйDouble-clock иFloat32 interpolation AudioDecoder. Простой hostPCM16 read отличался. Generic эмуляция32768B WAV packets+integerPTS совпала побитно со всеми1190678захваченными Android samples; reference/model параметры не менялись. Helper проверен против независимого scalar-алгоритма; повторный13file baseline использует исправленный hostport.

ТочноеPCM не устранило одно несовпадение слова: same-host probes/direct/actualAndroidPCM/emulation, полныйcase и AVX/SSE CPU-tier probes всё равно даютSkeleton; свежий productionGigaAmEngine наAndroid даётскелетон. Semver,ORT иgitaf2d8d81/date совпадают. Конкретная причина расхождения сборок не установлена; CPU-tier/PCM как единственная причина не доказаны. Это не объявляется исправленным ASR-багом или выигрышем модели. [Положительные/отрицательные доказательства](../artifacts/test-results/step-02/decoder-parity); сырыеPCM/временныеqemu binaries хранятся локально внеGit.

## Проверки и ограничения

65Python tests PASS:scorer39,pipeline16,decoder3,runner4,corpus-gate3; дополнительно80random DER cases сверены с exhaustive permutation/time oracle на двух collars. JVM89 остаются зелёными, unchanged tasksUP-TO-DATE; All-in-One и testAPK сборкиPASS. Androidbatch1test/5inferences,decoder1test иfreshASR1test PASS. MainAPK и ML/storage/UI не менялись; отдельно расширен testAPK.

Модели SHA-проверяются каждый process. Config,код,helper,зависимости,refs и savedartifacts fingerprinted; resume проверяетцелостность, partialattempt архивируется,failedexperiment получаетCSVстроку. Нулевой знаменатель→null, не выдуманный ноль. Реальныеtokens/timestamps GigaAM сохранены; tokens содержат ASCII-пробелы, не только`▁`. Word assignment ещё не внедрён.

Это baseline до улучшений. Automatic diarization по-прежнему плоха; корпус малый,3актёра,монтажный,не unseen-speaker/natural-dialogue acceptance. ARM/физический микрофон/энергопотребление/длинные записи остаются отдельными проверками. Последнее обновление:2026-11-07T00:02:35+03:00.

## 07.11.2026 — пункт 3, opt-in ASR context600

WER — ошибки, меньше лучше. Модели/VAD/gain/диаризация прежние; реальный ASR pre-roll600мс и word assignment по token emission frames. Обычный build-defaultv16 сохранён.

| Набор | Baseline raw WER ↓ | Context600 raw WER ↓ |
| --- | ---: | ---: |
| Host dev |124/533=23,265%|71/533=13,321%|
| Host прежний holdout |73/444=16,441%|49/444=11,036%|
| Host новый disjoint reserve |135/743=18,170%|83/743=11,171%|
| Actual Android, фиксированная пятёрка |75/442=16,968%|43/442=9,729%|

Normalized dev16/532=3,008% означает16 исправлений на532слова, а не3% успеха. Actual Android normalized11/439=2,506% против20/439=4,556% baseline. Short dev deletions2→0. Полная независимая word-time/diarization/speed приёмка не установлена: это ASR quality/port PASS за флагом. Старый holdout после первого отклонённого профиля используется как regression validation; reserve selection заморожена до второго выбора и проверяется отдельно.

Host fixed-five44/442, Android43/442, delta−0,226п.п.≤0,5PASS; per-file outlier−0,714п.п. и все текстовые/временные различия сохранены. 32native chunks/1224tokens/434words полностью восстановлены из actualpayload; fallback/truncation0. 125Python/111JVM/build/static/2nativeUI PASS; первая UI-попытка сохранена, исправлена только синхронизация теста.

Current-APK one-file timing control: legacyRTF4,739, word4,605; historicallegacy1,185. Обе текущиеSD стадии~219/217с против прежних50,7с. Причина отличия не установлена; benchmark не доказывает ускорение/ARM/телефон. Полная приёмка ещё открыта, defaultlegacy сохранён. [Полный отчёт D](STEP_03_VAD_WORD_ASR.md), [индекс](../artifacts/test-results/step-03/results.csv), [граница приёмки](../artifacts/test-results/step-03/acceptance.json), [контроль времени](../artifacts/test-results/step-03/performance-control.md).


## 07.11.2026 — пункт4 C2, host проверен; Android ML pending

Все48fixed-K и672automatic SD cases сохранены. Выбран один глобальный C2 на исходном
ERes2Net512: nativeSDthreshold0,30/shift0,1, clean1,5s/step0,75s, averageHCτ0,36,
reassign-small, grid125ms,max8,mincluster2s/3%,smooth500ms. Старые7моделей/pack1.5 прежние.

| Набор | Native DER0 baseline ↓ | C2 ↓ | Точное K baseline ↑ | C2 ↑ | C2 rawWER ↓ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dev8 |43,1567%|18,2985%|2/8|7/8|71/533|
| Original holdout5 |51,5457%|13,8896%|2/5|4/5|49/444|
| Reserve10 |47,6591%|22,4396%|1/10|5/10|83/743|

Новые полныеVAD/SD/windowembedding/HC/GigaAM прогоны13+10 COMPLETE; независимыйfullC2audit3164checksPASS.
ВсеJuryJSON/ASRtokens+timestamps/749vectors/refinedturns/coremetrics совпали сзафиксированными
исследовательскимивыходами, rawWER unchanged относительноD. Это previouslyseen regression cohorts,
не blind/natural-dialogue и не87,5% точности всехслов/реплик. Reserve K50% остаётся слабымместом.

Kotlin C2:157differential включая23actualcases без exactturn/IDs/acceptedрасхождений.
Gradle170JVM/0fail/0skip, All-in-One/debug/testAPK, staticARM64pack/signature и2AndroidUI PASS.
ПервыйUIFAIL приAsleepэмуляторе сохранён; wakeи повторбезизмененияAPK дали2/2PASS10,327s.
КандидатAPK305476189B SHA6a73427638ccd3e1e04e725d1080d604c5941d571e796544c1fa2733f4f965fd
сохранён отдельно; V1.6 иD hashes прежние. ActualAndroidC2ML, fixedfiveWERportgate иdev8nativeDER/count
ещё не выполнены. [Подробности](STEP_04_DIARIZATION.md), [аудит](../artifacts/test-results/step-04/full-c2-equivalence-audit.json),
[сборка/JVM](../artifacts/test-results/step-04/build-c2-v1/summary.json), [UI](../artifacts/test-results/step-04/ui-v2/summary.json).


### Итог C: actual Android10 и сохранённый контрольный профиль

Native8dev: K7/8, nativeDER0 **18,2985%**, raw70/533=13,1332%, normalized16/532=3,0075%,
cpWER145/533=27,2045%. Порогcount/DERпройден. Fixed5raw43/442vs44/442host,
Δ−0,226244п.п.≤0,5PASS; dev01−0,714286п.п. сохранён какдиагностика.
Все10sidecars:344реальных512dimвектора,56ASRчанков/2169токенов/767слов;
независимыйnativeaudit564checksPASS. Вектораhost/nativeнепобайтноравны,
текстовые/временныедиффысохранены; разметкаголосов/nativeDERсовпала.

Дополнительные32SDdevпрогонаподтвердилиотказотminOff0,25/1,0 иshift0,25/0,5:
K6/4/5/4из8, DER21,6134/19,7999/18,9807/24,2211%вместо7/8/18,2985%.
ИхASR—явныйreplayреальногоD,неповторныйGigaAM. КонтрольныйAPKне меняется.
Финальные345Python/173JVM/UI2/staticPASS. [ГраницаCприёмки](../artifacts/test-results/step-04/acceptance.json),
[нативныйаудит](../artifacts/test-results/step-04/context600-c2-android-v3/independent-audit.json),
[дополнительныепробы](../artifacts/test-results/step-04/final-native-parameter-audit.json).
ЕстественныйAMIпо-прежнемуK0/3,на третьемclipDERхужеlegacyна2,2794п.п.;
ARM/телефоннаяскорость/независимыеwordtimingsнеприняты.
