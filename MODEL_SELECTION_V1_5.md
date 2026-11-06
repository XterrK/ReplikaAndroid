# REPLIKA V1.5 — выбор модели

Дата исследования: 2026-11-05–06. Цель — локальная русская транскрибация на Android, компактный All-in-One, CPU без облака. Физический vivo X300 сейчас не подключён.

## Решение

Использовать **GigaAM v3 E2E RNNT INT8** в существующем sherpa-onnx 2.0.1. Whisper удалён по прямому запросу пользователя. Старые тексты с историческим source Whisper сохраняются; повторная обработка использует текущую GigaAM из manifest.

Выбор зафиксирован до позднего RU whisper holdout и после него не менялся. E2E не заявляется победителем на любом шёпоте: на семи студийных целых клипах v2/base дали 1/0 ошибок из 84 слов против 2 у E2E. Основная обнаруженная потеря находилась перед ASR: VAD целиком пропускал один клип длиной 13 s. Теперь detector-only RMS/headroom retry принят в source11 и проверен actual Android Worker на всех семи: 9/84 word errors, CER39/500=7.80%. Модель, ASR input gain и глобальный threshold0.5 сохранены; подробности ниже и в [ASR_QUALITY_V1_5.md](ASR_QUALITY_V1_5.md).

На заранее выбранных 32 русских записях FLEURS/test, 406.62 с / 670 слов, v3 дал 34 словных ошибки против 57 у v2: WER 5.07% против 8.51%. Это небольшой публичный набор, а не оценка всей русской речи или настоящего шёпота. Файлы выбраны по порядку архива до inference; слова эталона не передаются модели. Числа оцениваются буквально, без ручного исправления ошибок и подгонки словаря. [Исходные результаты](docs/test-evidence/v1.5/asr-host-ab.json), [набор и лицензии](docs/test-evidence/v1.5/fixtures.json).

**Существенная часть полного WER выигрыша — формат числительных.** На всех 96 файлах после симметричного исключения references с цифрами остаётся 77 файлов / 1446 слов: v2 65 ошибок (4.50%), v3 58 (4.01%). CER при этом у v2 немного лучше: 0.956% против 1.054%. Поэтому большой акустический прорыв не заявляется: у v3 удобнее итоговый текст и небольшой выигрыш lexical WER на этом subset, с отдельными регрессиями. [Аудит чисел без нового inference](docs/test-evidence/v1.5/asr-number-audit.json).

Веса v3 занимают 231,897,202 байта против 241,086,439 у v2. На Linux CPU с двумя потоками суммарный inference был 31.36 с против 59.34 с. Кеши, температура и фоновая нагрузка не контролировались: это совместимость и ориентир, **не измерение скорости, памяти, нагрева или батареи телефона**. Исторический результат пользователя «около 30 с на четырёхминутной записи» относится к старой версии на vivo и не переносится автоматически на v3.

