# Английский стенд (задача 07)

Пять монтажных диалогов по 2–4 **разных** диктора из LibriSpeech test-clean. Эталонный текст взят из LibriSpeech-PC: те же фразы, но с восстановленными регистром и пунктуацией. Поэтому raw WER (с регистром и знаками) здесь осмысленный.

| Файл | Длительность | Дикторы | Фраз |
| --- | ---: | ---: | ---: |
| en-01-two-mf | 63.0 с | 2 (М+Ж) | 8 |
| en-02-three | 92.9 с | 3 | 13 |
| en-03-short | 45.4 с | 2, фразы 1.2–4 с | 13 |
| en-04-four | 121.3 с | 4 | 21 |
| en-05-two-mm | 79.5 с | 2 (М+М) | 11 |

Отбор идёт только по метаданным (пол и длительность), seed `20261107`, дикторы не повторяются между файлами. Паузы между репликами 300–900 мс, без наложений и шума. Интервалы в эталоне — границы целых клипов, это грубый прокси таймкодов, как и в русском корпусе. Чистая начитка книг — лёгкий случай, разговорная английская речь здесь не представлена.

Аудио в Git не хранится. Воспроизведение:

```text
# LibriSpeech test-clean: https://www.openslr.org/resources/12/test-clean.tar.gz (346.7 МБ, SHA256 39fde525e59672dc6d1551919b1478f724438a95aa55f874b576be21967e6c23)
# LibriSpeech-PC manifests: https://www.openslr.org/resources/145/manifests.tar.gz (25.9 МБ, SHA256 96d4eae2222b29b66437a21959252419bcd4762e5042e71e023790171054d1c0)
python tools/eval/prepare_en_corpus.py --librispeech-root <...>/LibriSpeech --pc-manifest <...>/test-clean.json --audio-out <eval-en-audio>
```

SHA256 каждого WAV и эталона записан в `manifest.json`; `tools/eval/run.py` сверяет их перед прогоном.

Лицензия данных: LibriSpeech (V. Panayotov, G. Chen, D. Povey, S. Khudanpur, 2015) и LibriSpeech-PC (NVIDIA, 2023) распространяются под CC BY 4.0, https://creativecommons.org/licenses/by/4.0/. Аудио и тексты использованы без изменений, кроме склейки клипов и пикового нормирования.
