#!/usr/bin/env python3
"""One explicit compact-QA contract smoke; absence of --execute means no ADB.

Only dev-mono-s canonical audio and global policies enter Android. This is a
duplicate short contract check, not a benchmark or additional quality cohort.
The frozen performance runner validates/scorers the actual compact outputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

sys.dont_write_bytecode = True
CASE_ID = "dev-mono-s"
AUDIO_SHA = "97943f4d90c2b56166031263a6820c41e0f80b94643a9d3737327debdc8fbe53"
REFERENCE_SHA = "9259341e0d2aa8bc8bf6bdc9f616ea30e5025aa4e1adca14dc09f2089dcb15e1"
APKS = {"app": "0a03b2f1d0d30dad8e8de6339860187e725affd851002485b7fa248b05b948ca",
        "test": "ce4851c681962e8489bd9d8bc0edc0a229d245307b88fdfa9c19d0ef1f1df051"}
SOURCE_PINS = {
    "tools/run_plan19_perf.py": "a910dd990505175d031312e1dc0ed8848cb5caabcc64434dde19d367c2a4747c",
    "tools/eval/pull_refined_android.py": "a1f0524e5c0a814514143ff3db93c393bd9161dff9a6a2ac0c3a7e9ccee8ec5a",
    "tools/eval/native_diar_policy.py": "3cbd379c545b3d6206a5afc52817c34ae601836fae38cc808c6972e651c407df",
    "benchmark/eval/manifest.json": "47109cb1987624daaf8f4dc28e8eca3198b0c2bbcf01cd334b9611664eb38066",
    "configs/eval/c2-window-selected-full.json": "6e3a0f10a291e9121bae8df01dca0db3a67c4ac5c828f3fca38ace26b21ef189",
    "app/src/androidTest/java/ru/replika/EvaluationBatchTest.kt": "f4be2737a354fd408a5148de2d069fa1b86821acdfc0b23851d75a0de619a820",
}
SCOPE = ("Single duplicate dev-mono-s compact-QA contract smoke through the actual production Worker; "
         "automatic speakers -1, C2/context600, collectEvidence=false. "
         "Independent author reference stays host-only. Not a performance batch, a new independent "
         "quality cohort, full token/vector replay, ARM/phone or thermal acceptance.")
PROFILES = {"compact-auto-two": {"cpu_plan": "auto_v1", "threads": 2, "embedding_threads": 2,
                                "output": "compact-smoke-v1"},
            "legacy-c2-moderate-one": {"cpu_plan": "v16", "threads": 1, "embedding_threads": 2,
                                       "output": "compact-legacy-moderate-one-v1"}}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def modules(repo):
    sys.path.insert(0, str(repo))
    spec = importlib.util.spec_from_file_location("compact_smoke_frozen_perf", repo / "tools/run_plan19_perf.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    collector = importlib.import_module("tools.eval.pull_refined_android")
    if runner.REPO.resolve() != repo or Path(collector.REPO).resolve() != repo:
        raise ValueError("Imported semantics do not belong to --repo")
    return runner, collector


def preflight(args):
    """Read-only, no mkdir/subprocess/ADB; source pins checked before import."""
    repo = args.repo.resolve()
    if args.output.exists():
        raise ValueError("Use a fresh output; prior evidence is never overwritten")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", args.serial) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]+", args.package):
        raise ValueError("Unsafe explicit serial/package")
    if type(args.instrument_timeout_seconds) is not int or not 120 <= args.instrument_timeout_seconds <= 1800:
        raise ValueError("Smoke instrumentation timeout must be 120..1800 seconds")
    for name, expected in SOURCE_PINS.items():
        if sha(repo / name) != expected:
            raise ValueError("Frozen procedure source/input changed: " + name)
    runner, collector = modules(repo)
    policy = runner.policy
    manifest_path = repo / "benchmark/eval/manifest.json"
    manifest = runner.read_json(manifest_path)
    cases = manifest.get("files")
    if manifest.get("schema_version") != 1 or not isinstance(cases, list):
        raise ValueError("Invalid source manifest")
    chosen = [row for row in cases if row.get("id") == CASE_ID]
    if len(chosen) != 1:
        raise ValueError("Exactly the pinned short smoke case is required")
    case = chosen[0]
    if (case.get("audio_sha256") != AUDIO_SHA or type(case.get("duration_ms")) is not int
            or case["duration_ms"] != 6333 or case.get("split") != "dev"
            or case.get("kind") != "author_mono_clip"):
        raise ValueError("Pinned smoke identity/clock differs")
    audio = runner.confined(args.audio_root, case["audio"])
    reference = runner.confined(manifest_path.parent, case["reference"])
    if sha(audio) != AUDIO_SHA or sha(reference) != REFERENCE_SHA:
        raise ValueError("Original smoke audio/independent author reference SHA differs")
    frames = collector.canonical_audio(audio, case["duration_ms"])
    runner.scoring._document(runner.read_json(reference), case["duration_ms"])
    local = {str(path.resolve()): sha(path) for path in (audio, reference, manifest_path, Path(__file__))}
    lock_path = repo / "app/src/main/assets/models-lock.json"
    lock = runner.read_json(lock_path)
    policy.validate_model_lock(lock)
    local[str(lock_path)] = sha(lock_path)
    for row in lock["files"]:
        path = runner.confined(args.model_root, row["path"])
        if path.stat().st_size != row["size"] or sha(path) != row["sha256"]:
            raise ValueError("Pinned local model differs: " + row["path"])
        local[str(path)] = row["sha256"]
    apks = {}
    for role, path in (("app", args.app_apk), ("test", args.test_apk)):
        if sha(path) != APKS[role]:
            raise ValueError("Expected build-auto-v2/test-v3 APK differs: " + role)
        local[str(path.resolve())] = APKS[role]
        apks[role] = {"sha256": APKS[role], "bytes": path.stat().st_size}
    with zipfile.ZipFile(args.app_apk) as archive:
        policy.validate_model_lock(policy.strict_json(archive.read("assets/models-lock.json")))
    with zipfile.ZipFile(args.test_apk) as archive:
        if not any(b"evalCollectEvidence" in archive.read(name) for name in archive.namelist()
                   if re.fullmatch(r"classes[0-9]*\.dex", name)):
            raise ValueError("Test APK lacks the explicit compact-QA bridge")
    config = runner.read_json(repo / "configs/eval/c2-window-selected-full.json")
    transient, paired = runner.execution_config(config, 2)
    policy.validate_host_policy(transient, paired, cpu_plan="auto_v1", threads=2)
    fingerprint = {"code": runner.code_fingerprint(), "local_files": local, "apk": apks,
                   "procedure_sources": SOURCE_PINS, "script_sha256": sha(Path(__file__))}
    return runner, collector, {"case": case, "audio": audio, "reference": reference, "frames": frames,
        "models": lock, "config": config, "fingerprint": fingerprint}


def verify(checked, runner):
    runner.check_unchanged(checked)
    for relative, expected in SOURCE_PINS.items():
        if sha(runner.REPO / relative) != expected:
            raise ValueError("Smoke source changed after preflight: " + relative)


def legacy_policy(runner, value):
    """Narrow historical moderate1 stage pin, not the strict2 C acceptance gate."""
    policy = runner.policy
    policy.validate_native_policy(policy._asr_host(1), value)
    cpu = value.get("cpuPolicy")
    if not isinstance(cpu, dict) or type(cpu.get("availableCores")) is not int or not 1 <= cpu["availableCores"] <= 2**31-1:
        raise ValueError("Legacy moderate smoke requires actual bounded CPU cores")
    policy.equal(cpu, {"plan": "v16", "requestedThreads": 1, "availableCores": cpu["availableCores"],
        "asrThreads": 1, "diarizationThreads": 2, "refinementThreads": 2,
        "diarizationPinned": True, "refinementPinned": True}, "legacy moderate cpuPolicy")
    for key, expected in (("cpuPlan", "v16"), ("requestedThreads", 1)):
        if key in value:
            policy.equal(value[key], expected, "legacy." + key)
    for key in ("diarizationPlanRequested", "diarizationPlan"):
        policy.equal(value.get(key), policy.PLAN, key)
    expected = policy.policy_for_diar_plan()
    actual = value.get("diarizationPolicy")
    if not isinstance(actual, dict) or set(actual) != set(expected):
        raise ValueError("Legacy moderate C2 policy fields differ")
    for key, wanted in expected.items():
        if key in ("native_threshold", "window_shift", "min_duration_on", "min_duration_off"):
            policy.f32_equal(actual[key], wanted, key)
        else:
            policy.equal(actual[key], wanted, key)


def validate_legacy_compact(runner, checked, native, diagnostic, hypothesis):
    """Same compact safety boundary, actual ASR1/SD2/ref2 retained verbatim."""
    equal = runner.policy.equal
    case = checked["case"]
    for key, wanted in {"id": CASE_ID, "status": "COMPLETE", "audio_sha256": AUDIO_SHA,
        "newModelInference": True, "collectEvidence": False, "workManagerState": "SUCCEEDED"}.items():
        equal(native.get(key), wanted, "case." + key)
    duration, processing = native.get("duration_ms"), native.get("processing_ms")
    if (type(duration) is not int or abs(duration-case["duration_ms"]) > 1
            or type(processing) is not int or processing <= 0
            or type(native.get("processId")) is not int or native["processId"] <= 0):
        raise ValueError("Legacy moderate actual Worker clocks/PID differ")
    try:
        if str(uuid.UUID(native["workId"])) != native["workId"]:
            raise ValueError("Noncanonical Work UUID")
        record = native["recordingId"]
        if not record.startswith("qa-evaluation-") or str(uuid.UUID(record[14:])) != record[14:]:
            raise ValueError("Noncanonical recording UUID")
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise ValueError("Legacy moderate actual own work/record identity invalid") from error
    legacy_policy(runner, diagnostic)
    for key, wanted in {"runtime": "sherpa-onnx 2.0.1", "backend": runner.policy.base.SOURCE,
        "sampleRate": 16000, "vadThreads": 1, "maxAsrSegmentMs": 20000,
        "wordEvidenceRequested": False, "wordEvidenceBytes": 0, "wordEvidenceTruncated": False,
        "audioMs": duration, "totalMs": processing, "diarizationRefinementAccepted": True}.items():
        equal(diagnostic.get(key), wanted, key)
    if any(key.startswith("diarizationEvidence") for key in diagnostic):
        raise ValueError("QA=false legacy path must omit full sidecar fields")
    adapter = diagnostic.get("diarizationRefinement", {})
    for key, wanted in {"cpuPlan": "v16", "embeddingThreads": 2, "algorithm": "window-overcluster-v1",
        "nativeResourcesReleasedBeforeRefiner": True, "originalPcm": True, "embeddingInferenceCompleted": True,
        "computationalSupport": True, "retainedNativeModelCache": False, "config": runner.policy.WINDOW_CONFIG}.items():
        equal(adapter.get(key), wanted, "adapter." + key)
    if adapter.get("status") not in ("SUPPORTED", "PARTIAL_TEMPORAL"):
        raise ValueError("Legacy moderate refiner unsupported")
    counts = diagnostic.get("diarizationEmbeddingCounts", {})
    n = counts.get("measuredWindows")
    if type(n) is not int or n <= 0:
        raise ValueError("Legacy moderate actual measured embedding windows missing")
    for key, wanted in {"extractorLoads": 1, "embeddingDimension": 512, **{key: n for key in
        ("plannedWindows", "readWindows", "createdStreams", "releasedStreams", "computeAttempts", "embeddingForwardCalls")}}.items():
        equal(counts.get(key), wanted, "embedding." + key)
    parts = diagnostic.get("asrSlices")
    if not isinstance(parts, list) or not parts:
        raise ValueError("Legacy moderate actual ASR chunks missing")
    equal(diagnostic.get("wordProcessedChunks"), len(parts), "wordProcessedChunks")
    previous = 0
    for part in parts:
        a, b = part.get("startMs"), part.get("endMs")
        if type(a) is not int or type(b) is not int or not previous <= a < b <= duration or b-a > 20000:
            raise ValueError("Legacy moderate ASR chunk clock invalid")
        previous = b
        if (part.get("wordEvidenceIncluded") is not False or part.get("wordEvidenceOmittedReason") != "not_requested"
                or any(key in part for key in ("tokens", "timestamps", "words"))):
            raise ValueError("Legacy moderate compact path contains QA arrays")
        if type(part.get("text")) is not str or type(part.get("blank")) is not bool or part["blank"] != (not part["text"].strip()):
            raise ValueError("Legacy moderate ASR text/blank invalid")
        equal(part.get("frameStrideMs"), 40, "frameStrideMs")
        for key in ("tokenCount", "timestampCount", "wordCount"):
            if type(part.get(key)) is not int or part[key] < 0:
                raise ValueError("Legacy moderate compact ASR counts invalid")
    rows = runner.scoring._document(hypothesis, duration)
    if " ".join(row.text for row in rows).split() != " ".join(part["text"] for part in parts).split():
        raise ValueError("Legacy moderate exported Jury words differ from actual ASR text")
    return {"asr_chunks": len(parts), "reported_tokens": sum(part["tokenCount"] for part in parts),
        "reported_words": sum(part["wordCount"] for part in parts), "measured_embedding_windows": n,
        "resources_balanced": True, "compact_asr_text_preserved": True, "full_token_vector_replay_performed": False,
        "narrow_legacy_stage_pin_smoke": True, "strict_c2_acceptance_gate_applied": False}


def validate_actual(runner, checked, native_report, native, diagnostic, hypothesis, profile="compact-auto-two"):
    """Pure boundary shared by the executable path and controlled tests."""
    selected = PROFILES[profile]
    if profile == "compact-auto-two":
        transient, paired = runner.execution_config(checked["config"], 2)
        runner.policy.validate_native_diar_policy(transient, native_report, paired, cpu_plan="auto_v1", threads=2,
                                                  requested_threads=2)
    else:
        legacy_policy(runner, native_report)
    runner.policy.equal(native_report.get("cpuPlan"), selected["cpu_plan"], "report.cpuPlan")
    runner.policy.equal(native_report.get("requestedThreads"), selected["threads"], "report.requestedThreads")
    if (native_report.get("status") != "COMPLETE" or native_report.get("collectEvidence") is not False
            or native_report.get("newModelInference") is not True
            or not isinstance(native_report.get("cases"), list)
            or [row.get("id") for row in native_report["cases"]] != [CASE_ID]):
        raise ValueError("Exactly one COMPLETE compact-QA native report is required")
    pid = native_report.get("processId")
    if type(pid) is not int or pid <= 0 or native.get("processId") != pid:
        raise ValueError("Native report/case actual process ID differs")
    runner.validate_case_copy(native, native_report["cases"][0])
    counts = (runner.validate_compact_case(checked["case"], native, diagnostic, hypothesis, checked["config"], 2)
              if profile == "compact-auto-two" else validate_legacy_compact(runner, checked, native, diagnostic, hypothesis))
    adapter = diagnostic["diarizationRefinement"]
    runner.policy.equal(adapter, runner.policy.compact_refiner_diagnostic(adapter), "compact-only refiner payload")
    if any(key in diagnostic for key in ("cleanEmbeddingWindows", "windows", "wordEvidence")):
        raise ValueError("Compact path contains a full QA evidence payload")
    metrics = runner.score_case(runner.read_json(checked["reference"]), hypothesis, diagnostic,
                                native["duration_ms"], native["processing_ms"])
    return counts, metrics


def run(args):
    runner, collector, checked = preflight(args)
    selected = PROFILES[args.profile]
    if not args.execute:
        print(json.dumps({"status": "PREFLIGHT_PASS", "read_only": True, "adb_invoked": False,
            "new_model_inference": False, "scope": SCOPE, "case": CASE_ID, "duration_ms": 6333,
            "canonical_frames": checked["frames"], "collectEvidence": False, "threads": selected["threads"],
            "profile": args.profile, "expected_speakers": -1, "cpu_plan": selected["cpu_plan"], "asr_plan": runner.policy.ASR_PLAN,
            "diar_plan": runner.policy.PLAN, "fingerprint": checked["fingerprint"]}, ensure_ascii=False, indent=2))
        return 0
    args.output.mkdir(parents=True)
    report = {"schema_version": 1, "status": "STAGING", "created_utc": now(), "scope": SCOPE,
        "serial": args.serial, "package": args.package, "case": CASE_ID,
        "reference_text_or_counts_staged": False, "collectEvidence": False,
        "inference_requested": False, "new_model_inference": False, "inference_completion_verified": False,
        "fingerprint": checked["fingerprint"], "screen_power": {}, "planned_workers": 1,
        "performance_protocol_changed": False, "quality_acceptance": False, "profile": args.profile,
        "cpu_plan": selected["cpu_plan"], "requested_threads": selected["threads"]}
    runner.write_json(args.output / "run.json", report)
    saved_script = args.output / "procedure.py"
    shutil.copyfile(Path(__file__), saved_script)
    if sha(saved_script) != checked["fingerprint"]["script_sha256"]:
        raise ValueError("Procedure changed while archiving")
    session = "p19compact" + uuid.uuid4().hex
    remote = "files/evaluation/" + session

    def adb(*words, check=True, timeout=120):
        argv = [args.adb, "-s", args.serial, *map(str, words)]
        with (args.output / "commands.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": now(), "argv": argv}) + "\n")
        actual = subprocess.run(argv, capture_output=True, timeout=timeout)
        if check and actual.returncode:
            raise RuntimeError("ADB failed: " + actual.stderr.decode("utf-8", "replace"))
        return actual

    def push(local, suffix):
        if suffix not in ("batch.json", "audio/" + CASE_ID + ".wav"):
            raise ValueError("Only canonical audio and allowlisted batch may be staged")
        target = remote + "/" + suffix
        temporary = "/data/local/tmp/" + session + "-" + PurePosixPath(suffix).name
        adb("push", local, temporary)
        try:
            adb("shell", "run-as", args.package, "mkdir", "-p", str(PurePosixPath(target).parent))
            adb("shell", "run-as", args.package, "cp", temporary, target)
        finally:
            adb("shell", "rm", temporary, check=False)

    def pull_outputs():
        for name in ("report.json", *[CASE_ID + "." + suffix + ".json" for suffix in ("case", "hypothesis", "diagnostics")]):
            try:
                actual = adb("exec-out", "run-as", args.package, "cat", remote + "/output/" + name, check=False)
                if actual.returncode == 0:
                    (args.output / ("instrumentation-report.json" if name == "report.json" else name)).write_bytes(actual.stdout)
                else:
                    report.setdefault("pull_errors", []).append({"file": name, "returncode": actual.returncode,
                        "stderr": actual.stderr.decode("utf-8", "replace")})
            except Exception as error:
                report.setdefault("pull_errors", []).append({"file": name, "error": repr(error)})

    error = None
    instrument_started = False
    try:
        verify(checked, runner)
        if adb("get-state").stdout.strip() != b"device" or adb("shell", "getprop", "ro.kernel.qemu").stdout.strip() != b"1":
            raise ValueError("Explicit ready emulator required")
        report["installed_apks"] = {}
        for role, package in (("app", args.package), ("test", args.package + ".test")):
            paths = adb("shell", "pm", "path", package).stdout.decode().splitlines()
            if len(paths) != 1 or not paths[0].startswith("package:/data/app/"):
                raise ValueError("Exactly one installed base APK required")
            path = paths[0][8:]
            if not re.fullmatch(r"/data/app/[A-Za-z0-9_~./=+-]+\.apk", path) or ".." in PurePosixPath(path).parts:
                raise ValueError("Unsafe installed APK path")
            actual = adb("exec-out", "sha256sum", path).stdout.decode().split()[0]
            if actual != APKS[role]:
                raise ValueError("Installed/local frozen APK mismatch: " + role)
            report["installed_apks"][role] = {"package": package, "path": path, "sha256": actual}
        report["native_model_sha256_before"] = {}
        for row in checked["models"]["files"]:
            actual = adb("exec-out", "run-as", args.package, "sha256sum", "files/models/" + row["path"]).stdout.decode().split()[0]
            if actual != row["sha256"]:
                raise ValueError("Actual Android model SHA mismatch: " + row["path"])
            report["native_model_sha256_before"][row["path"]] = actual
        collector.screen_prepare(adb, args.package, args.output, report["screen_power"], emulator=True)
        if report["screen_power"].get("original_stay_on_while_plugged_in") != "1":
            raise ValueError("This dedicated smoke expects the recorded initial stay-on setting 1")
        if adb("shell", "run-as", args.package, "test", "-e", remote, check=False).returncode == 0:
            raise ValueError("Fresh remote run already exists; preserve it")
        batch = {"schema_version": 1, "run": session, "cases": [
            {"id": CASE_ID, "audio": "audio/" + CASE_ID + ".wav", "sha256": AUDIO_SHA}]}
        runner.write_json(args.output / "batch.json", batch)
        push(checked["audio"], "audio/" + CASE_ID + ".wav")
        push(args.output / "batch.json", "batch.json")
        verify(checked, runner)
        report.update(status="RUNNING", inference_requested=True, new_model_inference=None, remote_run=session)
        runner.write_json(args.output / "run.json", report)
        instrument_started = True
        try:
            actual = adb("shell", "am", "instrument", "-w", "-r", "-e", "evalRun", session,
                "-e", "evalThreads", str(selected["threads"]), "-e", "evalExpectedSpeakers", "-1", "-e", "evalCpuPlan", selected["cpu_plan"],
                "-e", "evalAsrPlan", runner.policy.ASR_PLAN, "-e", "evalDiarPlan", runner.policy.PLAN,
                "-e", "evalCollectEvidence", "false", "-e", "class", runner.BRIDGE,
                args.package + ".test/androidx.test.runner.AndroidJUnitRunner", check=False,
                timeout=args.instrument_timeout_seconds)
            report["instrumentation_exit_code"] = actual.returncode
            (args.output / "instrumentation.log").write_bytes(actual.stdout)
            (args.output / "instrumentation.stderr").write_bytes(actual.stderr)
        except subprocess.TimeoutExpired as timeout:
            (args.output / "instrumentation.log").write_bytes(timeout.stdout or b"")
            (args.output / "instrumentation.stderr").write_bytes(timeout.stderr or b"")
            raise
        finally:
            pull_outputs()
        raw = (args.output / "instrumentation.log").read_bytes()
        if report.get("instrumentation_exit_code") != 0 or not re.search(rb"OK \(1 tests?\)", raw) or re.search(rb"FAILURES!!!|INSTRUMENTATION_FAILED|Process crashed", raw):
            raise ValueError("Instrumentation failed; raw and available partial outputs preserved")
        native_report = runner.read_json(args.output / "instrumentation-report.json")
        runner.policy.equal(native_report.get("run"), session, "fresh native report.run")
        native, diagnostic, hypothesis = [runner.read_json(args.output / (CASE_ID + "." + suffix + ".json"))
                                         for suffix in ("case", "diagnostics", "hypothesis")]
        counts, metrics = validate_actual(runner, checked, native_report, native, diagnostic, hypothesis, args.profile)
        runner.write_json(args.output / (CASE_ID + ".metrics.json"), metrics)
        shutil.copyfile(checked["reference"], args.output / (CASE_ID + ".reference.json"))
        report.update(compact_evidence=counts, metrics=metrics, work_id=native["workId"], recording_id=native["recordingId"],
            process_id=native["processId"], new_model_inference=True, inference_completion_verified=True,
            completed_workers=1, duration_ms=native["duration_ms"], processing_ms=native["processing_ms"])
        report["native_model_sha256_after"] = {}
        for row in checked["models"]["files"]:
            actual = adb("exec-out", "run-as", args.package, "sha256sum", "files/models/" + row["path"]).stdout.decode().split()[0]
            if actual != row["sha256"]:
                raise ValueError("Android model changed during smoke")
            report["native_model_sha256_after"][row["path"]] = actual
        verify(checked, runner)
        report.update(status="COMPLETE", completed_utc=now(), contract_smoke_pass=True)
    except BaseException as caught:
        error = caught
        report.update(status="FAILED", error=repr(caught), failed_utc=now(), contract_smoke_pass=False,
            inference_may_still_be_running=instrument_started and not report["inference_completion_verified"])
    finally:
        try:
            restored = collector.screen_restore(adb, args.output, report["screen_power"])
        except BaseException as caught:
            restored = False
            report["restoration_error"] = repr(caught)
        if not restored:
            report.update(status="FAILED", contract_smoke_pass=False, restoration_failed=True)
        report["evidence_sha256"] = {path.name: sha(path) for path in args.output.iterdir() if path.is_file() and path.name != "run.json"}
        runner.write_json(args.output / "run.json", report)
    if error is not None:
        print(repr(error), file=sys.stderr)
    return 0 if report["status"] == "COMPLETE" else 1


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    choice = result.add_mutually_exclusive_group()
    choice.add_argument("--check", action="store_true", help="Local read-only preflight (also the default); no ADB")
    choice.add_argument("--execute", action="store_true", help="Explicitly run exactly one actual Android Worker")
    result.add_argument("--repo", type=Path, default=Path.cwd())
    result.add_argument("--profile", choices=tuple(PROFILES), default="compact-auto-two")
    result.add_argument("--serial", default="emulator-5556")
    result.add_argument("--package", default="ru.replika.offline")
    result.add_argument("--adb", default=shutil.which("adb") or "adb")
    result.add_argument("--audio-root", type=Path, required=True)
    result.add_argument("--model-root", type=Path)
    result.add_argument("--app-apk", type=Path)
    result.add_argument("--test-apk", type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--instrument-timeout-seconds", type=int, default=600)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    repo = args.repo.resolve()
    args.model_root = args.model_root or repo / "model-pack"
    args.app_apk = args.app_apk or repo / "app/build/outputs/apk/debug/app-debug.apk"
    args.test_apk = args.test_apk or repo / "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
    args.output = args.output or repo / "artifacts/test-results/step-05" / PROFILES[args.profile]["output"]
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
