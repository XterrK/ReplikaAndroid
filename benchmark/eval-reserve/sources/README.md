---
pretty_name: "Dialogs: Expressive Conversational Russian Speech Corpus"
license: openrail
license_link: LICENSE.md
language:
- ru
task_categories:
- text-to-speech
- automatic-speech-recognition
- audio-classification
tags:
- speech
- text-to-speech
- tts
- expressive
- emotional
- conversational
- dialog
- russian
- studio-quality
size_categories:
- 10K<n<100K
configs:
- config_name: default
  data_files:
  - split: preview
    path: preview.parquet
---

# Dialogs: A Studio-Quality Expressive Conversational Russian Speech Corpus

**Dialogs** is a 20.6-hour studio-quality corpus of expressive, conversational
Russian speech, designed for dialog-oriented and emotional text-to-speech.
Unlike existing Russian corpora — mostly single-speaker read speech or large but
low-quality web-mined audio — Dialogs was recorded by professional theatre actors
performing scripted dialogs **face-to-face**, capturing natural turn-taking,
timing, and expressive variation.

Presented at **Interspeech 2026** — I. Shigabeev and I. Latyshev (Langswap).

## Highlights

- 🎙️ **20.6 hours**, **11,796 utterances**, avg. 6.3 s/utterance
- 🗣️ **3 professional actors** — Masha (F, 9.9 h), Sveta (F, 4.4 h), Dima (M, 6.2 h)
- 🎭 **12 style/emotion labels** (neutral, happy, surprise, sad, disgust, angry,
  tongue-twister, poem, whisper, arrogance, laughing, fear)
- 🔊 **Studio quality**: 44.1 kHz, 16-bit WAV, ~20 dBA ambient noise
- 📊 **Ready-made splits**: train / validation / test = 11,428 / 180 / 188
  (19.9 h / 0.30 h / 0.37 h); test/dev stratified (5 per speaker per emotion)
- ✅ **Open & commercial-friendly** under a responsible-use license

## Contents & layout

- **`preview.parquet`** — a small sample (5 utterances per style, 60 total) with
  **audio embedded**. This is what powers the dataset viewer above, so you can
  listen before downloading. It is *not* the full corpus.
- **Full corpus** — all 11,796 utterances live in the split files
  **`train.csv` / `val.csv` / `test.csv`** (and `metadata.csv` for everything),
  with the audio in **`wavs/`**.

The CSVs are **pipe-delimited (`|`)**. Each row:

| field | description |
|---|---|
| `audio_path` | path to the WAV file (`wavs/...`) |
| `speaker_id` | `M` (Masha), `S` (Sveta), `D` (Dima) |
| `text` | transcript |
| `emotion` | style/emotion label (English) |
| `emotion_on_russian` | style/emotion label (Russian) |
| `accent_text` | transcript with stress marks (`+` before stressed vowel) |
| `duration` | seconds |

## Usage

**Preview (60 samples, audio included):**

```python
from datasets import load_dataset
preview = load_dataset("langswap/dialogs-ru-emotional-conversations", split="preview")
print(preview[0])  # has a decoded `audio` column
```

**Full corpus** — download the repo and read the split files + `wavs/`:

```python
import pandas as pd
from huggingface_hub import snapshot_download
local = snapshot_download("langswap/dialogs-ru-emotional-conversations", repo_type="dataset")
train = pd.read_csv(f"{local}/train.csv", sep="|")   # audio at f"{local}/{train.audio_path}"
```

## Intended use

Training and evaluation of expressive, conversational, and emotional TTS systems.
A VITS2 baseline trained on this corpus is described in the paper. We recommend
mixing Dialogs with larger Russian corpora for production-grade results, as
per-speaker data is limited (4.4–9.9 h).

## License

Dialogs is released under **OpenRAIL** — an open, royalty-free Responsible-AI
license. You're free to **download, use, modify, redistribute, and use it
commercially**, subject only to the standard OpenRAIL use restrictions (no
unlawful use, no harming minors, no harmful disinformation, no harassment or
defamation, etc.). Full terms: [LICENSE.md](LICENSE.md). The voice actors gave
written informed consent for open release and lawful use, including commercial.
**Запрещено использовать данные материалы в целях нарушающих закон и УК РФ**.

If Dialogs is useful to you, please **cite the paper** (below).

## Commercial use, services & support

Commercial use is **free** under OpenRAIL — you don't need our permission, and we
hope you build great things with it.

**Commercial inquiries are highly welcome.** For **$1000** we provide a commercial
agreement that includes **indemnification rights** and other commercial services —
a signed license, clean-rights warranty, support, and **custom or exclusive
expressive-speech data collection** to your spec. Email **shigabeevilya@gmail.com**.

**Donations are very welcome** and help us record and release more open data — get
in touch at the same address.

## Citation

**Paper:** https://arxiv.org/abs/2607.14310

```bibtex
@inproceedings{shigabeev2026dialogs,
  title     = {Dialogs: A Studio-Quality Expressive Conversational Russian Speech Corpus for Dialog Assistants},
  author    = {Shigabeev, Ilya and Latyshev, Ilya},
  booktitle = {Proc. Interspeech},
  url       = {https://arxiv.org/abs/2607.14310}
  year      = {2026}
}
```

## Contact

For questions, commercial-use notification, or custom expressive data collection:
**shigabeevilya@gmail.com**

To follow our research on telegram:
[@voicestuff](https://t.me/voicestuff)
