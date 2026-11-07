#!/usr/bin/env python3
"""Actual sherpa diarization experiments; replay frozen ASR only after inference.

Fixed K is an explicitly labelled research oracle. Automatic experiments never
receive gold K or text. Every threshold calls OfflineSpeakerDiarization.process;
set_config reuses model sessions, not hidden neural output caches.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import csv
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time

sys.dont_write_bytecode = True
if __package__:
    from . import pipeline as base
    from . import score as scoring
    from .run import REPO, confined, digest, write_json, evidence_hashes, archive_incomplete
    from .vad_words import words_from_tokens, assign_words, group_words
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.eval import pipeline as base
    from tools.eval import score as scoring
    from tools.eval.run import REPO, confined, digest, write_json, evidence_hashes, archive_incomplete
    from tools.eval.vad_words import words_from_tokens, assign_words, group_words


def thresholds(value):
    values = [float(x) for x in value.split(",")]
    if (not values or len(set(values)) != len(values)
            or any(not .05 <= x <= .99 or abs(x*100-round(x*100)) > 1e-9 for x in values)):
        raise ValueError("Unique finite hundredth thresholds within .05..99 required")
    return values


def make_config(model, segmentation, count, threshold, window_shift, threads, sherpa):
    return sherpa.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(segmentation), window_shift_ratio=window_shift),
            num_threads=threads, provider="cpu", debug=False),
        embedding=sherpa.SpeakerEmbeddingExtractorConfig(
            model=str(model), num_threads=threads, provider="cpu", debug=False),
        clustering=sherpa.FastClusteringConfig(num_clusters=count, threshold=threshold,
                                              compute_confidence=False),
        min_duration_on=.2, min_duration_off=.5)


def load_asr(folder, case, reference_hash):
    record = json.loads((folder / "case.json").read_text())
    if (record.get("id") != case["id"] or record.get("duration_ms") != case["duration_ms"]
            or record["audio_sha256"] != case["audio_sha256"] or record["reference_sha256"] != reference_hash):
        raise ValueError("ASR replay inputs differ: " + case["id"])
    if record.get("evidence_sha256") != evidence_hashes(folder):
        raise ValueError("ASR replay evidence changed: " + case["id"])
    if record.get("metrics") != json.loads((folder / "metrics.json").read_text()):
        raise ValueError("ASR replay embedded metrics differ")
    diagnostic = json.loads((folder / "diagnostics.json").read_text())
    policy = diagnostic.get("tokenTimestampPolicy", {})
    if (diagnostic.get("wordAssignmentSupported") is not True
            or type(diagnostic.get("fallbackChunks")) is not int or diagnostic["fallbackChunks"] != 0
            or policy.get("verified") is not True or type(policy.get("frame_stride_ms")) is not int
            or policy["frame_stride_ms"] != 40
            or diagnostic.get("audioMs") != case["duration_ms"]
            or diagnostic.get("audioSha256") != case["audio_sha256"]):
        raise ValueError("Need complete real token times for ASR replay")
    chunks = []
    for part in diagnostic["asrSlices"]:
        if (part.get("wordAssignmentSupported") is not True
                or part.get("timestampUnit") != "seconds within ASR VAD chunk"
                or not 0 <= part["startMs"] < part["endMs"] <= case["duration_ms"]):
            raise ValueError("Invalid saved ASR chunk policy/clock")
        parsed = words_from_tokens(part["text"], part["tokens"], part["timestamps"],
                                  part["startMs"], part["endMs"], 40)
        if not parsed.supported:
            raise ValueError("Unsupported saved ASR projection: " + parsed.reason)
        chunks.append(parsed.words)
    return chunks, record, diagnostic["backend"]


def project_asr(chunks, turns, source):
    segments = []
    for words in chunks:
        segments.extend(group_words(assign_words(words, turns), source, "none"))
    return {"transcript": base.jury_projection(segments)}


def extract_windows(samples, turns, model, threads, sherpa):
    from tools.eval.speaker_refiner import clean_windows
    windows = clean_windows(turns, len(samples) * 1000 // 16000)
    extractor = sherpa.SpeakerEmbeddingExtractor(sherpa.SpeakerEmbeddingExtractorConfig(
        model=str(model), num_threads=threads, provider="cpu", debug=False))
    records = []
    try:
        for window in windows:
            start, end = window.start_ms * 16, min(window.end_ms * 16, len(samples))
            stream = extractor.create_stream()
            stream.accept_waveform(16000, samples[start:end])
            stream.input_finished()
            if not extractor.is_ready(stream):
                raise ValueError("Extractor not ready for declared clean window")
            vector = extractor.compute(stream)
            vector = [float(x) for x in vector]
            if (not vector or not all(math.isfinite(x) for x in vector)
                    or math.hypot(*vector) <= 1e-12):
                raise ValueError("Extractor produced invalid clean-window vector")
            records.append({"start_ms": window.start_ms, "end_ms": window.end_ms,
                "speaker": window.speaker, "clean": True, "embedding": vector})
            del stream
    finally:
        del extractor
        gc.collect()
    return records


def summarize(records):
    result = {"cases": len(records), "speaker_count_exact_cases": 0, "audio_ms": 0,
              "diarization_inference_ms": 0.0, "speaker_absolute_error_sum": 0}
    for key in ("wer_raw", "wer_normalized", "cpwer_raw", "cpwer_normalized"):
        errors = sum(r["metrics"][key]["errors"] for r in records)
        n = sum(r["metrics"][key]["reference_tokens"] for r in records)
        result[key] = {"errors": errors, "reference_tokens": n, "rate": errors/n if n else None}
    for key in ("native_der_collar_0ms", "native_der_collar_250ms", "der_collar_0ms", "der_collar_250ms"):
        values = {name: sum(r["metrics"][key][name] for r in records)
                  for name in ("miss_ms", "false_alarm_ms", "confusion_ms", "reference_speaker_ms")}
        n = values["reference_speaker_ms"]
        values["rate"] = sum(values[k] for k in ("miss_ms", "false_alarm_ms", "confusion_ms"))/n if n else None
        result[key] = values
    for r in records:
        result["speaker_count_exact_cases"] += r["native_speaker_count_error"] == 0
        result["speaker_absolute_error_sum"] += r["native_speaker_count_error"]
        result["audio_ms"] += r["duration_ms"]
        result["diarization_inference_ms"] += r["diarization_inference_ms"]
    result["speaker_count_exact_success_fraction"] = result["speaker_count_exact_cases"]/len(records) if records else None
    result["rtf_diarization_stage"] = result["diarization_inference_ms"]/result["audio_ms"] if result["audio_ms"] else None
    result["timing_scope"] = "Actual diarization inference only; replayed ASR is excluded, not whole-app/Android RTF"
    return result


def save_csv(output, records):
    fields = ["profile", "case", "mode", "threshold", "window_shift", "model_id", "native_speaker_count",
              "reference_speaker_count", "native_speaker_count_error", "native_der_errors_fraction",
              "native_der250_errors_fraction", "raw_wer_errors_fraction", "cpwer_errors_fraction",
              "diarization_inference_ms", "duration_ms", "new_diarization_inference", "new_asr_inference"]
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({"profile": r["profile"], "case": r["id"], "mode": r["mode"],
                "threshold": r["threshold"], "window_shift": r["window_shift"], "model_id": r["model_id"],
                "native_speaker_count": r["native_speaker_count"], "reference_speaker_count": r["reference_speaker_count"],
                "native_speaker_count_error": r["native_speaker_count_error"],
                "native_der_errors_fraction": r["metrics"]["native_der_collar_0ms"]["rate"],
                "native_der250_errors_fraction": r["metrics"]["native_der_collar_250ms"]["rate"],
                "raw_wer_errors_fraction": r["metrics"]["wer_raw"]["rate"],
                "cpwer_errors_fraction": r["metrics"]["cpwer_raw"]["rate"],
                **{k: r[k] for k in ("diarization_inference_ms", "duration_ms", "new_diarization_inference", "new_asr_inference")}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO / "benchmark/eval/manifest.json")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--asr-run", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=REPO / "configs/eval/diar-models.json")
    parser.add_argument("--embedding-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=REPO / "model-pack")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--mode", choices=("fixed", "auto", "overcluster"), required=True)
    parser.add_argument("--thresholds", default="0.5")
    parser.add_argument("--window-shift", type=float, choices=(.1, .25, .5), default=.1)
    parser.add_argument("--threads", type=int, choices=(1, 2, 4), default=2)
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--collect-windows", action="store_true")
    parser.add_argument("--window-profiles", nargs="+", help="Collect real clean embeddings only for selected profiles")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    import numpy as np
    import sherpa_onnx as sherpa
    if sherpa.__version__ != base.RUNTIME_VERSION:
        raise ValueError("Pinned sherpa runtime required")
    values = thresholds(args.thresholds)
    if args.mode != "auto" and len(values) != 1:
        raise ValueError("Threshold sweep is for automatic mode only")
    if args.mode == "overcluster" and values[0] > .30:
        raise ValueError("Overcluster uses automatic distance threshold <=.30; pass --thresholds .30 explicitly")
    profiles = {args.mode} if args.mode != "auto" else {"auto-" + f"{v:.2f}".replace(".", "p") for v in values}
    if args.window_profiles and (not args.collect_windows or not set(args.window_profiles) <= profiles):
        raise ValueError("Window profiles must select actual experiment profiles with --collect-windows")
    manifest = json.loads(args.manifest.read_text())
    cases = [c for c in manifest["files"] if (args.split == "all" or c["split"] == args.split)
             and (not args.cases or c["id"] in args.cases)]
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Empty/duplicate case selection")
    if args.cases and set(args.cases) != {c["id"] for c in cases}:
        raise ValueError("Unknown selected case")
    catalog = json.loads(args.catalog.read_text())
    entry = next(c for c in catalog["models"] if c["id"] == args.model_id)
    model = confined(REPO if entry["repoRelative"] else args.embedding_root, entry["path"])
    if model.stat().st_size != entry["size"] or digest(model) != entry["sha256"]:
        raise ValueError("Embedding model pin mismatch")
    segmentation = args.model_root / "diar/segmentation.onnx"
    lock = json.loads((REPO / "app/src/main/assets/models-lock.json").read_text())
    seg_spec = next(c for c in lock["files"] if c["path"] == "diar/segmentation.onnx")
    if digest(segmentation) != seg_spec["sha256"]:
        raise ValueError("Segmentation pin mismatch")
    asr_meta = json.loads((args.asr_run / "run.json").read_text())
    asr_config = asr_meta["config"]
    if asr_meta["status"] != "COMPLETE" or asr_config["pipeline"] != "vad_words_v1" or asr_config["punctuation_mode"] != "none":
        raise ValueError("Need completed unmodified-text word ASR run")
    options = {k: getattr(args, k) for k in ("model_id", "mode", "window_shift", "threads", "collect_windows", "window_profiles")}
    fingerprint = {"manifest": digest(args.manifest), "catalog": digest(args.catalog), "embedding": digest(model),
        "segmentation": digest(segmentation), "asr_run": digest(args.asr_run / "run.json"),
        "runner": digest(__file__), "baseline_helpers": digest(base.__file__), "scorer": digest(scoring.__file__),
        "decoder_helpers": digest(Path(__file__).with_name("decoder_parity.py")),
        "word_helpers": digest(Path(__file__).with_name("vad_words.py")),
        "selected_ids": [c["id"] for c in cases], "options": options, "thresholds": values,
        "runtime": sherpa.__version__}
    if args.collect_windows:
        fingerprint["refiner_helpers"] = digest(Path(__file__).with_name("speaker_refiner.py"))
    output = args.output.resolve()
    if output.exists():
        if not args.resume:
            raise ValueError("Existing evidence cannot be overwritten")
        meta = json.loads((output / "run.json").read_text())
        if meta["fingerprint"] != fingerprint:
            raise ValueError("Resume fingerprint differs")
    else:
        output.mkdir(parents=True)
        meta = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
                "fingerprint": fingerprint, "options": options, "platform": platform.platform(),
                "scope": "Actual host diarization; ASR is verified saved replay, not new inference. Fixed K is research oracle only. Coarse montage DER proxy; no Android/phone speed claim."}
        write_json(output / "manifest.json", manifest)
        write_json(output / "catalog.json", catalog)
    write_json(output / "run.json", meta)
    records = []
    diarizer = None
    try:
        for case in cases:
            reference_file = confined(args.manifest.parent, case["reference"])
            reference_hash = digest(reference_file)
            if reference_hash != asr_meta["fingerprint"]["references"].get(case["id"]):
                raise ValueError("Reference pin mismatch")
            reference = json.loads(reference_file.read_text())
            audio = confined(args.audio_root, case["audio"])
            if digest(audio) != case["audio_sha256"]:
                raise ValueError("Audio pin mismatch")
            chunks, asr_record, source = load_asr(args.asr_run / case["id"], case, reference_hash)
            samples = None
            for threshold in values:
                profile = args.mode if args.mode != "auto" else "auto-" + f"{threshold:.2f}".replace(".", "p")
                folder = output / profile / case["id"]
                if (folder / "case.json").is_file():
                    record = json.loads((folder / "case.json").read_text())
                    if record["audio_sha256"] != case["audio_sha256"] or record["reference_sha256"] != reference_hash or record["evidence_sha256"] != evidence_hashes(folder):
                        raise ValueError("Saved experiment evidence changed")
                    records.append(record)
                    continue
                if folder.exists():
                    archive_incomplete(folder)
                folder.mkdir(parents=True)
                if samples is None:
                    samples = base._read_canonical_wav(audio, np)
                duration_ms = len(samples) * 1000 // 16000
                if duration_ms != case["duration_ms"]:
                    raise ValueError("Decoded audio duration differs from pinned manifest")
                count = case["expected_speakers"] if args.mode == "fixed" else -1
                inference_ms, load_ms = 0.0, 0.0
                raw_turns = []
                config = make_config(model, segmentation, count, threshold, args.window_shift, args.threads, sherpa)
                if diarizer is None:
                    start = time.perf_counter();diarizer = sherpa.OfflineSpeakerDiarization(config)
                    load_ms = (time.perf_counter()-start)*1000
                else:
                    diarizer.set_config(config)
                start = time.perf_counter();actual = diarizer.process(samples)
                inference_ms = (time.perf_counter()-start)*1000
                raw_turns = [base.Turn(max(0,min(duration_ms,base._kotlin_round_ms(t.start))),
                                      max(0,min(duration_ms,base._kotlin_round_ms(t.end))),t.speaker)
                             for t in actual.sort_by_start_time()]
                raw_turns = [t for t in raw_turns if t.end_ms > t.start_ms]
                turns = base.stable_turns(raw_turns)
                del actual
                hypothesis = project_asr(chunks, turns, source)
                metric = scoring.score(reference, hypothesis, duration_ms)
                if metric["wer_raw"] != asr_record["metrics"]["wer_raw"]:
                    raise ValueError("Diarization projection changed ASR text/order")
                native = [{"speaker_id": "native_"+str(t.speaker), "start_ms": t.start_ms,
                           "end_ms": t.end_ms,"text":""} for t in turns]
                metric["native_der_collar_0ms"] = scoring.der(reference["transcript"],native,duration_ms)
                metric["native_der_collar_250ms"] = scoring.der(reference["transcript"],native,duration_ms,250)
                native_count = len({t.speaker for t in turns})
                reference_count = metric["speakers"]["reference"]
                diagnostic = {"rawDiarizationTurns": base._turn_json(raw_turns), "diarizationTurns": base._turn_json(turns),
                    "mode": args.mode, "numClustersPassed": count, "threshold": threshold,
                    "thresholdApplied": args.mode in ("auto", "overcluster"), "windowShiftRatio": args.window_shift,
                    "threads": args.threads, "modelId": args.model_id, "modelSha256": entry["sha256"],
                    "diarizationInferenceMs": inference_ms, "modelLoadMs": load_ms,
                    "sessionReuse": "Same model config; set_config changes clustering only. Every process recomputes neural outputs.",
                    "newAsrInference": False, "asrEvidenceSha256": asr_record["evidence_sha256"],
                    "fixedCountSource": "manifest known-K research oracle, not deployment" if args.mode == "fixed" else "none",
                    "singleBypass": False,
                    "fixedSinglePolicy": "Actual diarizer process even K=1; separate production V1.6 single bypass comparison required",
                    "shortChunkCaveat": "Sherpa single-segmentation-chunk special case may skip embedding/clustering; no claim every threshold exercises those on short files."}
                diagnostic["newCleanWindowEmbeddingInference"] = False
                if args.collect_windows and (not args.window_profiles or profile in args.window_profiles):
                    window_start = time.perf_counter()
                    diagnostic["cleanEmbeddingWindows"] = extract_windows(samples, turns, model, args.threads, sherpa)
                    diagnostic["cleanWindowEmbeddingStageMs"] = (time.perf_counter()-window_start)*1000
                    diagnostic["newCleanWindowEmbeddingInference"] = True
                write_json(folder / "reference.json", reference)
                write_json(folder / "hypothesis.json", hypothesis)
                write_json(folder / "diagnostics.json", diagnostic)
                write_json(folder / "metrics.json", metric)
                record = {"id": case["id"], "split": case["split"], "profile": profile, "mode": args.mode,
                    "model_id": args.model_id, "threshold": threshold, "window_shift": args.window_shift,
                    "audio_sha256": case["audio_sha256"], "reference_sha256": reference_hash,
                    "duration_ms": duration_ms, "diarization_inference_ms": inference_ms,
                    "native_speaker_count": native_count, "reference_speaker_count": reference_count,
                    "native_speaker_count_error": abs(native_count-reference_count), "metrics": metric,
                    "new_diarization_inference": True, "new_asr_inference": False,
                    "evidence_sha256": evidence_hashes(folder), "completed_at": datetime.now(timezone.utc).isoformat()}
                write_json(folder / "case.json", record);records.append(record)
                save_csv(output,records)
                write_json(output / "summary.json", {"status":"RUNNING","profiles":{p:summarize([r for r in records if r["profile"]==p])for p in sorted({r["profile"]for r in records})}})
                print(json.dumps({"case":case["id"],"profile":profile,"model":args.model_id,"speakers":native_count,"reference":reference_count,"native_der_errors_fraction":metric["native_der_collar_0ms"]["rate"]}),flush=True)
        save_csv(output,records)
        meta.update(status="COMPLETE",completed_at=datetime.now(timezone.utc).isoformat())
        write_json(output / "run.json",meta)
        write_json(output / "summary.json", {"status":"COMPLETE","profiles":{p:summarize([r for r in records if r["profile"]==p])for p in sorted({r["profile"]for r in records})}})
    except BaseException as error:
        meta.update(status="FAILED",error=str(error));write_json(output / "run.json",meta)
        save_csv(output,records)
        raise
    finally:
        if diarizer is not None:
            del diarizer
        gc.collect()


if __name__ == "__main__":
    main()
