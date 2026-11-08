# RU whisper — дополнительная проверка V1.5

Дата: 2026-11-06. Все числа — Linux/WSL CPU, sherpa-onnx2.0.1, ASR2 threads / VAD1. GigaAM v3 E2E была выбрана и зафиксирована **до обнаружения и распознавания этого holdout**. Во время приведённых host экспериментов модели, production source и настройки не менялись. После них вариант C реализован в native source11; сборка/Android Worker proof ожидаются.

## Источник и независимый текст

[Dialogs, авторский dataset Langswap](https://huggingface.co/datasets/langswap/dialogs-ru-emotional-conversations), [статья авторов](https://arxiv.org/html/2607.14310v1), pinned revision `a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd`. Это живые студийные записи актёров; статья §§3.2–3.4 сообщает ручную сегментацию/выравнивание с transcripts и style labels по majority vote трёх аннотаторов. Сценарии создавались с помощью GPT-3.5 до записи людьми; эталоны взяты из авторского CSV, **не получены от тестируемых ASR**. Пословная правильность supplied transcripts и отсутствие фонации нами отдельно не прослушивались/не верифицировались.

До inference выбраны **все 7** строки `emotion=whisper` официального `test.csv`, а не5 удобных preview samples. Три актёра, 50.299s аудио, 84 normalized reference words / 500 reference characters. Все 7 WAV доступны без регистрации, HTTP200; полученные файлы — mono44.1kHz PCM16. Dataset API сообщает gated=false. Это студийный actor whisper по авторской разметке, не шёпот в реальный микрофон телефона; предобработка/нормализация при подготовке корпуса могут отличаться от телефонной записи. Возможное пересечение с обучением GigaAM неизвестно.

[Provenance, URL/SHA и actor rows](ru-whisper-dialogs-provenance.json), [фиксированный manifest и references](ru-whisper-dialogs-fixtures.json), [точный LICENSE](ru-whisper-dialogs-LICENSE.md). OpenRAIL разрешает использование и распространение с ограничениями использования и передачей лицензии/ограничений получателям. Raw WAV остаются в `/mnt/f/ReplikaToolchain/asr-v15-ru-whisper`, вне APK/repo. Копия LICENSE сопровождает research metadata; при передаче аудио нужно передавать её также. Это не изменение лицензии моделей или приложения.

## Точная методика

Те же `read_wav`, `words`, `distance`, `candidate_gain`, `vad_spans` из существующего `tools/benchmark_asr_v15.py`. Общий63-tap windowed-sinc downsample в mono16kHz float; нет цифрового ослабления, добавленного шума, hotwords или эталонных слов в recognizer. WER: lowercase, ё→е, Unicode word tokens, punctuation ignored; CER — посимвольный Levenshtein по словам, соединённым пробелом внутри каждого файла. Нет числового ITN-преимущества: references не содержат цифр.

Для трёх моделей распознаны целые клипы. Отдельно для текущей v3 E2E выполнена host-эмуляция **single-speaker** пути: штатный Silero threshold0.5, min speech/silence0.25/0.25s, max20s, те же512sample blocks, округление spans в ms вниз, context100/0ms, merge и max20s ASR slices. Диаризация/Room/MediaCodec не эмулируются. Это отличает качество direct recognizer от потерь на VAD/разрезании; результаты не названы полным Android pipeline benchmark.

## Результат ASR

| Модель / путь | Word errors /84 | WER | Char errors /500 | CER |
| --- | --- | --- | --- | --- |
| GigaAM v2 INT8, целый клип | 1/84 | 1.19% | 1/500 | 0.20% |
| Текущая GigaAM v3 E2E INT8, целый клип | 2/84 | 2.38% | 2/500 | 0.40% |
| GigaAM v3 base RNNT INT8, целый клип | 0/84 | 0.00% | 0/500 | 0.00% |
| Текущая v3 E2E, штатные VAD/context slices | 31/84 | 36.90% | 172/500 | 34.40% |

Base дал0 ошибок на этих 7 коротких студийных файлах; это не обещание0%WER на русском шёпоте. Малый набор не отменяет результаты96ordinary/quiet fixtures и не служит основанием менять текущую модель. E2E не объявляется лучше v2/base в этом whispered holdout. [Все гипотезы, spans, hashes моделей и timings](ru-whisper-dialogs-results.json).

## Уровень и VAD

У всех 7 исходный декодированный peak выше0.01, поэтому принятый boundedgain **равен1 во всех случаях**. Повторное усиление здесь не измеряется как улучшение. Signal peaks относятся к resampled16k PCM, не к dB SPL/чувствительности телефонного микрофона.

| Файл | Актёр | Clip s | Peak | Gain | VAD s | Context retained s | Slices |
| --- | --- | --- | --- | --- | --- | --- | --- |
| masha_dima_part9_158 | D | 6.902 | 0.290427 | 1 | 4.320 | 4.520 | 2 |
| masha_dima_part9_222 | M | 5.625 | 0.077390 | 1 | 4.096 | 4.296 | 2 |
| masha_dima_part9_397 | D | 6.476 | 0.079115 | 1 | 5.050 | 5.330 | 3 |
| masha_dima_part11_287 | M | 13.123 | 0.102050 | 1 | 0.000 | 0.000 | 0 |
| masha_dima_part11_296 | D | 11.189 | 0.091629 | 1 | 7.712 | 8.012 | 3 |
| masha_sveta_part9_770 | M | 3.254 | 0.077505 | 1 | 3.098 | 3.188 | 1 |
| masha_sveta_part9_1261 | S | 3.731 | 0.113737 | 1 | 2.490 | 2.676 | 2 |

VAD пропустил целиком1/7 файл: `masha_dima_part11_287`, 13.123s /23 слова, peak≈0.102. Целый клип распознаётся E2E с1 ошибкой, но штатный gate не передаёт его в ASR. Всего raw VAD26.766s, context28.022s из50.299s (55.71% длительности клипов), 13slices. Это **доля длительности**, не полнота слов/фонем: frame-level reference VAD отсутствует. Из 31word errors gated пути23 — удаления полностью пропущенного файла; ещё 8 на остальных 6 после разрезания. Уровневой gain не восстанавливает отсутствующую для VAD структуру сигнала.

## Ограниченный host-only backoff0.35

Проверена заранее заданная policy, без подбора thresholds по файлам: если штатный0.5 дал0spans **и original peak>1e-6**, повторить тот же Silero один раз при0.35; min speech/silence/context неизменны. Если первый проход непустой, spans сохраняются строго. Модель остаётся текущей v3 E2E. Это исследование, **policy не включена в production**.

Результат: единственная повторная попытка также дала0spans, recovered0/1. Все 6 ранее непустых first-pass intervals и тексты побайтно совпали. Итог остаётся31/84 (WER36.90%),172/500 (CER34.40%). Восстановление шёпота этим backoff не доказано.

Те же11 deterministic negative controls seed104, каждый original/currentgain:22runs. Новых false-VAD controls0, fabricated nonblank transcripts0. Уже существующие VAD срабатывания на impulse controls не выдаются за отсутствие false positives. Silence/near-silence peakguard пропускает retry; выбранных spans и ASR calls0. Общий research recognizer загружен заранее, поэтому эти host счётчики не называются замером Android `asrLoadMs=0`; production silence fast-path проверяется отдельно нативным тестом. [Backoff и negative raw evidence](ru-whisper-dialogs-zero-span-backoff.json).

## Воспроизведение и границы вывода

Research runner сохранён как [основной script](ru-whisper-dialogs-benchmark.py.txt) и [backoff script](ru-whisper-dialogs-zero-span-backoff.py.txt), hashes также находятся в JSON. Скопировать их в внешний каталог рядом с7WAV и `fixtures.json`; установить тот же host runtime sherpa-onnx2.0.1/NumPy. В этой среде зависимости находятся `/mnt/f/ReplikaToolchain/python`, base/E2E weights — `/tmp/replika-asr-candidates/`, старые v2 — `model-pack/giga-v2`; эти пути явно видны в scripts и могут быть перенесены без смены параметров. Команды выполняются последовательно:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=2 python3 /mnt/f/ReplikaToolchain/asr-v15-ru-whisper/run_ru_whisper.py --repo /mnt/f/Hackathons/ReplikaAndroid --out /mnt/f/ReplikaToolchain/asr-v15-ru-whisper/results.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=2 python3 /mnt/f/ReplikaToolchain/asr-v15-ru-whisper/run_zero_span_backoff.py
```

[Основной host log](ru-whisper-dialogs-host.log), [backoff log](ru-whisper-dialogs-zero-span-backoff.log). Полное время host процесса включает неконтролируемые холодные IO/model/runtime cleanup; inference timings не являются телефонным thermal/battery benchmark.

Получен воспроизводимый маленький RU whisper holdout и обнаружен существенный VAD false negative. Исследование фиксированного0.35backoff не дало исправления; позднее найден частично успешный host-only detector gain candidate C, описанный ниже. Production и телефонная приёмка этим не закрываются. Для телефонной приёмки нужны реальные записи устройства, проверенные человеком эталоны, более широкий корпус и негативные реальные шумы. Production модель/thresholds не изменены; test references не использовались для decoder/prompt/словарной подгонки.


## Дополнение: фиксированные detector-only кандидаты A/B/C

После неудачного0.35backoff заранее заданы ещё две policy: **A** — только после пустого штатного0.5 поднять вход VAD максимум4x с headroom0.95, threshold оставить0.5; **B** — только после пустого0.5 повторить при существующем diagnostic threshold0.2 с прежним gain. ASR во всех вариантах получает прежний сигнал с current gain, а не усиленный сигнал детектора. Nonempty first pass не заменяется.

A/B дали непустые, но короткие интервалы в пропущенном13.123s клипе: A1.864s context, B1.704s. A распознаёт лишь отдельные фрагменты, clip errors23→21; B остаётся23/23. У обоих все 6 непустых first passes неизменны и22 negative runs не добавили false-VAD IDs. Поэтому наличие хотя бы одного span не называется восстановлением всей фразы. [VAD A/B](ru-whisper-dialogs-vad-candidates.json), [ASR A/B](ru-whisper-dialogs-vad-candidate-asr.json).

У проблемного файла peak0.102050, RMS0.0018099, RMS/peak0.0177; у остальных 6 ratio0.1057–0.1932. Прежний peak-only gain не срабатывает из-за высокого отдельного пика при малом среднем уровне. Это диагностика уровня, не доказательство причины на любом шёпоте.

Поскольку 4x дал лишь малую часть фразы, проверен один заранее определённый **C**: только после нулевого first-pass VAD и original peak>1e-6, вычислить detector total gain

```text
max(currentGain, min(0.02 / originalRMS, 20, 0.95 / originalPeak))
```

Ненулевой RMS проверяется численно; silence guard исключает near-zero. Threshold остаётся0.5, min speech/silence0.25/0.25s, pre/post100/0ms. ASR input gain не меняется. Здесь detector total gain9.309172, ASR gain1. C находит два интервала с9.512s context вместо0, распознаёт21 из 23 слов; теряются начальные «Дима, кстати». Wholeclip E2E по-прежнему лучше —1 ошибка, поэтому это частичное восстановление gate, а не устранение всех ошибок шёпота.

| Host-only путь, все 7files | Word errors /84 | WER | Char errors /500 | CER |
| --- | --- | --- | --- | --- |
| Штатный0.5 / context100/0 | 31 | 36.90% | 172 | 34.40% |
| Empty-only0.35 | 31 | 36.90% | 172 | 34.40% |
| A: detector≤4x /0.5 | 29 | 34.52% | 144 | 28.80% |
| B: threshold0.2 / current gain | 31 | 36.90% | 154 | 30.80% |
| C: RMS/headroom detector gain /0.5 | 10 | 11.90% | 44 | 8.80% |
| C + uniform post150ms | 10 | 11.90% | 44 | 8.80% |

Post150ms проверен одинаково для всех 7, pre100ms/VAD spans не менялись. Для A также29/84и144/500без выигрыша. Добавление150ms не включается. Точные word timestamps не выводились и не подгонялись.

C сохраняет все 6 ранее непустых first-pass spans; общий context37.534s/50.299s, улучшение против baseline полностью находится в одном исходно пропущенном файле. На22 negative runs новых false-VAD IDs0. Их selected intervals совпадают с baseline/A, ASR samples/current gain те же; actual blank ASR outputs для совпадающих входов переиспользованы из уже выполненного теста. Для post150 были реально проверены22 negative cases, все transcript blank; C использует эти же входы/интервалы. Это честно отделено от нового ASR inference на изменившемся whisper clip. [C VAD](ru-whisper-dialogs-vad-candidate-C.json), [C ASR/reuse flags](ru-whisper-dialogs-vad-candidate-C-asr.json), [машинный свод](ru-whisper-dialogs-summary.json).

Результат C — измеренный host positive на одном сложном актёрском клипе без новых срабатываний на11 фиксированных синтетических controls. Во время этих измерений он не был включён в приложение. После положительного результата координатор принял native реализацию C: source11 добавляет только empty-primary detector retry с bounded RMS scan, прежним threshold0.5/context100/0 и неизменённым ASR input. Сборка и Android Worker proof ожидаются; [состояние интеграции](../../ASR_QUALITY_V1_5.md). Это не доказывает безопасность на реальной музыке/шуме, энергопотребление или шёпот телефона. Никакая policy не обучалась по эталонным словам, decoder/словари не менялись.

Снимки точных research scripts: [A/B VAD](ru-whisper-dialogs-run_vad_candidates.py.txt), [A/B ASR](ru-whisper-dialogs-run_vad_candidate_asr.py.txt), [C VAD](ru-whisper-dialogs-run_vad_candidate_C.py.txt), [C ASR](ru-whisper-dialogs-run_vad_candidate_C_asr.py.txt). Выполняются последовательно во внешнем каталоге рядом с прежними metadata/audio; file hashes сохранены в каждом result JSON. C ASR повторно распознаёт изменившийся файл, остальные неизменившиеся результаты связывает по сохранённым входам/spans.
