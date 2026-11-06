#!/usr/bin/env python3
"""Prepare a pinned, author-transcribed Russian research corpus; no model inference.

Audio/cache stays under --audio-root, outside the repository. Committed metadata
contains the deterministic selection, exact references, licenses and hashes.
The montage intervals are author-utterance placement bounds, NOT human speech-
activity annotation or evidence of natural-dialogue DER.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import urllib.request

import numpy as np
import scipy
from scipy.signal import resample_poly
import soundfile as sf


ROOT = Path(__file__).resolve().parents[2]
REPO = "langswap/dialogs-ru-emotional-conversations"
REVISION = "a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd"
BASE = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/"
RATE = 16000
SEED = "replika-eval-corpus-v1-before-inference"
SOURCE_INDEX_SHA256 = "1afb29556fa6b1fe8da6efbb68566fa5a680b9c01811ab136fe69494d28cfaf1"
PINNED_METADATA = {
    "val.csv": "657d7e050a05d7c541b8979ca20a49181fe9bbd9e1cb6524f20efae55a33b388",
    "test.csv": "824091e87e879fdf8c7b8201e3f49be842203f411fba745afd95e320e4e4b5f2",
    "LICENSE.md": "e136a6af001dd43a9002f20f39dd56d200afa9a6d408e28a625d90c9a0c22143",
    "README.md": "160a80ed2efde335e1d332f7a0f66370dc933c4866a0d42b51ff97c8aa8d1436",
}
# These seven test recordings informed V1.5 rescue work and cannot be new holdout.
PREVIOUSLY_EVALUATED = {
    "wavs/masha_dima_part9_158.wav", "wavs/masha_dima_part9_222.wav",
    "wavs/masha_dima_part9_397.wav", "wavs/masha_dima_part11_287.wav",
    "wavs/masha_dima_part11_296.wav", "wavs/masha_sveta_part9_770.wav",
    "wavs/masha_sveta_part9_1261.wav",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def put_identical_or_new(path: Path, content: bytes) -> None:
    """Do not quietly replace a frozen reference or a previous preparation."""
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Frozen output differs: {path}; use a NEW metadata/audio directory")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def fetch_cached(url: str, path: Path, expected: str | None, offline: bool) -> bytes:
    if path.exists():
        content = path.read_bytes()
    else:
        if offline:
            raise FileNotFoundError(f"Offline cache miss: {path}")
        request = urllib.request.Request(url, headers={"User-Agent": "REPLIKA-evaluation-corpus/1"})
        with urllib.request.urlopen(request, timeout=120) as response:
            content = response.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise ValueError(f"Unexpectedly large individual source: {url}")
        if expected and sha256(content) != expected:
            raise ValueError(f"Pinned source hash differs: {url}")
        put_identical_or_new(path, content)
    if expected and sha256(content) != expected:
        raise ValueError(f"Cached source hash differs: {path}")
    return content


def recipes():
    ordinary = ["neutral", "happy"]
    expressive = ["angry", "happy", "surprise", "laughing", "sad", "disgust", "fear", "arrogance"]
    # All constraints and order are fixed before inference. Short pools deliberately
    # include two actors in val: D has no <=3.5s / <=8-word val utterances.
    return [
        dict(id="dev-01-two-clean", split="dev", actors="MDMDMDMD", emotions=ordinary, min_s=4, max_s=12),
        dict(id="dev-02-three-clean", split="dev", actors="MSDMSDMSD", emotions=ordinary, min_s=4, max_s=12),
        dict(id="dev-03-short", split="dev", actors="MSMSMSMS", emotions=expressive + ["neutral"], min_s=.5, max_s=3.5, max_words=8, short=True),
        dict(id="dev-04-expressive", split="dev", actors="DMSDMS", emotions=expressive, min_s=3.5, max_s=12),
        dict(id="dev-05-whisper", split="dev", actors="MDSDDS", emotions=["whisper"], min_s=1, max_s=16),
        dict(id="dev-06-overlap", split="dev", actors="SMDMSD", emotions=ordinary + ["surprise", "sad"], min_s=4, max_s=10, overlap=True),
        dict(id="holdout-01-two-clean", split="holdout", actors="DMDMDMDM", emotions=ordinary, min_s=4, max_s=12),
        dict(id="holdout-02-three-clean", split="holdout", actors="SDMSDMSDM", emotions=ordinary, min_s=4, max_s=12),
        dict(id="holdout-03-short", split="holdout", actors="MSDMSMSM", emotions=expressive + ["neutral"], min_s=.5, max_s=3.5, max_words=8, short=True),
        dict(id="holdout-04-overlap-expressive", split="holdout", actors="DMSDMS", emotions=expressive, min_s=3.5, max_s=12, overlap=True),
        dict(id="dev-mono-m", split="dev", actors="M", emotions=ordinary, min_s=5, max_s=16, mono=True),
        dict(id="dev-mono-s", split="dev", actors="S", emotions=ordinary, min_s=5, max_s=16, mono=True),
        dict(id="holdout-mono-d", split="holdout", actors="D", emotions=ordinary, min_s=5, max_s=16, mono=True),
    ]


def select_sources(rows_by_split: dict, available: set[str]) -> list[dict]:
    used_paths: set[str] = set()
    used_texts: set[str] = set()
    result = []
    for recipe in recipes():
        chosen = []
        for actor in recipe["actors"]:
            candidates = [row for row in rows_by_split[recipe["split"]]
                          if row["speaker_id"] == actor and row["emotion"] in recipe["emotions"]
                          and recipe["min_s"] <= float(row["duration"]) <= recipe["max_s"]
                          and len(row["text"].split()) <= recipe.get("max_words", 10000)
                          and row["audio_path"] not in used_paths
                          and row["audio_path"] in available
                          and row["audio_path"] not in PREVIOUSLY_EVALUATED
                          and row["text"].strip() not in used_texts]
            candidates.sort(key=lambda row: sha256((SEED + "|" + row["audio_path"]).encode()))
            if not candidates:
                raise ValueError(f"No unused author row for {recipe['id']}/{actor}")
            row = dict(candidates[0])
            row["author_split"] = "val" if recipe["split"] == "dev" else "test"
            chosen.append(row)
            used_paths.add(row["audio_path"])
            used_texts.add(row["text"].strip())
        result.append({"recipe": recipe, "utterances": chosen})
    return result


def source_audio(audio_root: Path, row: dict, publisher: dict, offline: bool):
    path = row["audio_path"]
    if not path.startswith("wavs/") or Path(path).name != path[5:] or not path.endswith(".wav"):
        raise ValueError(f"Unsafe source path: {path}")
    raw_path = audio_root / "source-wavs" / Path(path).name
    content = fetch_cached(BASE + path, raw_path, publisher["sha256"], offline)
    if len(content) != publisher["bytes"]:
        raise ValueError(f"Publisher file size differs: {path}")
    samples, rate = sf.read(io.BytesIO(content), dtype="float64", always_2d=True)
    if not len(samples) or not np.isfinite(samples).all():
        raise ValueError(f"Empty/nonfinite source: {path}")
    source_channels = samples.shape[1]
    samples = samples.mean(axis=1)
    divisor = math.gcd(rate, RATE)
    if rate != RATE:
        samples = resample_poly(samples, RATE // divisor, rate // divisor,
                                window=("kaiser", 5.0), padtype="constant")
    metadata = {
        **row, "url": BASE + path, "audio_sha256": sha256(content),
        "publisher_lfs_sha256": publisher["sha256"],
        "bytes": len(content), "sample_rate": rate, "channels": source_channels,
        "source_frames": sf.info(io.BytesIO(content)).frames,
        "resampled_frames": len(samples),
    }
    return path, samples, metadata


def sample_ms(sample: int) -> int:
    # Match AudioDecoder/Worker floor conversion, including the final endpoint.
    return sample * 1000 // RATE


def prepare_audio_case(item: dict, loaded: dict, audio_root: Path):
    recipe, rows = item["recipe"], item["utterances"]
    placements = []
    end = 0 if recipe.get("mono") else RATE // 4
    for index, row in enumerate(rows):
        if index:
            gap_ms = [-500, 150][index % 2] if recipe.get("overlap") and index in (2, 4) else [180, 350, 550][index % 3]
            end += gap_ms * RATE // 1000
        samples = loaded[row["audio_path"]][0]
        placements.append((end, end + len(samples), row, samples))
        end += len(samples)
    total = end + (0 if recipe.get("mono") else RATE // 4)
    mixed = np.zeros(total, dtype=np.float64)
    for start, stop, row, samples in placements:
        mixed[start:stop] += samples
    peak = float(np.max(np.abs(mixed)))
    # Only prevent introduced PCM16 clipping; no loudness/gain/VAD tuning.
    headroom_gain = min(1.0, .999 / peak) if peak > 0 else 1.0
    mixed *= headroom_gain
    encoded = io.BytesIO()
    sf.write(encoded, mixed, RATE, format="WAV", subtype="PCM_16")
    content = encoded.getvalue()
    relative_audio = f"{recipe['split']}/{recipe['id']}.wav"
    put_identical_or_new(audio_root / relative_audio, content)
    speaker_map = {}
    turns, provenance_turns = [], []
    for start, stop, row, _ in placements:
        actor = row["speaker_id"]
        speaker_map.setdefault(actor, f"speaker_{len(speaker_map) + 1}")
        turn = {"speaker_id": speaker_map[actor], "start_ms": sample_ms(start),
                "end_ms": sample_ms(stop), "text": row["text"]}
        turns.append(turn)
        provenance_turns.append({**turn, "actor_id": actor,
                                 "source_audio_path": row["audio_path"],
                                 "source_audio_sha256": loaded[row["audio_path"]][1]["audio_sha256"],
                                 "source_start_frame": 0,
                                 "source_end_frame": loaded[row["audio_path"]][1]["source_frames"],
                                 "resampled_start_frame": start, "resampled_end_frame": stop,
                                 "interval_kind": "author_utterance_clip_bounds" if recipe.get("mono") else "simulated_placement_of_author_utterance_clip"})
    turns.sort(key=lambda turn: (turn["start_ms"], turn["end_ms"]))
    descriptor = {
        "id": recipe["id"], "split": recipe["split"], "language": "ru",
        "audio": relative_audio, "reference": f"references/{recipe['id']}.json",
        "duration_ms": sample_ms(total), "audio_sha256": sha256(content),
        "expected_speakers": len(speaker_map),
        "kind": "author_mono_clip" if recipe.get("mono") else "simulated_actor_montage",
        "source": {"repo": REPO, "revision": REVISION,
                   "author_split": "val" if recipe["split"] == "dev" else "test",
                   "license": "OpenRAIL; see sources/LICENSE.md",
                   "utterance_count": len(rows), "actors": list(speaker_map),
                   "audio_paths": [row["audio_path"] for row in rows]},
        "conditions": {"short_utterances": recipe.get("short", False),
                       "placed_clip_overlap": recipe.get("overlap", False),
                       "emotions": sorted({row["emotion"] for row in rows}),
                       "headroom_gain": headroom_gain},
        "timing_scope": "Author utterance clip bounds placed on a constructed clock; not manually annotated voice activity",
        "der_scope": "montage utterance-interval proxy; not natural-dialogue DER" if not recipe.get("mono") else "author utterance-interval proxy; not voice-activity DER",
    }
    provenance = {"id": recipe["id"], "audio": relative_audio, "sample_rate": RATE,
                  "frames": total, "unscaled_peak": peak, "headroom_gain": headroom_gain,
                  "speaker_map": speaker_map, "utterances": provenance_turns}
    return descriptor, {"transcript": turns}, provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--metadata-dir", type=Path, default=ROOT / "benchmark/eval")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--offline", action="store_true", help="Require all original files in local cache")
    parser.add_argument("--select-only", action="store_true", help="Freeze metadata selection without downloading audio")
    args = parser.parse_args(argv)
    audio_root, metadata_dir = args.audio_root.resolve(), args.metadata_dir.resolve()
    if audio_root == ROOT or ROOT in audio_root.parents:
        parser.error("--audio-root must be outside the source repository")
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be 1..8")
    rows = {}
    for filename, expected in PINNED_METADATA.items():
        content = fetch_cached(BASE + filename, audio_root / "source-metadata" / filename, expected, args.offline)
        put_identical_or_new(metadata_dir / "sources" / filename, content)
        if filename.endswith(".csv"):
            split = "dev" if filename == "val.csv" else "holdout"
            rows[split] = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter="|"))
    # Frozen publisher index avoids unavailable CSV paths. It was collected from
    # the pinned Git tree before inference; its LFS OIDs authenticate source bytes
    # relative to that immutable publisher revision, not a publisher signature.
    index_bytes = (ROOT / "benchmark/eval/sources/audio-index.json").read_bytes()
    if sha256(index_bytes) != SOURCE_INDEX_SHA256:
        raise ValueError("Frozen publisher audio index hash differs")
    put_identical_or_new(metadata_dir / "sources/audio-index.json", index_bytes)
    publisher_index = {item["path"]: item for item in json.loads(index_bytes)["files"]}
    selection = select_sources(rows, set(publisher_index))
    frozen_selection = {"schema_version": 1, "repo": REPO, "revision": REVISION,
                        "selection_seed": SEED, "selection_rule": "Fixed recipe constraints; unused author rows ordered by SHA256(seed|audio_path); no inference involved",
                        "previously_evaluated_excluded": sorted(PREVIOUSLY_EVALUATED), "files": selection}
    put_identical_or_new(metadata_dir / "selection.json", json_bytes(frozen_selection))
    print(f"Frozen selection: {len(selection)} files / {sum(len(i['utterances']) for i in selection)} unique source clips", flush=True)
    if args.select_only:
        return 0
    all_rows = [row for case in selection for row in case["utterances"]]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        fetched = list(executor.map(lambda row: source_audio(audio_root, row, publisher_index[row["audio_path"]], args.offline), all_rows))
    loaded = {path: (samples, metadata) for path, samples, metadata in fetched}
    raw_hashes = [meta["audio_sha256"] for _, meta in loaded.values()]
    if len(set(raw_hashes)) != len(raw_hashes):
        raise ValueError("Duplicate audio content under distinct selected source paths")
    files, case_provenance = [], []
    for case in selection:
        descriptor, reference, provenance = prepare_audio_case(case, loaded, audio_root)
        put_identical_or_new(metadata_dir / descriptor["reference"], json_bytes(reference))
        files.append(descriptor)
        case_provenance.append(provenance)
        print(f"Prepared {descriptor['id']}: {descriptor['duration_ms']}ms / {descriptor['expected_speakers']} speakers", flush=True)
    provenance = {
        "schema_version": 1, "repo": REPO, "revision": REVISION,
        "source_metadata_sha256": PINNED_METADATA,
        "publisher_audio_index_sha256": SOURCE_INDEX_SHA256,
        "reference_origin": "Unmodified text from pinned author val.csv/test.csv, not ASR hypotheses; authored punctuation/case preserved",
        "timing_origin": "Source files are author-segmented utterance clips; reference intervals span full clips including internal pauses. Montage offsets are constructed, not original conversational times or independently annotated voice activity.",
        "selection": "Frozen selection.json written before any inference; source paths, exact texts and raw audio hashes do not repeat across dev/holdout",
        "speaker_scope": "Three actors shared across splits; source utterances disjoint, not speaker/session-disjoint",
        "audio_processing": {"sample_rate": RATE, "subtype": "PCM_16", "source_decode": "libsndfile float64; mean channels",
                             "resampling": "scipy.signal.resample_poly, reduced integer up/down ratio, window=('kaiser',5.0), padtype='constant'; no trim/VAD/ASR alignment",
                             "mixing": "Fixed silence gaps or clip overlaps; whole-recording gain only if needed for 0.999 peak headroom, then PCM16 encoding",
                             "numpy": np.__version__, "scipy": scipy.__version__, "soundfile": sf.__version__},
        "natural_dialogue_limitation": "No accessible ungated, human-verified natural RU dialogue with independent speech-activity timestamps was obtained. DAI-ASR-I18N requires an approved custom gated agreement; no gated access attempted. This corpus cannot establish natural-dialogue DER.",
        "license": "OpenRAIL custom author LICENSE; retain restrictions/notice when distributing derivatives; no research audio in APK or Git",
        "sources": [meta for _, meta in loaded.values()], "files": case_provenance,
    }
    put_identical_or_new(metadata_dir / "provenance.json", json_bytes(provenance))
    manifest = {"schema_version": 1, "name": "REPLIKA Langswap actor corpus v1",
                "reference_scope": "Author text; utterance-interval timing proxy; montage is not a natural dialogue",
                "files": files}
    put_identical_or_new(metadata_dir / "manifest.json", json_bytes(manifest))
    put_identical_or_new(audio_root / "LICENSE.langswap.md", (metadata_dir / "sources/LICENSE.md").read_bytes())
    print(f"Ready: {metadata_dir / 'manifest.json'}; {sum(x['duration_ms'] for x in files) / 1000:.3f}s total", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
