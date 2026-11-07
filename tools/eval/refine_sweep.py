#!/usr/bin/env python3
"""Score speaker refinement from hashed saved C embeddings and saved D words.

No audio is opened and no neural model is constructed. References enter scoring
only, after refinement. A RUNNING source may provide a strict subset of completed
cases; pending/failed cases and coverage remain explicit and cannot imply a gate.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import traceback

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.eval import pipeline as base
from tools.eval import score as scoring
from tools.eval.diar_sweep import load_asr, project_asr, summarize
from tools.eval.run import confined, digest, evidence_hashes, write_json
from tools.eval.speaker_refiner import EmbeddingWindow, RefineConfig, refine


DEFAULT_THRESHOLDS = tuple(value / 100 for value in range(30, 96, 5))
TIMING_SCOPE = "Saved neural outputs; refiner-only wall time. No whole-pipeline or Android RTF."


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _safe(value, label):
    if not isinstance(value, str) or value in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError(label + " must be a safe path component")
    return value


def _thresholds(values):
    values = [float(item) for item in values.split(",")] if isinstance(values, str) else list(values)
    if not values or any(type(v) not in (int, float) or not math.isfinite(v) or not -1 < v < 1 for v in values):
        raise ValueError("Thresholds must be finite numbers strictly between -1 and 1")
    if len(set(values)) != len(values) or len({_tau_id(v) for v in values}) != len(values):
        raise ValueError("Duplicate/indistinguishable thresholds")
    return values


def _tau_id(value):
    return "tau-" + format(value, ".12g").replace("-", "m").replace(".", "p")


def _turns(items, duration):
    if not isinstance(items, list):
        raise ValueError("diarizationTurns must be an array")
    turns = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"startMs", "endMs", "speakerId"}:
            raise ValueError("Invalid saved native turn")
        start, end, speaker = (item[k] for k in ("startMs", "endMs", "speakerId"))
        if any(type(v) is not int for v in (start, end, speaker)) or not 0 <= start < end <= duration or speaker < 0:
            raise ValueError("Invalid saved native turn bounds/label")
        turns.append(base.Turn(start, end, speaker))
    return turns


def _windows(items):
    if not isinstance(items, list):
        raise ValueError("Missing real cleanEmbeddingWindows array; no embeddings will be fabricated")
    result = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"start_ms", "end_ms", "speaker", "embedding", "clean"}:
            raise ValueError("Invalid saved clean embedding window shape")
        if not isinstance(item["embedding"], list):
            raise ValueError("Saved embedding must be an array")
        result.append(EmbeddingWindow(item["start_ms"], item["end_ms"], item["speaker"],
                                      tuple(item["embedding"]), item["clean"]))
    return result


def _checked_record(folder, case, reference_hash, *, profile=None):
    record = read_json(folder / "case.json")
    for key in ("id", "split", "duration_ms", "audio_sha256"):
        if record.get(key) != case[key]:
            raise ValueError("Saved input mismatch: " + key)
    if record.get("reference_sha256") != reference_hash:
        raise ValueError("Saved independent reference hash mismatch")
    if profile is not None and record.get("profile") != profile:
        raise ValueError("Saved source profile mismatch")
    hashes = evidence_hashes(folder)
    if record.get("evidence_sha256") != hashes:
        raise ValueError("Saved evidence hashes changed")
    if hashes["reference.json"] != reference_hash:
        raise ValueError("Saved reference bytes differ from independent reference")
    if record.get("metrics") != read_json(folder / "metrics.json"):
        raise ValueError("Saved case/metrics objects differ")
    return record, {"case.json": digest(folder / "case.json"), **hashes}


def _source_format(meta, asr_hash):
    fingerprint = meta.get("fingerprint", {})
    if not isinstance(fingerprint, dict):
        raise ValueError("Unknown C source provenance format")
    names = {name for name in ("asr_run", "source_D_run") if name in fingerprint}
    if names == {"asr_run"}:
        kind, value = "diar_sweep_v1", fingerprint["asr_run"]
    elif names == {"source_D_run"}:
        kind, value = "collect_diar_windows_v1", fingerprint["source_D_run"]
    else:
        raise ValueError("Unknown or ambiguous C source provenance format")
    if value != asr_hash:
        raise ValueError("C source ASR run fingerprint differs from supplied saved D run")
    return kind


def _check_asr_link(kind, meta, diagnostic, diar_record, asr_record, asr_hashes, asr_run_hash, case_id, folder):
    if kind == "diar_sweep_v1":
        if "sourceDRunSha256" in diagnostic or "sourceDEvidence" in diagnostic:
            raise ValueError("Mixed C source provenance formats in diagnostic")
        if diagnostic.get("asrEvidenceSha256") != asr_record["evidence_sha256"]:
            raise ValueError("C source ASR evidence hashes differ from supplied saved D case")
    elif kind == "collect_diar_windows_v1":
        if "asrEvidenceSha256" in diagnostic:
            raise ValueError("Mixed C source provenance formats in diagnostic")
        expected = {"case_sha256": asr_hashes["case.json"], "evidence_sha256": asr_record["evidence_sha256"]}
        if (diagnostic.get("sourceDRunSha256") != asr_run_hash
                or diar_record.get("source_D_run_sha256") != asr_run_hash
                or diagnostic.get("sourceDEvidence") != expected
                or meta["fingerprint"].get("source_cases", {}).get(case_id) != expected):
            raise ValueError("Collector C source D run/case evidence hashes differ")
        # The collector keeps original D metrics separately from its timing-null
        # derived metrics. Check that additional source artifact as well.
        if (diar_record.get("source_metrics_sha256") != asr_hashes["metrics.json"]
                or digest(folder / "source-metrics.json") != asr_hashes["metrics.json"]):
            raise ValueError("Collector original D source metrics hash differs")
    else:
        raise ValueError("Unknown C source provenance format")


def _score_turns(turns, reference, chunks, backend, duration, expected_raw):
    hypothesis = project_asr(chunks, turns, backend)
    metrics = scoring.score(reference, hypothesis, duration)
    if metrics["wer_raw"] != expected_raw:
        raise ValueError("Raw WER invariant violated: ASR text/order changed during speaker projection")
    native = [{"speaker_id": "native_" + str(t.speaker), "start_ms": t.start_ms,
               "end_ms": t.end_ms, "text": ""} for t in turns]
    metrics["native_der_collar_0ms"] = scoring.der(reference["transcript"], native, duration)
    metrics["native_der_collar_250ms"] = scoring.der(reference["transcript"], native, duration, 250)
    metrics["native_speaker_count"] = len({t.speaker for t in turns})
    return hypothesis, metrics


def _summarize(records, expected):
    result = summarize(records)
    # Common diar summary assumes actual inference. Never mislabel a replay as
    # zero-latency inference or whole-app RTF.
    result.pop("rtf_diarization_stage", None)
    result.pop("diarization_inference_ms", None)
    result.update(expected_cases=expected, complete_case_coverage=len(records) == expected,
                  new_diarization_inference=False, new_asr_inference=False,
                  refiner_only_ms=sum(r["refiner_only_ms"] for r in records), timing_scope=TIMING_SCOPE,
                  refiner_accepted_cases=sum(r["refiner_accepted"] is True for r in records),
                  refiner_unsupported_cases=sum(r["refiner_accepted"] is False for r in records),
                  raw_wer_invariant=all(r["raw_wer_invariant"] for r in records))
    return result


def _csv(path, records, failures):
    columns = ["profile", "id", "stage", "threshold", "status", "error", "native_speaker_count",
               "reference_speaker_count", "native_speaker_count_error", "native_der_0", "native_der_250",
               "cpwer_raw", "wer_raw", "raw_wer_invariant", "refiner_accepted", "refiner_only_ms",
               "duration_ms", "new_diarization_inference", "new_asr_inference"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            row = {key: record[key] for key in columns if key in record}
            row.update(status="SCORED", native_der_0=record["metrics"]["native_der_collar_0ms"]["rate"],
                       native_der_250=record["metrics"]["native_der_collar_250ms"]["rate"],
                       cpwer_raw=record["metrics"]["cpwer_raw"]["rate"], wer_raw=record["metrics"]["wer_raw"]["rate"])
            writer.writerow(row)
        for failure in failures:
            writer.writerow({key: failure[key] for key in columns if key in failure})


def score_saved(diar_run, asr_run, manifest, *, profile, thresholds=DEFAULT_THRESHOLDS,
                split="dev", missing_policy="retain", small_min_sim=None,
                output=None, stages=("baseline", "refined"), cases=None):
    """Return summaries/records; optionally persist a fresh, complete audit tree.

    RUNNING diar sources score only completed cases; absent case.json entries are
    pending. COMPLETE sources must provide every selected case. Invalid completed
    evidence is a failure, never silently skipped. No gold K/text enters refine.
    """
    diar_run, asr_run, manifest = map(Path, (diar_run, asr_run, manifest))
    profile = _safe(profile, "profile")
    values = _thresholds(thresholds)
    if split not in ("dev", "holdout", "all"):
        raise ValueError("split must be dev, holdout or all")
    stages = tuple(stages)
    if not stages or len(set(stages)) != len(stages) or set(stages) - {"baseline", "refined"}:
        raise ValueError("stages must select baseline and/or refined")
    config = RefineConfig(small_missing_centroid_policy=missing_policy,
                          minimum_reassignment_similarity=small_min_sim)
    # Validate explicit options before opening any saved run/reference.
    refine([], [], 0, config)
    started = datetime.now(timezone.utc).isoformat()
    settings = {"schema_version": 1, "profile": profile, "thresholds": values, "split": split,
                "stages": list(stages), "refiner_config": asdict(config), "cases": list(cases) if cases else None}
    out = Path(output).resolve() if output is not None else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=False)
        write_json(out / "config.json", settings)
        write_json(out / "run.json", {"status": "RUNNING", "started_at": started, "config": settings})
    records, failures, pending, source_cases = [], [], [], {}
    fingerprint = {"runner": digest(__file__),
                   "refiner": digest(Path(__file__).with_name("speaker_refiner.py")),
                   "diar_helpers": digest(Path(__file__).with_name("diar_sweep.py")),
                   "word_helpers": digest(Path(__file__).with_name("vad_words.py")),
                   "scorer": digest(Path(scoring.__file__)), "baseline_helpers": digest(Path(base.__file__))}
    fatal = None
    selected = []
    try:
        fingerprint["manifest"] = digest(manifest)
        diar_meta, asr_meta = read_json(diar_run / "run.json"), read_json(asr_run / "run.json")
        if diar_meta.get("status") not in ("COMPLETE", "RUNNING"):
            raise ValueError("Diarization source must be COMPLETE or RUNNING")
        asr_config = asr_meta.get("config", {})
        if asr_meta.get("status") != "COMPLETE" or asr_config.get("pipeline") != "vad_words_v1" or asr_config.get("punctuation_mode") != "none":
            raise ValueError("ASR source must be completed actual D words with punctuation_mode=none")
        if profile == "fixed" or diar_meta.get("options", {}).get("mode") == "fixed":
            raise ValueError("Known-K research oracle is not a deployment refiner input")
        fingerprint.update(diar_run=digest(diar_run / "run.json"), asr_run=digest(asr_run / "run.json"),
                           diar_source_status=diar_meta["status"])
        source_format = _source_format(diar_meta, fingerprint["asr_run"])
        fingerprint["source_format"] = source_format
        corpus = read_json(manifest)
        selected = [c for c in corpus["files"] if (split == "all" or c["split"] == split)
                    and (cases is None or c["id"] in cases)]
        if not selected or len({c["id"] for c in selected}) != len(selected):
            raise ValueError("Empty or duplicate selected corpus cases")
        if cases is not None and set(cases) != {c["id"] for c in selected}:
            raise ValueError("Unknown/out-of-split selected case")
        for case in selected:
            case_id = _safe(case["id"], "case id")
            folder = confined(diar_run / profile, case_id)
            if not (folder / "case.json").is_file() and diar_meta["status"] == "RUNNING":
                pending.append(case_id)
                continue
            try:
                reference_file = confined(manifest.parent, case["reference"])
                reference_hash = digest(reference_file)
                if case.get("reference_sha256", reference_hash) != reference_hash:
                    raise ValueError("Independent reference pin mismatch")
                diar_record, diar_hashes = _checked_record(folder, case, reference_hash, profile=profile)
                if diar_record.get("mode") == "fixed":
                    raise ValueError("Known-K research oracle is not a deployment refiner input")
                asr_folder = confined(asr_run, case_id)
                asr_record, asr_hashes = _checked_record(asr_folder, case, reference_hash)
                chunks, replay_record, backend = load_asr(asr_folder, case, reference_hash)
                if replay_record != asr_record:
                    raise ValueError("ASR case changed while loading")
                diagnostic = read_json(folder / "diagnostics.json")
                _check_asr_link(source_format, diar_meta, diagnostic, diar_record, asr_record,
                                asr_hashes, fingerprint["asr_run"], case_id, folder)
                duration = case["duration_ms"]
                turns = _turns(diagnostic.get("diarizationTurns"), duration)
                windows = _windows(diagnostic.get("cleanEmbeddingWindows")) if "refined" in stages else []
                source_hashes = {"diar": diar_hashes, "asr": asr_hashes,
                                 "reference": reference_hash, "original_audio": case["audio_sha256"]}
                source_cases[case_id] = source_hashes
                reference = read_json(reference_file)
                jobs = [("baseline", None)] if "baseline" in stages else []
                if "refined" in stages:
                    jobs.extend(("refined", threshold) for threshold in values)
                for stage, threshold in jobs:
                    variant = "baseline" if stage == "baseline" else _tau_id(threshold)
                    case_output = out / variant / case_id if out else None
                    try:
                        refiner_ms, accepted, details = 0., None, None
                        projected_turns = turns
                        if stage == "refined":
                            began = time.perf_counter()
                            # Only real turns/windows, duration and global config
                            # cross this boundary. No reference, text, K or case ID.
                            result = refine(turns, windows, duration, replace(config, merge_threshold=threshold))
                            refiner_ms = (time.perf_counter() - began) * 1000
                            projected_turns, accepted, details = result.turns, result.accepted, result.diagnostics
                        hypothesis, metrics = _score_turns(projected_turns, reference, chunks, backend, duration,
                                                           asr_record["metrics"]["wer_raw"])
                        count, truth = metrics["native_speaker_count"], metrics["speakers"]["reference"]
                        detail = {"diarizationTurns": base._turn_json(projected_turns), "stage": stage,
                                  "refiner": details, "refinerAccepted": accepted, "sourceEvidence": source_hashes,
                                  "rawWerInvariant": True, "cleanEmbeddingWindowCount": len(windows),
                                  "newDiarizationInference": False, "newAsrInference": False,
                                  "refinerOnlyMs": refiner_ms, "timingScope": TIMING_SCOPE}
                        record = {"id": case_id, "split": case["split"], "profile": variant,
                                  "source_profile": profile, "stage": stage, "threshold": threshold,
                                  "audio_sha256": case["audio_sha256"], "reference_sha256": reference_hash,
                                  "duration_ms": duration, "diarization_inference_ms": 0.,
                                  "refiner_only_ms": refiner_ms, "refiner_accepted": accepted,
                                  "native_speaker_count": count, "reference_speaker_count": truth,
                                  "native_speaker_count_error": abs(count - truth), "metrics": metrics,
                                  "new_diarization_inference": False, "new_asr_inference": False,
                                  "raw_wer_invariant": True, "source_evidence_sha256": source_hashes,
                                  "completed_at": datetime.now(timezone.utc).isoformat()}
                        if case_output:
                            case_output.mkdir(parents=True, exist_ok=False)
                            for name, value in (("reference", reference), ("hypothesis", hypothesis),
                                                ("metrics", metrics), ("diagnostics", detail)):
                                write_json(case_output / (name + ".json"), value)
                            write_json(case_output / "turns.json", base._turn_json(projected_turns))
                            record["evidence_sha256"] = evidence_hashes(case_output)
                            record["turns_sha256"] = digest(case_output / "turns.json")
                            write_json(case_output / "case.json", record)
                        records.append(record)
                    except Exception as exc:
                        failure = {"id": case_id, "profile": variant, "stage": stage, "threshold": threshold,
                                   "status": "FAILED", "error": f"{type(exc).__name__}: {exc}",
                                   "traceback": traceback.format_exc(), "source_evidence_sha256": source_hashes}
                        failures.append(failure)
                        if out:
                            write_json(out / "failures" / variant / (case_id + ".json"), failure)
                # Do not permit an input edited during the sweep to appear paired.
                if diar_hashes != {"case.json": digest(folder / "case.json"), **evidence_hashes(folder)} or asr_hashes != {"case.json": digest(asr_folder / "case.json"), **evidence_hashes(asr_folder)} or digest(reference_file) != reference_hash:
                    raise ValueError("Saved input changed during refinement")
            except Exception as exc:
                # Preserve any written attempt, but never aggregate a case whose
                # inputs failed validation (including edits during processing).
                records[:] = [record for record in records if record["id"] != case_id]
                failure = {"id": case_id, "profile": profile, "stage": "input_validation", "status": "FAILED",
                           "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
                failures.append(failure)
                if out:
                    write_json(out / "failures" / "inputs" / (case_id + ".json"), failure)
    except Exception as exc:
        fatal = {"status": "FAILED", "stage": "run_validation", "error": f"{type(exc).__name__}: {exc}",
                 "traceback": traceback.format_exc()}
        failures.append(fatal)
        if out:
            write_json(out / "failures" / "run.json", fatal)
    fingerprint["cases"] = source_cases
    fingerprint["selected_ids"] = [c["id"] for c in selected]
    fingerprint["config"] = settings
    fingerprint_hash = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, allow_nan=False).encode()).hexdigest()
    summaries = {variant: _summarize([r for r in records if r["profile"] == variant], len(selected))
                 for variant in (["baseline"] if "baseline" in stages else []) +
                 ([_tau_id(v) for v in values] if "refined" in stages else [])}
    status = "FAILED" if failures else "PARTIAL_SOURCE" if pending else "COMPLETE"
    report = {"schema_version": 1, "status": status, "started_at": started,
              "completed_at": datetime.now(timezone.utc).isoformat(), "config": settings,
              "source_fingerprint": fingerprint, "source_fingerprint_sha256": fingerprint_hash,
              "summaries": summaries, "records": records, "failures": failures, "pending_cases": pending,
              "new_diarization_inference": False, "new_asr_inference": False, "timing_scope": TIMING_SCOPE,
              "scope": "Saved-evidence refiner research; montage interval DER proxy. No release gate or Android performance claim."}
    if out:
        write_json(out / "source-fingerprint.json", fingerprint)
        write_json(out / "summary.json", {key: value for key, value in report.items() if key not in ("records", "source_fingerprint")})
        write_json(out / "run.json", {key: value for key, value in report.items() if key not in ("records", "summaries", "source_fingerprint")})
        _csv(out / "results.csv", records, failures)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diar-run", type=Path, required=True)
    parser.add_argument("--asr-run", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--thresholds", default=",".join(str(v) for v in DEFAULT_THRESHOLDS))
    parser.add_argument("--missing-policy", choices=("retain", "temporal"), default="retain")
    parser.add_argument("--small-min-sim", type=float)
    parser.add_argument("--stages", nargs="+", choices=("baseline", "refined"), default=["baseline", "refined"])
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = score_saved(args.diar_run, args.asr_run, args.manifest, profile=args.profile,
                         thresholds=args.thresholds, split=args.split, missing_policy=args.missing_policy,
                         small_min_sim=args.small_min_sim, output=args.output, stages=args.stages, cases=args.cases)
    print(json.dumps({key: report[key] for key in ("status", "summaries", "pending_cases", "failures")}, ensure_ascii=False, indent=2))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
