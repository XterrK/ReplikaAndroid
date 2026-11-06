#!/usr/bin/env python3
"""Run local baseline inference, then score independent references; preserve every output.

The recognizer receives audio/model paths and explicit configuration only. Gold speaker counts
and texts never enter inference. Audio remains outside Git; references/configs/results are saved.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import resource
import sys
import time

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def confined(root, relative):
    root = Path(root).resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Manifest path escapes its root: " + str(relative))
    return target


def validate_configuration(config):
    allowed = {"schema_version", "id", "pipeline", "expected_speakers", "threads", "notes"}
    if config.get("pipeline") == "vad_words_v1":
        allowed |= {"punctuation_mode", "energy_split", "vad_min_speech_sec", "vad_min_silence_sec", "vad_threshold", "pre_roll_ms"}
    if set(config) - allowed:
        raise ValueError("Unsupported configuration options: " + str(sorted(set(config) - allowed)))
    if config.get("schema_version") != 1 or config.get("pipeline") not in {"v16", "vad_words_v1"}:
        raise ValueError("Unsupported evaluation pipeline")
    if config["pipeline"] == "vad_words_v1":
        if config.get("punctuation_mode") not in {"none", "seam"} or type(config.get("energy_split")) is not bool:
            raise ValueError("Word pipeline needs explicit punctuation_mode and energy_split")
        for field in ("vad_min_speech_sec", "vad_min_silence_sec"):
            value = config.get(field, .25)
            if type(value) not in (int, float) or not math.isfinite(value) or not .05 <= value <= 1:
                raise ValueError(field + " must be finite and within 0.05..1 seconds")
        threshold = config.get("vad_threshold", .5)
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or not .1 <= threshold <= .9:
            raise ValueError("vad_threshold must be finite and within 0.1..0.9")
        pre_roll = config.get("pre_roll_ms", 100)
        if type(pre_roll) is not int or not 0 <= pre_roll <= 1000:
            raise ValueError("pre_roll_ms must be an integer within 0..1000")
    if type(config.get("threads")) is not int or config["threads"] not in (1, 2, 4):
        raise ValueError("threads must match MlPolicy: 1, 2 or 4")
    count = config.get("expected_speakers")
    if type(count) is not int or not (count == -1 or 1 <= count <= 20):
        raise ValueError("expected_speakers must be -1 (automatic), 1, or 2..20")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", config.get("id", "")):
        raise ValueError("Configuration id must be a safe filename")


def validated_hypothesis(transcript):
    for row in transcript:
        if set(row) != {"speaker_id", "start_ms", "end_ms", "text"}:
            raise ValueError("Pipeline produced fields outside the jury contract")
        if not re.fullmatch(r"speaker_[1-9][0-9]*", row["speaker_id"]):
            raise ValueError("Pipeline produced an invalid speaker ID")
        if not isinstance(row["text"], str) or not row["text"].strip():
            raise ValueError("Pipeline produced blank text")
        if type(row["start_ms"]) is not int or type(row["end_ms"]) is not int:
            raise ValueError("Timestamps must be integer milliseconds")
        if row["start_ms"] < 0 or row["end_ms"] < row["start_ms"]:
            raise ValueError("Invalid timestamp interval")
    if [r["start_ms"] for r in transcript] != sorted(r["start_ms"] for r in transcript):
        raise ValueError("Pipeline output is not chronological")
    return {"transcript": transcript}


def evidence_hashes(case_dir):
    return {name: digest(case_dir / name) for name in
            ("reference.json", "hypothesis.json", "diagnostics.json", "metrics.json")}


def archive_incomplete(case_dir):
    if not case_dir.exists():
        return
    archive_root = case_dir.parent / "attempts"
    archive_root.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    case_dir.rename(archive_root / (case_dir.name + "-" + stamp))


def aggregate(records):
    output = {"cases": len(records)}
    for field in ("wer_raw", "wer_punctuation_tokens", "wer_normalized", "cer_normalized",
                  "cpwer_raw", "cpwer_normalized"):
        values = [r["metrics"][field] for r in records]
        counts = {key: sum(v.get(key, 0) for v in values)
                  for key in ("errors", "substitutions", "deletions", "insertions", "reference_tokens", "hypothesis_tokens")}
        counts["rate"] = counts["errors"] / counts["reference_tokens"] if counts["reference_tokens"] else None
        output[field] = counts
    for field in ("der_collar_0ms", "der_collar_250ms", "native_der_collar_0ms", "native_der_collar_250ms"):
        values = [r["metrics"][field] for r in records]
        counts = {key: sum(v.get(key, 0) for v in values)
                  for key in ("miss_ms", "false_alarm_ms", "confusion_ms", "reference_speaker_ms")}
        counts["rate"] = (counts["miss_ms"] + counts["false_alarm_ms"] + counts["confusion_ms"]) / counts["reference_speaker_ms"] if counts["reference_speaker_ms"] else None
        output[field] = counts
    output["speaker_count_exact_cases"] = sum(r["metrics"]["speakers"]["absolute_error"] == 0 for r in records)
    output["native_speaker_count_exact_cases"] = sum(r["metrics"]["native_speaker_count_error"] == 0 for r in records)
    output["audio_ms"] = sum(r["duration_ms"] for r in records)
    output["processing_ms"] = sum(r["processing_ms"] for r in records)
    output["rtf"] = output["processing_ms"] / output["audio_ms"] if output["audio_ms"] else None
    return output


def write_csv(path, records, config_id):
    fields = ["config", "id", "split", "kind", "status", "audio_ms", "processing_ms", "rtf",
              "wer_raw", "S", "D", "I", "reference_words", "wer_normalized", "wer_punctuation_tokens",
              "cpwer_raw", "der_collar_0ms", "der_collar_250ms", "native_der_collar_0ms", "native_der_collar_250ms",
              "speaker_count_error", "native_speaker_count", "native_speaker_count_error", "new_model_inference", "error"]
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            if record.get("status") == "FAILED":
                writer.writerow({"config": config_id, "id": record["id"], "split": record["split"],
                                 "kind": record["kind"], "status": "FAILED", "error": record["error"]})
                continue
            metric = record["metrics"]
            writer.writerow({"config": config_id, "id": record["id"], "split": record["split"], "kind": record["kind"],
                "status": "COMPLETE", "audio_ms": record["duration_ms"], "processing_ms": record["processing_ms"],
                "rtf": metric["rtf"], "wer_raw": metric["wer_raw"]["rate"],
                "S": metric["wer_raw"]["substitutions"], "D": metric["wer_raw"]["deletions"], "I": metric["wer_raw"]["insertions"],
                "reference_words": metric["wer_raw"]["reference_tokens"], "wer_normalized": metric["wer_normalized"]["rate"],
                "wer_punctuation_tokens": metric["wer_punctuation_tokens"]["rate"], "cpwer_raw": metric["cpwer_raw"]["rate"],
                "der_collar_0ms": metric["der_collar_0ms"]["rate"], "der_collar_250ms": metric["der_collar_250ms"]["rate"],
                "native_der_collar_0ms": metric["native_der_collar_0ms"]["rate"], "native_der_collar_250ms": metric["native_der_collar_250ms"]["rate"],
                "native_speaker_count": metric["native_speaker_count"], "native_speaker_count_error": metric["native_speaker_count_error"],
                "speaker_count_error": metric["speakers"]["absolute_error"], "new_model_inference": True})
    temporary.replace(path)


def run(args):
    # Imports are delayed so contract/manifest helpers can be tested without native ML libraries.
    import pipeline as baseline_pipeline
    import score as scoring
    import sherpa_onnx

    if sherpa_onnx.__version__ != "2.0.1":
        raise ValueError("Baseline requires sherpa-onnx==2.0.1, matching production")

    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_configuration(config)
    selected_pipeline = baseline_pipeline
    options = {}
    if config["pipeline"] == "vad_words_v1":
        import pipeline_words as selected_pipeline
        options = {"punctuation_mode": config["punctuation_mode"], "energy_split": config["energy_split"]}
        options.update({key: config[key] for key in ("vad_min_speech_sec", "vad_min_silence_sec", "vad_threshold", "pre_roll_ms") if key in config})
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported corpus manifest schema")
    cases = [c for c in manifest["files"] if (args.split == "all" or c["split"] == args.split)
             and (not args.cases or c["id"] in args.cases)]
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Empty selection or duplicate case IDs")
    if args.cases and set(args.cases) != {c["id"] for c in cases}:
        raise ValueError("Requested cases not found in selected split")
    frozen_references = {}
    for case in cases:
        reference_path = confined(args.manifest.parent, case["reference"])
        reference_bytes = reference_path.read_bytes()
        reference_hash = hashlib.sha256(reference_bytes).hexdigest()
        if case.get("reference_sha256", reference_hash) != reference_hash:
            raise ValueError("Pinned reference hash mismatch: " + case["id"])
        frozen_references[case["id"]] = {"path": reference_path, "sha256": reference_hash,
                                         "value": json.loads(reference_bytes)}
    lock_path = REPO / "app/src/main/assets/models-lock.json"
    model_files = {}
    for spec in json.loads(lock_path.read_text())["files"]:
        model_file = confined(args.model_root, spec["path"])
        if model_file.stat().st_size != spec["size"] or digest(model_file) != spec["sha256"]:
            raise ValueError("Pinned model mismatch: " + spec["path"])
        model_files[spec["path"]] = spec["sha256"]
    fingerprint = {"config_sha256": digest(args.config), "manifest_sha256": digest(args.manifest),
                   "model_lock_sha256": digest(lock_path), "models": model_files,
                   "runtime": sherpa_onnx.__version__, "pipeline_code_sha256": digest(selected_pipeline.__file__),
                   "baseline_helpers_sha256": digest(baseline_pipeline.__file__),
                   "decoder_code_sha256": digest(Path(baseline_pipeline.__file__).with_name("decoder_parity.py")),
                   "requirements_lock_sha256": digest(Path(__file__).with_name("requirements.lock.txt")),
                   "scorer_code_sha256": digest(scoring.__file__), "runner_code_sha256": digest(__file__),
                   "references": {key: value["sha256"] for key, value in frozen_references.items()},
                   "selected_ids": [c["id"] for c in cases]}
    if config["pipeline"] == "vad_words_v1":
        fingerprint["word_planner_code_sha256"] = digest(Path(__file__).with_name("vad_words.py"))
    output = args.output.resolve()
    if output.exists():
        if not args.resume or not (output / "run.json").is_file():
            raise ValueError("Output exists; choose a fresh path or explicit --resume for this run")
        old = json.loads((output / "run.json").read_text())
        if old["fingerprint"] != fingerprint:
            raise ValueError("Resume config/manifest/selection mismatch; preserve old evidence")
        meta = old
    else:
        output.mkdir(parents=True)
        meta = {"schema_version": 1, "status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
                "fingerprint": fingerprint, "config": config, "host": {"platform": platform.platform(),
                "python": sys.version, "machine": platform.machine(), "logical_cpus": os.cpu_count()},
                "scope": "Host CPU baseline; not Android/ARM/phone performance. Reference texts/counts never enter inference."}
        write_json(output / "config.json", config)
        write_json(output / "manifest.json", manifest)
    write_json(output / "run.json", meta)
    records = []
    for case in cases:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", case["id"]):
            raise ValueError("Unsafe case ID")
        case_dir = output / case["id"]
        audio = confined(args.audio_root, case["audio"])
        frozen_reference = frozen_references[case["id"]]
        reference_path = frozen_reference["path"]
        audio_hash = digest(audio)
        if audio_hash != case["audio_sha256"]:
            raise ValueError("Audio hash mismatch: " + case["id"])
        reference_hash = frozen_reference["sha256"]
        if digest(reference_path) != reference_hash:
            raise ValueError("Reference changed after run initialization: " + case["id"])
        if args.resume and (case_dir / "case.json").is_file():
            record = json.loads((case_dir / "case.json").read_text())
            if record["audio_sha256"] != audio_hash or record["reference_sha256"] != reference_hash:
                raise ValueError("Completed case input changed; cannot resume: " + case["id"])
            if record.get("evidence_sha256") != evidence_hashes(case_dir):
                raise ValueError("Saved evidence changed; cannot silently resume: " + case["id"])
            records.append(record)
        else:
            if case_dir.exists():
                archive_incomplete(case_dir)
            case_dir.mkdir(exist_ok=True)
            start = time.perf_counter()
            try:
                # Deliberately use CONFIG, never case.expected_speakers or reference labels.
                actual = selected_pipeline.process(audio, args.model_root, expected_speakers=config["expected_speakers"], threads=config["threads"], **options)
                hypothesis = validated_hypothesis(actual["transcript"])
                if digest(audio) != audio_hash:
                    raise ValueError("Inference modified original audio: " + case["id"])
                if digest(reference_path) != reference_hash:
                    raise ValueError("Reference changed during inference: " + case["id"])
                reference = frozen_reference["value"]
                write_json(case_dir / "reference.json", reference)
                write_json(case_dir / "hypothesis.json", hypothesis)
                write_json(case_dir / "diagnostics.json", actual["diagnostics"])
                metric = scoring.score(reference, hypothesis, duration_ms=actual["duration_ms"], processing_ms=actual["processing_ms"])
                native_turns = [{"speaker_id": "native_" + str(t["speakerId"]), "start_ms": t["startMs"],
                                 "end_ms": t["endMs"], "text": ""} for t in actual["diagnostics"]["diarizationTurns"]]
                metric["native_der_collar_0ms"] = scoring.der(reference["transcript"], native_turns, actual["duration_ms"], collar_ms=0)
                metric["native_der_collar_250ms"] = scoring.der(reference["transcript"], native_turns, actual["duration_ms"], collar_ms=250)
                metric["native_speaker_count"] = len({t["speaker_id"] for t in native_turns})
                metric["native_speaker_count_error"] = abs(metric["native_speaker_count"] - metric["speakers"]["reference"])
                metric["corpus_scope"] = {"kind": case.get("kind", "unspecified"),
                    "diarization_reference": "Author utterance/clip intervals; montage proxy, not independent natural-dialogue voice-activity DER"}
                write_json(case_dir / "metrics.json", metric)
                record = {"id": case["id"], "split": case["split"], "kind": case.get("kind", "unspecified"),
                    "audio_sha256": audio_hash, "reference_sha256": reference_hash,
                    "duration_ms": actual["duration_ms"], "processing_ms": actual["processing_ms"],
                    "runner_wall_ms": round((time.perf_counter()-start)*1000), "metrics": metric,
                    "evidence_sha256": evidence_hashes(case_dir),
                    "new_model_inference": True, "completed_at": datetime.now(timezone.utc).isoformat()}
                write_json(case_dir / "case.json", record)
                records.append(record)
            except BaseException as error:
                write_json(case_dir / "failure.json", {"at": datetime.now(timezone.utc).isoformat(),
                    "type": type(error).__name__, "message": str(error), "completed": False})
                meta["status"] = "FAILED"
                write_json(output / "run.json", meta)
                write_csv(output / "results.csv", records + [{"id": case["id"], "split": case["split"],
                    "kind": case.get("kind", "unspecified"), "status": "FAILED", "error": str(error)}], config["id"])
                raise
        write_csv(output / "results.csv", records, config["id"])
        summary = {"status": "RUNNING", "all": aggregate(records),
                   "by_split": {split: aggregate([r for r in records if r["split"] == split])
                                for split in sorted({r["split"] for r in records})}}
        write_json(output / "summary.json", summary)
        print(json.dumps({"case": case["id"], "split": case["split"], "wer_raw": records[-1]["metrics"]["wer_raw"]["rate"],
                          "rtf": records[-1]["metrics"]["rtf"]}, ensure_ascii=False), flush=True)
    meta.update(status="COMPLETE", completed_at=datetime.now(timezone.utc).isoformat(),
                host_process_peak_rss_kib_cumulative=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                memory_scope="Linux process high-water RSS for the whole run; not per-file PSS or phone memory")
    write_json(output / "run.json", meta)
    summary["status"] = "COMPLETE"
    write_json(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO / "benchmark/eval/manifest.json")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=REPO / "model-pack")
    parser.add_argument("--config", type=Path, default=REPO / "configs/eval/baseline-v16.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
