#!/usr/bin/env python3
"""C2 global window clustering from verified saved neural evidence, dev only.

No audio/model is opened. The clustering helper receives predicted turns, real
window vectors, duration and one global config. Independent references are read
only after the helper returns. Every output retains the exact saved ASR words.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.eval import pipeline as base
from tools.eval import refine_sweep as saved
from tools.eval.diar_sweep import REPO, load_asr, summarize
from tools.eval.refiner_ablation import _tokens, score_projection
from tools.eval.run import confined, digest, evidence_hashes, write_json
from tools.eval.speaker_refiner import clean_windows


def load_inputs(diar_run, asr_run, manifest, profile):
    meta, asr_meta = saved.read_json(diar_run / "run.json"), saved.read_json(asr_run / "run.json")
    if meta.get("status") != "COMPLETE" or asr_meta.get("status") != "COMPLETE":
        raise ValueError("Complete saved runs are required; no subset acceptance")
    if (profile == "fixed" or meta.get("options", {}).get("mode") == "fixed"
            or asr_meta.get("config", {}).get("pipeline") != "vad_words_v1"
            or asr_meta["config"].get("punctuation_mode") != "none"):
        raise ValueError("Need automatic C turns and actual unmodified-text D words")
    cases = [c for c in saved.read_json(manifest)["files"] if c["split"] == "dev"]
    if len(cases) != 8 or len({c["id"] for c in cases}) != 8:
        raise ValueError("Full eight-case dev selection required")
    asr_hash = digest(asr_run / "run.json")
    kind = saved._source_format(meta, asr_hash)
    result, dimensions, model_ids = [], set(), set()
    for case in cases:
        identifier = saved._safe(case["id"], "case id")
        folder, afolder = confined(diar_run / profile, identifier), confined(asr_run, identifier)
        reference = confined(manifest.parent, case["reference"])
        rh = digest(reference)
        if asr_meta["fingerprint"]["references"].get(identifier) != rh:
            raise ValueError("Independent reference differs from actual D pin")
        record, hashes = saved._checked_record(folder, case, rh, profile=profile)
        arecord, ahashes = saved._checked_record(afolder, case, rh)
        if record.get("mode") != "auto":
            raise ValueError("Known-K input is not an automatic candidate")
        chunks, replay_record, backend = load_asr(afolder, case, rh)
        if arecord != replay_record:
            raise ValueError("D evidence changed while loading")
        diag = saved.read_json(folder / "diagnostics.json")
        saved._check_asr_link(kind, meta, diag, record, arecord, ahashes, asr_hash, identifier, folder)
        turns = saved._turns(diag.get("diarizationTurns"), case["duration_ms"])
        windows = saved._windows(diag.get("cleanEmbeddingWindows"))
        expected = {(w.start_ms, w.end_ms, w.speaker) for w in clean_windows(turns, case["duration_ms"])}
        keys = [(w.start_ms, w.end_ms, w.speaker) for w in windows]
        if len(set(keys)) != len(keys) or set(keys) != expected:
            raise ValueError("Measured window coverage differs from clean-window planner")
        dimensions.update(len(w.embedding) for w in windows)
        model_ids.add(record.get("model_id"))
        result.append(SimpleNamespace(case_id=identifier, duration_ms=case["duration_ms"],
            audio_sha256=case["audio_sha256"], reference_path=reference, reference_sha256=rh,
            turns=tuple(turns), windows=tuple(windows), chunks=tuple(chunks), backend=backend,
            expected_raw=arecord["metrics"]["wer_raw"], source_tokens=_tokens(saved.read_json(afolder / "hypothesis.json")),
            source_hashes={"diar": hashes, "asr": ahashes, "reference": rh, "original_audio": case["audio_sha256"]}))
    if len(dimensions) != 1 or min(dimensions) <= 0 or len(model_ids) != 1 or None in model_ids:
        raise ValueError("Mixed/invalid embedding model or dimensions")
    fingerprint = {"manifest": digest(manifest), "diar_run": digest(diar_run / "run.json"),
        "asr_run": asr_hash, "source_format": kind, "model_id": next(iter(model_ids)),
        "embedding_dimension": next(iter(dimensions)), "selected_ids": [c.case_id for c in result],
        "cases": {c.case_id: c.source_hashes for c in result}}
    return result, fingerprint


def aggregate(records):
    summary = summarize(records)
    summary.pop("rtf_diarization_stage")
    summary.pop("diarization_inference_ms")
    summary.update(new_diarization_inference=False, new_asr_inference=False,
        new_embedding_inference=False, timing_scope="Pure window clustering of saved vectors only; no RTF",
        refiner_only_ms=sum(c["refiner_only_ms"] for c in records), complete_case_coverage=len(records) == 8,
        raw_wer_invariant=all(c["raw_wer_invariant"] for c in records),
        refiner_accepted_cases=sum(c["refiner_accepted"] is True for c in records))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diar-run", type=Path, required=True)
    parser.add_argument("--asr-run", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=REPO / "benchmark/eval/manifest.json")
    parser.add_argument("--profile", default="auto-0p50")
    parser.add_argument("--method", choices=("complete", "average"), required=True)
    parser.add_argument("--reassign-small", action="store_true")
    parser.add_argument("--protocol", type=Path, default=REPO / "configs/eval/diar-protocol-window-v1.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    from tools.eval.window_overcluster import WindowClusterConfig, overcluster
    import scipy

    protocol = saved.read_json(args.protocol)
    values = protocol["initial_global_grid"]["cosine_thresholds"]
    if args.method not in protocol["initial_global_grid"]["linkage"]:
        raise ValueError("Method is outside the frozen dev protocol")
    inputs, fingerprint = load_inputs(args.diar_run, args.asr_run, args.manifest, args.profile)
    config = WindowClusterConfig(method=args.method, reassign_small=args.reassign_small)
    # Fail invalid global options before creating an evidence directory.
    overcluster([], [], 0, config)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    settings = {"algorithm": "window-overcluster-v1", "profile": args.profile, "thresholds": values,
        "method": args.method, "refiner_config": asdict(config), "window_protocol_sha256": digest(args.protocol)}
    fingerprint.update(config=settings, runner=digest(__file__),
        refiner=digest(Path(__file__).with_name("window_overcluster.py")),
        source_loader=digest(Path(__file__).with_name("refine_sweep.py")),
        asr_replay_helpers=digest(Path(__file__).with_name("refiner_ablation.py")),
        scorer=digest(Path(__file__).with_name("score.py")), scipy=scipy.__version__)
    fp_hash = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, allow_nan=False).encode()).hexdigest()
    meta = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
        "config": settings, "source_fingerprint_sha256": fp_hash, "failures": [], "pending_cases": [],
        "new_embedding_inference": False, "new_diarization_inference": False, "new_asr_inference": False,
        "scope": "Host-only C2 saved-window research; no holdout/Android/release/whole-pipeline acceptance"}
    write_json(out / "config.json", settings)
    write_json(out / "source-fingerprint.json", fingerprint)
    write_json(out / "run.json", meta)
    records, cache = [], {}
    try:
        for tau in values:
            variant = saved._tau_id(tau)
            local_config = WindowClusterConfig(**{**asdict(config), "tau": tau})
            for case in inputs:
                began = time.perf_counter()
                # No reference object, expected speaker count, text or case ID.
                result = overcluster(case.turns, case.windows, case.duration_ms, local_config)
                elapsed = (time.perf_counter()-began)*1000
                hypothesis, metrics = score_projection(case, result.turns, cache)
                count, truth = metrics["native_speaker_count"], metrics["speakers"]["reference"]
                diag = {"algorithm": "window-overcluster-v1", "diarizationTurns": base._turn_json(result.turns),
                    "refiner": result.diagnostics, "refinerAccepted": result.accepted,
                    "sourceEvidence": case.source_hashes, "rawWerInvariant": True,
                    "newDiarizationInference": False, "newAsrInference": False,
                    "refinerOnlyMs": elapsed, "timingScope": "Pure saved-vector clustering; no RTF"}
                folder = out / variant / case.case_id
                for name, value in (("reference", saved.read_json(case.reference_path)),
                        ("hypothesis", hypothesis), ("metrics", metrics), ("diagnostics", diag)):
                    write_json(folder / (name + ".json"), value)
                record = {"id": case.case_id, "split": "dev", "profile": variant, "source_profile": args.profile,
                    "stage": "refined", "threshold": tau, "audio_sha256": case.audio_sha256,
                    "reference_sha256": case.reference_sha256, "duration_ms": case.duration_ms,
                    "native_speaker_count": count, "reference_speaker_count": truth,
                    "native_speaker_count_error": abs(count-truth), "metrics": metrics,
                    "refiner_accepted": result.accepted, "refiner_only_ms": elapsed,
                    "diarization_inference_ms": 0, "new_diarization_inference": False, "new_asr_inference": False,
                    "raw_wer_invariant": True, "source_evidence_sha256": case.source_hashes,
                    "evidence_sha256": evidence_hashes(folder), "completed_at": datetime.now(timezone.utc).isoformat()}
                write_json(folder / "case.json", record)
                records.append(record)
            summary = aggregate([r for r in records if r["profile"] == variant])
            print(json.dumps({"tau": tau, "exact": summary["speaker_count_exact_cases"],
                "native_der_errors_fraction": summary["native_der_collar_0ms"]["rate"]}), flush=True)
        # Check the source files remained identical throughout research/scoring.
        _, final_fingerprint = load_inputs(args.diar_run, args.asr_run, args.manifest, args.profile)
        if any(final_fingerprint[k] != fingerprint[k] for k in final_fingerprint):
            raise ValueError("Saved source changed during research")
        meta.update(status="COMPLETE", completed_at=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        failure = {"profile": locals().get("variant", "unknown"),
            "id": getattr(locals().get("case"), "case_id", "unknown"),
            "stage": "window_clustering_or_scoring", "status": "FAILED", "error": str(error)}
        meta["failures"].append(failure)
        write_json(out / "failures" / (failure["profile"] + "-" + failure["id"] + ".json"), failure)
        meta.update(status="FAILED", error=str(error), completed_at=datetime.now(timezone.utc).isoformat())
        raise
    finally:
        summaries = {variant: aggregate([r for r in records if r["profile"] == variant])
                     for variant in sorted({r["profile"] for r in records})}
        write_json(out / "summary.json", {"status": meta["status"], "summaries": summaries})
        write_json(out / "run.json", meta)
        saved._csv(out / "results.csv", records, meta["failures"])


if __name__ == "__main__":
    main()
