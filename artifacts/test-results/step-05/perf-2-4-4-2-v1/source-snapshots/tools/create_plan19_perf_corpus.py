#!/usr/bin/env python3
"""Prepare related 1/3/10-minute performance proxies; no ASR, VAD or NN calls.

Keep complete author utterances from the frozen dev-01 prefix, including their
exact last PCM frame from source provenance. Pad one block to 60 seconds, then
repeat its original PCM and independently authored reference rows unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import wave

REPO = Path(__file__).resolve().parents[1]
SOURCE_ID = "dev-01-two-clean"
PINS = {
    "manifest.json": "47109cb1987624daaf8f4dc28e8eca3198b0c2bbcf01cd334b9611664eb38066",
    "references/dev-01-two-clean.json": "523b1097852d70d1f6d2cf2f3c632ee5c5ac3bedf8e64487ecbdada21c25d127",
    "provenance.json": "2cc46d1f10f35383b3f047e789536aed7c70c994397675a0314b3a63503a0ce3",
    "sources/LICENSE.md": "e136a6af001dd43a9002f20f39dd56d200afa9a6d408e28a625d90c9a0c22143",
}
AUDIO_SHA256 = "80bdb11e4d9e313d2440c01b80babc0dbe319c9dbea371988ef62716ffb9d77b"
RATE = 16000
BLOCK_MS = 60000
BLOCK_FRAMES = RATE * 60
REPEATS = (1, 3, 10)
ROW_KEYS = {"speaker_id", "start_ms", "end_ms", "text"}
SCOPE = ("Related controlled repeats of a previously evaluated acted dev montage; "
         "not independent recordings, natural dialogue, blind quality validation or word-time gold. "
         "Author text/actor IDs are retained; intervals remain whole author-clip timing proxies. "
         "No recognizer output, VAD or forced alignment enters corpus construction.")


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def confined(root: Path, relative: str) -> Path:
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError("Source path escapes its root")
    return result


def source_block(metadata: Path, audio_root: Path) -> tuple[bytes, list[dict], dict, dict, Path]:
    for relative, expected in PINS.items():
        if sha(metadata / relative) != expected:
            raise ValueError("Frozen source metadata differs: " + relative)
    manifest = read_json(metadata / "manifest.json")
    source = next(row for row in manifest["files"] if row["id"] == SOURCE_ID)
    if source["audio_sha256"] != AUDIO_SHA256 or source["kind"] != "simulated_actor_montage":
        raise ValueError("Unexpected frozen dev source")
    audio = confined(audio_root, source["audio"])
    if sha(audio) != AUDIO_SHA256:
        raise ValueError("Frozen dev audio SHA differs")
    document = read_json(metadata / source["reference"])
    if set(document) != {"transcript"}:
        raise ValueError("Invalid independent reference document")
    rows = document["transcript"]
    provenance = next(row for row in read_json(metadata / "provenance.json")["files"] if row["id"] == SOURCE_ID)
    utterances = provenance["utterances"]
    if len(rows) != len(utterances):
        raise ValueError("Author reference/provenance coverage differs")
    for row, utterance in zip(rows, utterances):
        if set(row) != ROW_KEYS or any(row[key] != utterance[key] for key in ROW_KEYS):
            raise ValueError("Author text/actor interval differs from provenance")
        if (type(row["start_ms"]) is not int or type(row["end_ms"]) is not int
                or not 0 <= row["start_ms"] < row["end_ms"] or not row["text"].strip()):
            raise ValueError("Invalid author row")
        if (utterance["resampled_start_frame"] // 16 != row["start_ms"]
                or utterance["resampled_end_frame"] // 16 != row["end_ms"]):
            raise ValueError("Author millisecond proxy does not match exact PCM placement")
    kept_indices = [index for index, row in enumerate(rows) if row["end_ms"] <= BLOCK_MS]
    if not kept_indices or kept_indices != list(range(len(kept_indices))):
        raise ValueError("Only a contiguous whole-utterance source prefix is allowed")
    end_frame = max(utterances[index]["resampled_end_frame"] for index in kept_indices)
    if not 0 < end_frame <= BLOCK_FRAMES:
        raise ValueError("Whole source utterance exceeds the 60-second block")
    if any(row["resampled_start_frame"] < end_frame for row in utterances[len(kept_indices):]):
        raise ValueError("Prefix would cut another author utterance")
    with wave.open(str(audio), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, RATE, "NONE"):
            raise ValueError("Frozen input must remain canonical mono 16k PCM16 WAV")
        if stream.getnframes() != provenance["frames"] or stream.getnframes() * 1000 // RATE != source["duration_ms"]:
            raise ValueError("Frozen input sample clock differs")
        prefix = stream.readframes(end_frame)
    if len(prefix) != end_frame * 2:
        raise ValueError("Truncated frozen source PCM")
    block = prefix + bytes((BLOCK_FRAMES - end_frame) * 2)
    facts = {
        "source_id": SOURCE_ID, "source_audio": source["audio"], "source_audio_sha256": AUDIO_SHA256,
        "source_metadata_sha256": PINS, "source_revision": source["source"]["revision"],
        "source_repo": source["source"]["repo"], "source_license": source["source"]["license"],
        "source_frames": provenance["frames"], "kept_utterance_indices": kept_indices,
        "kept_utterances": len(kept_indices), "last_gold_end_ms": rows[kept_indices[-1]]["end_ms"],
        "exact_prefix_frames": end_frame, "exact_prefix_ms": end_frame * 1000 / RATE,
        "submillisecond_author_clip_tail_retained_samples": end_frame - rows[kept_indices[-1]]["end_ms"] * 16,
        "silence_padding_frames": BLOCK_FRAMES - end_frame, "block_frames": BLOCK_FRAMES,
        "block_ms": BLOCK_MS, "block_pcm16_sha256": hashlib.sha256(block).hexdigest(),
        "prefix_pcm16_sha256": hashlib.sha256(prefix).hexdigest(),
        "boundary_policy": "last complete author utterance with end_ms<=60000; exact end frame from frozen provenance; no word truncation/VAD trimming",
        "speaker_policy": "Same author actor ID across every repetition; no new speaker per block",
    }
    return block, [dict(rows[index]) for index in kept_indices], facts, source, audio


def prepare(source_metadata: Path, source_audio_root: Path, audio_root: Path, metadata: Path) -> dict:
    if audio_root.exists() or metadata.exists():
        raise FileExistsError("Use fresh audio and metadata directories; existing WAV/references are never overwritten")
    if audio_root.resolve().is_relative_to(REPO):
        raise ValueError("Derived performance audio must stay outside the repository")
    if metadata.resolve().is_relative_to(audio_root.resolve()) or audio_root.resolve().is_relative_to(metadata.resolve()):
        raise ValueError("Audio/metadata directories must be separate")
    block, author_rows, facts, source, original = source_block(source_metadata, source_audio_root)
    audio_root.mkdir(parents=True)
    metadata.mkdir(parents=True)
    (audio_root / "audio").mkdir()
    (metadata / "sources").mkdir()
    snapshots = {"manifest.json": "source-manifest.json", "references/dev-01-two-clean.json": "source-reference.json",
                 "provenance.json": "source-provenance.json", "sources/LICENSE.md": "LICENSE.md"}
    for relative, name in snapshots.items():
        shutil.copyfile(source_metadata / relative, metadata / "sources" / name)
    shutil.copyfile(source_metadata / "sources/LICENSE.md", audio_root / "LICENSE.md")
    files = []
    for repeat in REPEATS:
        identity = f"perf-{repeat:02d}m"
        audio = audio_root / "audio" / f"{identity}.wav"
        with wave.open(str(audio), "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(RATE)
            for _ in range(repeat):
                stream.writeframesraw(block)
        reference = {"transcript": [
            {**row, "start_ms": row["start_ms"] + index * BLOCK_MS, "end_ms": row["end_ms"] + index * BLOCK_MS}
            for index in range(repeat) for row in author_rows
        ]}
        ref_path = metadata / "references" / f"{identity}.json"
        write_json(ref_path, reference)
        with wave.open(str(audio), "rb") as stream:
            if stream.getnframes() != BLOCK_FRAMES * repeat:
                raise AssertionError("Derived WAV clock differs")
            for _ in range(repeat):
                if stream.readframes(BLOCK_FRAMES) != block:
                    raise AssertionError("A repeated PCM block differs")
        files.append({
            "id": identity, "split": "performance_proxy", "language": "ru", "audio": f"audio/{identity}.wav",
            "reference": f"references/{identity}.json", "duration_ms": BLOCK_MS * repeat,
            "frames": BLOCK_FRAMES * repeat, "audio_sha256": sha(audio), "audio_bytes": audio.stat().st_size,
            "reference_sha256": sha(ref_path), "expected_speakers": len({row["speaker_id"] for row in author_rows}),
            "reference_utterances": len(reference["transcript"]),
            "reference_whitespace_words": sum(len(row["text"].split()) for row in reference["transcript"]),
            "kind": "related_controlled_repeat", "repeat_blocks": repeat,
            "source": {"id": SOURCE_ID, "audio_sha256": AUDIO_SHA256, "block_pcm16_sha256": facts["block_pcm16_sha256"]},
            "timing_scope": "Repeated author utterance-clip intervals, not word-time or speech-activity gold",
            "der_scope": "Related montage utterance-interval proxy; not natural-dialogue DER",
        })
    if sha(original) != AUDIO_SHA256:
        raise AssertionError("Original source changed during preparation")
    created = datetime.now(timezone.utc).isoformat()
    provenance = {"schema_version": 1, "status": "COMPLETE", "created_utc": created,
                  "new_model_inference": False, "scope": SCOPE, "source": facts,
                  "generator_sha256": sha(Path(__file__)), "original_source_unchanged": True,
                  "total_audio_ms": sum(row["duration_ms"] for row in files), "files": files}
    write_json(metadata / "provenance.json", provenance)
    manifest = {"schema_version": 1, "name": "PLAN19 related controlled performance proxy v1", "scope": SCOPE,
                "source_provenance_sha256": sha(metadata / "provenance.json"), "files": files}
    write_json(metadata / "manifest.json", manifest)
    readme = f"""# PLAN19 controlled performance proxy\n\n{SCOPE}\n\nThe frozen source is `{SOURCE_ID}` at source SHA `{AUDIO_SHA256}`.\nKeep its first {facts['kept_utterances']} complete author utterances through exact PCM\nframe {facts['exact_prefix_frames']} ({facts['exact_prefix_ms']} ms), retain the\nsubmillisecond clip tail omitted by the floored gold end_ms, and append\n{facts['silence_padding_frames']} zero samples to 60 seconds. Repeat this block\n1/3/10 times. Author spelling, punctuation and actor IDs remain literal, with\ninteger 60000 ms shifts. No utterance/word is cut or invented.\n\nThe three recordings share the same six utterances and speakers. Their total\naudio duration is 14 minutes, with 52.659 seconds of unique source-prefix\nmaterial. They measure length/repetition behavior; they are not a fresh quality\ncohort, actor-disjoint data, natural dialogue or word timestamps. Do not pool\nthem with dev/holdout/reserve or describe repeated rows as independent examples.\n\nSource is Langswap Dialogs, revision `{source['source']['revision']}`, under\nthe authors' custom OpenRAIL license, retained in `sources/LICENSE.md` and the\nexternal audio root. Derived audio is not CC0 and must remain outside Git/APK.\nSource metadata/reference/provenance snapshots and SHA pins are retained.\n\nReproduce in fresh directories (never overwrite):\n\n```bash\npython tools/create_plan19_perf_corpus.py \\\n  --source-audio-root /path/outside/repository/eval-audio \\\n  --audio-root /path/outside/repository/plan19-perf-v1 \\\n  --metadata-dir /path/to/new/perf-metadata-v1\n```\n\nOnly canonical WAV/ID/SHA and global policies may enter Android. Reference\ntext and speaker counts stay on the host for independent post-inference scoring.\n"""
    (metadata / "README.md").write_text(readme, encoding="utf-8")
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-metadata", type=Path, default=REPO / "benchmark/eval")
    parser.add_argument("--source-audio-root", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--metadata-dir", type=Path, default=REPO / "benchmark/eval-perf")
    arguments = parser.parse_args()
    result = prepare(arguments.source_metadata, arguments.source_audio_root, arguments.audio_root, arguments.metadata_dir)
    print(json.dumps({"status": result["status"], "files": len(result["files"]),
                      "audio_ms": result["total_audio_ms"], "prefix_frames": result["source"]["exact_prefix_frames"],
                      "manifest_sha256": sha(arguments.metadata_dir / "manifest.json"), "new_model_inference": False}))


if __name__ == "__main__":
    main()
