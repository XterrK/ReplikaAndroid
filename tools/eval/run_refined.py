#!/usr/bin/env python3
"""Fresh full C-candidate inference, followed by independent reference scoring.

No saved ASR or feature cache can be supplied. Reference bytes are frozen before
inference for pairing, but parsed/scored only after the actual pipeline returns.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
from hostmem import peak_rss_kib
import sys
import time

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.eval import pipeline_refined as pipeline
from tools.eval import score as scoring
from tools.eval.run import REPO, aggregate, confined, digest, evidence_hashes, validated_hypothesis, write_csv, write_json

DEFAULT_CONFIG = {"schema_version": 1, "id": "C1-resnet34-sd050-tau070-smallguard070-temporal",
    "pipeline": "refined_words_v1", "expected_speakers": -1, "threads": 2,
    "model_id": "wespeaker_resnet34_lm", "window_shift": .1, "native_threshold": .5,
    "refiner_tau": .7, "minimum_reassignment_similarity": .7, "missing_centroid_policy": "temporal"}
OPTION_FIELDS = ("model_id", "window_shift", "native_threshold", "refiner_tau",
                 "minimum_reassignment_similarity", "missing_centroid_policy")
WINDOW_CONFIG = {"schema_version": 1, "id": "C2-eres2net-sd030-average-small-tau036",
    "pipeline": "window_words_v1", "expected_speakers": -1, "threads": 2,
    "model_id": "eres2net_zh", "window_shift": .1, "native_threshold": .3,
    "window_config": copy.deepcopy(pipeline.C2_WINDOW_CONFIG)}
WINDOW_OPTION_FIELDS = ("model_id", "window_shift", "native_threshold", "window_config")


def inference_options(config):
    cpu = {"cpu_plan": config["cpu_plan"]} if "cpu_plan" in config else {}
    if config["pipeline"] == "window_words_v1":
        return {"strategy": "window_v1", **{key: copy.deepcopy(config[key]) for key in WINDOW_OPTION_FIELDS}, **cpu}
    return {**{key: config[key] for key in OPTION_FIELDS}, **cpu}


def validate_configuration(config):
    if not isinstance(config, dict) or config.get("pipeline") not in ("refined_words_v1", "window_words_v1"):
        raise ValueError("Invalid C configuration schema/pipeline/ID")
    required = set(WINDOW_CONFIG if config["pipeline"] == "window_words_v1" else DEFAULT_CONFIG)
    allowed = required | {"notes", "candidate_freeze_sha256", "cpu_plan"}
    if not required <= set(config) or set(config) - allowed:
        raise ValueError("Incomplete/unsupported full C configuration")
    if (type(config["schema_version"]) is not int or config["schema_version"] != 1
            or not isinstance(config["id"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", config["id"])):
        raise ValueError("Invalid C configuration schema/pipeline/ID")
    if "candidate_freeze_sha256" in config and (not isinstance(config["candidate_freeze_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", config["candidate_freeze_sha256"])):
        raise ValueError("Invalid frozen-candidate fingerprint")
    pipeline.validate_options(config["expected_speakers"], config["threads"],
                              **inference_options(config))


def _native_rows(turns):
    return [{"speaker_id": "native_" + str(turn["speakerId"]), "start_ms": turn["startMs"],
             "end_ms": turn["endMs"], "text": ""} for turn in turns]


def run(args):
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Choose a fresh output; no overwrite or cached-ASR resume is supported")
    config = json.loads(args.config.read_text()) if args.config else copy.deepcopy(DEFAULT_CONFIG)
    validate_configuration(config)
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported manifest schema")
    cases = [case for case in manifest["files"] if (args.split == "all" or case["split"] == args.split)
             and (not args.cases or case["id"] in args.cases)]
    if (not cases or len({case["id"] for case in cases}) != len(cases)
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", case["id"]) for case in cases)
            or args.cases and set(args.cases) != {case["id"] for case in cases}):
        raise ValueError("Empty, duplicate, unsafe or unknown selected case IDs")
    frozen = {}
    for case in cases:
        reference = confined(args.manifest.parent, case["reference"])
        reference_bytes = reference.read_bytes()
        reference_hash = hashlib.sha256(reference_bytes).hexdigest()
        audio = confined(args.audio_root, case["audio"])
        if (case.get("reference_sha256", reference_hash) != reference_hash
                or digest(audio) != case["audio_sha256"]):
            raise ValueError("Pinned audio/reference input differs: " + case["id"])
        frozen[case["id"]] = {"reference": reference, "bytes": reference_bytes,
            "reference_sha256": reference_hash, "audio": audio}
    # Validate every file before the first neural call, then pipeline.process
    # repeats its full per-invocation SHA checks inside the measured scope.
    original_models, _ = pipeline.base._verify_models(args.model_root, True)
    external, entry, catalog_hash = pipeline.verify_embedding(args.catalog, args.embedding_root, config["model_id"])
    pipeline.validate_embedding_policy(entry, "window_v1" if config["pipeline"] == "window_words_v1" else "centroid_v1")
    import sherpa_onnx
    from sherpa_onnx.lib import _sherpa_onnx as native
    if sherpa_onnx.__version__ != pipeline.base.RUNTIME_VERSION:
        raise ValueError("Pinned sherpa runtime required")
    dependency_paths = [Path(__file__), Path(pipeline.__file__), Path(scoring.__file__),
        Path(pipeline.base.__file__), Path(pipeline.words.__file__), Path(pipeline.diar_sweep.__file__),
        Path(__file__).with_name("decoder_parity.py"), Path(__file__).with_name("vad_words.py"),
        Path(__file__).with_name("speaker_refiner.py"), Path(__file__).with_name("run.py")]
    if config["pipeline"] == "window_words_v1":
        dependency_paths.append(Path(__file__).with_name("window_overcluster.py"))
    fingerprint = {"manifest_sha256": digest(args.manifest),
        "config_sha256": digest(args.config) if args.config else hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "model_lock_sha256": digest(pipeline.base.MANIFEST),
        "packaged_models": {model["path"]: model["sha256"] for model in original_models},
        "external_embedding": {"id": entry["id"], "sha256": entry["sha256"], "size": entry["size"],
            "dimension": entry["embedding_dimension"], "catalog_sha256": catalog_hash},
        "runtime": {"version": sherpa_onnx.__version__, "git": native.git_sha1, "git_date": native.git_date,
            "onnxruntime": native.onnxruntime_version, "extension_sha256": digest(Path(native.__file__))},
        "code": {str(path.relative_to(REPO)): digest(path) for path in dependency_paths},
        "selected_ids": [case["id"] for case in cases],
        "references": {key: value["reference_sha256"] for key, value in frozen.items()},
        "audio": {case["id"]: case["audio_sha256"] for case in cases}}
    output.mkdir(parents=True)
    meta = {"schema_version": 1, "status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": fingerprint, "config": config,
        "paired_asr_policy": pipeline.paired_asr_policy(config["threads"], config.get("cpu_plan", "v16")),
        "platform": platform.platform(), "scope": "Actual full host candidate inference. No ASR replay, no reference text or K enters process. Not Android/ARM/phone acceptance.",
        "inference_requested": False, "new_model_inference": False}
    write_json(output / "run.json", meta)
    write_json(output / "config.json", config)
    write_json(output / "manifest.json", manifest)
    records = []
    summary = None

    def unchanged_code_and_policy():
        if (digest(args.catalog) != catalog_hash or digest(pipeline.base.MANIFEST) != fingerprint["model_lock_sha256"]
                or any(digest(path) != fingerprint["code"][str(path.relative_to(REPO))] for path in dependency_paths)
                or args.config and digest(args.config) != fingerprint["config_sha256"]):
            raise ValueError("Frozen model catalog/config/code changed during full inference")

    try:
        for case in cases:
            unchanged_code_and_policy()
            case_input = frozen[case["id"]]
            if (digest(case_input["audio"]) != case["audio_sha256"]
                    or digest(case_input["reference"]) != case_input["reference_sha256"]):
                raise ValueError("Input changed after preflight: " + case["id"])
            folder = output / case["id"]
            folder.mkdir()
            began = time.perf_counter()
            meta["inference_requested"] = True
            if meta["new_model_inference"] is not True:
                meta["new_model_inference"] = None  # An interrupted call may have run only some stages.
            write_json(output / "run.json", meta)
            pipeline_returned = False
            try:
                # Only audio/model paths and global config cross the inference API.
                actual = pipeline.process(case_input["audio"], args.model_root,
                    expected_speakers=config["expected_speakers"], threads=config["threads"],
                    catalog_path=args.catalog, embedding_root=args.embedding_root,
                    **inference_options(config))
                pipeline_returned = True
                duration, processing_ms = actual["duration_ms"], actual["processing_ms"]
                if duration != case["duration_ms"] or type(processing_ms) not in (int, float) or not math.isfinite(processing_ms) or processing_ms < 0:
                    raise ValueError("Actual duration/timing differs from valid input contract")
                hypothesis = validated_hypothesis(actual["transcript"])
                (folder / "reference.json").write_bytes(case_input["bytes"])
                write_json(folder / "hypothesis.json", hypothesis)
                write_json(folder / "diagnostics.json", actual["diagnostics"])
                unchanged_code_and_policy()
                diagnostic = actual["diagnostics"]
                if config.get("cpu_plan") == "auto_v1":
                    expected_asr = pipeline.paired_asr_policy(config["threads"], "auto_v1")
                    cpu = diagnostic.get("cpuExecutionPolicy", {})
                    fields = ("asrThreads", "diarizationThreads", "refinementThreads")
                    if (cpu.get("plan") != "auto_v1" or cpu.get("vadThreads") != 1
                            or any(type(cpu.get(key)) is not int or cpu[key] != config["threads"] for key in fields)
                            or diagnostic.get("pairedAsrPolicy") != expected_asr
                            or diagnostic.get("config", {}).get("asr") != expected_asr
                            or type(diagnostic.get("config", {}).get("threads")) is not int
                            or diagnostic["config"]["threads"] != config["threads"]):
                        raise ValueError("Actual native CPU execution policy differs from the explicit host experiment")
                if (diagnostic.get("asrReplay") is not False or diagnostic.get("newDiarizationInference") is not True
                        or diagnostic.get("pipelineVariant") != config["pipeline"]
                        or diagnostic.get("externalEmbedding", {}).get("sha256") != entry["sha256"]
                        or diagnostic["externalEmbedding"].get("catalogSha256") != catalog_hash
                        or {item["path"]: item["sha256"] for item in diagnostic["modelFiles"]} != fingerprint["packaged_models"]):
                    raise ValueError("Actual output is not the pinned full C inference policy")
                if config["pipeline"] == "window_words_v1":
                    if (diagnostic.get("refinementStrategy") != "window_v1"
                            or diagnostic.get("windowConfig") != config["window_config"]
                            or diagnostic.get("refiner", {}).get("algorithm") != "window-overcluster-v1"
                            or diagnostic["refiner"].get("config") != config["window_config"]
                            or diagnostic.get("selectedNativePolicy") != {"model_id": config["model_id"],
                                "threshold": config["native_threshold"], "window_shift": config["window_shift"],
                                "threads": config["threads"], "num_clusters": -1}):
                        raise ValueError("Actual output is not the frozen full C2 window policy")
                meta["new_model_inference"] = True
                if (digest(case_input["audio"]) != case["audio_sha256"]
                        or digest(case_input["reference"]) != case_input["reference_sha256"]):
                    raise ValueError("Input changed during actual inference; outputs preserved unscored")
                reference = json.loads(case_input["bytes"])
                metric = scoring.score(reference, hypothesis, duration, processing_ms)
                final = _native_rows(actual["diagnostics"]["diarizationTurns"])
                initial = _native_rows(actual["diagnostics"]["nativeDiarizationTurns"])
                for collar in (0, 250):
                    metric[f"native_der_collar_{collar}ms"] = scoring.der(reference["transcript"], final, duration, collar)
                    metric[f"unrefined_native_der_collar_{collar}ms"] = scoring.der(reference["transcript"], initial, duration, collar)
                metric["native_speaker_count"] = len({turn["speaker_id"] for turn in final})
                metric["unrefined_native_speaker_count"] = len({turn["speaker_id"] for turn in initial})
                metric["native_speaker_count_error"] = abs(metric["native_speaker_count"] - metric["speakers"]["reference"])
                metric["corpus_scope"] = {"kind": case.get("kind", "unspecified"),
                    "diarization_reference": "Author clip-placement proxy; not natural-dialogue activity or independent word gold"}
                write_json(folder / "metrics.json", metric)
                record = {"id": case["id"], "split": case["split"], "kind": case.get("kind", "unspecified"),
                    "audio_sha256": case["audio_sha256"], "reference_sha256": case_input["reference_sha256"],
                    "duration_ms": duration, "processing_ms": processing_ms,
                    "runner_wall_ms": round((time.perf_counter() - began) * 1000), "metrics": metric,
                    "new_model_inference": True, "new_diarization_inference": actual["diagnostics"]["newDiarizationInference"],
                    "new_embedding_inference": actual["diagnostics"]["newEmbeddingInference"],
                    "new_asr_inference": actual["diagnostics"]["newAsrInference"], "asr_replay": False,
                    "evidence_sha256": evidence_hashes(folder), "completed_at": datetime.now(timezone.utc).isoformat()}
                write_json(folder / "case.json", record)
                records.append(record)
            except BaseException as error:
                write_json(folder / "failure.json", {"at": datetime.now(timezone.utc).isoformat(),
                    "type": type(error).__name__, "message": str(error), "pipeline_returned": pipeline_returned,
                    "inference_attempted": True, "scoring_completed": False})
                raise
            write_csv(output / "results.csv", records, config["id"])
            summary = {"status": "RUNNING", "expected_cases": len(cases), "all": aggregate(records),
                "by_split": {split: aggregate([record for record in records if record["split"] == split])
                             for split in sorted({record["split"] for record in records})}}
            write_json(output / "summary.json", summary)
            print(json.dumps({"case": case["id"], "split": case["split"], "raw_wer": metric["wer_raw"]["rate"],
                "native_speakers": metric["native_speaker_count"], "native_der0": metric["native_der_collar_0ms"]["rate"]}), flush=True)
        meta.update(status="COMPLETE", completed_at=datetime.now(timezone.utc).isoformat(),
            host_process_peak_rss_kib_cumulative=peak_rss_kib(),
            memory_scope="Whole host process cumulative RSS high-water; not per-file continuous PSS/phone memory")
        summary["status"] = "COMPLETE"
        write_json(output / "summary.json", summary)
        write_json(output / "run.json", meta)
        return summary
    except BaseException as error:
        meta.update(status="FAILED", error=str(error), failed_at=datetime.now(timezone.utc).isoformat())
        write_json(output / "run.json", meta)
        write_csv(output / "results.csv", records, config["id"])
        if summary:
            summary["status"] = "FAILED"
            write_json(output / "summary.json", summary)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO / "benchmark/eval/manifest.json")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=REPO / "model-pack")
    parser.add_argument("--catalog", type=Path, default=REPO / "configs/eval/diar-models.json")
    parser.add_argument("--embedding-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="Explicit global C configuration; default is the provisional frozen C1 policy")
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="all")
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args(argv))


if __name__ == "__main__":
    main()
