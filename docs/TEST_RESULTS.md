# Результаты тестирования — PLAN_19H

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
