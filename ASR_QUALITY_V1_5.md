# REPLIKA V1.5 — качество распознавания и тихий вход

Дата: 2026-11-06. Host-эксперименты выполнены на Linux CPU, sherpa-onnx 2.0.1, два ASR-потока / один VAD-поток. Отдельно подтверждён настоящий Android Worker source11 на API35/x86_64: все семь студийных RU whisper файлов прошли декодирование, VAD, ASR, Room и JSON export. Эти результаты приведены отдельно от host. Шёпот в физический микрофон vivo X300, реальные шумы и тепловое поведение телефона не проверены.

## Что изменено

1. Текущая модель — GigaAM v3 E2E RNNT INT8; удалён runtime dispatch Whisper, legacy backend при повторной обработке разрешается в текущую GigaAM из manifest.
2. Добавлен консервативный постоянный gain **только для очень тихого файла**: исходный peak ниже `0.01` (-40 dBFS), выше `1e-6`; target peak `0.1`, максимум `20x` (+26 dB). Во всех остальных случаях gain=1.
3. Gain применяется только к временным массивам VAD и ASR. Оригинальный файл, дисковый PCM, waveform peaks, воспроизведение и вход диаризации сохраняются. Не создаётся новая микрофонная сессия, повторное декодирование или полный массив записи. У достаточно громкой записи обработка массива пропускается за O(1).
4. Diagnostics сохраняют исходный peak, применённый gain и его область действия. Threshold VAD `.5`, silence/speech `.25/.25 s`, max speech 20 s, контекст `100/0 ms`, thermal guards и single-speaker bypass диаризации сохранены.
5. Если после VAD/alignment нет ASR slices, native распознаватель вообще не создаётся; `asrLoadMs=0`, `asrInferenceMs=0`. Атрибуция текущей модели, финальный `READY`/«Речь не найдена», таймкоды и Room transaction сохраняются. Это устранение ненужной загрузки весов, а не измеренное обещание батареи/температуры телефона.
6. После положительного host эксперимента C реализован в **source11 и подтверждён настоящим Android Worker на всех семи файлах**: только после полностью пустого primary VAD, peak>1e-6 и current gain<20 выполняется bounded RMS scan оригинального PCM. Дополнительный detector-only gain=`max(currentGain,min(.02/RMS,20,.95/peak))`; второй VAD запускается лишь при росте gain более 1%. Primary threshold0.5, hysteresis и context100/0ms сохранены. Непустой primary и тишина пропускают RMS scan/retry; ASR input gain, исходный PCM и диаризация не меняются. Первый detector освобождается до второго.

Код: [QuietAudioGain.kt](app/src/main/java/ru/replika/domain/QuietAudioGain.kt), [ProcessingWorker.kt](app/src/main/java/ru/replika/ml/ProcessingWorker.kt), [AsrEngine.kt](app/src/main/java/ru/replika/ml/AsrEngine.kt). Anti-alias фильтр и оптимизированный PCM reader не менялись.

## Контролируемые измерения

32 обычные русские записи FLEURS/test: 406.62 с, 670 слов, заранее фиксированный порядок архива. Ослабленный вариант — тот же файл, умноженный на `0.01` (-40 dB), **это не настоящий шёпот** и не проверка плохого SNR. Метрика WER — Levenshtein по словам после lower-case, удаления пунктуации и ё→е; числа не преобразуются, ошибки не исправляются вручную. CER включает межсловные пробелы.

| Условие | v2 без gain | v3 без gain | v3 с принятым gain |
|---|---:|---:|---:|
| Обычная речь: словных ошибок / 670 | 57 | 34 | 34 |
| Обычная речь: WER | 8.51% | 5.07% | 5.07% |
| Искусственные -40 dB: ошибок / 670 | 140 | 146 | 33 |
| Искусственные -40 dB: WER | 20.90% | 21.79% | 4.93% |