V3 распознаёт пунктуацию и регистр непосредственно. Авторы описывают обучение на голосовых сообщениях, atypical/natural speech и других доменах; их опубликованные общие улучшения не считаются доказательством качества русского шёпота в REPLIKA. [Официальный GigaAM](https://github.com/salute-developers/GigaAM), [карточка v3, MIT](https://huggingface.co/ai-sage/GigaAM-v3).

Важно: v3 **без подготовки уровня** на искусственно ослабленной на 40 dB обычной речи дал WER 21.79%, v2 — 20.90%. Исправление очень тихого входа описано отдельно в [ASR_QUALITY_V1_5.md](ASR_QUALITY_V1_5.md); версия модели сама по себе этот дефект не устранила.

## Проверенные альтернативы

| Модель | Применимость к REPLIKA | Вывод |
|---|---|---|
| GigaAM v2 RNNT INT8 | Подтверждённая пользователем историческая работа на vivo, тот же runtime, около 241 MB весов | Сохранён как исходный A/B и backup; на нашем ordinary subset уступает v3 |
| GigaAM v3 E2E RNNT INT8 | Около 232 MB, MIT, совместим с текущим runtime, текст с пунктуацией | Основная конфигурация V1.5 |
| GigaAM v3 non-E2E RNNT INT8 | 229,343,109 байт, MIT, char decoder, без пунктуации/ITN | Небольшое lexical преимущество на ordinary no-digits, не устойчивый выигрыш на тихом PCM16; не поставляется |
| Parakeet TDT 0.6B v3 INT8 | 25 языков, включая русский, CC BY 4.0; готовая sherpa-конверсия, 670,478,772 байта | На тех же 32 файлах WER 8.06% ordinary / 7.76% quiet+gain, хуже выбранной GigaAM; не поставляется |
| GigaAM Multilingual 220M / 600M | MIT, char-wise CTC, новое семейство с несколькими языками; требует отдельной проверки export/frontend/decoder | Перспективная отдельная работа, не автоматическая замена RNNT |
| T-one 71M | Apache 2.0, потоковая телефония 8 kHz, свой CTC/splitter/KenLM pipeline | Не является прямой заменой для широкополосных голосовых и видео; полный официальный LM около 5.46 GB |
| Vosk | Малые мобильные и большие серверные модели, другой runtime | Малый размер полезен для слабых устройств, но выигрыша качества для текущего сценария не доказано |

Parakeet: [официальная NVIDIA model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3), [поддержка sherpa](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html), [точные файлы конверсии](docs/test-evidence/v1.5/parakeet-v3-provenance.json). Больший размер сам по себе не доказывает лучший русский ASR.

T-one: авторы показывают преимущество в телефонии, но Common Voice у него хуже GigaAM v2 в их сравнении. В [официальной конфигурации](https://huggingface.co/t-tech/T-one/blob/main/config.json) sample_rate=8000; [проект и архитектура](https://github.com/voicekit-team/T-one), [веса и опубликованные тесты](https://huggingface.co/t-tech/T-one). Это полезный специализированный вариант, не основание расширять наш APK на несколько GB.

Vosk: [официальный каталог](https://alphacephei.com/vosk/models) разделяет мобильные малые и серверные большие модели. Чужие WER на других наборах не смешиваются с нашим FLEURS subset.

## Новое GigaAM Multilingual не пропущено

Семейство опубликовано в 2026 году: 220M/600M энкодеры, pretrain 2M часов, ASR fine-tune 50K часов. Официальная карточка сообщает Russian FLEURS WER 4.4%/3.0%, CV 7.1%/5.1%, internal 7.6%/6.0%. Методика исключает references с цифрами и файлы длиннее 30 с, нормализует числительные в слова. Эти числа нельзя напрямую сопоставлять с нашими 32 файлами или таблицей v3. [Карточка](https://huggingface.co/ai-sage/GigaAM-Multilingual), [статья авторов](https://arxiv.org/abs/2607.10371).

В проверенном [каталоге официальных sherpa GigaAM export scripts](https://github.com/k2-fsa/sherpa-onnx/tree/master/scripts/nemo/GigaAM) есть v1–v3 CTC/RNNT, но готовой проверенной интеграции нового multilingual семейства в наш Android runtime не найдено. Сам upstream умеет ONNX export; это не равно подтверждённой работе нужного frontend и decoding на Android. 600M дополнительно увеличивает требования к памяти. Для русского приложения сейчас выбран измеренный совместимый v3; абсолютное звание «лучшая модель для любого устройства и шёпота» не заявляется.

## Воспроизводимость и сохранение

V3 export: [репозиторий конвертера sherpa](https://huggingface.co/csukuangfj/sherpa-onnx-nemo-transducer-punct-giga-am-v3-russian-2025-12-16), revision `a6039be7cee829a9044a69ac0ebaf1c191217c97`; [SHA-256 каждого файла](docs/test-evidence/v1.5/giga-v3-provenance.json). MIT LICENSE включён в поставку. Native модель не обучалась и не дообучалась на тестовых текстах.

Старые `model-pack/giga-v2` и исходный `model-pack/replika-offline-pack.zip` сохранены. Новый V1.5 pack содержит только текущую GigaAM, VAD и диаризацию. Нативная приёмка, сборка и ограничения устройства фиксируются в общем отчёте V1.5; автоматическая диаризация не объявлена исправленной.

## Дополнительные A/B

После выбора conservative gain проверены следующие **64 новых файла** архива, не использованные при его разработке: 687.90 с, 1189 слов. Ordinary v2: 82/1189 ошибок (6.90%); v3: 55/1189 (4.63%). С принятым gain на -40 dB: v2 83/1189 (6.98%), v3 59/1189 (4.96%). У всех 64 ordinary gain=1, VAD интервалы совпадают. [Holdout raw evidence](docs/test-evidence/v1.5/asr-host-holdout.json).

Суммарно на 96 ordinary файлах, 1094.52 с / 1859 слов: v2 139 ошибок (7.48%), v3 89 (4.79%). Это подтверждает выбор в двух фиксированных частях данного набора, но не гарантирует превосходства на каждом отдельном файле, вне FLEURS или на русском шёпоте.

### Non-E2E RNNT против E2E

На 96 файлах base v3 RNNT: literal WER 127/1859 (6.83%) ordinary и 132/1859 (7.10%) quiet+gain. На no-digits subset 77/1446 ordinary: base 53 ошибки (3.67%), E2E 58 (4.01%); quiet+gain: base 59 (4.08%), E2E 61 (4.22%). Разница невелика и не доказывает универсального преимущества base. На первых 32 файлах с дополнительной **signed PCM16 quantization после -40dB** результат обратный: no-digits base 34/490, E2E 30/490; literal base 58/670 (8.66%), E2E 39/670 (5.82%).

Base не заменяет удобный текст с пунктуацией ради пяти слов на small ordinary subset. Не добавлялись выдуманная пунктуация, вторая пользовательская модель или дообучение по тестовым словам. [Base raw evidence](docs/test-evidence/v1.5/asr-host-v3-rnnt.json), [PCM16 base](docs/test-evidence/v1.5/asr-host-v3-rnnt-pcm16.json), [PCM16 E2E](docs/test-evidence/v1.5/asr-host-e2e-pcm16.json), [аудит quiet subset](docs/test-evidence/v1.5/asr-number-audit-quiet.json), [точная base revision/hashes](docs/test-evidence/v1.5/giga-v3-rnnt-provenance.json).

Размеры энкодеров отличаются всего на 6 байт. Байтовый аудит сам по себе недостаточен из-за возможного сдвига protobuf: поэтому отдельно сравнены 954 embedded initializer tensors по именам, shape/type и payload hashes. Отличаются 862 tensors; это **разные ONNX параметры**, их нельзя просто разделить между двумя головами. Файлы не объединялись и не подменялись. [Тензорная проверка](docs/test-evidence/v1.5/encoder-tensor-comparison.json), [байтовый аудит](docs/test-evidence/v1.5/encoder-comparison.json).

### Parakeet и beam

Parakeet на тех же первых 32 файлах: ordinary 54/670 (8.06%) против E2E 34/670 (5.07%); quiet+gain 52/670 (7.76%) против 33/670 (4.93%). На no-digits 26/490 ordinary: Parakeet 37 ошибок против 23; quiet: 40 против 22. Размер весов примерно в 2.9 раза больше. Поэтому он не выбран для All-in-One. [Все гипотезы](docs/test-evidence/v1.5/asr-host-parakeet.json). Отдельные [Linux RSS snapshots](docs/test-evidence/v1.5/host-memory-observations.json) не являются измерением peak или памяти телефона.

Modified beam search с 4 active paths действительно поддерживается [NeMo decoder в sherpa2.0.1](https://github.com/k2-fsa/sherpa-onnx/blob/v2.0.1/sherpa-onnx/csrc/offline-recognizer-transducer-nemo-impl.h). Он дал 35/670 word errors против 34 greedy на 32 файлах; no-digits 24 против 23. CER немного лучше, но общего word-quality выигрыша нет. Production остаётся greedy без hotwords/LM/blank penalty. [Beam raw evidence](docs/test-evidence/v1.5/asr-host-beam.json).

### Поздний независимый RU whisper holdout

Открытый [Dialogs / Langswap](https://huggingface.co/datasets/langswap/dialogs-ru-emotional-conversations), pinned revision `a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd`: все 7 официальных test rows с меткой whisper, 50.299s /84 слова /3 актёра. Живой студийный whisper по авторской/crowd разметке; независимые manually aligned transcripts из CSV по [статье](https://arxiv.org/html/2607.14310v1), не hypotheses GigaAM. OpenRAIL, audio вне APK; телефон и фонация нами не верифицированы, training overlap неизвестен. [Provenance/license](docs/test-evidence/v1.5/ru-whisper-dialogs-provenance.json).

С одинаковым существующим resampling/normalization и ASR2threads: v2wholeclip1/84 (WER1.19%, CER1/500=0.20%); current E2E2/84 (2.38%,2/500=0.40%); base RNNT0/84 (0%,0/500). Это малый controlled actor corpus:0 ошибок не означают0%WER в реальной речи и не основание переобучать/переключать уже выбранный pipeline по 7файлам.

Основная выявленная потеря находится перед recognizer: E2E по штатным VAD/context slices даёт31/84 (WER36.90%, CER172/500=34.40%). Один13.123sклип/23 слова полностью отвергнут VAD0.5 при peak≈0.102; wholeclip E2E имеет в нём1 ошибку. Gain1длявсех 7; raw VAD26.766s, context28.022s/50.299s,13slices. Fixed host-only retry0.35 **только после пустого0.5** не восстановил этот файл;6 nonempty first passes сохранились,22negative runs не добавили false-VAD IDs/текстов. Backoff не включён: positive improvement отсутствует. Модель не может восстановить слова, которые gate не передал в ASR.

[Host отчёт](docs/test-evidence/v1.5/ru-whisper-dialogs-report.md), [ASR hypotheses/model hashes](docs/test-evidence/v1.5/ru-whisper-dialogs-results.json), [неудачный 0.35 backoff/negative evidence](docs/test-evidence/v1.5/ru-whisper-dialogs-zero-span-backoff.json). Неэффективное снижение threshold0.35 не принято; отдельный RMS/headroom detector retry описан далее. Настоящий русский телефонный шёпот не объявляется исправленным.

После этого исследован detector-only RMS/headroom retry, без изменения модели или ASR input gain: только после пустого VAD0.5 при ненулевом входе detector total gain=`max(currentGain,min(0.02/RMS,20,0.95/peak))`. На одном пропущенном файле это9.309x только для VAD; ASR сохраняет gain 1. Host gated errors уменьшаются23→2 в файле и31→10/84 по всем семи (WER11.90%, CER8.80%). Шесть непустых first passes остаются прежними,22synthetic negative runs не добавляют false-VAD IDs; одинаковые ASR negative inputs/spans переиспользуют уже измеренные blank outputs. Постконтекст150ms выигрыша не дал. [A/B/C evidence](docs/test-evidence/v1.5/ru-whisper-dialogs-summary.json).

Этот положительный результат относится к обработке входа **детектора**, не доказывает превосходство E2E acoustic model. C принят в native source11: сборка успешна, полная JVM-регрессия 80/80 PASS, включая восемь policy/RMS тестов. `WhisperPipelineV15Test` прошёл на API35/x86_64: все семь файлов через настоящий Worker, 9/84 word errors (**WER10.714%**),39/500 char errors (**CER7.80%**). В клипе длиной 13.123 s primary VAD дал 0 spans; detector gain 9.273613 восстановил 21 из 23 слов при прежнем ASR gain 1. Остальные шесть не входят в retry/RMS scan. Проверены исходные WAV SHA, Room и JSON exports. [Acceptance JSON](docs/human-review/v1.5/evidence/whisper-native11/acceptance.json), [Android log](docs/human-review/v1.5/evidence/android-tests-build11/WhisperPipelineV15Test-20261106T023158.log), [нативная policy](ASR_QUALITY_V1_5.md).

31→10 ошибок — парное сравнение **host** без/с C;9 ошибок — отдельный **Android** результат после C. Нативный baseline без C на всех семи не измерен, поэтому31→9 не выдаётся за Android A/B. Эти семь студийных записей трёх актёров имеют авторскую/crowd метку whisper; наша ручная проверка фонации и пословный аудит эталона не проведены. Модель была выбрана до этого набора; decoder/словарь не подстраивались и эталонные слова не передавались recognizer. Шёпот в физический vivo X300, реальные шумы/музыка, батарея и нагрев остаются отдельной приёмкой.
