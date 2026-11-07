#!/usr/bin/env python3
"""Dev-only global C2 ablations of frozen refinement on complete saved evidence.

No audio, model constructor, neural inference or holdout data is used. References
are hashed for pairing and parsed only inside scoring, after a refinement call.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.eval import refine_sweep as saved
from tools.eval import speaker_refiner as refiner
from tools.eval import pipeline as base
from tools.eval.run import confined, digest, evidence_hashes, write_json

TAUS = tuple(value / 100 for value in range(30, 96, 5))
FAMILIES = ("full", "no_eigengap", "merge_only", "small_smooth_only",
            "full_small_cos_0p3", "full_small_cos_0p5", "full_small_cos_0p7")
MISSING_POLICIES = ("retain", "temporal")
DER_LIMIT = .288851817
MIN_EXACT = 7


def config_for(family, tau, missing_policy):
    if family not in FAMILIES or missing_policy not in MISSING_POLICIES or tau not in TAUS:
        raise ValueError("Use a prespecified global C2 family, tau and missing policy")
    config = refiner.RefineConfig(merge_threshold=tau, small_missing_centroid_policy=missing_policy)
    if family == "no_eigengap":
        return replace(config, use_eigengap=False)
    if family == "merge_only":
        return replace(config, use_eigengap=False, reassign_small=False, smooth=False)
    if family == "small_smooth_only":
        return replace(config, merge_similar=False, use_eigengap=False)
    if family.startswith("full_small_cos_"):
        return replace(config, minimum_reassignment_similarity=float(family.rsplit("_", 1)[1].replace("p", ".")))
    return config


def stage_trace(result):
    """Account for actual helper events; unsupported results explicitly roll back."""
    diagnostic = result.diagnostics
    initial = diagnostic.get("input_clusters", 0)
    counts = Counter(event["stage"] for event in diagnostic.get("merges", []))
    small = diagnostic.get("small_reassignments", [])
    applied = [event for event in small if event.get("applied") is True]
    after_cosine = initial - counts["cosine"]
    after_eigengap = after_cosine - counts["eigengap"]
    after_small = after_eigengap - len(applied)
    after_cap = after_small - counts["forced_cap"]
    final = len({turn.speaker for turn in result.turns if turn.speaker >= 0})
    if min(initial, after_cosine, after_eigengap, after_small, after_cap) < 0:
        raise ValueError("Inconsistent helper stage accounting")
    mapping = diagnostic.get("source_mapping_before_smoothing")
    if mapping is not None and len({entry["target"] for entry in mapping}) != after_cap:
        raise ValueError("Helper merge accounting disagrees with pre-smoothing mapping")
    if result.accepted and diagnostic.get("output_clusters") != final:
        raise ValueError("Helper output count disagrees with returned turns")
    return {"input_k": initial, "after_cosine_k": after_cosine, "after_eigengap_k": after_eigengap,
        "after_small_k": after_small, "after_forced_cap_k": after_cap, "output_k": final,
        "cosine_merges": counts["cosine"], "eigengap_merges": counts["eigengap"],
        "small_reassignments_applied": len(applied), "small_temporal_applied": sum(e.get("method") == "temporal" for e in applied),
        "small_centroid_applied": sum(e.get("method") == "centroid" for e in applied),
        "small_reassignments_retained": len(small) - len(applied),
        "small_retention_reasons": dict(Counter(e.get("reason", "unspecified") for e in small if not e.get("applied"))),
        "forced_cap_merges": counts["forced_cap"], "smoothing_events": len(diagnostic.get("smoothing", [])),
        "smoothing_cluster_reduction": after_cap - final if result.accepted else None,
        "overlap_collapses_ms": diagnostic.get("overlap_collapses_ms", 0),
        "low_similarity_merges": diagnostic.get("low_similarity_merges", 0),
        "missing_centroid_labels": diagnostic.get("missing_centroid_labels", []),
        "eigengap_estimated_k": diagnostic.get("eigengap", {}).get("estimated_k"),
        "eigengap_reason": diagnostic.get("eigengap", {}).get("reason"),
        "computation_supported": result.accepted, "status": diagnostic.get("status"),
        "fallback_reason": diagnostic.get("reason") if not result.accepted else None,
        "attempted_stages_rolled_back_to_native": not result.accepted}


@dataclass(frozen=True)
class Inputs:
    case_id: str
    duration_ms: int
    audio_sha256: str
    reference_path: Path
    reference_sha256: str
    turns: tuple
    windows: tuple
    chunks: tuple
    backend: str
    expected_raw: dict
    source_tokens: tuple
    source_hashes: dict


def _tokens(hypothesis):
    return tuple(token for row in hypothesis["transcript"] for token in row["text"].split())


def load_inputs(diar_run, asr_run, manifest, profile="auto-0p50"):
    meta, asr_meta = saved.read_json(diar_run / "run.json"), saved.read_json(asr_run / "run.json")
    if meta.get("status") != "COMPLETE" or asr_meta.get("status") != "COMPLETE":
        raise ValueError("C2 requires complete saved sources; no partial coverage")
    if (meta.get("options", {}).get("mode") == "fixed" or profile == "fixed"
            or asr_meta.get("config", {}).get("pipeline") != "vad_words_v1"
            or asr_meta.get("config", {}).get("punctuation_mode") != "none"):
        raise ValueError("Need automatic saved C source and unmodified-text D words")
    corpus = saved.read_json(manifest)
    cases = [case for case in corpus["files"] if case["split"] == "dev"]
    if len(cases) != 8 or len({case["id"] for case in cases}) != 8:
        raise ValueError("Complete protocol dev8 coverage is required")
    source_format = saved._source_format(meta, digest(asr_run / "run.json"))
    result = []
    for case in cases:
        case_id = saved._safe(case["id"], "case id")
        folder, asr_folder = confined(diar_run / profile, case_id), confined(asr_run, case_id)
        reference = confined(manifest.parent, case["reference"])
        reference_hash = digest(reference)
        if asr_meta["fingerprint"]["references"].get(case_id) != reference_hash:
            raise ValueError("Reference pin differs from saved D")
        record, source_hashes = saved._checked_record(folder, case, reference_hash, profile=profile)
        asr_record, asr_hashes = saved._checked_record(asr_folder, case, reference_hash)
        if record.get("mode") != "auto":
            raise ValueError("Oracle K is excluded from C2")
        chunks, actual_asr, backend = saved.load_asr(asr_folder, case, reference_hash)
        if actual_asr != asr_record:
            raise ValueError("ASR input changed while loading")
        diagnostic = saved.read_json(folder / "diagnostics.json")
        saved._check_asr_link(source_format, meta, diagnostic, record, asr_record, asr_hashes,
            digest(asr_run / "run.json"), case_id, folder)
        turns = tuple(saved._turns(diagnostic.get("diarizationTurns"), case["duration_ms"]))
        windows = tuple(saved._windows(diagnostic.get("cleanEmbeddingWindows")))
        expected = {(w.start_ms, w.end_ms, w.speaker) for w in refiner.clean_windows(turns, case["duration_ms"])}
        keys = [(w.start_ms, w.end_ms, w.speaker) for w in windows]
        if len(set(keys)) != len(keys) or set(keys) != expected:
            raise ValueError("Clean-window coverage differs from frozen planner")
        validated = refiner.refine(turns, windows, case["duration_ms"], refiner.RefineConfig(
            merge_similar=False, use_eigengap=False, reassign_small=False, smooth=False))
        if validated.diagnostics.get("invalid_windows") or validated.diagnostics.get("invalid_turns"):
            raise ValueError("Invalid or nonclean saved observations")
        if any(len(window.embedding) != 512 for window in windows):
            raise ValueError("Baseline ERes vectors must have 512 dimensions")
        result.append(Inputs(case_id, case["duration_ms"], case["audio_sha256"], reference,
            reference_hash, turns, windows, tuple(chunks), backend, asr_record["metrics"]["wer_raw"],
            _tokens(saved.read_json(asr_folder / "hypothesis.json")),
            {"diar": source_hashes, "asr": asr_hashes, "reference": reference_hash}))
    if sum(len(case.windows) for case in result) != 232:
        raise ValueError("Expected the complete 232-vector baseline C2 dataset")
    fingerprint = {"manifest": digest(manifest), "diar_run": digest(diar_run / "run.json"),
        "asr_run": digest(asr_run / "run.json"), "source_format": source_format,
        "selected_ids": [case.case_id for case in result],
        "cases": {case.case_id: case.source_hashes for case in result}}
    return result, fingerprint


def score_projection(case, turns, cache):
    key = (case.case_id, tuple((turn.start_ms, turn.end_ms, turn.speaker) for turn in turns))
    if key not in cache:
        # Reference values cross only the scoring boundary, never refine().
        reference = saved.read_json(case.reference_path)
        hypothesis, metrics = saved._score_turns(turns, reference, case.chunks, case.backend,
                                                case.duration_ms, case.expected_raw)
        if _tokens(hypothesis) != case.source_tokens:
            raise ValueError("Literal ASR token sequence changed")
        cache[key] = (hypothesis, metrics)
    hypothesis, metrics = cache[key]
    return copy.deepcopy(hypothesis), copy.deepcopy(metrics)


def _aggregate(records):
    summary = saved._summarize(records, 8)
    for key in ("new_embedding_inference", "new_diarization_inference", "new_asr_inference"):
        summary[key] = False
    summary["stage_reductions"] = {field: sum(record["stage_trace"][field] for record in records)
        for field in ("cosine_merges", "eigengap_merges", "small_reassignments_applied", "small_temporal_applied",
            "small_centroid_applied", "forced_cap_merges", "smoothing_events", "overlap_collapses_ms")}
    complete = len(records) == 8
    summary["research_gate"] = {"complete": complete, "required_exact_cases": MIN_EXACT,
        "maximum_native_der0": DER_LIMIT, "accepted": complete and summary["speaker_count_exact_cases"] >= MIN_EXACT
        and summary["native_der_collar_0ms"]["rate"] <= DER_LIMIT and summary["raw_wer_invariant"]}
    return summary


def _write_csv(path, records):
    fields = ["profile", "id", "family", "missing_policy", "threshold", "native_speaker_count",
        "reference_speaker_count", "native_speaker_count_error", "native_der0", "native_der250", "cpwer_raw",
        "raw_wer", "raw_wer_invariant", "refiner_accepted", "refiner_only_ms", "input_k", "after_cosine_k",
        "after_eigengap_k", "after_small_k", "after_forced_cap_k", "output_k", "cosine_merges", "eigengap_merges",
        "small_reassignments_applied", "small_temporal_applied", "small_centroid_applied", "small_reassignments_retained",
        "forced_cap_merges", "smoothing_events", "smoothing_cluster_reduction", "overlap_collapses_ms", "fallback_reason"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({**record, **record["stage_trace"],
                "native_der0": record["metrics"]["native_der_collar_0ms"]["rate"],
                "native_der250": record["metrics"]["native_der_collar_250ms"]["rate"],
                "cpwer_raw": record["metrics"]["cpwer_raw"]["rate"], "raw_wer": record["metrics"]["wer_raw"]["rate"]})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diar-run", type=Path, required=True)
    parser.add_argument("--asr-run", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", default="auto-0p50")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Preserve existing evidence; choose a fresh output")
    inputs, fingerprint = load_inputs(args.diar_run, args.asr_run, args.manifest, args.profile)
    fingerprint["code"] = {path.name: digest(path) for path in [Path(__file__), Path(saved.__file__),
        Path(refiner.__file__), Path(base.__file__), Path(saved.scoring.__file__),
        Path(__file__).with_name("vad_words.py"), Path(__file__).with_name("diar_sweep.py")]}
    settings = {"families": FAMILIES, "missing_policies": MISSING_POLICIES, "taus": TAUS,
        "native_der0_limit": DER_LIMIT, "required_exact_cases": MIN_EXACT,
        "all_global_configs": {f"{family}-{policy}-{saved._tau_id(tau)}": asdict(config_for(family, tau, policy))
            for family in FAMILIES for policy in MISSING_POLICIES for tau in TAUS}}
    fingerprint["config"] = settings
    fingerprint_hash = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, allow_nan=False).encode()).hexdigest()
    output.mkdir(parents=True)
    write_json(output / "source-fingerprint.json", fingerprint)
    meta = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
        "source_fingerprint_sha256": fingerprint_hash, "config": settings, "cases": len(inputs),
        "clean_windows": sum(len(case.windows) for case in inputs), "new_model_inference": False,
        "new_diarization_inference": False, "new_asr_inference": False, "new_embedding_inference": False,
        "scope": "C2 dev-only saved-evidence ablation; no holdout, no gate changes, no RTF claim"}
    write_json(output / "run.json", meta)
    records, summaries, score_cache = [], {}, {}
    try:
        for family in FAMILIES:
            for policy in MISSING_POLICIES:
                for tau in TAUS:
                    profile = f"{family}-{policy}-{saved._tau_id(tau)}"
                    config = config_for(family, tau, policy)
                    variant = []
                    for case in inputs:
                        began = time.perf_counter()
                        result = refiner.refine(case.turns, case.windows, case.duration_ms, config)
                        elapsed_ms = (time.perf_counter() - began) * 1000
                        trace = stage_trace(result)
                        hypothesis, metrics = score_projection(case, result.turns, score_cache)
                        count = len({turn.speaker for turn in result.turns if turn.speaker >= 0})
                        reference_count = metrics["speakers"]["reference"]
                        folder = output / profile / case.case_id
                        folder.mkdir(parents=True)
                        detail = {"refiner": result.diagnostics, "stageTrace": trace,
                            "sourceEvidence": case.source_hashes, "diarizationTurns": base._turn_json(result.turns),
                            "rawWerInvariant": True, "literalRawTokenSequencePreserved": True,
                            "cleanEmbeddingWindowCount": len(case.windows), "newModelInference": False,
                            "newDiarizationInference": False, "newAsrInference": False, "newEmbeddingInference": False,
                            "timingScope": "Pure refiner wall time only; no pipeline RTF", "refinerOnlyMs": elapsed_ms}
                        record = {"id": case.case_id, "split": "dev", "profile": profile, "stage": "refined",
                            "family": family, "missing_policy": policy, "threshold": tau,
                            "duration_ms": case.duration_ms, "audio_sha256": case.audio_sha256,
                            "reference_sha256": case.reference_sha256, "diarization_inference_ms": 0.,
                            "refiner_only_ms": elapsed_ms, "refiner_accepted": result.accepted,
                            "native_speaker_count": count, "reference_speaker_count": reference_count,
                            "native_speaker_count_error": abs(count - reference_count), "metrics": metrics,
                            "raw_wer_invariant": True, "stage_trace": trace,
                            "new_diarization_inference": False, "new_asr_inference": False, "new_embedding_inference": False}
                        (folder / "reference.json").write_bytes(case.reference_path.read_bytes())
                        write_json(folder / "hypothesis.json", hypothesis)
                        write_json(folder / "metrics.json", metrics)
                        write_json(folder / "diagnostics.json", detail)
                        write_json(folder / "turns.json", base._turn_json(result.turns))
                        record["evidence_sha256"] = evidence_hashes(folder)
                        record["turns_sha256"] = digest(folder / "turns.json")
                        write_json(folder / "case.json", record)
                        records.append(record)
                        variant.append(record)
                    summaries[profile] = _aggregate(variant)
                write_json(output / "summary.json", {"status": "RUNNING", "summaries": summaries})
        # Verify saved inputs again; edited inputs cannot silently remain paired.
        _, current = load_inputs(args.diar_run, args.asr_run, args.manifest, args.profile)
        if current != {key: value for key, value in fingerprint.items() if key not in ("code", "config")}:
            raise ValueError("Input evidence changed during ablation")
        _write_csv(output / "results.csv", records)
        ranked = sorted(summaries, key=lambda key: (not summaries[key]["research_gate"]["accepted"],
            summaries[key]["native_der_collar_0ms"]["rate"], summaries[key]["cpwer_raw"]["rate"],
            -summaries[key]["speaker_count_exact_cases"], key))
        best_by_family = {f"{family}-{policy}": min((key for key in summaries if key.startswith(f"{family}-{policy}-")),
            key=lambda key: (-summaries[key]["speaker_count_exact_cases"], summaries[key]["native_der_collar_0ms"]["rate"], key))
            for family in FAMILIES for policy in MISSING_POLICIES}
        final = {"status": "COMPLETE", "summaries": summaries, "best_by_family_count_then_der": best_by_family,
            "ranked_global_profiles": ranked, "passing_profiles": [key for key in ranked if summaries[key]["research_gate"]["accepted"]],
            "research_only": True, "old_C1_failures_preserved": True, "gates_unchanged": True,
            "scored_case_variants": len(records), "distinct_scoring_inputs": len(score_cache)}
        write_json(output / "summary.json", final)
        meta.update(status="COMPLETE", completed_at=datetime.now(timezone.utc).isoformat(), case_variants=len(records))
        write_json(output / "run.json", meta)
        print(json.dumps({"status": "COMPLETE", "profiles": len(summaries), "case_variants": len(records),
            "passing_profiles": final["passing_profiles"], "maximum_exact_cases": max(s["speaker_count_exact_cases"] for s in summaries.values()),
            "best_profile": ranked[0], "best_native_der0": summaries[ranked[0]]["native_der_collar_0ms"]["rate"]}))
        return 0
    except BaseException as error:
        _write_csv(output / "results.csv", records)
        meta.update(status="FAILED", error=str(error), completed_at=datetime.now(timezone.utc).isoformat())
        write_json(output / "run.json", meta)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