У всех 32 исходных ordinary записей peak не ниже 0.022: принятый gain=1, текст и VAD интервалы совпадают с исходными. Сумма найденной VAD речи у ослабленных записей выросла с 184.41 до 307.712 с, число полностью пропущенных файлов уменьшилось с 4 до 0. Это сумма интервалов, **не VAD recall**: отдельной ручной разметки границ речи нет. На исходных файлах VAD находит 317.006 с; это не эталон разметки.

[Raw A/B](docs/test-evidence/v1.5/asr-host-ab.json), [принятая conservative policy](docs/test-evidence/v1.5/asr-host-quiet-safe.json).

Первый эксперимент с trigger peak `0.1` был отклонён: он изменял обычные тихие файлы и увеличил число ordinary ошибок с 34 до 36. Результат сохранён, а не скрыт: [отклонённый эксперимент](docs/test-evidence/v1.5/asr-host-gain-exploratory.json). Консервативный trigger не выбирается по словам эталона; дополнительные 64 новых файла проверяют его отдельно.

## Реальный публичный шёпот

Доступен реальный **английский** whisper sample EARS `p012/rainbow_05_whisper.wav` с опубликованным текстом и CC BY-NC 4.0. Он скачан из [официальной страницы авторов](https://sp-uhh.github.io/ears_dataset/), [лицензия и транскрипты](https://github.com/facebookresearch/ears_dataset). Использован только для отдельного исследования VAD; в APK и review ZIP аудио не включено. Русский GigaAM не оценивается по English WER.

Исходный EN whisper: VAD 13.984 с, принятая policy не меняет его (peak≈0.069). У дополнительно ослабленного на 40 dB реального шёпота VAD находил 0 с, с bounded gain — 4.256 с. Это частичное восстановление детекции, **не исправление whispered ASR** и не доказательство полноты найденных слов.

Первоначальный поиск дал [NCSpeech whisper-test-ru](https://ncspeech.org/blog/asr-benchmark-oct-2026), описанный авторами как 1003 файла / 2 ч. Указанный ими [HF dataset endpoint](https://huggingface.co/datasets/NCSpeech/whisper-test-ru) и API вернули HTTP 401 без авторизации; этот набор не использован. Последующий ограниченный поиск нашёл открытый студийный RU whisper в авторском Dialogs; результаты ниже. Публикации без доступных лицензированных audio+transcript не подменяются произвольным YouTube-контентом. EN пример, цифровое ослабление, студийный RU whisper и телефонный шёпот — разные проверки.

Усиливание громкости сохраняет акустику входа; оно не восстанавливает отсутствующее озвончение, произношение редких слов или речь, потерянную микрофоном/кодеком. Малый лицензированный студийный corpus теперь доступен, но для телефонного сценария по-прежнему нужны более широкий набор и реальные записи устройства.

### Дополнение: реальные студийные RU whisper test rows

[Dialogs авторов Langswap](https://huggingface.co/datasets/langswap/dialogs-ru-emotional-conversations), revision `a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd`: **все 7** строки `emotion=whisper` официального `test.csv`, 50.299s /84reference words /500characters, 3 актёра. Это живые студийные записи с авторской/crowd меткой whisper, ручным выравниванием transcripts по [статье §3.3–3.4](https://arxiv.org/html/2607.14310v1). Тексты взяты из независимого авторского CSV; сценарии GPT-assisted до записи людьми, не результаты тестируемого ASR. Нами не проведён пословный/фонационный auditory audit; это не телефонные записи. OpenRAIL с use restrictions/flow-down; raw WAV вне APK/repo. [Полный отчёт и воспроизведение](docs/test-evidence/v1.5/ru-whisper-dialogs-report.md), [provenance/SHA](docs/test-evidence/v1.5/ru-whisper-dialogs-provenance.json), [LICENSE](docs/test-evidence/v1.5/ru-whisper-dialogs-LICENSE.md).

| Модель / host путь | Word errors /84 | WER | Char errors /500 | CER |
| --- | --- | --- | --- | --- |
| v2, целые клипы | 1 | 1.19% | 1 | 0.20% |
| Текущая v3 E2E, целые клипы | 2 | 2.38% | 2 | 0.40% |
| v3 base RNNT, целые клипы | 0 | 0.00% | 0 | 0.00% |
| Текущая v3 E2E, штатные VAD/context single-speaker slices | 31 | 36.90% | 172 | 34.40% |

Gain=1 во всех 7: decoded peaks0.077390–0.290427, выше trigger0.01. Штатный VAD0.5 пропустил один файл целиком — 13.123s/23 слова, хотя whole-clip E2E распознаёт его с1 ошибкой. Raw VAD26.766s, context100/0ms сохраняет28.022s из50.299s (55.71% длительности клипов), 13slices. Это не ground-truth speech coverage: frame-level labels нет. Из 31gated word errors23 — полностью удалённый файл, ещё 8 — остальные6 после разрезания. [Все гипотезы и spans](docs/test-evidence/v1.5/ru-whisper-dialogs-results.json).

Проверен **только host-only** фиксированный backoff: после0spans при0.5 и original peak>1e-6 один retry0.35 с той же hysteresis/context. Пропущенный файл снова дал 0 spans; восстановлено0/1, итог31/84не изменился. Шесть непустых first passes и их тексты сохранились побайтно. На11 synthetic negatives×original/gain=22runs новых false-VAD IDs0, непустых transcript0; silence/near-silence guard оставляет0ASR calls. Положительного эффекта нет — policy **не включена**. [Backoff/negative evidence](docs/test-evidence/v1.5/ru-whisper-dialogs-zero-span-backoff.json).

Текущая модель была выбрана до этого малого holdout и после него не менялась. На этих 7files base/v2 не хуже E2E; основной выявленный дефект — VAD false negative/разрезание, а не недостаточное усиление. Универсальное улучшение настоящего шёпота не подтверждено; настройки не подбирались под эталоны.

### Host-only detector gain после пустого VAD

У пропущенного файла RMS≈0.0018099 при peak≈0.10205, ratio0.0177 против0.1057–0.1932 у остальных шести: отдельный высокий пик блокирует прежний peak-only gain. Проверены заранее фиксированные empty-only policies; ASR input gain в них остаётся прежним. A: detector-only gain≤4x с headroom0.95 и threshold0.5. B: threshold0.2 с прежним gain. Оба дают лишь короткие интервалы (1.864/1.704s context из13.123s), общий WER29/84 (34.52%) и31/84 (36.90%); это не восстановление всей фразы.

По заранее заданному следующему варианту C detector total gain=`max(currentGain,min(0.02/RMS,20,0.95/originalPeak))`, только когда первый VAD0.5 пустой и original peak>1e-6. Threshold/hysteresis/pre100/post0 не меняются. Здесь detector gain9.309x, **ASR gain1**: context9.512s и clip errors23→2/23; общий gated результат10/84, WER11.90%, CER44/500=8.80% против baseline31/84 и34.40%. Оставшиеся ошибки не объявляются исправленными. Uniform post150ms не улучшил WER/CER.

Все шесть непустых first passes сохранены. На11fixed synthetic controls×original/currentgain=22runs новых false-VAD IDs0; selected negative intervals и ASR input совпадают с уже проверенными baseline/A. Их actual blank outputs переиспользованы по идентичным входам; изменившийся whisper clip действительно распознан текущей v3. Post150 negative cases также проверены, непустых текстов0. [A/B/C подробности и границы](docs/test-evidence/v1.5/ru-whisper-dialogs-report.md), [машинный итог](docs/test-evidence/v1.5/ru-whisper-dialogs-summary.json).

**C принят в native source11; сборка успешна, Android Worker проверен на всех семи студийных whisper файлах.** Код: [ZeroSpanVadRescue.kt](app/src/main/java/ru/replika/domain/ZeroSpanVadRescue.kt), [ProcessingWorker.kt](app/src/main/java/ru/replika/ml/ProcessingWorker.kt). Это подтверждение конкретной ветки на небольшом студийном наборе, не телефонная приёмка и не гарантия на настоящей музыке/шуме. Модель, ASR input и глобальный VAD threshold не менялись. Post150ms не принят.

Native сканирует original big-endian float PCM блоками512, суммирует квадраты в Double с постоянной памятью, проверяет cancellation на каждом блоке и thermal status примерно раз в секунду. У invalid/empty RMS, gain cap и незначимого роста retry не запускается. `vadMs`/`vadLoadMs` суммируют оба прохода; `vadRescueRmsMs`/`vadRescuePassMs` показывают дополнительные затраты. В Room diagnostics добавлены `vadPrimarySpanCount`, `vadPrimarySpans`, `vadRescueAttempted`, `vadRescueApplied`, `vadDetectorGain`, `vadRescueRms`, `vadRescueRmsSamples`, `vadRescueReason`; эти параметры не выводятся в Logcat. `vadSpans` содержит итоговый выбранный результат. Empty final slices сохраняют0ASR load/inference.

[Pure policy/RMS tests](app/src/test/java/ru/replika/ZeroSpanVadRescueTest.kt): 8/8 PASS в standalone Kotlin2.1.20/JUnit4.13.2; [лог](docs/test-evidence/v1.5/zero-span-rescue-host-jvm.log). Полная JVM-регрессия build11: **80/80 PASS**, включая эти восемь тестов; [JUnit XML](docs/human-review/v1.5/evidence/jvm-build11/). Проверены measured positive gain, nonempty/silence scan guards, finite/invalid input, headroom/cap, сохранение current gain и sample-weighted RMS.

### Подтверждение настоящим Android Worker — source11

`WhisperPipelineV15Test`: **PASS**, один инструментальный тест обрабатывает все семь официальных test rows через настоящие Worker/MediaCodec/VAD/GigaAM, с одним участником. Независимые авторские эталоны используются только для подсчёта ошибок. Итог Android35/x86_64: **9/84 word errors, WER10.714%; 39/500 char errors, CER7.80%**. [Acceptance JSON со всеми гипотезами и Room diagnostics](docs/human-review/v1.5/evidence/whisper-native11/acceptance.json), [instrumentation log](docs/human-review/v1.5/evidence/android-tests-build11/WhisperPipelineV15Test-20261106T023158.log).

У проблемного `masha_dima_part11_287` длиной 13.123 s первичный Android VAD действительно вернул ноль spans. Дополнительный проход с detector gain 9.273613 сработал; ASR gain остался1. Получено 21 из 23 авторских слов, две ошибки вместо отсутствия текста: начальные «Дима, кстати» остаются потерянными. У остальных шести primary VAD непустой, retry не вызывается и RMS не сканируется (`vadRescueRms=null`). Во всех семи `recognitionInputGain=1`, SHA исходных WAV до/после совпадает; проверены свежий запрос Room, временные границы/участник и соответствие JSON export сохранённым сегментам. Это не утверждение о побитовом SHA временного PCM: тест сохраняет SHA исходного аудиофайла, а PCM read-only по реализации.

| Платформа / путь на тех же семи файлах | Word errors /84 | WER | Char errors /500 | CER |
| --- | --- | --- | --- | --- |
| Linux host, прежний VAD без rescue | 31 | 36.90% | 172 | 34.40% |
| Linux host, detector-only rescue C | 10 | 11.90% | 44 | 8.80% |
| Android35/x86_64, actual Worker source11 с C | 9 | 10.714% | 39 | 7.80% |

**Android baseline без C на всех семи не измерен.** Поэтому31→10 — парный host результат; число9 — отдельная нативная приёмка после изменения. Нельзя называть это Android улучшением31→9 или считать различие host10/native9 преимуществом платформы/модели. Студийные данные имеют авторскую/crowd метку whisper; наша ручная проверка фонации и пословный аудит эталона не проводились. Набор всего семь файлов трёх актёров, возможное training overlap неизвестно. Физический vivo X300, шёпот в его микрофон, реальные шумы/музыка, батарея и нагрев остаются непроверенными.

## Отрицательные и регрессионные проверки

Тишина, white noise -60/-40 dBFS и 80 Hz hum -50 dBFS, по 15 с, фиксированный seed: исходный VAD и принятый gain дают ноль speech intervals. В штатном pipeline ASR не вызывается для этих сигналов, поэтому gain не создаёт текст из этих четырёх отрицательных контролей. Это ограниченный набор, не гарантия на любую музыку или шум.

JVM `QuietAudioGainTest`: ordinary audio сохраняется побитово, включая паузы и signed zero; временный quiet буфер усиливается без clipping и изменения исходного массива; silence/non-finite/threshold не создают gain. Итог JVM/Android сборки см. общий отчёт, не host JSON.

Добавлен Android `QuietPipelineV15Test`: проверенный SHA официального WAV → отдельная копия → декодирование → умножение на 0.01 → signed PCM16 → настоящий Worker с одним говорящим. Проверяются фактический gain, VAD, непустой GigaAM prefix и перечитывание результата из Room. Отдельный silence case проверяет отсутствие текста и ошибки. QA строки/временные копии удаляются после окончания native work; исходный SHA сохраняется. Это imported-fixture regression, а не физическая микрофонная/whisper проверка. Выполнен на API35/x86_64: **2/2 PASS**, включая реальное отсутствие загрузки ASR на тишине (`asrLoadMs=0`, `asrInferenceMs=0`). [Android log](docs/human-review/v1.5/evidence/android-tests/QuietPipelineV15Test-20261105T235925.log), [quiet PCM16](docs/human-review/v1.5/evidence/v15-quiet-pipeline/quiet-pcm16-minus40db.json), [silence](docs/human-review/v1.5/evidence/v15-quiet-pipeline/silence.json).

Полный native pipeline — декодирование MediaCodec, VAD slicing, timestamps, Room, ручные правки, diarization и thermal management — требует Android regressions. Приведённый direct-ASR WER не выдаётся за WER всего Android pipeline. Automatic diarization остаётся известной проблемой.

## Как повторить

Host требует Python, NumPy и именно `sherpa-onnx==2.0.1`; Android runtime не заменяется. Все скачанные аудио хранятся за пределами repo/APK. Точные references, licenses, dataset revision и SHA-256 каждого fixture: [первые 32](docs/test-evidence/v1.5/fixtures.json), [следующие 64](docs/test-evidence/v1.5/fixtures-holdout.json). Веса и их hashes: [GigaAM v3](docs/test-evidence/v1.5/giga-v3-provenance.json), [Parakeet](docs/test-evidence/v1.5/parakeet-v3-provenance.json).

```bash
REPLIKA_EVAL_DIR=/tmp/replika-asr-v15
python3 tools/fetch_asr_v15_candidates.py --model giga-v3 --out "$REPLIKA_EVAL_DIR/giga-v3"
python3 tools/fetch_asr_v15_candidates.py --model parakeet-v3 --out "$REPLIKA_EVAL_DIR/parakeet-v3"
python3 tools/fetch_asr_v15_fixtures.py --out "$REPLIKA_EVAL_DIR/fixtures" --count 32 \
  --revision 70bb2e84b976b7e960aa89f1c648e09c59f894dd
python3 tools/fetch_asr_v15_fixtures.py --out "$REPLIKA_EVAL_DIR/holdout" --offset 32 --count 64 \
  --revision 70bb2e84b976b7e960aa89f1c648e09c59f894dd
python3 tools/benchmark_asr_v15.py \
  --python-path /mnt/f/ReplikaToolchain/python \
  --fixtures "$REPLIKA_EVAL_DIR/fixtures" \
  --v2 model-pack/giga-v2 \
  --v3 "$REPLIKA_EVAL_DIR/giga-v3" \
  --vad model-pack/vad/silero_vad.onnx \
  --out /tmp/asr-ab.json
python3 tools/benchmark_asr_v15.py \
  --python-path /mnt/f/ReplikaToolchain/python \
  --fixtures "$REPLIKA_EVAL_DIR/fixtures" \
  --v2 model-pack/giga-v2 \
  --v3 "$REPLIKA_EVAL_DIR/giga-v3" \
  --vad model-pack/vad/silero_vad.onnx \
  --models giga-v3 --gain-mode candidate_bounded_gain --gain-trigger .01 \
  --out /tmp/asr-quiet-safe.json
```

Для holdout заменить `--fixtures` на `$REPLIKA_EVAL_DIR/holdout`, оставить `.01`, модели `giga-v2,giga-v3`. Для Parakeet: `--parakeet "$REPLIKA_EVAL_DIR/parakeet-v3" --models parakeet-v3`. Для проверки beam: `--models giga-v3 --methods modified_beam_search --levels 1 --skip-vad`. Для PCM16-проверки: добавить `--pcm16`. Все runs выполняются последовательно; время inference не является контролируемым thermal benchmark. `--python-path` — только расположение host Python dependencies в этой среде; его можно опустить, если NumPy/sherpa установлены в используемом окружении.

## Дополнительная проверка

Следующие 64 файла архива использованы как отдельный holdout после фиксации gain policy: 687.90 с, 1189 слов. Ordinary v2: 82 ошибки / 6.90%; v3: 55 / 4.63%. Ослабленные -40 dB с принятой policy: v2 83 / 6.98%; v3 59 / 4.96%. Ordinary gain=1 во всех 64 файлах; VAD интервалы не изменились. У ослабленных VAD полностью терял 6/64, после gain — 0/64; суммарная детекция 343.508→519.118 с против 530.472 с на обычном сигнале. [Все гипотезы и интервалы](docs/test-evidence/v1.5/asr-host-holdout.json).

Объединённые 96 ordinary файлов: 1094.52 с / 1859 слов, v2 139/1859 (7.48%), v3 89/1859 (4.79%). На -40 dB v3 с conservative gain: 92/1859 (4.95%). Исходный -40 dB baseline без gain измерен на первых 32, поэтому не создаётся вымышленное общее число для 96 без gain.

Проверка влияния ITN без нового inference: исключены все 19 файлов, reference которых содержит цифру, одинаково для обеих моделей. На оставшихся 77 файлах / 1446 словах v2 65 ошибок (WER4.50%, CER0.956%), v3 58 (WER4.01%, CER1.054%). В этих 77 hypotheses цифр тоже нет. Полный WER заметно выигрывает от оформления числительных; no-digits lexical WER улучшился слабо, CER немного ухудшился. Это не объявляется большим акустическим улучшением. [Машинный аудит и исключённые случаи](docs/test-evidence/v1.5/asr-number-audit.json).

На ослабленном holdout с одинаковым conservative gain, no-digit references дают 51 файл / 956 слов: v2 35 ошибок (3.66%), v3 39 (4.08%). Преимущество новой версии на тихой акустике не подтверждено; доказанный крупный эффект относится к восстановлению уровня, а не к фонетике русского шёпота.

```bash
python3 tools/audit_asr_v15_numbers.py \
  --input docs/test-evidence/v1.5/asr-host-ab.json docs/test-evidence/v1.5/asr-host-holdout.json \
  --out /tmp/asr-number-audit.json
```

Один громкий стук/фрагмент поднимает глобальный peak и может отключить repair для тихой речи в остальной записи. Fixed gain не улучшает SNR и не исправляет уже потерянные кодеком/микрофоном детали. Автоматическое усиление по коротким окнам не добавлено: оно требует отдельного корпуса и проверки ложных срабатываний.

### Подтверждение на signed PCM16

Дополнительно первые 32 файла после -40 dB квантованы в signed PCM16 **до** gain, что учитывает потерю разрядности: E2E без gain 149/670 ошибок (22.24%), с gain 39/670 (5.82%). Base RNNT с gain 58/670 (8.66%). На no-digits 26/490 — E2E 30 ошибок, base 34. Это по-прежнему digitally attenuated voiced speech, не настоящая запись русского шёпота. [PCM16 raw](docs/test-evidence/v1.5/asr-host-e2e-pcm16-raw.json), [PCM16 E2E+gain](docs/test-evidence/v1.5/asr-host-e2e-pcm16.json), [PCM16 base+gain](docs/test-evidence/v1.5/asr-host-v3-rnnt-pcm16.json).

### Отрицательные сигналы и beam

Расширенная проверка: 11 детерминированных synthetic controls, по original/gain — 22 runs. Тишина, near-silence, white/pink noise, hum/harmonics, stationary chord, fan noise, повторяющиеся короткие impulses и их ослабленная копия. **Все direct ASR hypotheses и все gated transcripts пустые.** У двух impulse controls VAD выдаёт интервал уже в baseline; gain не добавил новых control IDs с false VAD, но это не нулевой false-positive VAD rate и не доказательство на любой реальной музыке/шуме. Модель не заменялась, текст не фильтровался/не чистился после recognizer. [10 исходных controls](docs/test-evidence/v1.5/asr-host-negatives.json), [дополнительные тихие impulses](docs/test-evidence/v1.5/asr-host-negative-quiet-impulses.json).

Modified beam search действительно поддержан runtime и проверен с 4 active paths: 35/670 word errors против 34 greedy; no-digits 24/490 против 23. CER чуть лучше, но word-quality выигрыша нет. Beam не включён; hotwords, vocabulary, LM и blank penalty по эталонам не настраивались. [Результаты](docs/test-evidence/v1.5/asr-host-beam.json).

### Окончательная конфигурация

GigaAM v3 **E2E** RNNT INT8, sherpa2.0.1 CPU, greedy; существующие допустимые 1/2/4 ASR threads, VAD 1 thread; mono 16 kHz; VAD threshold 0.5, min speech/silence 0.25/0.25 s, max 20 s; pre/post 100/0 ms; gain trigger 0.01, target 0.1, cap 20x, silence floor 1e-6. Gain один на всю запись; original PCM/playback/diarization сохраняются. Empty slices не загружают ASR. Производственная конфигурация после этих экспериментов зафиксирована, модели не раздваиваются.

Дополнение source11: empty-primary detector-only RMS/headroom retry C из раздела выше. Recognition gain и threshold сохранены; ветка подтверждена build11 и actual Worker на всех семи лицензированных студийных whisper fixtures. Это не замена отдельной телефонной приёмки.

Base RNNT имеет небольшой lexical выигрыш на float no-digits subset, но теряет пунктуацию/ITN и не улучшает PCM16 quiet subset. Parakeet больше примерно в 2.9 раза и на том же 32-file batch хуже E2E. Подробности, честное разделение ITN/акустики и источники — [MODEL_SELECTION_V1_5.md](MODEL_SELECTION_V1_5.md).

Первоначальная FLEURS/quiet/negative matrix сводится без нового inference: [машинный итог](docs/test-evidence/v1.5/asr-final-summary.json). Дополнительный RU whisper holdout и неудачный 0.35backoff записаны отдельно в [RU whisper report](docs/test-evidence/v1.5/ru-whisper-dialogs-report.md), в первоначальный итог не смешиваются. Android quiet/silence test выполняется отдельно на финальном build; host результаты его не заменяют.

```bash
python3 tools/benchmark_asr_negative_v15.py \
  --python-path /mnt/f/ReplikaToolchain/python \
  --model "$REPLIKA_EVAL_DIR/giga-v3" --vad model-pack/vad/silero_vad.onnx \
  --out /tmp/asr-negatives.json
python3 tools/summarize_asr_v15.py
```

Для точного повторения опубликованных 22 negative runs первый negative run ограничить `--only silence,near_silence,white_noise_-60dBFS,white_noise_-40dBFS,pink_noise_peak_004,hum_80Hz_peak_003,hum_50Hz_harmonics,repeating_short_impulses,synthetic_stationary_chord,fan_hum_and_noise`, второй — `--only quiet_repeating_short_impulses`. Без `--only` новый runner выполняет все 11 controls вместе с тем же seed 104.
