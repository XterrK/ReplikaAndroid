#!/usr/bin/env python3
"""Explicit Android performance experiment; --check never invokes ADB/subprocess.

Four sequential batches (CPU2,4,4,2), each 1/3/10 minutes in one production-
Worker instrumentation invocation. No reference text/count reaches Android.
Full token/vector QA is deliberately disabled, not silently truncated. Snapshot
sampling adds overhead and never establishes continuous peak RAM or ARM speed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave
import zipfile

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(REPO))
from tools.eval import native_diar_policy as policy
from tools.eval import score as scoring
from tools.create_plan19_perf_corpus import PINS, AUDIO_SHA256, BLOCK_FRAMES

ORDER = (2, 4, 4, 2)
CASE_IDS = ("perf-01m", "perf-03m", "perf-10m")
DURATIONS = (60000, 180000, 600000)
BRIDGE = "ru.replika.EvaluationBatchTest#stagedCanonicalInputsThroughProductionWorker"
SCOPE = ("Related controlled 1/3/10-minute repeats; actual production Worker, CPU auto_v1 with explicit 2/4 threads. "
         "References remain host-only. Full tokens/vectors are not collected or replayed in this performance run. "
         "Stage PSS and periodic RSS/PSS/thermal samples are snapshots, not continuous peaks. "
         "Device caches/temperature, instrumentation and sampling overhead are uncontrolled; no causal speed, ARM, "
         "natural-dialogue or independent-quality acceptance is established.")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return policy.strict_json(Path(path).read_bytes())


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def confined(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path escapes source root")
    return path


def code_fingerprint():
    files = list((REPO / "app/src/main/java").rglob("*.kt"))
    files += [REPO / path for path in (
        "tools/run_plan19_perf.py", "tools/create_plan19_perf_corpus.py", "tools/eval/score.py",
        "tools/eval/native_diar_policy.py", "tools/eval/native_policy.py", "tools/eval/pipeline.py",
        "tools/eval/vad_words.py", "tools/eval/speaker_refiner.py", "tools/eval/window_overcluster.py",
        "app/src/androidTest/java/ru/replika/EvaluationBatchTest.kt", "app/build.gradle.kts",
        "app/src/main/assets/models-lock.json", "configs/eval/c2-window-selected-full.json")]
    return {str(path.relative_to(REPO)): sha(path) for path in sorted(set(files))}


def check_unchanged(checked):
    if code_fingerprint() != checked["fingerprint"]["code"]:
        raise ValueError("Source/configuration changed after preflight; preserve this run and start a fresh one")
    for name, expected in checked["fingerprint"]["local_files"].items():
        if sha(Path(name)) != expected:
            raise ValueError("Pinned input/reference/APK/model changed after preflight: " + name)


def preflight(args):
    """Read-only local pins/shape validation; no mkdir, ADB or subprocess."""
    if args.output.exists():
        raise ValueError("Use a fresh output; prior evidence is never overwritten")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", args.serial) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]+", args.package):
        raise ValueError("Unsafe explicit serial/package")
    if not 2 <= args.sample_seconds <= 120 or not math.isfinite(args.sample_seconds):
        raise ValueError("Snapshot interval must be finite within 2..120 seconds")
    if type(args.instrument_timeout_seconds) is not int or args.instrument_timeout_seconds < 1200:
        raise ValueError("Whole three-file instrumentation timeout must be at least 1200 seconds")
    manifest = read_json(args.manifest)
    cases = manifest.get("files")
    if (manifest.get("schema_version") != 1 or not isinstance(cases, list)
            or [row.get("id") for row in cases] != list(CASE_IDS)
            or [row.get("duration_ms") for row in cases] != list(DURATIONS)):
        raise ValueError("Exactly the frozen ordered 1/3/10-minute performance corpus is required")
    provenance_path = args.manifest.parent / "provenance.json"
    if sha(provenance_path) != manifest.get("source_provenance_sha256"):
        raise ValueError("Performance corpus provenance SHA differs")
    provenance = read_json(provenance_path)
    if provenance.get("status") != "COMPLETE" or provenance.get("new_model_inference") is not False:
        raise ValueError("Corpus must be complete and prepared without model inference")
    source = provenance.get("source", {})
    if source.get("source_audio_sha256") != AUDIO_SHA256 or source.get("source_metadata_sha256") != PINS:
        raise ValueError("Corpus no longer derives from the frozen dev source")
    snapshot_names = {"manifest.json": "source-manifest.json", "references/dev-01-two-clean.json": "source-reference.json",
                      "provenance.json": "source-provenance.json", "sources/LICENSE.md": "LICENSE.md"}
    for relative, expected in PINS.items():
        if sha(args.manifest.parent/"sources"/snapshot_names[relative]) != expected:
            raise ValueError("Frozen author source snapshot differs")
    author = read_json(args.manifest.parent/"sources/source-reference.json")["transcript"]
    indices = source.get("kept_utterance_indices")
    if indices != list(range(6)) or source.get("exact_prefix_frames") != 842543 or source.get("silence_padding_frames") != 117457:
        raise ValueError("Complete-utterance prefix/padding policy differs")
    author = [author[index] for index in indices]
    protocol_path = args.protocol
    protocol = read_json(protocol_path)
    if (protocol.get("threads_order") != list(ORDER) or protocol.get("case_order") != list(CASE_IDS)
            or protocol.get("collectEvidence") is not False or protocol.get("expected_speakers") != -1
            or protocol.get("cpu_plan") != "auto_v1"):
        raise ValueError("Frozen performance protocol differs")
    inputs = {}
    local = {str(args.manifest.resolve()): sha(args.manifest), str(provenance_path.resolve()): sha(provenance_path)}
    local[str(protocol_path.resolve())] = sha(protocol_path)
    for name in snapshot_names.values():
        path = (args.manifest.parent/"sources"/name).resolve()
        local[str(path)] = sha(path)
    for case in cases:
        audio = confined(args.audio_root, case["audio"])
        reference = confined(args.manifest.parent, case["reference"])
        if case.get("kind") != "related_controlled_repeat" or case.get("split") != "performance_proxy":
            raise ValueError("Do not rebrand related repeats as independent quality data")
        if any(type(case.get(key)) is not int or case[key] <= 0 for key in ("duration_ms", "frames", "repeat_blocks")):
            raise ValueError("Performance clock/repeat counts must be positive integers")
        if sha(audio) != case["audio_sha256"] or sha(reference) != case["reference_sha256"]:
            raise ValueError("Pinned performance audio/reference differs")
        with wave.open(str(audio), "rb") as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError("Only canonical 16k mono PCM16 WAV is accepted")
            if stream.getnframes() != case["frames"] or stream.getnframes() * 1000 // 16000 != case["duration_ms"]:
                raise ValueError("Canonical performance clock differs")
            first = stream.readframes(BLOCK_FRAMES)
            if hashlib.sha256(first).hexdigest() != source["block_pcm16_sha256"]:
                raise ValueError("Canonical repeated block SHA differs")
            if any(first[842543*2:]) or hashlib.sha256(first[:842543*2]).hexdigest() != source["prefix_pcm16_sha256"]:
                raise ValueError("Original prefix or silence padding differs")
            for _ in range(case["repeat_blocks"]-1):
                if stream.readframes(BLOCK_FRAMES) != first:
                    raise ValueError("Repeated PCM block differs")
        reference_document = read_json(reference)
        scoring._document(reference_document, case["duration_ms"])
        expected_reference = {"transcript": [{**row, "start_ms": row["start_ms"] + block*60000,
                                             "end_ms": row["end_ms"] + block*60000}
                                            for block in range(case["repeat_blocks"]) for row in author]}
        policy.equal(reference_document, expected_reference, "repeated literal author reference")
        inputs[case["id"]] = {"audio": audio, "reference": reference}
        local.update({str(audio): sha(audio), str(reference): sha(reference)})
    lock_path = REPO / "app/src/main/assets/models-lock.json"
    lock = read_json(lock_path);policy.validate_model_lock(lock)
    for row in lock["files"]:
        path = confined(args.model_root, row["path"])
        if path.stat().st_size != row["size"] or sha(path) != row["sha256"]:
            raise ValueError("Pinned local model differs: " + row["path"])
        local[str(path)] = row["sha256"]
    apks = {}
    for role, path in (("app", args.app_apk), ("test", args.test_apk)):
        apks[role] = {"sha256": sha(path), "bytes": path.stat().st_size}
        local[str(path.resolve())] = apks[role]["sha256"]
    with zipfile.ZipFile(args.app_apk) as archive:
        policy.validate_model_lock(policy.strict_json(archive.read("assets/models-lock.json")))
    with zipfile.ZipFile(args.test_apk) as archive:
        if not any(b"evalCollectEvidence" in archive.read(name) for name in archive.namelist() if re.fullmatch(r"classes[0-9]*\.dex", name)):
            raise ValueError("Test APK predates explicit evalCollectEvidence=false; rebuild the QA bridge first")
    bridge = (REPO / "app/src/androidTest/java/ru/replika/EvaluationBatchTest.kt").read_text()
    if "evalCollectEvidence" not in bridge:
        raise ValueError("QA source must explicitly implement evalCollectEvidence before a performance run")
    config = read_json(REPO / "configs/eval/c2-window-selected-full.json")
    for threads in set(ORDER):
        transient, paired = execution_config(config, threads)
        policy.validate_host_policy(transient, paired, cpu_plan="auto_v1", threads=threads)
    return {"cases": cases, "inputs": inputs, "models": lock, "config": config,
            "fingerprint": {"code": code_fingerprint(), "local_files": local, "apk": apks},
            "scope": SCOPE, "order": list(ORDER), "audio_ms_per_batch": sum(DURATIONS),
            "total_audio_ms": sum(DURATIONS) * len(ORDER), "workers": 12, "protocol": protocol}


def execution_config(config, threads):
    transient = {**config, "threads": threads, "cpu_plan": "auto_v1"}
    paired = {"plan": policy.ASR_PLAN, "vad_threshold": .5, "vad_min_speech_sec": .25,
        "vad_min_silence_sec": .25, "pre_roll_ms": 600, "punctuation_mode": "none", "energy_split": True,
        "threads": threads, "provider": "cpu", "sample_rate": 16000, "feature_dim": 80, "dither": 0.0,
        "model_type": "nemo_transducer", "decoding_method": "greedy_search", "max_active_paths": 4,
        "modeling_unit": "", "hotwords_file": "", "blank_penalty": 0.0, "vad_window_samples": 512, "max_asr_ms": 20000}
    return transient, paired


def validate_case_copy(native_case, report_case):
    """Bind the complete pulled case to the same object in the batch report."""
    if not isinstance(native_case, dict) or not isinstance(report_case, dict):
        raise ValueError("Native case/report entry must be JSON objects")
    policy.equal(native_case, report_case, "native case file/batch report copy")


def update_verified_progress(report, *, requested=False):
    """Count only cases appended after contract checks and independent scoring."""
    verified = sum(len(batch["cases"]) for batch in report["batches"])
    planned = report["planned_workers"]
    if type(planned) is not int or planned <= 0 or verified > planned:
        raise ValueError("Invalid planned/verified Worker coverage")
    report.update(verified_workers=verified, completed_workers=verified,
                  inference_completion_verified=verified == planned)
    if verified:
        report["new_model_inference"] = True
    elif requested:
        report["new_model_inference"] = None  # Requested but actual completion remains unverified.
    return verified


def validate_compact_case(case, native, diagnostic, hypothesis, config, threads):
    duration = native.get("duration_ms");processing = native.get("processing_ms")
    if (native.get("id") != case["id"] or native.get("status") != "COMPLETE" or native.get("newModelInference") is not True
            or native.get("audio_sha256") != case["audio_sha256"] or type(duration) is not int
            or abs(duration - case["duration_ms"]) > 1 or type(processing) is not int or processing <= 0):
        raise ValueError("Actual Worker case identity/clock/timing differs")
    if native.get("collectEvidence") is not False:
        raise ValueError("Bridge must explicitly confirm collectEvidence=false in each case")
    if native.get("workManagerState") != "SUCCEEDED" or type(native.get("processId")) is not int or native["processId"] <= 0:
        raise ValueError("Real Worker completion/process evidence missing")
    try:
        if str(uuid.UUID(native.get("workId", ""))) != native["workId"]:
            raise ValueError("Noncanonical work UUID")
        if not native.get("recordingId", "").startswith("qa-evaluation-") or str(uuid.UUID(native["recordingId"][14:])) != native["recordingId"][14:]:
            raise ValueError("Noncanonical own QA recording UUID")
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid actual WorkManager/recording identity") from error
    transient, paired = execution_config(config, threads)
    policy.validate_native_diar_policy(transient, diagnostic, paired, cpu_plan="auto_v1", threads=threads)
    for key, expected in {"runtime": "sherpa-onnx 2.0.1", "backend": policy.base.SOURCE,
                          "sampleRate": 16000, "vadThreads": 1, "maxAsrSegmentMs": 20000}.items():
        policy.equal(diagnostic.get(key), expected, key)
    for key, expected in {"wordEvidenceRequested": False, "wordEvidenceBytes": 0,
                          "wordEvidenceTruncated": False, "audioMs": duration, "totalMs": processing}.items():
        policy.equal(diagnostic.get(key), expected, key)
    if any(key.startswith("diarizationEvidence") for key in diagnostic):
        raise ValueError("QA=false production path must omit full diarization sidecar fields")
    if diagnostic.get("diarizationRefinementAccepted") is not True:
        raise ValueError("Actual selected refiner did not accept computation")
    adapter = diagnostic.get("diarizationRefinement", {})
    for key, expected in {"cpuPlan": "auto_v1", "embeddingThreads": threads, "algorithm": "window-overcluster-v1"}.items():
        policy.equal(adapter.get(key), expected, "adapter." + key)
    if type(adapter.get("status")) is not str or adapter["status"] not in ("SUPPORTED", "PARTIAL_TEMPORAL"):
        raise ValueError("Selected refiner computational status is unsupported")
    for key in ("nativeResourcesReleasedBeforeRefiner", "originalPcm", "embeddingInferenceCompleted", "computationalSupport"):
        if adapter.get(key) is not True:
            raise ValueError("Actual refinement lifecycle/support flag missing: " + key)
    if adapter.get("retainedNativeModelCache") is not False:
        raise ValueError("Unexpected retained native model cache")
    policy.equal(adapter.get("config"), policy.WINDOW_CONFIG, "adapter.config")
    counts = diagnostic.get("diarizationEmbeddingCounts", {})
    count = counts.get("measuredWindows")
    if type(count) is not int or count <= 0 or type(counts.get("extractorLoads")) is not int or counts.get("extractorLoads") != 1 or type(counts.get("embeddingDimension")) is not int or counts.get("embeddingDimension") != 512:
        raise ValueError("Actual window embedding inference counts missing")
    for key in ("plannedWindows", "readWindows", "createdStreams", "releasedStreams", "computeAttempts", "embeddingForwardCalls"):
        if type(counts.get(key)) is not int or counts[key] != count:
            raise ValueError("Unbalanced actual embedding lifecycle count: " + key)
    parts = diagnostic.get("asrSlices")
    if not isinstance(parts, list) or not parts or diagnostic.get("wordProcessedChunks") != len(parts):
        raise ValueError("Actual ASR chunk summary missing")
    previous = 0
    for part in parts:
        a, b = part.get("startMs"), part.get("endMs")
        if type(a) is not int or type(b) is not int or not previous <= a < b <= duration or b-a > 20000:
            raise ValueError("ASR chunk clock invalid")
        previous = b
        if (part.get("wordEvidenceIncluded") is not False or part.get("wordEvidenceOmittedReason") != "not_requested"
                or any(key in part for key in ("tokens", "timestamps", "words"))):
            raise ValueError("Full word QA was collected/truncated instead of disabled")
        if type(part.get("text")) is not str or type(part.get("blank")) is not bool or part.get("blank") != (not part["text"].strip()):
            raise ValueError("Invalid actual ASR text/blank summary")
        if type(part.get("frameStrideMs")) is not int or part["frameStrideMs"] != 40:
            raise ValueError("Unverified compact model token clock")
        for key in ("tokenCount", "timestampCount", "wordCount"):
            if type(part.get(key)) is not int or part[key] < 0:
                raise ValueError("Actual compact ASR count invalid")
    rows = scoring._document(hypothesis, duration)
    if " ".join(row.text for row in rows).split() != " ".join(part["text"] for part in parts).split():
        raise ValueError("Exported Jury words differ from actual compact ASR text")
    return {"asr_chunks": len(parts), "reported_tokens": sum(part["tokenCount"] for part in parts),
            "reported_words": sum(part["wordCount"] for part in parts), "measured_embedding_windows": count,
            "resources_balanced": True, "compact_asr_text_preserved": True,
            "full_token_vector_replay_performed": False}


def score_case(reference, hypothesis, diagnostic, duration, processing):
    metrics = scoring.score(reference, hypothesis, duration, processing_ms=processing)
    turns = policy.turns_from_json(diagnostic["diarizationTurns"], duration)
    rows = [{"speaker_id": str(turn.speaker), "start_ms": turn.start_ms, "end_ms": turn.end_ms, "text": ""} for turn in turns]
    for collar in (0, 250):
        metrics[f"native_der_collar_{collar}ms"] = scoring.der(reference["transcript"], rows, duration, collar_ms=collar)
    metrics["native_speaker_count"] = len({turn.speaker for turn in turns})
    return metrics


def batch_summary(records):
    result = {"cases": len(records), "audio_ms": sum(row["duration_ms"] for row in records),
              "processing_ms": sum(row["processing_ms"] for row in records)}
    result["rtf"] = result["processing_ms"] / result["audio_ms"] if result["audio_ms"] else None
    for name in ("wer_raw", "wer_normalized", "cpwer_raw"):
        errors = sum(row["metrics"][name]["errors"] for row in records)
        words = sum(row["metrics"][name]["reference_tokens"] for row in records)
        result[name] = {"errors": errors, "reference_tokens": words, "rate": errors/words if words else None}
    return result


def sampled_resources(directory):
    samples = [json.loads(line) for line in (directory/"samples.jsonl").read_text().splitlines() if line]
    return {"scope": "Observed periodic batch snapshots only, not continuous peak; startup samples excluded until instrumentation report exists",
            "samples": len(samples), "errors": sum("error" in row for row in samples),
            "observed_pids": sorted({row["pids"] for row in samples if row.get("pids")}),
            "maximum_observed_rss_kb": max((row["rss_kb"] for row in samples if row.get("rss_kb") is not None), default=None),
            "maximum_observed_pss_kb": max((row["pss_kb"] for row in samples if row.get("pss_kb") is not None), default=None)}


def write_csv(path, batches):
    fields = ["batch", "threads", "case", "audio_ms", "processing_ms", "rtf", "raw_errors", "reference_words",
              "wer_raw", "wer_normalized", "cpwer_raw", "native_der_0ms", "native_der_250ms", "native_speakers",
              "stage_observed_max_pss_kb", "thermal_wait_ms", "thermal_status_available", "new_model_inference", "full_qa_replay"]
    temporary = path.with_name(path.name+".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields);writer.writeheader()
        for batch in batches:
            for row in batch["cases"]:
                metrics, telemetry = row["metrics"], row.get("telemetry") or {}
                writer.writerow({"batch": batch["batch"], "threads": batch["threads"], "case": row["id"],
                    "audio_ms": row["duration_ms"], "processing_ms": row["processing_ms"], "rtf": metrics["rtf"],
                    "raw_errors": metrics["wer_raw"]["errors"], "reference_words": metrics["wer_raw"]["reference_tokens"],
                    "wer_raw": metrics["wer_raw"]["rate"], "wer_normalized": metrics["wer_normalized"]["rate"],
                    "cpwer_raw": metrics["cpwer_raw"]["rate"], "native_der_0ms": metrics["native_der_collar_0ms"]["rate"],
                    "native_der_250ms": metrics["native_der_collar_250ms"]["rate"], "native_speakers": metrics["native_speaker_count"],
                    "stage_observed_max_pss_kb": telemetry.get("observedMaxPssKb"),
                    "thermal_wait_ms": (row.get("stages_ms") or {}).get("thermalWaitMs"),
                    "thermal_status_available": telemetry.get("thermalStatusAvailable"),
                    "new_model_inference": True, "full_qa_replay": False})
    temporary.replace(path)


def run(args):
    checked = preflight(args)
    if args.check:
        print(json.dumps({"status": "PREFLIGHT_PASS", "read_only": True, "adb_invoked": False, "new_model_inference": False,
                          **{key: value for key, value in checked.items() if key not in ("inputs", "models", "config")}}, ensure_ascii=False, indent=2))
        return 0
    if not args.execute:
        raise ValueError("Actual ADB/Worker inference requires explicit --execute")
    args.output.mkdir(parents=True)
    report = {"schema_version": 1, "status": "STAGING", "created_utc": now(), "scope": SCOPE,
        "fingerprint": checked["fingerprint"], "protocol": checked["protocol"], "reference_text_or_counts_staged": False,
        "collectEvidence": False, "inference_requested": False, "batches": [], "order": list(ORDER),
        "new_model_inference": False, "inference_completion_verified": False,
        "verified_workers": 0, "completed_workers": 0,
        "planned_workers": 12, "planned_audio_ms": checked["total_audio_ms"], "serial": args.serial,
        "snapshot_interval_seconds": args.sample_seconds, "instrument_timeout_seconds": args.instrument_timeout_seconds,
        "scoring_python": sys.version}
    write_json(args.output / "run.json", report)
    write_csv(args.output/"results.csv", [])
    for relative, expected in checked["fingerprint"]["code"].items():
        saved = args.output/"source-snapshots"/relative
        saved.parent.mkdir(parents=True, exist_ok=True);shutil.copyfile(REPO/relative, saved)
        if sha(saved) != expected:
            raise ValueError("Source changed while archiving its preflight snapshot")
    command_lock = threading.Lock()
    def command(*words):
        argv = [args.adb, "-s", args.serial, *map(str, words)]
        with command_lock, (args.output / "commands.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": now(), "argv": argv}) + "\n")
        return argv
    def adb(*words, check=True, timeout=120):
        result = subprocess.run(command(*words), capture_output=True, timeout=timeout)
        if check and result.returncode:
            raise RuntimeError("ADB failed: " + result.stderr.decode("utf-8", "replace"))
        return result
    def push(local, remote):
        if not re.fullmatch(r"files/evaluation/[A-Za-z0-9_/-]+(?:\.wav|\.json)", remote) or ".." in PurePosixPath(remote).parts:
            raise ValueError("Unsafe private staged path")
        temporary = "/data/local/tmp/" + PurePosixPath(remote).name + "-" + session
        adb("push", local, temporary)
        adb("shell", "run-as", args.package, "mkdir", "-p", str(PurePosixPath(remote).parent))
        adb("shell", "run-as", args.package, "cp", temporary, remote)
        adb("shell", "rm", temporary)
    def pull(remote, local):
        result = adb("exec-out", "run-as", args.package, "cat", remote, check=False)
        if result.returncode == 0:
            Path(local).write_bytes(result.stdout)
            return True
        return False
    def sample(stop, directory, remote_report):
        index = 0
        while not stop.is_set():
            stamp = {"at": now(), "monotonic_seconds": time.monotonic(), "scope": "periodic snapshot; not continuous peak"}
            try:
                # Exclude the Activity process before instrumentation's own report exists.
                ready = adb("shell", "run-as", args.package, "test", "-e", remote_report, check=False, timeout=10).returncode == 0
                if ready:
                    pids = adb("shell", "pidof", args.package, check=False, timeout=10).stdout.decode().strip()
                    stamp["pids"] = pids
                    if re.fullmatch(r"[0-9]+", pids):
                        raw = adb("exec-out", "run-as", args.package, "cat", f"/proc/{pids}/status", check=False, timeout=10)
                        (directory / f"sample-{index:05d}-proc.txt").write_bytes(raw.stdout)
                        match = re.search(rb"^VmRSS:\s+(\d+)\s+kB", raw.stdout, re.M)
                        stamp["rss_kb"] = int(match[1]) if match else None
                    memory = adb("shell", "dumpsys", "meminfo", args.package, check=False, timeout=10).stdout
                    (directory / f"sample-{index:05d}-meminfo.txt").write_bytes(memory)
                    match = re.search(rb"TOTAL PSS:\s*(\d+)", memory)
                    stamp["pss_kb"] = int(match[1]) if match else None
                    (directory / f"sample-{index:05d}-thermal.txt").write_bytes(adb("shell", "dumpsys", "thermalservice", check=False, timeout=10).stdout)
                else:
                    stamp["state"] = "waiting_for_instrumentation_report"
            except Exception as error:
                stamp["error"] = str(error)
            with (directory / "samples.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(stamp) + "\n")
            index += 1
            stop.wait(args.sample_seconds)
    session = "p19perf" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    prior_stay = None
    seen_work_ids, seen_recordings = set(), set()
    try:
        check_unchanged(checked)
        if adb("get-state").stdout.strip() != b"device" or adb("shell", "getprop", "ro.kernel.qemu").stdout.strip() != b"1":
            raise ValueError("Explicit ready emulator required; physical/ARM acceptance is a separate experiment")
        report["device"] = {name: adb("shell", "getprop", prop).stdout.decode().strip() for name, prop in (
            ("fingerprint", "ro.build.fingerprint"), ("abi", "ro.product.cpu.abi"), ("sdk", "ro.build.version.sdk"))}
        report["network_settings_observed"] = {name: adb("shell", "settings", "get", "global", name).stdout.decode().strip()
                                               for name in ("airplane_mode_on", "wifi_on")}
        report["installed_apks"] = {}
        for role, package in (("app", args.package), ("test", args.package + ".test")):
            paths = adb("shell", "pm", "path", package).stdout.decode().splitlines()
            if len(paths) != 1 or not paths[0].startswith("package:/data/app/"):
                raise ValueError("One installed base APK required")
            path = paths[0][8:]
            if not re.fullmatch(r"/data/app/[A-Za-z0-9_~./=+-]+\.apk", path) or ".." in PurePosixPath(path).parts:
                raise ValueError("Unsafe installed APK path")
            actual = adb("exec-out", "sha256sum", path).stdout.decode().split()[0]
            if actual != checked["fingerprint"]["apk"][role]["sha256"]:
                raise ValueError("Installed/local APK SHA mismatch: " + role)
            report["installed_apks"][role] = {"package": package, "path": path, "sha256": actual}
        report["native_model_sha256_before"] = {}
        for row in checked["models"]["files"]:
            actual = adb("exec-out", "run-as", args.package, "sha256sum", "files/models/" + row["path"]).stdout.decode().split()[0]
            if actual != row["sha256"]:
                raise ValueError("Actual Android model SHA mismatch: " + row["path"])
            report["native_model_sha256_before"][row["path"]] = actual
        prior_stay = adb("shell", "settings", "get", "global", "stay_on_while_plugged_in").stdout.decode().strip()
        if prior_stay != "null" and not re.fullmatch(r"[0-9]+", prior_stay):
            prior_stay = None;raise ValueError("Unexpected original stay-on setting")
        adb("shell", "input", "keyevent", "KEYCODE_WAKEUP");adb("shell", "wm", "dismiss-keyguard")
        adb("shell", "svc", "power", "stayon", "true")
        adb("shell", "am", "start", "-W", "-n", args.package + "/ru.replika.MainActivity")
        for index, threads in enumerate(ORDER):
            check_unchanged(checked)
            directory = args.output / f"batch-{index+1:02d}-threads{threads}";directory.mkdir()
            run_id = f"{session}_{index+1}"
            remote = "files/evaluation/" + run_id
            if adb("shell", "run-as", args.package, "test", "-e", remote, check=False).returncode == 0:
                raise ValueError("Remote run exists; preserve it")
            batch = {"schema_version": 1, "run": run_id, "cases": [
                {"id": row["id"], "audio": "audio/" + row["id"] + ".wav", "sha256": row["audio_sha256"]}
                for row in checked["cases"]]}
            write_json(directory / "batch.json", batch)
            for case in checked["cases"]:
                push(checked["inputs"][case["id"]]["audio"], remote + "/audio/" + case["id"] + ".wav")
            push(directory / "batch.json", remote + "/batch.json")
            state = {"batch": index+1, "threads": threads, "run": run_id, "status": "RUNNING", "cases": []}
            report["batches"].append(state);report.update(status="RUNNING", inference_requested=True)
            update_verified_progress(report, requested=True)
            write_json(args.output / "run.json", report)
            stop = threading.Event()
            sampler = threading.Thread(target=sample, args=(stop, directory, remote+"/output/report.json"), daemon=True)
            sampler.start()
            logger = None
            try:
                with (directory/"stage-pss-logcat.txt").open("wb") as stage_log, (directory/"stage-pss-logcat.stderr").open("wb") as stage_error:
                    logger = subprocess.Popen(command("logcat", "-v", "epoch", "-T", "1", "-s", "ReplikaPerf:I", "*:S"), stdout=stage_log, stderr=stage_error)
                    with (directory/"instrumentation.log").open("wb") as log, (directory/"instrumentation.stderr").open("wb") as error:
                        actual = subprocess.run(command("shell", "am", "instrument", "-w", "-r", "-e", "evalRun", run_id,
                            "-e", "evalThreads", threads, "-e", "evalExpectedSpeakers", "-1", "-e", "evalCpuPlan", "auto_v1",
                            "-e", "evalAsrPlan", policy.ASR_PLAN, "-e", "evalDiarPlan", policy.PLAN,
                            "-e", "evalCollectEvidence", "false", "-e", "class", BRIDGE,
                            args.package+".test/androidx.test.runner.AndroidJUnitRunner"), stdout=log, stderr=error,
                            timeout=args.instrument_timeout_seconds)
                        state["instrumentation_exit_code"] = actual.returncode
            finally:
                stop.set();sampler.join(timeout=60)
                if logger is not None:
                    logger.terminate()
                    try: logger.wait(timeout=10)
                    except subprocess.TimeoutExpired: logger.kill();logger.wait()
                # Collect partial outputs even for instrumentation failure/nonzero/timeout.
                pull(remote+"/output/report.json", directory/"instrumentation-report.json")
                for case in checked["cases"]:
                    for suffix in ("hypothesis", "diagnostics", "case"):
                        pull(remote+f"/output/{case['id']}.{suffix}.json", directory/f"{case['id']}.{suffix}.json")
            raw_log = (directory/"instrumentation.log").read_bytes()
            if (state.get("instrumentation_exit_code") != 0 or not re.search(rb"OK \(1 tests?\)", raw_log)
                    or re.search(rb"FAILURES!!!|INSTRUMENTATION_FAILED|Process crashed", raw_log)):
                raise ValueError("Instrumentation failed; raw/partial outputs preserved")
            native_report = read_json(directory/"instrumentation-report.json")
            transient, paired = execution_config(checked["config"], threads)
            policy.validate_native_diar_policy(transient, native_report, paired, cpu_plan="auto_v1", threads=threads)
            if (native_report.get("status") != "COMPLETE" or native_report.get("collectEvidence") is not False or native_report.get("newModelInference") is not True
                    or [case.get("id") for case in native_report.get("cases", [])] != list(CASE_IDS)):
                raise ValueError("Expected a complete ordered compact-QA three-file batch")
            if type(native_report.get("processId")) is int and native_report["processId"] > 0:
                process_ids = [case.get("processId") for case in native_report["cases"]]
                if any(pid != native_report["processId"] for pid in process_ids):
                    raise ValueError("Three-file batch did not retain its instrumented process ID")
                state["single_instrumented_process_id"] = native_report["processId"]
            else:
                raise ValueError("Instrumented process ID missing")
            for case in checked["cases"]:
                identity = case["id"]
                native = read_json(directory/f"{identity}.case.json")
                validate_case_copy(native, next(row for row in native_report["cases"] if row["id"] == identity))
                diagnostic = read_json(directory/f"{identity}.diagnostics.json")
                hypothesis = read_json(directory/f"{identity}.hypothesis.json")
                counts = validate_compact_case(case, native, diagnostic, hypothesis, checked["config"], threads)
                if native["workId"] in seen_work_ids or native["recordingId"] in seen_recordings:
                    raise ValueError("Every actual Worker must have fresh work/recording UUIDs")
                seen_work_ids.add(native["workId"]);seen_recordings.add(native["recordingId"])
                reference_path = checked["inputs"][identity]["reference"]
                reference = read_json(reference_path)
                metrics = score_case(reference, hypothesis, diagnostic, native["duration_ms"], native["processing_ms"])
                shutil.copyfile(reference_path, directory/f"{identity}.reference.json")
                write_json(directory/f"{identity}.metrics.json", metrics)
                state["cases"].append({"id": identity, "duration_ms": native["duration_ms"], "processing_ms": native["processing_ms"],
                    "metrics": metrics, "compact_evidence": counts, "stages_ms": diagnostic.get("stagesMs"),
                    "work_id": native["workId"], "recording_id": native["recordingId"], "process_id": native["processId"],
                    "telemetry": diagnostic.get("telemetry"), "new_model_inference": True,
                    "evidence_sha256": {suffix: sha(directory/f"{identity}.{suffix}.json") for suffix in ("reference", "hypothesis", "diagnostics", "case", "metrics")}})
                update_verified_progress(report)
                write_csv(args.output/"results.csv", report["batches"])
            state.update(status="COMPLETE", summary=batch_summary(state["cases"]), sampled_resources=sampled_resources(directory))
            check_unchanged(checked);write_json(args.output/"run.json", report)
        report["native_model_sha256_after"] = {}
        for row in checked["models"]["files"]:
            actual = adb("exec-out", "run-as", args.package, "sha256sum", "files/models/" + row["path"]).stdout.decode().split()[0]
            if actual != row["sha256"]:
                raise ValueError("Actual Android model changed during the experiment")
            report["native_model_sha256_after"][row["path"]] = actual
        if update_verified_progress(report) != report["planned_workers"]:
            raise ValueError("All twelve planned Workers must be verified before completion")
        report.update(status="COMPLETE",
                      completed_audio_ms=sum(row["duration_ms"] for batch in report["batches"] for row in batch["cases"]))
        comparisons = []
        for first, second in ((0,1), (3,2)):
            two, four = report["batches"][first], report["batches"][second]
            comparisons.append({"threads2_batch": first+1, "threads4_batch": second+1,
                "threads4_over_threads2_processing_ratio": four["summary"]["processing_ms"]/two["summary"]["processing_ms"],
                "scope": "Paired descriptive ratio with order retained; uncontrolled conditions, no causal speed claim",
                "per_case": [{"id": a["id"], "threads4_over_threads2_ratio": b["processing_ms"]/a["processing_ms"],
                    "raw_errors_threads2": a["metrics"]["wer_raw"]["errors"], "raw_errors_threads4": b["metrics"]["wer_raw"]["errors"]}
                    for a,b in zip(two["cases"],four["cases"])]})
        report["paired_comparisons"] = comparisons
        write_json(args.output/"run.json", report)
        return 0
    except BaseException as error:
        report.update(status="FAILED", error=repr(error), failed_utc=now())
        update_verified_progress(report, requested=report["inference_requested"])
        report["inference_may_still_be_running"] = any(batch["status"] == "RUNNING" for batch in report["batches"])
        write_json(args.output/"run.json", report)
        raise
    finally:
        if prior_stay is not None:
            try:
                if prior_stay == "null": adb("shell", "settings", "delete", "global", "stay_on_while_plugged_in")
                else: adb("shell", "settings", "put", "global", "stay_on_while_plugged_in", prior_stay)
                restored = adb("shell", "settings", "get", "global", "stay_on_while_plugged_in").stdout.decode().strip()
                report["screen_power"] = {"original": prior_stay, "restored": restored, "restored_exactly": restored == prior_stay}
                if restored != prior_stay: raise ValueError("Original stay-on setting did not restore")
            except Exception as error:
                report.update(status="FAILED", restoration_error=repr(error))
                write_json(args.output/"run.json", report)
                raise
            write_json(args.output/"run.json", report)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    choice = result.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check", action="store_true", help="Read-only local preflight; no output, subprocess or ADB")
    choice.add_argument("--execute", action="store_true", help="Explicitly start twelve actual Workers on the named emulator")
    result.add_argument("--adb", default=shutil.which("adb") or "adb")
    result.add_argument("--serial", required=True)
    result.add_argument("--package", default="ru.replika.offline")
    result.add_argument("--manifest", type=Path, default=REPO/"benchmark/eval-perf/manifest.json")
    result.add_argument("--protocol", type=Path, default=REPO/"benchmark/eval-perf/protocol.json")
    result.add_argument("--audio-root", type=Path, required=True)
    result.add_argument("--model-root", type=Path, default=REPO/"model-pack")
    result.add_argument("--app-apk", type=Path, required=True)
    result.add_argument("--test-apk", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--sample-seconds", type=float, default=10)
    result.add_argument("--instrument-timeout-seconds", type=int, default=5400)
    return result


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
