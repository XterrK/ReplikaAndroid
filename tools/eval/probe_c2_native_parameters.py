#!/usr/bin/env python3
"""Final bounded C2 native-gap/shift probes: fresh SD/windows, saved D ASR only.

Each invocation measures one frozen global profile on all eight dev recordings.
No reference text/count/case ID crosses the native or pure-refiner APIs. Timings
are diagnostic stage observations, never concurrent-probe speed acceptance.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gc
import json
import math
from pathlib import Path
import re
import struct
import sys
import time

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.eval import diar_sweep as sweep
from tools.eval import native_diar_policy as policy
from tools.eval import pipeline as base
from tools.eval.native_policy import policy_for_plan, validate_native_policy
from tools.eval.pull_refined_android import _host_case, canonical_audio
from tools.eval.run import REPO, confined, digest, evidence_hashes, write_json
from tools.eval.speaker_refiner import EmbeddingWindow, clean_windows
from tools.eval.window_overcluster import WindowClusterConfig, overcluster

PROFILES = [
    {"id": "baseline-existing", "window_shift": .1, "min_duration_off": .5, "inference": False},
    {"id": "off-0p25", "window_shift": .1, "min_duration_off": .25, "inference": True},
    {"id": "off-1p0", "window_shift": .1, "min_duration_off": 1., "inference": True},
    {"id": "shift-0p25", "window_shift": .25, "min_duration_off": .5, "inference": True},
    {"id": "shift-0p5", "window_shift": .5, "min_duration_off": .5, "inference": True},
]
FRESH_PROFILES = tuple(row["id"] for row in PROFILES if row["inference"])
SCOPE = ("Final C dev-only native gap/shift quality probe. Fresh SD and original-PCM clean-window "
         "embedding inference; verified real D ASR replay, no new ASR. No gold to inference, "
         "no holdout/reserve/AMI selection, no whole-pipeline RTF or concurrent speed acceptance.")


def load(path):
    return policy.strict_json(Path(path).read_bytes())


def raw_tokens(hypothesis):
    return [token for row in hypothesis["transcript"] for token in row["text"].split()]


def validate_protocol(protocol, profile_id):
    common = {"schema_version": 1, "id": "c2-final-native-parameters-v1", "model_id": "eres2net_zh",
        "native_threshold": .3, "threads": 2, "expected_speakers": -1, "min_duration_on": .2,
        "window_config": policy.WINDOW_CONFIG, "split": "dev", "expected_cases": 8,
        "paired_asr_plan": "vad_words_context600", "asr_replay": True, "new_asr_inference": False,
        "new_neural_inference_in_this_file": False, "profiles": PROFILES}
    for key, value in common.items():
        policy.equal(protocol.get(key), value, "protocol." + key)
    selection = protocol.get("selection", {})
    for key, value in {"count_minimum": 7, "cases": 8, "maximum_native_der0": .18298480576441103,
                       "raw_errors_must_equal": 71, "raw_reference_tokens": 533}.items():
        policy.equal(selection.get(key), value, "selection." + key)
    frozen = datetime.fromisoformat(protocol["frozen_at_utc"])
    if frozen.tzinfo is None or frozen > datetime.now(timezone.utc):
        raise ValueError("Protocol must be frozen with timezone before probe execution")
    if profile_id not in FRESH_PROFILES:
        raise ValueError("Only the four frozen fresh-inference alternatives may run")
    return dict(next(row for row in PROFILES if row["id"] == profile_id))


def make_config(profile, embedding, segmentation, sherpa):
    config = sweep.make_config(embedding, segmentation, -1, .3, profile["window_shift"], 2, sherpa)
    # Set BEFORE constructing OfflineSpeakerDiarization; every case gets a new session.
    config.min_duration_off = profile["min_duration_off"]
    return config


def sdk_metadata(profile, sherpa):
    """Real SDK config objects only: no model/session/process or waveform calls."""
    config = make_config(profile, "metadata-only-embedding.onnx", "metadata-only-segmentation.onnx", sherpa)
    observed = {"native_threshold": config.clustering.threshold,
        "window_shift": config.segmentation.pyannote.window_shift_ratio,
        "min_duration_on": config.min_duration_on, "min_duration_off": config.min_duration_off}
    expected = {"native_threshold": .3, "window_shift": profile["window_shift"],
                "min_duration_on": .2, "min_duration_off": profile["min_duration_off"]}
    for key, value in expected.items():
        policy.f32_equal(observed[key], value, "SDK." + key)
    policy.equal(config.clustering.num_clusters, -1, "SDK.automatic")
    policy.equal(config.segmentation.num_threads, 2, "SDK.segmentation_threads")
    policy.equal(config.embedding.num_threads, 2, "SDK.embedding_threads")
    return {"observed": observed, "float32_bits": {k: struct.pack("!f", v).hex() for k, v in observed.items()},
            "num_clusters": -1, "threads": 2, "new_neural_inference": False}


def _dependencies():
    names = ("probe_c2_native_parameters", "diar_sweep", "native_diar_policy", "native_policy",
        "pull_refined_android", "port_comparison", "pipeline", "pipeline_words", "decoder_parity",
        "score", "run", "speaker_refiner", "vad_words", "window_overcluster")
    return {"tools/eval/" + name + ".py": digest(Path(__file__).with_name(name + ".py")) for name in names}


def preflight(args, sherpa, native):
    if args.output.exists():
        raise ValueError("Choose fresh output; previous success/failure evidence is immutable")
    protocol = load(args.protocol)
    profile = validate_protocol(protocol, args.profile)
    if sherpa.__version__ != "2.0.1":
        raise ValueError("Pinned sherpa-onnx 2.0.1 required")
    sdk = sdk_metadata(profile, sherpa)
    manifest_path = args.manifest or confined(REPO, protocol["manifest"])
    asr_run = args.asr_run or confined(REPO, protocol["asr_run"])
    baseline_run = args.baseline_run or confined(REPO, protocol["baseline_run"])
    if (manifest_path.resolve() != confined(REPO, protocol["manifest"])
            or asr_run.resolve() != confined(REPO, protocol["asr_run"])
            or baseline_run.resolve() != confined(REPO, protocol["baseline_run"])):
        raise ValueError("Protocol-pinned source paths must match")
    if (digest(manifest_path) != protocol["manifest_sha256"]
            or digest(asr_run / "run.json") != protocol["asr_run_sha256"]
            or any(digest(baseline_run / name) != sha for name, sha in protocol["baseline_source_sha256"].items())
            or digest(args.catalog) != protocol["catalog_sha256"]
            or digest(base.MANIFEST) != protocol["models_lock_sha256"]):
        raise ValueError("Frozen protocol/source/config/catalog/lock fingerprints differ")
    lock = load(base.MANIFEST)
    pins = policy.validate_model_lock(lock)
    model_files, _ = base._verify_models(args.model_root, True)
    catalog = load(args.catalog)
    entry = next(row for row in catalog["models"] if row["id"] == "eres2net_zh")
    if (entry.get("baseline") is not True or entry.get("sha256") != policy.EMBEDDING_SHA256
            or entry.get("embedding_dimension") != 512 or entry.get("size") != policy.MODEL_PINS[5][1]):
        raise ValueError("Pinned baseline ERes catalog entry differs")
    asr_meta = load(asr_run / "run.json")
    fp = asr_meta["fingerprint"]
    validate_native_policy(asr_meta["config"], {"threads": 2, "expectedSpeakers": -1,
        "asrPlan": "vad_words_context600", "asrPolicy": policy_for_plan("vad_words_context600")})
    if (asr_meta.get("status") != "COMPLETE"
            or ("new_model_inference" in asr_meta and asr_meta["new_model_inference"] is not True)
            or fp.get("models") != pins or fp.get("model_lock_sha256") != digest(base.MANIFEST)
            or fp.get("manifest_sha256") != digest(manifest_path) or fp.get("runtime") != "2.0.1"):
        raise ValueError("Need complete actual pinned D ASR, not replay/fixed-K")
    for field, name in {"baseline_helpers_sha256": "pipeline", "decoder_code_sha256": "decoder_parity",
        "scorer_code_sha256": "score", "word_planner_code_sha256": "vad_words",
        "pipeline_code_sha256": "pipeline_words"}.items():
        if fp.get(field) != digest(Path(__file__).with_name(name + ".py")):
            raise ValueError("Frozen D helper differs: " + name)
    baseline_meta = load(baseline_run / "run.json")
    policy.validate_host_policy(baseline_meta["config"], baseline_meta["paired_asr_policy"])
    if (baseline_meta.get("status") != "COMPLETE" or baseline_meta.get("new_model_inference") is not True
            or baseline_meta["fingerprint"].get("packaged_models") != pins):
        raise ValueError("Completed actual C2 baseline required")
    for filename, sha in baseline_meta["fingerprint"]["code"].items():
        if digest(confined(REPO, filename)) != sha:
            raise ValueError("Frozen C2 baseline helper changed")
    manifest = load(manifest_path)
    cases = [row for row in manifest["files"] if row["split"] == "dev"]
    if len(cases) != 8 or len({row["id"] for row in cases}) != 8 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", row["id"]) for row in cases):
        raise ValueError("Exactly eight safe, distinct dev cases required")
    inputs, baseline_records, source_cases = [], [], {}
    for case in cases:
        identifier = case["id"]
        audio, reference = confined(args.audio_root, case["audio"]), confined(manifest_path.parent, case["reference"])
        ref_sha = digest(reference)
        if digest(audio) != case["audio_sha256"] or fp["references"].get(identifier) != ref_sha:
            raise ValueError("Pinned dev audio/reference differs: " + identifier)
        canonical_audio(audio, case["duration_ms"])
        chunks, record, backend = sweep.load_asr(asr_run / identifier, case, ref_sha)
        if record.get("new_model_inference") is not True:
            raise ValueError("Need actual D per-case neural evidence")
        d_diag = load(asr_run / identifier / "diagnostics.json")
        if d_diag.get("onnxruntimeVersion") != native.onnxruntime_version:
            raise ValueError("Source D ONNX Runtime differs")
        original = policy.turns_from_json(d_diag["diarizationTurns"], case["duration_ms"])
        if sweep.project_asr(chunks, original, backend) != load(asr_run / identifier / "hypothesis.json"):
            raise ValueError("Original actual D words/hypothesis fail reconstruction")
        baseline = _host_case(baseline_run, case, reference, baseline_meta)
        diag = load(baseline_run / identifier / "diagnostics.json")
        n = len({row["speakerId"] for row in diag["diarizationTurns"]})
        truth = baseline["metrics"]["speakers"]["reference"]
        if baseline["metrics"]["wer_raw"] != record["metrics"]["wer_raw"]:
            raise ValueError("Baseline/actual D raw ASR differs")
        baseline_records.append({**baseline, "native_speaker_count": n, "reference_speaker_count": truth,
            "native_speaker_count_error": abs(n - truth), "diarization_inference_ms": 0.})
        source_cases[identifier] = {"case_sha256": digest(asr_run / identifier / "case.json"),
            "evidence_sha256": evidence_hashes(asr_run / identifier),
            "baseline_case_sha256": digest(baseline_run / identifier / "case.json"),
            "baseline_evidence_sha256": evidence_hashes(baseline_run / identifier)}
        inputs.append({"case": case, "audio": audio, "reference": reference, "reference_sha256": ref_sha,
                       "chunks": chunks, "source_record": record, "backend": backend,
                       "source_raw_tokens": raw_tokens(load(asr_run / identifier / "hypothesis.json"))})
    baseline_summary = sweep.summarize(baseline_records)
    if (baseline_summary["native_der_collar_0ms"]["rate"] != protocol["selection"]["maximum_native_der0"]
            or baseline_summary["wer_raw"]["errors"] != 71 or baseline_summary["wer_raw"]["reference_tokens"] != 533):
        raise ValueError("Frozen baseline dev quality/counts differ")
    baseline_summary.update(rtf_diarization_stage=None, timing_scope="Saved C2 baseline quality only; no current NN measured")
    fingerprint = {"protocol_sha256": digest(args.protocol), "profile": profile, "manifest_sha256": digest(manifest_path),
        "catalog_sha256": digest(args.catalog), "models_lock_sha256": digest(base.MANIFEST), "models": model_files,
        "asr_run_sha256": digest(asr_run / "run.json"), "baseline_source_sha256": protocol["baseline_source_sha256"],
        "source_cases": source_cases, "selected_ids": [row["id"] for row in cases],
        "references": {x["case"]["id"]: x["reference_sha256"] for x in inputs},
        "audio": {row["id"]: row["audio_sha256"] for row in cases}, "code": _dependencies(),
        "runtime": {"version": sherpa.__version__, "git": native.git_sha1, "onnxruntime": native.onnxruntime_version,
                    "extension_sha256": digest(Path(native.__file__))}}
    return {"protocol": protocol, "profile": profile, "sdk_config": sdk, "inputs": inputs, "manifest": manifest,
        "asr_run": asr_run, "baseline_run": baseline_run, "baseline_summary": baseline_summary, "fingerprint": fingerprint}


def infer(samples, embedding, segmentation, profile, sherpa):
    """Only original PCM, model paths, global profile and SDK cross this boundary."""
    duration = len(samples) * 1000 // 16000
    counts = {"sdLoads": 0, "sdProcessCalls": 0, "sdReleased": False, "extractorLoads": 0,
              "createdStreams": 0, "releasedStreams": 0, "computeAttempts": 0, "embeddingForwardCalls": 0}
    diagnostic = {"counts": counts, "newAsrInference": False, "newDiarizationInference": False,
                  "newEmbeddingInference": False, "originalPcm": True, "sampleRate": 16000}
    sd, actual, extractor, stream = None, None, None, None
    try:
        began = time.perf_counter()
        sd = sherpa.OfflineSpeakerDiarization(make_config(profile, embedding, segmentation, sherpa))
        counts["sdLoads"] += 1
        diagnostic["sdLoadMs"] = (time.perf_counter() - began) * 1000
        began = time.perf_counter()
        counts["sdProcessCalls"] += 1
        diagnostic["newDiarizationInference"] = True
        actual = sd.process(samples)
        diagnostic["sdProcessMs"] = (time.perf_counter() - began) * 1000
        raw = [base.Turn(max(0, min(duration, base._kotlin_round_ms(t.start))),
                         max(0, min(duration, base._kotlin_round_ms(t.end))), int(t.speaker))
               for t in actual.sort_by_start_time()]
        raw = [t for t in raw if t.end_ms > t.start_ms]
        actual = None; sd = None; gc.collect(); counts["sdReleased"] = True
        turns = base.stable_turns(raw)
        diagnostic.update(rawDiarizationTurns=base._turn_json(raw), nativeDiarizationTurns=base._turn_json(turns))
        planned = clean_windows(turns, duration)
        counts["plannedWindows"] = len(planned)
        if not 0 < len(planned) <= 2048:
            raise ValueError("Unsupported empty/oversized clean-window set")
        began = time.perf_counter()
        extractor = sherpa.SpeakerEmbeddingExtractor(sherpa.SpeakerEmbeddingExtractorConfig(
            model=str(embedding), num_threads=2, provider="cpu", debug=False))
        counts["extractorLoads"] += 1
        if extractor.dim != 512:
            raise ValueError("Expected actual 512-dimensional ERes output")
        windows = []
        diagnostic["cleanEmbeddingWindows"] = windows
        for window in planned:
            try:
                stream = extractor.create_stream(); counts["createdStreams"] += 1
                stream.accept_waveform(16000, samples[window.start_ms * 16:window.end_ms * 16])
                stream.input_finished()
                if not extractor.is_ready(stream):
                    raise ValueError("Actual clean-window embedding stream not ready")
                counts["computeAttempts"] += 1
                diagnostic["newEmbeddingInference"] = True
                vector = [float(x) for x in extractor.compute(stream)]
                counts["embeddingForwardCalls"] += 1
                if len(vector) != 512 or any(not math.isfinite(x) for x in vector) or not any(x != 0 for x in vector):
                    raise ValueError("Invalid actual embedding output")
                windows.append({**asdict(window), "embedding": vector})
            finally:
                if stream is not None:
                    stream = None; counts["releasedStreams"] += 1
        extractor = None; gc.collect()
        diagnostic["windowEmbeddingMs"] = (time.perf_counter() - began) * 1000
        counts.update(measuredWindows=len(windows), embeddingDimension=512, extractorReleased=True)
        result = overcluster(turns, [EmbeddingWindow(**w) for w in windows], duration,
                             WindowClusterConfig(**policy.WINDOW_CONFIG))
        diagnostic.update(refiner=result.diagnostics, refinerAccepted=result.accepted,
                          diarizationTurns=base._turn_json(result.turns))
        if not result.accepted:
            raise ValueError("Unsupported pure C2 refiner: " + str(result.diagnostics.get("reason")))
        return diagnostic
    except BaseException as error:
        error.c2_diagnostics = diagnostic
        raise
    finally:
        actual = None; sd = None; stream = None; extractor = None; gc.collect()
        if counts["sdLoads"]:
            counts["sdReleased"] = True
        if counts["extractorLoads"]:
            counts["extractorReleased"] = True
        counts["nativeResourcesReleased"] = True


def quality_gate(records, protocol):
    good = [r for r in records if r.get("status") == "COMPLETE"]
    summary = sweep.summarize(good)
    complete = len(records) == len(good) == 8 and len({r["id"] for r in good}) == 8
    selection = protocol["selection"]
    raw = summary["wer_raw"]
    invariant = complete and all(r["raw_asr_invariant"] for r in good) and raw["errors"] == selection["raw_errors_must_equal"] and raw["reference_tokens"] == selection["raw_reference_tokens"]
    rate = summary["native_der_collar_0ms"]["rate"]
    count = summary["speaker_count_exact_cases"]
    conditions = {"complete_dev8": complete, "raw_asr_invariant": invariant,
        "native_count_at_least7": complete and count >= 7,
        "native_der_no_regrowth": complete and rate is not None and rate <= selection["maximum_native_der0"]}
    summary.update(rtf=None, rtf_diarization_stage=None,
                   timing_scope="New SD/embedding stage observations only; no full-pipeline or concurrent speed acceptance")
    return {"gate_pass": all(conditions.values()), "conditions": conditions, "aggregate": summary,
        "strictly_better_der": all(conditions.values()) and rate < selection["maximum_native_der0"],
        "tie_policy": "retain existing C2", "baseline_native_der0": selection["maximum_native_der0"]}


def _csv(output, records):
    import csv
    fields = ["id", "profile", "status", "window_shift", "min_duration_off", "native_speaker_count",
        "reference_speaker_count", "native_speaker_count_error", "native_der0", "native_der250", "cpwer_raw",
        "raw_errors", "reference_tokens", "raw_asr_invariant", "sd_process_ms", "embedding_ms", "error"]
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore"); writer.writeheader()
        for record in records:
            metric = record.get("metrics", {})
            writer.writerow({**record, "native_der0": metric.get("native_der_collar_0ms", {}).get("rate"),
                "native_der250": metric.get("native_der_collar_250ms", {}).get("rate"),
                "cpwer_raw": metric.get("cpwer_raw", {}).get("rate"), "raw_errors": metric.get("wer_raw", {}).get("errors"),
                "reference_tokens": metric.get("wer_raw", {}).get("reference_tokens")})


def run(args, *, sherpa=None, native=None):
    if sherpa is None:
        import sherpa_onnx as sherpa
        from sherpa_onnx.lib import _sherpa_onnx as native
    checked = preflight(args, sherpa, native)
    if args.check:
        print(json.dumps({"status": "PREFLIGHT_PASS", "scope": SCOPE, "sdk_config": checked["sdk_config"],
            "fingerprint": checked["fingerprint"], "baseline_dev": checked["baseline_summary"]}, indent=2))
        return 0
    args.output.mkdir(parents=True)
    meta = {"schema_version": 1, "status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
        "scope": SCOPE, "profile": checked["profile"], "fingerprint": checked["fingerprint"],
        "sdk_config": checked["sdk_config"], "new_asr_inference": False, "asr_replay": True,
        "inference_requested": False, "new_diarization_inference": False, "new_embedding_inference": False}
    write_json(args.output / "run.json", meta)
    write_json(args.output / "protocol.json", checked["protocol"])
    records = []
    try:
        import numpy as np
        for item in checked["inputs"]:
            case, profile = item["case"], checked["profile"]
            identifier = case["id"]
            if (_dependencies() != checked["fingerprint"]["code"] or digest(args.protocol) != checked["fingerprint"]["protocol_sha256"]
                    or digest(item["audio"]) != case["audio_sha256"] or digest(item["reference"]) != item["reference_sha256"]
                    or evidence_hashes(checked["asr_run"] / identifier) != checked["fingerprint"]["source_cases"][identifier]["evidence_sha256"]):
                raise ValueError("Frozen code/source/audio/reference changed after preflight")
            folder = args.output / identifier; folder.mkdir()
            record = {"id": identifier, "split": "dev", "profile": profile["id"], "window_shift": profile["window_shift"],
                      "min_duration_off": profile["min_duration_off"], "audio_sha256": case["audio_sha256"],
                      "reference_sha256": item["reference_sha256"], "duration_ms": case["duration_ms"]}
            try:
                current_models, _ = base._verify_models(args.model_root, True)
                if current_models != checked["fingerprint"]["models"]:
                    raise ValueError("Actual model bytes differ from preflight pins")
                samples = base._read_canonical_wav(item["audio"], np)
                if len(samples) * 1000 // 16000 != case["duration_ms"]:
                    raise ValueError("Canonical decoded clock differs")
                meta.update(inference_requested=True, new_diarization_inference=None, new_embedding_inference=None)
                write_json(args.output / "run.json", meta)
                # No source text, K, reference/case object reaches neural APIs.
                diag = infer(samples, args.model_root / "diar/embedding.onnx", args.model_root / "diar/segmentation.onnx", profile, sherpa)
                del samples
                turns = policy.turns_from_json(diag["diarizationTurns"], case["duration_ms"])
                hyp = sweep.project_asr(item["chunks"], turns, item["backend"])
                reference = load(item["reference"])
                metric = sweep.scoring.score(reference, hyp, case["duration_ms"])
                native_rows = [{"speaker_id": "native_" + str(t.speaker), "start_ms": t.start_ms,
                    "end_ms": t.end_ms, "text": ""} for t in turns]
                for collar in (0, 250):
                    metric["native_der_collar_" + str(collar) + "ms"] = sweep.scoring.der(reference["transcript"], native_rows, case["duration_ms"], collar)
                invariant = (metric["wer_raw"] == item["source_record"]["metrics"]["wer_raw"]
                             and raw_tokens(hyp) == item["source_raw_tokens"])
                diag.update(asrEvidenceSha256=checked["fingerprint"]["source_cases"][identifier]["evidence_sha256"],
                    sourceDRunSha256=checked["fingerprint"]["asr_run_sha256"], sdkConfig=checked["sdk_config"],
                    modelFiles=checked["fingerprint"]["models"], profile=profile, asrReplay=True)
                (folder / "reference.json").write_bytes(item["reference"].read_bytes())
                for name, value in (("hypothesis", hyp), ("metrics", metric), ("diagnostics", diag)):
                    write_json(folder / (name + ".json"), value)
                count, truth = len({t.speaker for t in turns}), metric["speakers"]["reference"]
                record.update(status="COMPLETE", native_speaker_count=count, reference_speaker_count=truth,
                    native_speaker_count_error=abs(count - truth), metrics=metric, raw_asr_invariant=invariant,
                    diarization_inference_ms=diag["sdProcessMs"], sd_process_ms=diag["sdProcessMs"], embedding_ms=diag["windowEmbeddingMs"],
                    new_diarization_inference=True, new_embedding_inference=True, new_asr_inference=False,
                    asr_replay=True, evidence_sha256=evidence_hashes(folder))
                meta.update(new_diarization_inference=True, new_embedding_inference=True)
            except Exception as error:
                record.update(status="FAILED", error=str(error), new_asr_inference=False)
                partial = getattr(error, "c2_diagnostics", {})
                write_json(folder / "failure.json", {"error": str(error), "partial_diagnostics": partial})
            record["completed_at"] = datetime.now(timezone.utc).isoformat()
            write_json(folder / "case.json", record); records.append(record)
            _csv(args.output, records)
            write_json(args.output / "summary.json", quality_gate(records, checked["protocol"]))
        meta.update(status="COMPLETE" if all(r["status"] == "COMPLETE" for r in records) else "FAILED",
                    completed_at=datetime.now(timezone.utc).isoformat())
        write_json(args.output / "run.json", meta)
        gate = quality_gate(records, checked["protocol"])
        write_json(args.output / "summary.json", gate)
        print(json.dumps({"status": meta["status"], "profile": args.profile, **gate}, indent=2))
        return 0 if meta["status"] == "COMPLETE" else 1
    except BaseException as error:
        meta.update(status="FAILED", error=str(error), failed_at=datetime.now(timezone.utc).isoformat())
        write_json(args.output / "run.json", meta); _csv(args.output, records)
        raise


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--protocol", type=Path, default=REPO / "configs/eval/c2-final-native-parameters-v1.json")
    p.add_argument("--profile", choices=FRESH_PROFILES, required=True)
    p.add_argument("--audio-root", type=Path, required=True)
    p.add_argument("--model-root", type=Path, default=REPO / "model-pack")
    p.add_argument("--catalog", type=Path, default=REPO / "configs/eval/diar-models.json")
    p.add_argument("--manifest", type=Path)
    p.add_argument("--asr-run", type=Path)
    p.add_argument("--baseline-run", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--check", action="store_true", help="All dev source pins + real SDK config metadata, no NN/output")
    return p


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
