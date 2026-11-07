#!/usr/bin/env python3
"""Fresh C2 production-Worker QA; preflight every local pin before any ADB.

Only canonical audio, IDs/hashes, and global policies enter instrumentation.
Independent author references/counts remain local. Pure sidecar/token replay
verifies the actual Android evidence before independent scoring. No native PCM
SHA is invented: canonical input/clock + the unchanged, separately audited
AudioDecoder and real token frameStride40 are the decoder evidence scope.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import wave
import zipfile

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.eval import native_diar_policy as policy
from tools.eval import pipeline as base
from tools.eval import score as scoring
from tools.eval.diar_sweep import load_asr, project_asr
from tools.eval.port_comparison import summarize
from tools.eval.run import REPO, aggregate, confined, digest, evidence_hashes, write_json, write_csv
from tools.eval.speaker_refiner import EmbeddingWindow
from tools.eval.window_overcluster import WindowClusterConfig, overcluster

FIXED_FIVE = ("dev-01-two-clean", "dev-03-short", "holdout-02-three-clean",
              "holdout-04-overlap-expressive", "dev-mono-s")
HOST_CODE = {"tools/eval/" + name + ".py" for name in (
    "run_refined", "pipeline_refined", "score", "pipeline", "pipeline_words", "diar_sweep",
    "decoder_parity", "vad_words", "speaker_refiner", "run", "window_overcluster")}
FIXED_DEV_SUMMARY_SHA256 = "6cf29600a98830f2b9fd76d9728f4aadaca0233c5d9de437dbf76e347e13417d"
SCOPE = ("Actual production Worker C2 QA; no reference text/counts staged. WER parity is weighted "
         "over the historical fixed five only; dev8 native count/DER reported separately. "
         "Canonical source WAV hash/shape/clock and frameStride40 are checked; unchanged "
         "AudioDecoder has separate D PCM parity evidence, no new native PCM SHA is claimed. "
         "x86 emulator evidence is not ARM/phone speed, memory or natural-dialogue acceptance.")


def read_json(path):
    return policy.strict_json(Path(path).read_bytes())


def collector_code_fingerprint():
    """Native QA semantics are separate from the already frozen host NN pins."""
    paths = (Path(__file__), Path(policy.__file__), Path(__file__).with_name("native_policy.py"),
             Path(__file__).with_name("port_comparison.py"))
    return {str(path.relative_to(REPO)): digest(path) for path in paths}


def verify_collector_code(fingerprint):
    if fingerprint != collector_code_fingerprint():
        raise ValueError("Native collector semantic sources changed after preflight")


def canonical_audio(path, duration):
    with wave.open(str(path), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, 16000, "NONE"):
            raise ValueError("Expected original canonical mono PCM16 16kHz WAV")
        frames = stream.getnframes()
        if frames * 1000 // 16000 != duration or len(stream.readframes(frames)) != frames * 2:
            raise ValueError("Canonical frame count/duration/truncation differs")
    return frames


def _host_case(host_run, case, reference, fingerprint):
    """Rehash/recompute actual host evidence; no neural inference or refiner K."""
    folder = confined(host_run, case["id"])
    record = read_json(folder / "case.json")
    if (record.get("id") != case["id"] or record.get("audio_sha256") != case["audio_sha256"]
            or record.get("reference_sha256") != digest(reference)
            or record.get("duration_ms") != case["duration_ms"]
            or record.get("asr_replay") is not False
            or any(record.get(k) is not True for k in ("new_model_inference", "new_diarization_inference", "new_embedding_inference", "new_asr_inference"))):
        raise ValueError("Incomplete/mismatched full host inference: " + case["id"])
    actual_hashes = evidence_hashes(folder)
    if record.get("evidence_sha256") != actual_hashes or digest(reference) != actual_hashes["reference.json"]:
        raise ValueError("Host case evidence/reference hashes differ: " + case["id"])
    diagnostic = read_json(folder / "diagnostics.json")
    metric = read_json(folder / "metrics.json")
    hypothesis = read_json(folder / "hypothesis.json")
    if metric != record.get("metrics"):
        raise ValueError("Host metrics copies differ")
    policy.equal(diagnostic.get("config"), {"provider": "cpu", "threads": 2, "vadThreads": 1,
        "nativeNumClusters": -1, "nativeThreshold": .3, "segmentationWindowShiftRatio": .1,
        "diarMinDurationOnSec": .2, "diarMinDurationOffSec": .5, "cleanWindowMs": 1500,
        "cleanWindowStepMs": 750, "cleanMinimumIslandMs": 1000,
        "refiner": policy.WINDOW_CONFIG, "asr": fingerprint["paired_asr_policy"]}, "host.diag.config")
    policy.equal(diagnostic.get("windowConfig"), policy.WINDOW_CONFIG, "host.windowConfig")
    policy.equal(diagnostic.get("selectedNativePolicy"), {"model_id": "eres2net_zh", "threshold": .3,
        "window_shift": .1, "threads": 2, "num_clusters": -1}, "host.selectedNativePolicy")
    policy.equal(diagnostic.get("pairedAsrPolicy"), fingerprint["paired_asr_policy"], "host.diag.asr")
    if (diagnostic.get("audioSha256") != case["audio_sha256"] or diagnostic.get("audioMs") != case["duration_ms"]
            or diagnostic.get("sampleRate") != 16000 or diagnostic.get("pipelineVariant") != "window_words_v1"
            or diagnostic.get("runtime") != "sherpa-onnx 2.0.1" or diagnostic.get("refinerAccepted") is not True
            or diagnostic.get("refinerFallbackToNative") is not False
            or diagnostic.get("wordAssignmentSupported") is not True or diagnostic.get("fallbackChunks") != 0
            or diagnostic.get("nativeModelCacheRetained") is not False
            or any(diagnostic.get(k) is not True for k in ("newDiarizationInference", "newEmbeddingInference", "newAsrInference"))):
        raise ValueError("Unsupported/incomplete host C2 evidence")
    models = diagnostic.get("modelFiles", [])
    if [(x.get("path"), x.get("bytes"), x.get("sha256")) for x in models] != list(policy.MODEL_PINS):
        raise ValueError("Host per-case model pins differ")
    stride = diagnostic.get("tokenTimestampPolicy", {})
    if stride.get("verified") is not True or stride.get("frame_stride_ms") != 40:
        raise ValueError("Unverified host token clock")
    native = policy.turns_from_json(diagnostic["nativeDiarizationTurns"], case["duration_ms"])
    raw = policy.turns_from_json(diagnostic["rawDiarizationTurns"], case["duration_ms"])
    if base.stable_turns(raw) != native:
        raise ValueError("Host native stable mapping differs")
    windows = [EmbeddingWindow(**{**w, "embedding": tuple(w["embedding"])}) for w in diagnostic["cleanEmbeddingWindows"]]
    if not windows or any(len(w.embedding) != 512 for w in windows):
        raise ValueError("Missing host real 512-dimensional vectors")
    replay = overcluster(native, windows, case["duration_ms"], WindowClusterConfig(**policy.WINDOW_CONFIG))
    if not replay.accepted or policy.turn_json(replay.turns) != diagnostic.get("diarizationTurns") or diagnostic.get("refinedDiarizationTurns") != diagnostic.get("diarizationTurns"):
        raise ValueError("Host C2 pure replay differs")
    chunks, _, source = load_asr(folder, case, digest(reference))
    if project_asr(chunks, list(replay.turns), source) != hypothesis:
        raise ValueError("Host actual words/Jury projection differs")
    recomputed = score_case(read_json(reference), hypothesis, diagnostic, case["duration_ms"], record["processing_ms"])
    for key in ("wer_raw", "wer_normalized", "cpwer_raw", "native_der_collar_0ms", "native_der_collar_250ms"):
        if recomputed[key] != metric[key]:
            raise ValueError("Host independent metrics differ: " + key)
    return record


def preflight(args):
    """Read-only: all local evidence checks precede mkdir, subprocess or ADB."""
    if args.output.exists():
        raise ValueError("Choose a fresh output path; evidence is never overwritten")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]+", args.package):
        raise ValueError("Unsafe package name")
    if args.threads != 2 or type(args.threads) is not int or args.expected_speakers != -1 or type(args.expected_speakers) is not int:
        raise ValueError("Frozen C2 requires threads2 and automatic -1")
    if args.asr_plan != policy.ASR_PLAN or args.diar_plan != policy.PLAN:
        raise ValueError("Frozen C2 requires paired vad_words_context600 / eres2net_window_v1")
    manifest = read_json(args.manifest)
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError("Invalid manifest")
    chosen = {row["id"]: row for row in manifest["files"]}
    if len(chosen) != len(manifest["files"]) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", x) for x in chosen):
        raise ValueError("Unsafe/duplicate manifest IDs")
    dev = [x["id"] for x in manifest["files"] if x["split"] == "dev"]
    if len(dev) != 8:
        raise ValueError("Exactly the frozen eight dev cases required")
    fixed_meta = read_json(args.fixed_five_run / "run.json")
    fixed = [row["id"] for row in fixed_meta.get("cases", [])]
    if fixed_meta.get("status") != "COMPLETE" or len(fixed) != 5 or set(fixed) != set(FIXED_FIVE):
        raise ValueError("Historical fixed-five corpus identity differs")
    selected = dev + [x for x in fixed if x not in dev]
    if len(selected) != 10 or not set(selected) <= set(chosen):
        raise ValueError("Exact dev8/fixed5 union must contain ten pinned cases")
    if args.cases is not None and (len(args.cases) != 10 or set(args.cases) != set(selected)):
        raise ValueError("Android C2 QA requires the complete dev8/fixed5 union10")
    baseline_summary = args.fixed_dev_run / "summary.json"
    if digest(baseline_summary) != FIXED_DEV_SUMMARY_SHA256:
        raise ValueError("Frozen fixed-V1.6 dev quality baseline differs")
    baseline = read_json(baseline_summary)
    baseline_run = read_json(args.fixed_dev_run / "run.json")
    if (baseline.get("cases") != 8 or baseline_run.get("status") != "COMPLETE"
            or baseline_run.get("manifest_sha256") != digest(args.manifest)):
        raise ValueError("Fixed-V1.6 dev cohort coverage differs")
    host = read_json(args.host_run / "run.json")
    if (host.get("status") != "COMPLETE" or host.get("new_model_inference") is not True
            or host.get("inference_requested") is not True):
        raise ValueError("Completed fresh full host C2 inference required")
    policy.validate_host_policy(host["config"], host["paired_asr_policy"])
    fp = host["fingerprint"]
    policy.equal(read_json(args.host_run / "config.json"), host["config"], "saved host config")
    if fp.get("config_sha256") != digest(args.host_run / "config.json") or fp.get("manifest_sha256") != digest(args.manifest):
        raise ValueError("Host config/manifest fingerprint differs")
    lock_path = REPO / "app/src/main/assets/models-lock.json"
    models = read_json(lock_path)
    pins = policy.validate_model_lock(models)
    if fp.get("model_lock_sha256") != digest(lock_path) or fp.get("packaged_models") != pins:
        raise ValueError("Host legacy model lock fingerprint differs")
    if (set(fp.get("code", {})) != HOST_CODE
            or any(digest(confined(REPO, name)) != sha for name, sha in fp["code"].items())):
        raise ValueError("Frozen host code fingerprints differ")
    if (len(fp.get("selected_ids", [])) != len(chosen) or set(fp["selected_ids"]) != set(chosen)
            or set(fp.get("references", {})) != set(chosen) or set(fp.get("audio", {})) != set(chosen)):
        raise ValueError("Full host corpus coverage differs")
    embedding = fp.get("external_embedding", {})
    if (embedding.get("id") != "eres2net_zh" or embedding.get("sha256") != policy.EMBEDDING_SHA256
            or embedding.get("size") != policy.MODEL_PINS[5][1] or embedding.get("dimension") != 512
            or embedding.get("catalog_sha256") != digest(REPO / "configs/eval/diar-models.json")
            or fp.get("runtime", {}).get("version") != "2.0.1"):
        raise ValueError("Host runtime/ERes model provenance differs")
    # Hash every weight before the first device call, including non-staging runs.
    for spec in models["files"]:
        local = confined(args.model_root, spec["path"])
        if local.stat().st_size != spec["size"] or digest(local) != spec["sha256"]:
            raise ValueError("Local pinned model differs: " + spec["path"])
    cases, host_records, inputs = [], {}, {}
    for identifier in selected:
        case = chosen[identifier]
        audio = confined(args.audio_root, case["audio"])
        reference = confined(args.manifest.parent, case["reference"])
        reference_sha = digest(reference)
        if (digest(audio) != case["audio_sha256"] or fp["audio"][identifier] != case["audio_sha256"]
                or fp["references"][identifier] != reference_sha
                or case.get("reference_sha256", reference_sha) != reference_sha):
            raise ValueError("Host/current original audio/reference pin differs: " + identifier)
        canonical_audio(audio, case["duration_ms"])
        host_records[identifier] = _host_case(args.host_run, case, reference, host)
        if identifier in fixed:
            old = read_json(args.fixed_five_run / identifier / "case.json")
            old_ref = args.fixed_five_run / identifier / "reference.json"
            if old.get("audio_sha256") != case["audio_sha256"] or digest(old_ref) != reference_sha:
                raise ValueError("Historical fixed-five audio/reference pairing differs")
        inputs[identifier] = {"audio": audio, "reference": reference, "reference_sha256": reference_sha}
        cases.append(case)
    apks = {}
    for role, path in (("app", args.app_apk), ("test", args.test_apk)):
        apks[role] = {"sha256": digest(path), "bytes": path.stat().st_size}
    with zipfile.ZipFile(args.app_apk) as archive:
        if policy.validate_model_lock(policy.strict_json(archive.read("assets/models-lock.json"))) != pins:
            raise ValueError("APK model lock differs")
    return {"host": host, "models": models, "cases": cases, "host_records": host_records,
        "fixed_dev_baseline": baseline,
        "inputs": inputs, "dev_ids": dev, "fixed_five_ids": fixed,
        "fingerprint": {"host_run_sha256": digest(args.host_run / "run.json"),
            "fixed_five_run_sha256": digest(args.fixed_five_run / "run.json"),
            "manifest_sha256": digest(args.manifest), "model_lock_sha256": digest(lock_path),
            "fixed_dev_baseline_summary_sha256": digest(baseline_summary),
            "fixed_dev_baseline_run_sha256": digest(args.fixed_dev_run / "run.json"),
            "host_fingerprint": fp, "apk": apks,
            "collector_code": collector_code_fingerprint(),
            "selected_case_sha256": {i: digest(args.host_run / i / "case.json") for i in selected}}}


def score_case(reference, hypothesis, diagnostic, duration, processing_ms):
    if not policy.finite(processing_ms) or processing_ms < 0:
        raise ValueError("Invalid actual processing time")
    metrics = scoring.score(reference, hypothesis, duration, processing_ms=processing_ms)
    turns = policy.turns_from_json(diagnostic["diarizationTurns"], duration)
    rows = [{"speaker_id": "native_" + str(t.speaker), "start_ms": t.start_ms,
             "end_ms": t.end_ms, "text": ""} for t in turns]
    for collar in (0, 250):
        metrics["native_der_collar_" + str(collar) + "ms"] = scoring.der(reference["transcript"], rows, duration, collar_ms=collar)
    count = len({t.speaker for t in turns})
    metrics["native_speaker_count"] = count
    metrics["native_speaker_count_error"] = abs(count - metrics["speakers"]["reference"])
    return metrics


def paired_summary(rows, dev_ids, fixed_ids):
    """The dev diagnostics can never mask the historical fixed-five WER gate."""
    table = {row["id"]: row for row in rows}
    expected = set(dev_ids) | set(fixed_ids)
    if len(table) != len(rows) or set(table) != expected:
        raise ValueError("Incomplete/duplicate native union coverage")
    gate = summarize([table[i] for i in fixed_ids], threshold_pp=.5)
    return {"fixed_five_wer_port_gate": gate,
            "dev_ids": list(dev_ids), "fixed_five_ids": list(fixed_ids),
            "gate_pass": gate["gate_pass"], "union_cases": len(rows),
            "per_file_outliers_retained": True, "dev_cases_do_not_expand_wer_gate": True}


def dev_quality(summary, baseline):
    """Separate planned C quality gate; never part of the fixed-five WER pool."""
    count = summary.get("native_speaker_count_exact_cases")
    current, fixed = (x.get("native_der_collar_0ms", {}) for x in (summary, baseline))
    rate, reference_rate = current.get("rate"), fixed.get("rate")
    defined = (summary.get("cases") == 8 and baseline.get("cases") == 8
        and type(count) is int and 0 <= count <= 8 and policy.finite(rate) and policy.finite(reference_rate)
        and policy.finite(current.get("reference_speaker_ms")) and current["reference_speaker_ms"] > 0
        and current.get("reference_speaker_ms") == fixed.get("reference_speaker_ms"))
    count_pass = defined and count >= 7
    der_pass = defined and rate <= reference_rate + .02
    return {"gate_pass": bool(count_pass and der_pass), "defined_complete_eight_dev": bool(defined),
        "count_pass": bool(count_pass), "native_count_exact": count, "count_required": 7, "cases_required": 8,
        "native_der0_pass": bool(der_pass), "native_der0": rate,
        "fixed_v16_native_der0": reference_rate,
        "maximum_native_der0": reference_rate + .02 if policy.finite(reference_rate) else None,
        "der_allowance_percentage_points": 2, "wer_corpus_unchanged": "historical fixed five only",
        "scope": "Montage utterance-interval DER proxy; independent of weighted five-file WER port parity"}


def screen_prepare(adb, package, output, state, *, emulator):
    """Dedicated emulator only: wake/stay awake, preserving its original setting."""
    (output / "power-before.txt").write_bytes(adb("shell", "dumpsys", "power").stdout)
    if emulator:
        original = adb("shell", "settings", "get", "global", "stay_on_while_plugged_in").stdout.decode().strip()
        if original != "null" and not re.fullmatch(r"[0-9]+", original):
            raise ValueError("Unexpected stay_on_while_plugged_in value")
        state["original_stay_on_while_plugged_in"] = original
        adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        adb("shell", "wm", "dismiss-keyguard")
        adb("shell", "svc", "power", "stayon", "true")
        adb("shell", "am", "start", "-W", "-n", package + "/.MainActivity")
    power = adb("shell", "dumpsys", "power").stdout
    activities = adb("shell", "dumpsys", "activity", "activities").stdout
    (output / "power-pre-inference.txt").write_bytes(power)
    (output / "activity-pre-inference.txt").write_bytes(activities)
    if not re.search(rb"mWakefulness=Awake\b", power):
        raise ValueError("Device is not Awake before Android inference")
    if not any(package.encode() in line and (b"mResumedActivity" in line or b"topResumedActivity" in line)
               for line in activities.splitlines()):
        raise ValueError("QA app activity is not RESUMED before Android inference")
    state["pre_inference_awake_resumed"] = True


def screen_restore(adb, output, state):
    """Always restore the original setting, including staging/instrument failures."""
    original = state.get("original_stay_on_while_plugged_in")
    errors = []
    if original is not None:
        try:
            if original == "null":
                adb("shell", "settings", "delete", "global", "stay_on_while_plugged_in")
            else:
                adb("shell", "settings", "put", "global", "stay_on_while_plugged_in", original)
            restored = adb("shell", "settings", "get", "global", "stay_on_while_plugged_in").stdout.decode().strip()
            state["restored_stay_on_while_plugged_in"] = restored
            if restored != original:
                raise ValueError("Original stay-on setting did not restore")
        except Exception as error:
            errors.append(str(error))
    try:
        (output / "power-after.txt").write_bytes(adb("shell", "dumpsys", "power").stdout)
    except Exception as error:
        errors.append(str(error))
    state["restoration_errors"] = errors
    return not errors


def run(args):
    checked = preflight(args)  # Must precede output mkdir and any ADB/subprocess.
    verify_collector_code(checked["fingerprint"]["collector_code"])
    if args.check:
        print(json.dumps({"status": "PREFLIGHT_PASS", "cases": [c["id"] for c in checked["cases"]],
            "fixed_five_ids": checked["fixed_five_ids"], "scope": SCOPE,
            "fingerprint": checked["fingerprint"]}, ensure_ascii=False, indent=2))
        return 0
    args.output.mkdir(parents=True)
    run_id = "eval" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = {"schema_version": 1, "status": "STAGING", "run": run_id, "serial": args.serial,
        "cases": [], "scope": SCOPE, "reference_text_or_counts_staged": False,
        "new_model_inference": False, "inference_requested": False, "fingerprint": checked["fingerprint"],
        "requested_asr_plan": policy.ASR_PLAN, "requested_diar_plan": policy.PLAN,
        "requested_diar_policy": policy.policy_for_diar_plan(), "dev_ids": checked["dev_ids"],
        "fixed_five_ids": checked["fixed_five_ids"], "word_evidence_cases": [], "diarization_evidence_cases": []}
    write_json(args.output / "run.json", report)
    log_path = args.output / "commands.jsonl"

    def adb(*arguments, check=True):
        command = [args.adb, "-s", args.serial, *map(str, arguments)]
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "argv": command}) + "\n")
        result = subprocess.run(command, capture_output=True)
        if check and result.returncode:
            raise RuntimeError("ADB failed: " + result.stderr.decode("utf-8", "replace") + result.stdout.decode("utf-8", "replace"))
        return result

    def push_file(local, relative):
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or not re.fullmatch(r"[A-Za-z0-9_./-]+", relative):
            raise ValueError("Unsafe staged path")
        temporary = "/data/local/tmp/" + run_id + "/" + "-".join(path.parts)
        adb("push", local, temporary)
        adb("shell", "run-as", args.package, "mkdir", "-p", str(PurePosixPath("files") / path.parent))
        adb("shell", "run-as", args.package, "cp", temporary, "files/" + relative)
        adb("shell", "rm", temporary)

    records, screen = [], {}
    try:
        if adb("get-state").stdout.strip() != b"device":
            raise ValueError("Explicit selected device is not ready")
        emulator = adb("shell", "getprop", "ro.kernel.qemu").stdout.strip() == b"1"
        if not emulator and not args.allow_physical:
            raise ValueError("Physical device requires --allow-physical")
        if (args.stage_models or args.offline) and not emulator:
            raise ValueError("Direct model staging/offline changes are dedicated-emulator only")
        if args.install:
            adb("install", "-r", "-g", args.app_apk)
            adb("install", "-r", args.test_apk)
        installed = {}
        for role, package in (("app", args.package), ("test", args.package + ".test")):
            paths = adb("shell", "pm", "path", package).stdout.decode().splitlines()
            if len(paths) != 1 or not paths[0].startswith("package:"):
                raise ValueError("Exactly one installed base APK expected: " + package)
            path = paths[0][len("package:"):].strip()
            if not re.fullmatch(r"/data/app/[A-Za-z0-9_~./=+-]+\.apk", path) or ".." in PurePosixPath(path).parts:
                raise ValueError("Unexpected installed APK path")
            actual_sha = adb("exec-out", "sha256sum", path).stdout.decode().split()
            if not actual_sha or actual_sha[0] != checked["fingerprint"]["apk"][role]["sha256"]:
                raise ValueError("Installed APK differs from preflight local file: " + package)
            installed[role] = {"package": package, "path": path, "sha256": actual_sha[0]}
        report["installed_apks"] = installed
        remote_root = "evaluation/" + run_id
        if adb("shell", "run-as", args.package, "test", "-e", "files/" + remote_root, check=False).returncode == 0:
            raise ValueError("Remote evidence directory already exists")
        adb("shell", "mkdir", "-p", "/data/local/tmp/" + run_id)
        if args.stage_models:
            adb("shell", "am", "force-stop", args.package)
            for spec in checked["models"]["files"]:
                push_file(confined(args.model_root, spec["path"]), "models/" + spec["path"])
        # Independently verify actual staged/existing remote model bytes, not just local pins.
        report["native_model_sha256"] = {}
        for spec in checked["models"]["files"]:
            raw = adb("exec-out", "run-as", args.package, "sha256sum", "files/models/" + spec["path"]).stdout.decode().split()
            if not raw or raw[0] != spec["sha256"]:
                raise ValueError("Actual native model hash differs: " + spec["path"])
            report["native_model_sha256"][spec["path"]] = raw[0]
        rows = []
        seen_work_ids, seen_recordings = set(), set()
        for case in checked["cases"]:
            local = checked["inputs"][case["id"]]["audio"]
            if digest(local) != case["audio_sha256"]:
                raise ValueError("Audio changed after preflight")
            relative = "audio/" + case["id"] + ".wav"
            push_file(local, remote_root + "/" + relative)
            rows.append({"id": case["id"], "audio": relative, "sha256": case["audio_sha256"]})
        write_json(args.output / "batch.json", {"schema_version": 1, "run": run_id, "cases": rows})
        push_file(args.output / "batch.json", remote_root + "/batch.json")
        if args.offline:
            adb("shell", "cmd", "connectivity", "airplane-mode", "enable")
            adb("shell", "svc", "wifi", "disable")
            adb("shell", "svc", "data", "disable")
            if (adb("shell", "settings", "get", "global", "airplane_mode_on").stdout.strip() != b"1"
                    or adb("shell", "settings", "get", "global", "wifi_on").stdout.strip() != b"0"):
                raise ValueError("Requested emulator offline state not established")
        # Recheck local run pin immediately before inference; no references staged.
        if digest(args.host_run / "run.json") != checked["fingerprint"]["host_run_sha256"]:
            raise ValueError("Host run changed after preflight")
        verify_collector_code(checked["fingerprint"]["collector_code"])
        screen_prepare(adb, args.package, args.output, screen, emulator=emulator)
        report["screen_power"] = screen
        report.update(status="RUNNING", emulator=emulator, expected_speakers=-1, threads=2,
                      inference_requested=True, new_model_inference=None)
        write_json(args.output / "run.json", report)
        result = adb("shell", "am", "instrument", "-w", "-r", "-e", "evalRun", run_id,
            "-e", "evalThreads", 2, "-e", "evalExpectedSpeakers", -1,
            "-e", "evalAsrPlan", policy.ASR_PLAN, "-e", "evalDiarPlan", policy.PLAN,
            "-e", "class", "ru.replika.EvaluationBatchTest#stagedCanonicalInputsThroughProductionWorker",
            args.package + ".test/androidx.test.runner.AndroidJUnitRunner", check=False)
        log = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
        (args.output / "instrumentation.log").write_text(log, encoding="utf-8")
        # Pull all available outputs first, even when instrumentation fails; never overwrite.
        output = "files/" + remote_root + "/output/"
        native_report = adb("exec-out", "run-as", args.package, "cat", output + "report.json", check=False)
        if native_report.returncode == 0:
            (args.output / "android-report.json").write_bytes(native_report.stdout)
        for case in checked["cases"]:
            folder = args.output / case["id"]
            folder.mkdir()
            for suffix in ("case", "hypothesis", "diagnostics", "diarization-evidence"):
                raw = adb("exec-out", "run-as", args.package, "cat", output + case["id"] + "." + suffix + ".json", check=False)
                if raw.returncode == 0:
                    (folder / (suffix + ".json")).write_bytes(raw.stdout)
                else:
                    (folder / (suffix + ".pull-error.txt")).write_bytes(raw.stderr + raw.stdout)
        if result.returncode != 0 or not re.search(r"OK \(1 tests?\)", log) or "FAILURES!!!" in log:
            raise RuntimeError("Instrumentation failed; all available raw evidence retained")
        completed = read_json(args.output / "android-report.json")
        verify_collector_code(checked["fingerprint"]["collector_code"])
        identifiers = [r["id"] for r in completed.get("cases", [])]
        if (completed.get("status") != "COMPLETE" or len(identifiers) != 10
                or set(identifiers) != {c["id"] for c in checked["cases"]}
                or completed.get("run") != run_id or completed.get("newModelInference") is not True):
            raise ValueError("Incomplete/duplicate native report coverage")
        completed_cases = {r["id"]: r for r in completed["cases"]}
        policy.validate_native_diar_policy(checked["host"]["config"], completed, checked["host"]["paired_asr_policy"])
        report["new_model_inference"] = True
        for case in checked["cases"]:
            identifier, duration = case["id"], case["duration_ms"]
            folder = args.output / identifier
            try:
                native = read_json(folder / "case.json")
                policy.equal(native, completed_cases[identifier], "native case/report copy")
                diagnostic = read_json(folder / "diagnostics.json")
                hypothesis = read_json(folder / "hypothesis.json")
                if native.get("segments") != len(hypothesis.get("transcript", [])):
                    raise ValueError("Native segment count differs from actual JuryJSON")
                policy.validate_native_diar_policy(checked["host"]["config"], diagnostic, checked["host"]["paired_asr_policy"])
                diar = policy.validate_diarization_evidence(diagnostic, native, (folder / "diarization-evidence.json").read_bytes(),
                    case_id=identifier, audio_sha256=case["audio_sha256"], duration_ms=duration)
                if native["workId"] in seen_work_ids or native["recordingId"] in seen_recordings:
                    raise ValueError("Native work/record identity reused across cases")
                seen_work_ids.add(native["workId"])
                seen_recordings.add(native["recordingId"])
                reconstructed, words = policy.reconstruct_jury(diagnostic, duration)
                policy.equal(hypothesis, reconstructed, "actual JuryJSON reconstruction")
                source_ref = checked["inputs"][identifier]["reference"]
                if digest(source_ref) != checked["inputs"][identifier]["reference_sha256"]:
                    raise ValueError("Independent reference changed after preflight")
                (folder / "reference.json").write_bytes(source_ref.read_bytes())
                metrics = score_case(read_json(source_ref), hypothesis, diagnostic, duration, native["processing_ms"])
                write_json(folder / "metrics.json", metrics)
                host = checked["host_records"][identifier]
                row = {"id": identifier, "split": case["split"], "reference_words": metrics["wer_raw"]["reference_tokens"],
                       "native_errors": metrics["wer_raw"]["errors"], "host_errors": host["metrics"]["wer_raw"]["errors"]}
                report["cases"].append(row)
                report["word_evidence_cases"].append({"id": identifier, **words, "actual_jury_reconstructed": True})
                report["diarization_evidence_cases"].append({"id": identifier, **diar})
                record = {"id": identifier, "split": case["split"], "kind": case["kind"], "status": "COMPLETE",
                    "duration_ms": duration, "processing_ms": native["processing_ms"], "metrics": metrics,
                    "audio_sha256": case["audio_sha256"], "reference_sha256": digest(source_ref),
                    "new_model_inference": True, "evidence_sha256": evidence_hashes(folder)}
                records.append(record)
                write_json(folder / "scored-case.json", record)
            except Exception as error:
                write_json(folder / "validation-failure.json", {"id": identifier, "status": "FAILED", "error": str(error)})
                report.setdefault("failures", []).append({"id": identifier, "error": str(error)})
                records.append({"id": identifier, "split": case["split"], "kind": case["kind"],
                                "status": "FAILED", "error": str(error)})
            write_csv(args.output / "results.csv", records, checked["host"]["config"]["id"])
            write_json(args.output / "run.json", report)
        if report.get("failures"):
            raise ValueError("Native evidence validation failed; every per-case failure retained")
        report.update(paired_summary(report["cases"], checked["dev_ids"], checked["fixed_five_ids"]))
        report["dev_native_quality"] = aggregate([r for r in records if r["id"] in checked["dev_ids"]])
        report["dev_host_quality"] = aggregate([checked["host_records"][i] for i in checked["dev_ids"]])
        report["dev_quality_gate"] = dev_quality(report["dev_native_quality"], checked["fixed_dev_baseline"])
        report["wer_port_parity_pass"] = report["fixed_five_wer_port_gate"]["gate_pass"]
        report["gate_pass"] = report["wer_port_parity_pass"] and report["dev_quality_gate"]["gate_pass"]
        status = "COMPLETE" if report["gate_pass"] else ("PORT_PARITY_FAIL" if not report["wer_port_parity_pass"] else "C2_QUALITY_FAIL")
        report.update(status=status, completed_at=datetime.now(timezone.utc).isoformat(),
            full_project_accepted=False, arm_phone_performance_accepted=False)
        write_json(args.output / "run.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["gate_pass"] else 2
    except BaseException as error:
        report.update(status="FAILED", error=str(error), failed_at=datetime.now(timezone.utc).isoformat())
        write_json(args.output / "run.json", report)
        raise
    finally:
        if screen:
            restored = screen_restore(adb, args.output, screen)
            report["screen_power"] = screen
            if not restored:
                report["prior_status_before_restoration_failure"] = report["status"]
                if "error" in report:
                    report["prior_error_before_restoration_failure"] = report["error"]
                report.update(status="FAILED", error="Screen-power restoration failed; see screen_power")
            write_json(args.output / "run.json", report)
            if not restored:
                raise RuntimeError("Original emulator stay-on setting failed to restore")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb", default=shutil.which("adb") or "adb")
    p.add_argument("--serial", required=True)
    p.add_argument("--allow-physical", action="store_true")
    p.add_argument("--package", default="ru.replika.offline")
    p.add_argument("--manifest", type=Path, default=REPO / "benchmark/eval/manifest.json")
    p.add_argument("--audio-root", type=Path, required=True)
    p.add_argument("--model-root", type=Path, default=REPO / "model-pack")
    p.add_argument("--host-run", type=Path, required=True)
    p.add_argument("--fixed-five-run", type=Path, default=REPO / "artifacts/test-results/step-03/context600-android")
    p.add_argument("--fixed-dev-run", type=Path, default=REPO / "artifacts/test-results/step-04/fixed-v16-production-comparison")
    p.add_argument("--cases", nargs="+")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--expected-speakers", type=int, default=-1)
    p.add_argument("--asr-plan", default=policy.ASR_PLAN)
    p.add_argument("--diar-plan", default=policy.PLAN)
    p.add_argument("--install", action="store_true")
    p.add_argument("--app-apk", type=Path, default=REPO / "app/build/outputs/apk/debug/app-debug.apk")
    p.add_argument("--test-apk", type=Path, default=REPO / "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk")
    p.add_argument("--stage-models", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--check", action="store_true", help="Read-only preflight; no output mkdir, subprocess or ADB")
    return p


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
