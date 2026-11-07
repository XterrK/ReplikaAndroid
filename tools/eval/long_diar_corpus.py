#!/usr/bin/env python3
"""Synthetic long-recording splices with known speaker labels (step 6).

Builds deterministic "meetings" of a requested length from single-actor
Langswap clips (actors M/D/S, labels from the author CSV metadata) and,
optionally, AMI EN2002 blocks with their manual-word RTTM speech intervals
(global participant IDs, so the same person keeps one label across blocks).

The reference is an utterance-interval proxy, exactly like the montage corpus:
the whole clip span is one reference turn. Clips repeat once the pool is
exhausted (the pool is 7.7 min for ``tune`` and 5.8 min for ``check``), so
long splices measure length/memory behaviour and global label consistency,
not fresh-voice generalisation. Audio stays outside Git (custom OpenRAIL/AMI
licences); only this recipe and the small reference JSON are reproducible.

Usage:
  python tools/eval/long_diar_corpus.py --pool tune --minutes 30 --seed 1 \
      --ami --out C:/R/eval-long-audio
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import wave
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

SR = 16000
EVAL_AUDIO = Path("C:/R/eval-audio")
RESERVE_AUDIO = Path("C:/R/eval-reserve-audio")
AMI_AUDIO = Path("C:/R/eval-natural-ami-audio/diagnostic")
REPO = Path(__file__).resolve().parents[2]
AMI_REFS = REPO / "benchmark/eval-natural-ami/references"
AMI_IDS = ("ami-natural-en2002a-headset-first60", "ami-natural-en2002c-headset-first60",
           "ami-natural-en2002a-array-first60")
POOLS = {"tune": EVAL_AUDIO / "source-wavs", "check": RESERVE_AUDIO / "source-wavs"}


def actor_labels() -> dict[str, str]:
    labels = {}
    for name in ("test.csv", "val.csv"):
        with open(EVAL_AUDIO / "source-metadata" / name, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="|"):
                labels[Path(row["audio_path"]).name] = row["speaker_id"]
    return labels


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError(f"mono PCM16 expected: {path}")
        rate = source.getframerate()
        data = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768
    if rate == SR:
        return data
    if rate != 44100:
        raise ValueError(f"unexpected rate {rate}: {path}")
    return resample_poly(data, 160, 441).astype(np.float32)


def load_pool(pool: str):
    labels = actor_labels()
    clips: dict[str, list[tuple[str, np.ndarray]]] = {}
    for path in sorted(POOLS[pool].glob("*.wav")):
        actor = labels.get(path.name)
        if actor is None:
            raise ValueError(f"no actor label for {path.name}")
        clips.setdefault(actor, []).append((path.name, read_wav(path)))
    return clips


def load_ami():
    blocks = []
    for ident in AMI_IDS:
        audio = read_wav(AMI_AUDIO / f"{ident}.wav")
        rows = json.loads((AMI_REFS / f"{ident}.json").read_text(encoding="utf-8"))["transcript"]
        blocks.append((ident, audio, [(r["start_ms"], r["end_ms"], r["speaker_id"]) for r in rows]))
    return blocks


class Builder:
    def __init__(self, path: Path):
        self.out = wave.open(str(path), "wb")
        self.out.setnchannels(1)
        self.out.setsampwidth(2)
        self.out.setframerate(SR)
        self.samples = 0
        self.rows: list[dict] = []
        self.hash = hashlib.sha256()

    @property
    def ms(self) -> int:
        return self.samples * 1000 // SR

    def silence(self, ms: int):
        self.write(np.zeros(ms * SR // 1000, dtype=np.float32))

    def write(self, audio: np.ndarray):
        pcm = np.clip(np.round(audio * 32768), -32768, 32767).astype("<i2").tobytes()
        self.out.writeframes(pcm)
        self.hash.update(pcm)
        self.samples += len(audio)

    def close(self):
        self.out.close()


def build(pool: str, minutes: float, seed: int, ami: bool, out_dir: Path) -> dict:
    rng = random.Random(f"replika-step06-{pool}-{seed}-{minutes}-{ami}")
    clips = load_pool(pool)
    actors = sorted(clips)
    queues = {a: [] for a in actors}

    def next_clip(actor):
        if not queues[actor]:
            queues[actor] = list(range(len(clips[actor])))
            rng.shuffle(queues[actor])
        return clips[actor][queues[actor].pop()]

    ami_blocks = load_ami() if ami else []
    ami_order: list[int] = []
    ident = f"long-{pool}-{'mix' if ami else 'ru'}-{int(minutes):03d}m-s{seed}"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / f"{ident}.wav"
    target_ms = int(minutes * 60000)
    builder = Builder(wav_path)
    scenes = []
    try:
        while builder.ms < target_ms:
            if ami_blocks and rng.random() < .2:
                if not ami_order:
                    ami_order = list(range(len(ami_blocks)))
                    rng.shuffle(ami_order)
                name, audio, rows = ami_blocks[ami_order.pop()]
                offset = builder.ms
                for start, end, speaker in rows:
                    builder.rows.append({"speaker_id": speaker, "start_ms": offset + start,
                                         "end_ms": offset + end, "text": ""})
                builder.write(audio * rng.uniform(.7, 1.))
                scenes.append({"kind": "ami", "source": name, "start_ms": offset})
            else:
                cast = rng.sample(actors, rng.choice([2, 2, 3]) if len(actors) >= 3 else len(actors))
                offset = builder.ms
                previous = None
                for _ in range(rng.randint(8, 20)):
                    actor = rng.choice([a for a in cast if a != previous] or cast)
                    previous = actor
                    name, audio = next_clip(actor)
                    start = builder.ms
                    builder.write(audio * rng.uniform(.6, 1.))
                    builder.rows.append({"speaker_id": actor, "start_ms": start, "end_ms": builder.ms,
                                         "text": "", "source": name})
                    builder.silence(rng.randint(150, 1000))
                scenes.append({"kind": "ru", "cast": cast, "start_ms": offset})
            pause = rng.randint(20000, 60000) if rng.random() < .08 else rng.randint(1000, 8000)
            builder.silence(pause)
    finally:
        builder.close()
    speakers: dict[str, int] = {}
    for row in builder.rows:
        speakers[row["speaker_id"]] = speakers.get(row["speaker_id"], 0) + row["end_ms"] - row["start_ms"]
    meta = {"id": ident, "pool": pool, "seed": seed, "ami": ami, "duration_ms": builder.ms,
            "audio": wav_path.name, "audio_pcm_sha256": builder.hash.hexdigest(),
            "speakers": len(speakers), "speaker_ms": dict(sorted(speakers.items())),
            "scenes": len(scenes), "reference_scope": "clip/RTTM interval proxy; clips repeat after pool exhaustion",
            "transcript": builder.rows}
    (out_dir / f"{ident}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pool", choices=sorted(POOLS), default="tune")
    parser.add_argument("--minutes", type=float, nargs="+", required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ami", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    for minutes in args.minutes:
        meta = build(args.pool, minutes, args.seed, args.ami, args.out)
        print(meta["id"], meta["duration_ms"], meta["speakers"], meta["speaker_ms"])


if __name__ == "__main__":
    main()
