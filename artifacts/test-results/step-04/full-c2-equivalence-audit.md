Полный C2 host: аудит эквивалентности PASS, все23 файла, 3164 проверок. Аудитор не запускал NN.

Все23 JuryJSON совпали побайтно. Новые ASR chunks/text/tokens/timestamps совпали с Dcontext600; raw/stable/refined turns, реальные clean-window vectors и refiner diagnostics — с выбранными C2 research projections. Все основные метрики, включая segment timing proxy, совпали по каждому файлу и пересчитаны независимо. Агрегаты не скрывают различий между файлами.

| Набор | Верный K | NativeDER0 | RawWER |
| --- | --- | --- | --- |
| dev | 7/8 | 18.298481% | 71/533 |
| holdout | 4/5 | 13.889566% | 49/444 |
| reserve | 5/10 | 22.439619% | 83/743 |

Новые полные прогоны: 130 ASR forwards, 4681 tokens, 1685 word proxies, 749 реальных clean vectors. Проверены NN markers, counts, положительные stage timings, отсутствие replay/cache и все code/config/catalog/model-lock/model/reference/audio SHA с историческими source snapshots. Подробности — full-c2-equivalence-audit.json.

Исключено только время выполнения wall/stage/processing/RTF; скорость не заявляется. Это host-эквивалентность, а не Android/ARM/телефонная приёмка. Наборы — montage-прокси, word gold отсутствует, blind/natural-dialogue обобщение не установлено. Reserve K остаётся5/10.
