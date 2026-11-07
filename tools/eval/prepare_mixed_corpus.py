#!/usr/bin/env python3
"""Diagnostic RU+EN mixed files for the experimental per-segment language mode (task 07).

Each file is one Russian montage followed (or preceded) by one English montage, joined with
700 ms of silence; references are concatenated with shifted times and renumbered speakers.
Not a tuning set: it only shows what file-level vs per-segment identification does.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import wave

PAIRS = [
    ("mixed-01-ru-then-en", ("ru", "dev-01-two-clean"), ("en", "en-01-two-mf")),
    ("mixed-02-en-then-ru", ("en", "en-03-short"), ("ru", "holdout-03-short")),
]
GAP_MS = 700


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_wav(path):
    with wave.open(str(path)) as source:
        if source.getframerate() != 16000 or source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError("Expected 16 kHz mono PCM16: " + str(path))
        return source.readframes(source.getnframes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ru-manifest", type=Path, required=True)
    parser.add_argument("--ru-audio", type=Path, required=True)
    parser.add_argument("--en-manifest", type=Path, required=True)
    parser.add_argument("--en-audio", type=Path, required=True)
    parser.add_argument("--audio-out", type=Path, required=True)
    parser.add_argument("--bench-out", type=Path, default=Path(__file__).resolve().parents[2] / "benchmark/eval-mixed")
    args = parser.parse_args()
    sources = {}
    for language, manifest, root in (("ru", args.ru_manifest, args.ru_audio), ("en", args.en_manifest, args.en_audio)):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for item in data["files"]:
            sources[(language, item["id"])] = (root / item["audio"], manifest.parent / item["reference"], item)
    (args.audio_out / "mixed").mkdir(parents=True, exist_ok=True)
    (args.bench_out / "references").mkdir(parents=True, exist_ok=True)
    files = []
    for mixed_id, *parts in PAIRS:
        pcm, rows, offset_ms, speaker_offset = b"", [], 0, 0
        used = []
        for index, key in enumerate(parts):
            audio, reference, item = sources[key]
            if sha256(audio) != item["audio_sha256"]:
                raise ValueError("Source audio hash mismatch: " + key[1])
            frames = read_wav(audio)
            if index:
                pcm += b"\0\0" * (GAP_MS * 16)
                offset_ms += GAP_MS
            transcript = json.loads(reference.read_text(encoding="utf-8"))["transcript"]
            ids = sorted({row["speaker_id"] for row in transcript}, key=lambda s: int(s.split("_")[1]))
            for row in transcript:
                rows.append({"speaker_id": "speaker_" + str(speaker_offset + ids.index(row["speaker_id"]) + 1),
                             "start_ms": row["start_ms"] + offset_ms, "end_ms": row["end_ms"] + offset_ms,
                             "text": row["text"], "language": key[0]})
            speaker_offset += len(ids)
            pcm += frames
            offset_ms = len(pcm) // 2 * 1000 // 16000
            used.append({"language": key[0], "id": key[1], "audio_sha256": item["audio_sha256"]})
        target = args.audio_out / "mixed" / (mixed_id + ".wav")
        with wave.open(str(target), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(pcm)
        reference_path = args.bench_out / "references" / (mixed_id + ".json")
        # The jury format has no language field; keep it in a side file for analysis only.
        reference_path.write_text(json.dumps({"transcript": [{k: v for k, v in r.items() if k != "language"} for r in rows]},
                                             ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        files.append({"id": mixed_id, "split": "mixed", "language": "mixed", "audio": "mixed/" + mixed_id + ".wav",
                      "reference": "references/" + mixed_id + ".json", "duration_ms": len(pcm) // 2 * 1000 // 16000,
                      "audio_sha256": sha256(target), "reference_sha256": sha256(reference_path),
                      "expected_speakers": speaker_offset, "kind": "diagnostic_ru_en_concatenation",
                      "row_languages": [r["language"] for r in rows], "parts": used})
    manifest = {"schema_version": 1, "name": "REPLIKA RU+EN mixed diagnostic v1",
                "reference_scope": "Concatenation of existing RU and EN montages; diagnostic only, not tuning",
                "files": files}
    (args.bench_out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                 encoding="utf-8", newline="\n")
    for item in files:
        print(item["id"], item["duration_ms"], item["expected_speakers"])


if __name__ == "__main__":
    main()
