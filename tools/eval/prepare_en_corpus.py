#!/usr/bin/env python3
"""Build the English montage corpus from LibriSpeech test-clean + LibriSpeech-PC texts.

Selection uses metadata only (speaker id, sex, duration) with a fixed seed; no ASR output
or model is consulted. Each dialogue concatenates whole utterances of DIFFERENT speakers
with 300-900 ms pauses. References use LibriSpeech-PC punctuated/cased text in the jury
format; intervals are whole-clip placement (coarse timing proxy, like the RU corpus).

Audio stays outside Git; the manifest, references and selection are committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import wave

SEED = 20261107
DIALOGUES = [
    # id, speakers by sex, target seconds, min/max utterance seconds
    ("en-01-two-mf", "MF", 60, 2.0, 12.0),
    ("en-02-three", "MFF", 90, 2.0, 12.0),
    ("en-03-short", "FM", 45, 1.2, 4.0),
    ("en-04-four", "MFMF", 120, 2.0, 12.0),
    ("en-05-two-mm", "MM", 75, 2.0, 12.0),
]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def speakers_by_sex(librispeech_root):
    result = {}
    for line in (Path(librispeech_root) / "SPEAKERS.TXT").read_text(encoding="utf-8").splitlines():
        if line.startswith(";"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3 and parts[2] == "test-clean":
            result.setdefault(parts[1], []).append(parts[0])
    return {sex: sorted(ids, key=int) for sex, ids in result.items()}


def build(librispeech_root, pc_manifest, audio_out, bench_out):
    import numpy as np
    import soundfile as sf
    rng = random.Random(SEED)
    librispeech_root, audio_out, bench_out = Path(librispeech_root), Path(audio_out), Path(bench_out)
    utterances = {}
    for line in Path(pc_manifest).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        speaker = row["audio_filepath"].split("/")[1]
        utterances.setdefault(speaker, []).append(row)
    for rows in utterances.values():
        rows.sort(key=lambda r: r["audio_filepath"])
    pools = speakers_by_sex(librispeech_root)
    used_speakers = set()
    (audio_out / "en").mkdir(parents=True, exist_ok=True)
    (bench_out / "references").mkdir(parents=True, exist_ok=True)
    files = []
    for dialogue_id, sexes, target_s, min_s, max_s in DIALOGUES:
        speakers = []
        for sex in sexes:
            candidates = [s for s in pools[sex] if s not in used_speakers and s in utterances
                          and sum(1 for r in utterances[s] if min_s <= r["duration"] <= max_s) >= 8]
            choice = rng.choice(candidates)
            used_speakers.add(choice)
            speakers.append(choice)
        queues = {s: [r for r in utterances[s] if min_s <= r["duration"] <= max_s] for s in speakers}
        for queue in queues.values():
            rng.shuffle(queue)
        audio, transcript, sources, cursor, previous = [], [], [], 0, None
        lead = np.zeros(4000, dtype=np.float32)  # 250 ms leading silence
        audio.append(lead)
        cursor = len(lead)
        while cursor < target_s * 16000:
            options = [s for s in speakers if s != previous and queues[s]]
            if not options:
                break
            speaker = rng.choice(options)
            row = queues[speaker].pop()
            samples, rate = sf.read(librispeech_root / row["audio_filepath"], dtype="float32")
            if rate != 16000 or samples.ndim != 1:
                raise ValueError("Unexpected LibriSpeech format: " + row["audio_filepath"])
            start_ms = cursor * 1000 // 16000
            audio.append(samples)
            cursor += len(samples)
            end_ms = cursor * 1000 // 16000
            label = "speaker_" + str(speakers.index(speaker) + 1)
            transcript.append({"speaker_id": label, "start_ms": start_ms, "end_ms": end_ms, "text": row["text"]})
            sources.append(row["audio_filepath"])
            pause = np.zeros(rng.randint(300, 900) * 16, dtype=np.float32)
            audio.append(pause)
            cursor += len(pause)
            previous = speaker
        # Renumber speakers by first appearance, as the jury format expects.
        order = []
        for item in transcript:
            if item["speaker_id"] not in order:
                order.append(item["speaker_id"])
        for item in transcript:
            item["speaker_id"] = "speaker_" + str(order.index(item["speaker_id"]) + 1)
        mixed = np.concatenate(audio)
        peak = float(np.max(np.abs(mixed)))
        if peak > .99:
            mixed *= .99 / peak
        pcm = np.clip(np.round(mixed * 32767), -32768, 32767).astype("<i2")
        wav_path = audio_out / "en" / (dialogue_id + ".wav")
        with wave.open(str(wav_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(pcm.tobytes())
        reference_path = bench_out / "references" / (dialogue_id + ".json")
        reference_path.write_text(json.dumps({"transcript": transcript}, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8", newline="\n")
        files.append({"id": dialogue_id, "split": "en", "language": "en",
                      "audio": "en/" + dialogue_id + ".wav", "reference": "references/" + dialogue_id + ".json",
                      "duration_ms": len(pcm) * 1000 // 16000, "audio_sha256": sha256(wav_path),
                      "reference_sha256": sha256(reference_path),
                      "expected_speakers": len(speakers), "kind": "simulated_librispeech_montage",
                      "source": {"dataset": "LibriSpeech test-clean (openslr 12) + LibriSpeech-PC texts (openslr 145)",
                                 "license": "CC-BY-4.0", "speakers": speakers, "speaker_sexes": list(sexes),
                                 "utterance_count": len(sources), "audio_paths": sources}})
    manifest = {"schema_version": 1, "name": "REPLIKA English LibriSpeech montage v1",
                "reference_scope": "LibriSpeech-PC cased/punctuated text; whole-clip interval timing proxy; montage is not a natural dialogue",
                "selection": {"seed": SEED, "rule": "metadata only: speaker sex/duration; distinct speakers per corpus"},
                "files": files}
    (bench_out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--librispeech-root", type=Path, required=True, help="folder with SPEAKERS.TXT and test-clean/")
    parser.add_argument("--pc-manifest", type=Path, required=True, help="LibriSpeech-PC test-clean.json")
    parser.add_argument("--audio-out", type=Path, required=True)
    parser.add_argument("--bench-out", type=Path, default=Path(__file__).resolve().parents[2] / "benchmark/eval-en")
    args = parser.parse_args()
    manifest = build(args.librispeech_root, args.pc_manifest, args.audio_out, args.bench_out)
    for item in manifest["files"]:
        print(item["id"], item["duration_ms"], item["expected_speakers"], item["source"]["utterance_count"])


if __name__ == "__main__":
    main()
