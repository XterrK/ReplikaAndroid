#!/usr/bin/env python3
"""Compute baseline ERes2Net clean-window vectors from verified, saved D native turns.

The saved automatic diarization and ASR are replayed without rerunning either.
Only the additional clean-window embedding stage performs new neural inference.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import gc
import json
import math
from pathlib import Path
import platform
import re
import struct
import sys
import time

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.eval import diar_sweep as sweep
from tools.eval import pipeline as base


def _same_float32(actual, expected):
    if type(actual) not in (int, float) or not math.isfinite(actual):
        return False
    try:
        return struct.pack("!f", actual) == struct.pack("!f", expected)
    except (OverflowError, struct.error):
        return False


def source_run_policy(meta, model_specs):
    """Only the original, automatic baseline neural policy is a valid D turn source."""
    config, fingerprint = meta.get("config", {}), meta.get("fingerprint", {})
    if (meta.get("status") != "COMPLETE" or config.get("pipeline") != "vad_words_v1"
            or config.get("punctuation_mode") != "none" or config.get("expected_speakers") != -1
            or fingerprint.get("runtime") != base.RUNTIME_VERSION
            or fingerprint.get("models") != {item["path"]: item["sha256"] for item in model_specs}):
        raise ValueError("Need completed automatic D ASR with the unchanged pinned model pack")
    return config, fingerprint


def source_turns(diagnostic, duration_ms, model_specs):
    """Validate a saved actual SD result; no reference labels/counts enter this function."""
    config = diagnostic.get("config", {})
    wanted = {"clusterThreshold": .5, "segmentationWindowShiftRatio": .1,
              "diarMinDurationOnSec": .2, "diarMinDurationOffSec": .5}
    files = {item.get("path"): item for item in diagnostic.get("modelFiles", [])}
    if (diagnostic.get("clusteringMode") != "automatic" or diagnostic.get("expectedSpeakers") != -1
            or diagnostic.get("runtime") != "sherpa-onnx " + base.RUNTIME_VERSION
            or any(not _same_float32(config.get(key), value) for key, value in wanted.items())):
        raise ValueError("Saved source is not the original automatic diarization policy")
    for spec in model_specs:
        saved = files.get(spec["path"], {})
        if saved.get("sha256") != spec["sha256"] or saved.get("bytes") != spec["size"]:
            raise ValueError("Saved source model fingerprint differs: " + spec["path"])
    turns = []
    for item in diagnostic.get("diarizationTurns", []):
        start, end, speaker = (item.get(key) for key in ("startMs", "endMs", "speakerId"))
        if (any(type(value) is not int for value in (start, end, speaker))
                or not 0 <= start < end <= duration_ms or speaker < 0):
            raise ValueError("Saved native turn exceeds the original audio clock")
        turns.append(base.Turn(start, end, speaker))
    return turns


def derived_metrics(source):
    """Retain source scores while removing historical timings from this derived run."""
    result = copy.deepcopy(source)
    result["rtf"] = None
    result["inputs"]["processing_ms"] = None
    return result


def _summary(records):
    quality = sweep.summarize(records)
    quality["rtf_diarization_stage"] = None
    quality["timing_scope"] = "Saved D diarization/ASR replay; no SD or whole-pipeline RTF was measured"
    quality["new_diarization_inference"] = False
    quality["new_asr_inference"] = False
    quality["window_embedding_stage_ms"] = sum(item["window_embedding_stage_ms"] for item in records)
    quality["window_embedding_stage_rtf"] = (quality["window_embedding_stage_ms"] / quality["audio_ms"]
        if quality["audio_ms"] else None)
    quality["embedding_timing_scope"] = "Extractor construction, clean-window extraction/Compute and release; decode excluded"
    quality["clean_embedding_windows"] = sum(item["clean_embedding_window_count"] for item in records)
    return {"profiles": {"auto-0p50": quality}}


def _csv(output, records):
    fields = ["profile", "id", "mode", "model_id", "native_speaker_count", "reference_speaker_count",
        "native_speaker_count_error", "duration_ms", "diarization_inference_ms", "decode_ms",
        "window_embedding_stage_ms", "clean_embedding_window_count", "new_diarization_inference",
        "new_asr_inference", "new_embedding_inference"]
    temporary = output / "results.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    temporary.replace(output / "results.csv")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asr-run", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=sweep.REPO / "benchmark/eval/manifest.json")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=sweep.REPO / "model-pack")
    parser.add_argument("--threads", type=int, choices=(1, 2, 4), default=2)
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Choose a fresh output; saved evidence must not be overwritten")
    import numpy as np
    import sherpa_onnx as sherpa
    from sherpa_onnx.lib import _sherpa_onnx as native
    if sherpa.__version__ != base.RUNTIME_VERSION:
        raise ValueError("Pinned sherpa-onnx runtime required")
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported manifest")
    cases = [case for case in manifest["files"] if (args.split == "all" or case["split"] == args.split)
             and (not args.cases or case["id"] in args.cases)]
    if (not cases or len({case["id"] for case in cases}) != len(cases)
            or any(not re.fullmatch(r"[A-Za-z0-9_-]+", case["id"]) for case in cases)
            or args.cases and set(args.cases) != {case["id"] for case in cases}):
        raise ValueError("Empty, duplicate or unknown selected case IDs")
    lock_path = sweep.REPO / "app/src/main/assets/models-lock.json"
    lock = json.loads(lock_path.read_text())
    diar_specs = [item for item in lock["files"] if item["path"] in ("diar/embedding.onnx", "diar/segmentation.onnx")]
    if len(diar_specs) != 2:
        raise ValueError("Need both baseline diarization model pins")
    for spec in diar_specs:
        model_file = sweep.confined(args.model_root, spec["path"])
        if model_file.stat().st_size != spec["size"] or sweep.digest(model_file) != spec["sha256"]:
            raise ValueError("Baseline model pin mismatch: " + spec["path"])
    embedding = sweep.confined(args.model_root, "diar/embedding.onnx")
    source_meta = json.loads((args.asr_run / "run.json").read_text())
    source_config, source_fingerprint = source_run_policy(source_meta, lock["files"])
    dependencies = {"baseline_helpers_sha256": Path(base.__file__),
                    "decoder_code_sha256": Path(base.__file__).with_name("decoder_parity.py"),
                    "scorer_code_sha256": Path(sweep.scoring.__file__),
                    "word_planner_code_sha256": Path(base.__file__).with_name("vad_words.py")}
    for field, path in dependencies.items():
        if source_fingerprint.get(field) != sweep.digest(path):
            raise ValueError("Source D decoder/helper changed: " + field)
    if source_fingerprint.get("model_lock_sha256") != sweep.digest(lock_path):
        raise ValueError("Source D model lock changed")

    preflight, source_cases = [], {}
    for case in cases:
        folder = args.asr_run / case["id"]
        audio = sweep.confined(args.audio_root, case["audio"])
        reference = sweep.confined(args.manifest.parent, case["reference"])
        reference_hash = sweep.digest(reference)
        if (sweep.digest(audio) != case["audio_sha256"]
                or source_fingerprint["references"].get(case["id"]) != reference_hash
                or sweep.digest(folder / "reference.json") != reference_hash):
            raise ValueError("Source/audio/reference pin mismatch: " + case["id"])
        chunks, source_record, source = sweep.load_asr(folder, case, reference_hash)
        diagnostic = json.loads((folder / "diagnostics.json").read_text())
        if diagnostic.get("onnxruntimeVersion") != native.onnxruntime_version:
            raise ValueError("Source D ONNX Runtime differs")
        turns = source_turns(diagnostic, case["duration_ms"], diar_specs)
        hypothesis = json.loads((folder / "hypothesis.json").read_text())
        if sweep.project_asr(chunks, turns, source) != hypothesis:
            raise ValueError("Source D hypothesis does not reconstruct from real tokens/turns")
        source_cases[case["id"]] = {"case_sha256": sweep.digest(folder / "case.json"),
            "evidence_sha256": sweep.evidence_hashes(folder)}
        preflight.append((case, audio, folder, source_record, diagnostic, turns))

    output.mkdir(parents=True)
    runtime = {"sherpa": sherpa.__version__, "git": native.git_sha1, "git_date": native.git_date,
        "onnxruntime": native.onnxruntime_version, "extension_sha256": sweep.digest(Path(native.__file__))}
    fingerprint = {"manifest": sweep.digest(args.manifest), "source_D_run": sweep.digest(args.asr_run / "run.json"),
        "source_cases": source_cases, "lock": sweep.digest(lock_path), "model_files": diar_specs,
        "threads": args.threads, "selected_ids": [case["id"] for case in cases], "runtime": runtime,
        "code": {path.name: sweep.digest(path) for path in [Path(__file__), Path(sweep.__file__),
            Path(base.__file__), Path(base.__file__).with_name("decoder_parity.py"),
            Path(base.__file__).with_name("vad_words.py"), Path(base.__file__).with_name("speaker_refiner.py")]}}
    meta = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": fingerprint, "platform": platform.platform(), "source_D_config": source_config,
        "scope": "Additional real baseline ERes clean-window embeddings from saved D native turns. No new SD or ASR inference; no full-pipeline RTF.",
        "new_diarization_inference": False, "new_asr_inference": False}
    sweep.write_json(output / "run.json", meta)
    sweep.write_json(output / "manifest.json", manifest)
    records = []
    try:
        for case, audio, source_folder, source_record, source_diag, turns in preflight:
            if (sweep.digest(audio) != case["audio_sha256"]
                    or sweep.digest(source_folder / "case.json") != source_cases[case["id"]]["case_sha256"]
                    or sweep.evidence_hashes(source_folder) != source_cases[case["id"]]["evidence_sha256"]):
                raise ValueError("Source changed after preflight: " + case["id"])
            folder = output / "auto-0p50" / case["id"]
            folder.mkdir(parents=True)
            start = time.perf_counter()
            samples = base._read_canonical_wav(audio, np)
            decode_ms = (time.perf_counter() - start) * 1000
            duration_ms = len(samples) * 1000 // 16000
            if duration_ms != case["duration_ms"]:
                raise ValueError("Decoded source clock changed")
            start = time.perf_counter()
            windows = sweep.extract_windows(samples, turns, embedding, args.threads, sherpa)
            window_ms = (time.perf_counter() - start) * 1000
            del samples
            diagnostic = {"rawDiarizationTurns": copy.deepcopy(source_diag.get("rawDiarizationTurns", [])),
                "diarizationTurns": base._turn_json(turns), "cleanEmbeddingWindows": windows,
                "mode": "auto", "numClustersPassed": -1, "threshold": .5, "thresholdApplied": True,
                "windowShiftRatio": .1, "threads": args.threads, "modelId": "eres2net_zh",
                "modelSha256": next(spec["sha256"] for spec in diar_specs if spec["path"] == "diar/embedding.onnx"),
                "diarizationInferenceMs": 0., "newDiarizationInference": False, "newAsrInference": False,
                "newEmbeddingInference": bool(windows), "cleanEmbeddingForwardCalls": len(windows),
                "windowEmbeddingStageMs": window_ms, "decodeMs": decode_ms,
                "windowEmbeddingTimingScope": "Extractor load, original-PCM clean-window Compute calls and release only; excludes decode, replayed SD and ASR",
                "sourceDRunSha256": fingerprint["source_D_run"], "sourceDPath": str(args.asr_run.resolve()),
                "sourceDEvidence": source_cases[case["id"]], "sourceDModelFingerprint": source_fingerprint["models"],
                "sourceDRuntime": source_diag["runtime"], "runtime": runtime,
                "sourceMetricsTimingScope": "source-metrics.json retains historical D timings; derived metrics processing_ms/RTF are null",
                "embeddingInputScope": "Original decoded Float32 PCM, predicted clean windows only; no reference text/counts or recognition gain"}
            metrics = derived_metrics(source_record["metrics"])
            for name in ("reference.json", "hypothesis.json"):
                (folder / name).write_bytes((source_folder / name).read_bytes())
            (folder / "source-metrics.json").write_bytes((source_folder / "metrics.json").read_bytes())
            sweep.write_json(folder / "diagnostics.json", diagnostic)
            sweep.write_json(folder / "metrics.json", metrics)
            count = len({turn.speaker for turn in turns})
            reference_count = metrics["speakers"]["reference"]
            record = {"id": case["id"], "split": case["split"], "profile": "auto-0p50", "mode": "auto",
                "model_id": "eres2net_zh", "threshold": .5, "window_shift": .1,
                "audio_sha256": case["audio_sha256"], "reference_sha256": source_record["reference_sha256"],
                "duration_ms": duration_ms, "processing_ms": None, "diarization_inference_ms": 0.,
                "decode_ms": decode_ms, "window_embedding_stage_ms": window_ms,
                "clean_embedding_window_count": len(windows), "native_speaker_count": count,
                "reference_speaker_count": reference_count, "native_speaker_count_error": abs(count - reference_count),
                "metrics": metrics, "new_diarization_inference": False, "new_asr_inference": False,
                "new_embedding_inference": bool(windows), "source_D_run_sha256": fingerprint["source_D_run"],
                "source_metrics_sha256": sweep.digest(folder / "source-metrics.json"),
                "evidence_sha256": sweep.evidence_hashes(folder), "completed_at": datetime.now(timezone.utc).isoformat()}
            sweep.write_json(folder / "case.json", record)
            records.append(record)
            _csv(output, records)
            sweep.write_json(output / "summary.json", {"status": "RUNNING", **_summary(records)})
            print(json.dumps({"case": case["id"], "clean_windows": len(windows),
                "new_sd": False, "new_asr": False, "new_embedding": bool(windows)}, ensure_ascii=False), flush=True)
        meta.update(status="COMPLETE", completed_at=datetime.now(timezone.utc).isoformat(),
            new_embedding_inference=any(record["new_embedding_inference"] for record in records))
        sweep.write_json(output / "run.json", meta)
        sweep.write_json(output / "summary.json", {"status": "COMPLETE", **_summary(records)})
    except BaseException as error:
        meta.update(status="FAILED", error=str(error), failed_at=datetime.now(timezone.utc).isoformat())
        sweep.write_json(output / "run.json", meta)
        _csv(output, records)
        raise
    finally:
        gc.collect()


if __name__ == "__main__":
    main()
