#!/usr/bin/env python3
"""Freeze/build an unused-source reserve from author metadata only; no inference.

All cases are future holdout. This does not replace or relax any old holdout
gate. No model output, hypothesis, metric, or old reference file is read.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys

if __package__:
    from . import prepare_corpus as corpus
else:
    import prepare_corpus as corpus

ROOT = Path(__file__).resolve().parents[2]
SEED = "plan19h-reserve-v1-20261107"
OLD_MANIFEST_SHA256 = "47109cb1987624daaf8f4dc28e8eca3198b0c2bbcf01cd334b9611664eb38066"


def recipes():
    ordinary = ["neutral", "happy", "surprise", "sad"]
    expressive = ["angry", "laughing", "fear", "arrogance", "disgust", "surprise", "happy", "sad"]
    return [
        dict(id="reserve-01-two-clean", split="holdout", actors="MDMDMD", emotions=ordinary, min_s=3.5, max_s=12),
        dict(id="reserve-02-two-clean", split="holdout", actors="MSMSMS", emotions=ordinary, min_s=3.5, max_s=12),
        dict(id="reserve-03-three-clean", split="holdout", actors="MSDMSD", emotions=ordinary, min_s=3.5, max_s=12),
        dict(id="reserve-04-three-clean", split="holdout", actors="SDMSDM", emotions=ordinary, min_s=3.5, max_s=12),
        dict(id="reserve-05-short", split="holdout", actors="MSMSMS", emotions=expressive + ["neutral"], min_s=.5, max_s=3.5, max_words=8, short=True),
        dict(id="reserve-06-short", split="holdout", actors="SMSMSM", emotions=expressive + ["neutral"], min_s=.5, max_s=3.5, max_words=8, short=True),
        dict(id="reserve-07-expressive", split="holdout", actors="DMSDMS", emotions=expressive, min_s=3.5, max_s=12),
        dict(id="reserve-08-expressive", split="holdout", actors="MDSMDS", emotions=expressive, min_s=3.5, max_s=12),
        dict(id="reserve-09-overlap", split="holdout", actors="DMDMDM", emotions=ordinary, min_s=3.5, max_s=12, overlap=True),
        dict(id="reserve-10-overlap", split="holdout", actors="SMDMSD", emotions=ordinary, min_s=3.5, max_s=12, overlap=True),
    ]


def load_sources():
    source_dir = ROOT / "benchmark/eval/sources"
    original = ROOT / "benchmark/eval/manifest.json"
    if corpus.file_sha256(original) != OLD_MANIFEST_SHA256:
        raise ValueError("Original corpus manifest changed; refuse to alter frozen exclusions")
    old = json.loads(original.read_text(encoding="utf-8"))
    old_paths = {path for case in old["files"] for path in case["source"]["audio_paths"]}
    if len(old_paths) != 77:
        raise ValueError("Expected exactly 77 original source clips")
    source_bytes = {}
    rows = []
    for name, expected in corpus.PINNED_METADATA.items():
        content = (source_dir / name).read_bytes()
        if corpus.sha256(content) != expected:
            raise ValueError("Pinned author metadata differs: " + name)
        source_bytes[name] = content
        if name.endswith(".csv"):
            rows += [dict(row, author_split=name[:-4]) for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter="|")]
    index_bytes = (source_dir / "audio-index.json").read_bytes()
    if corpus.sha256(index_bytes) != corpus.SOURCE_INDEX_SHA256:
        raise ValueError("Pinned publisher audio index differs")
    source_bytes["audio-index.json"] = index_bytes
    publisher = {item["path"]: item for item in json.loads(index_bytes)["files"]}
    excluded_paths = old_paths | corpus.PREVIOUSLY_EVALUATED
    excluded_hashes = {publisher[path]["sha256"] for path in excluded_paths if path in publisher}
    excluded_texts = {row["text"].strip() for row in rows if row["audio_path"] in excluded_paths}
    return source_bytes, rows, publisher, old_paths, excluded_paths, excluded_hashes, excluded_texts


def select_sources(rows, publisher, excluded_paths, excluded_hashes, excluded_texts):
    used_paths, used_hashes, used_texts = set(excluded_paths), set(excluded_hashes), set(excluded_texts)
    selected = []
    for recipe in recipes():
        chosen = []
        for actor in recipe["actors"]:
            eligible = [row for row in rows if row["audio_path"] in publisher
                        and row["audio_path"] not in used_paths
                        and publisher[row["audio_path"]]["sha256"] not in used_hashes
                        and row["text"].strip() not in used_texts
                        and row["speaker_id"] == actor and row["emotion"] in recipe["emotions"]
                        and recipe["min_s"] <= float(row["duration"]) <= recipe["max_s"]
                        and len(row["text"].split()) <= recipe.get("max_words", 10000)]
            eligible.sort(key=lambda row: corpus.sha256((SEED + "|" + row["audio_path"]).encode()))
            if not eligible:
                raise ValueError(f"Insufficient unused source pool for {recipe['id']}/{actor}; no reserve audio built")
            row = dict(eligible[0])
            chosen.append(row)
            used_paths.add(row["audio_path"])
            used_hashes.add(publisher[row["audio_path"]]["sha256"])
            used_texts.add(row["text"].strip())
        selected.append({"recipe": recipe, "utterances": chosen})
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--metadata-dir", type=Path, default=ROOT / "benchmark/eval-reserve")
    parser.add_argument("--select-only", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    audio_root, metadata = args.audio_root.resolve(), args.metadata_dir.resolve()
    if audio_root.is_relative_to(ROOT):
        parser.error("Audio root must be outside the source repository")
    if not 1 <= args.workers <= 8:
        parser.error("workers must be 1..8")
    source_bytes, rows, publisher, old_paths, excluded_paths, excluded_hashes, excluded_texts = load_sources()
    selected = select_sources(rows, publisher, excluded_paths, excluded_hashes, excluded_texts)
    selection_path = metadata / "selection.json"
    frozen_at = json.loads(selection_path.read_text())["frozen_at"] if selection_path.exists() else datetime.now(timezone.utc).isoformat()
    selection = {"schema_version": 1, "seed": SEED, "frozen_at": frozen_at,
                 "selection_inputs": "Pinned author CSV rows, publisher LFS index, fixed recipes and exclusions only",
                 "model_output_or_hypothesis_input": False, "old_reference_file_input": False,
                 "old_manifest_sha256": OLD_MANIFEST_SHA256,
                 "excluded_original_source_paths": sorted(old_paths),
                 "excluded_prior_whisper_paths": sorted(corpus.PREVIOUSLY_EVALUATED),
                 "files": selected}
    corpus.put_identical_or_new(metadata / "recipes.json", corpus.json_bytes({"schema_version": 1, "seed": SEED, "recipes": recipes()}))
    corpus.put_identical_or_new(selection_path, corpus.json_bytes(selection))
    for name, content in source_bytes.items():
        corpus.put_identical_or_new(metadata / "sources" / name, content)
    print(json.dumps({"selection_cases": len(selected), "selected_clips": sum(len(case["utterances"]) for case in selected),
                      "selection_sha256": corpus.file_sha256(selection_path), "frozen_at": frozen_at}), flush=True)
    if args.select_only:
        return 0
    all_rows = [row for item in selected for row in item["utterances"]]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        fetched = list(executor.map(lambda row: corpus.source_audio(audio_root, row, publisher[row["audio_path"]], args.offline), all_rows))
    loaded = {path: (samples, info) for path, samples, info in fetched}
    paths = set(loaded)
    hashes = {info["audio_sha256"] for _, info in loaded.values()}
    texts = {info["text"].strip() for _, info in loaded.values()}
    if len(paths) != 60 or len(hashes) != 60 or len(texts) != 60 or paths & excluded_paths or hashes & excluded_hashes or texts & excluded_texts:
        raise ValueError("Reserve source disjointness/uniqueness check failed")
    files, placements = [], []
    for item in selected:
        case, reference, placement = corpus.prepare_audio_case(item, loaded, audio_root)
        case["source"].pop("author_split")
        case["source"]["author_splits"] = sorted({row["author_split"] for row in item["utterances"]})
        case["reserve"] = True
        corpus.put_identical_or_new(metadata / case["reference"], corpus.json_bytes(reference))
        files.append(case)
        placements.append(placement)
    proof = {"schema_version": 1, "frozen_at": frozen_at, "selection_sha256": corpus.file_sha256(selection_path),
             "seed": SEED, "original_manifest_sha256": OLD_MANIFEST_SHA256,
             "source_csv_sha256": corpus.PINNED_METADATA, "publisher_index_sha256": corpus.SOURCE_INDEX_SHA256,
             "original_source_clips": len(old_paths), "prior_whisper_clips": len(corpus.PREVIOUSLY_EVALUATED),
             "reserve_source_clips": len(paths), "original_or_prior_source_path_intersection": [],
             "original_or_prior_audio_hash_intersection": [], "original_or_prior_exact_text_intersection": [],
             "unique_reserve_paths": len(paths), "unique_reserve_audio_hashes": len(hashes),
             "unique_reserve_texts": len(texts), "model_or_hypothesis_files_read": False,
             "reference_creation": "Verbatim author CSV text and deterministic clip placement only; no ASR/VAD/forced alignment"}
    corpus.put_identical_or_new(metadata / "disjointness.json", corpus.json_bytes(proof))
    provenance = {"schema_version": 1, "repo": corpus.REPO, "revision": corpus.REVISION,
                  "frozen_at": frozen_at, "seed": SEED, "selection_sha256": corpus.file_sha256(selection_path),
                  "preparation_helper_sha256": corpus.file_sha256(Path(corpus.__file__)),
                  "source_metadata_sha256": corpus.PINNED_METADATA,
                  "publisher_audio_index_sha256": corpus.SOURCE_INDEX_SHA256,
                  "sources": [info for _, info in loaded.values()], "files": placements,
                  "audio_processing": {"rate": 16000, "channels": 1, "subtype": "PCM_16",
                      "resampler": "Same pinned corpus helper: float64 mean channels; scipy.signal.resample_poly reduced rate ratio, Kaiser5.0, constant padding; no trim/VAD/ASR",
                      "montage": "250ms outer silence, fixed gaps/500ms placed clip overlaps, whole-file gain only for0.999 peak headroom; floor millisecond boundaries",
                      "numpy": corpus.np.__version__, "scipy": corpus.scipy.__version__, "soundfile": corpus.sf.__version__},
                  "scope": "Future reserve holdout; no model inference or candidate input. Same3 actors/sessions may occur in original corpus. Montage utterance-interval DER proxy is not natural-dialogue or human word/speech-activity gold.",
                  "original_gate": "Original holdout remains mandatory; reserve is an additional check and cannot replace or excuse a failed original gate.",
                  "license": "Pinned author OpenRAIL sources/LICENSE.md retained with research data; audio outside Git/APK"}
    corpus.put_identical_or_new(metadata / "provenance.json", corpus.json_bytes(provenance))
    manifest = {"schema_version": 1, "name": "REPLIKA independent unused-source reserve v1",
                "seed": SEED, "frozen_at": frozen_at,
                "reference_scope": "All holdout; author text and montage utterance-bound proxies. Original holdout gate remains required.", "files": files}
    corpus.put_identical_or_new(metadata / "manifest.json", corpus.json_bytes(manifest))
    corpus.put_identical_or_new(audio_root / "LICENSE.langswap.md", source_bytes["LICENSE.md"])
    summary = {"cases": len(files), "source_clips": len(paths), "duration_ms": sum(case["duration_ms"] for case in files),
               "case_splits": ["holdout"], "speaker_count_cases": {str(n): sum(case["expected_speakers"] == n for case in files) for n in (2, 3)},
               "short_cases": sum(case["conditions"]["short_utterances"] for case in files),
               "overlap_cases": sum(case["conditions"]["placed_clip_overlap"] for case in files),
               "manifest_sha256": corpus.file_sha256(metadata / "manifest.json"), "inference_performed": False}
    corpus.put_identical_or_new(metadata / "summary.json", corpus.json_bytes(summary))
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        raise SystemExit(1)
