#!/usr/bin/env python3
"""Stage canonical QA audio on one explicit device, run production Worker, pull and score.

Requires a matching debuggable APK/test APK. No app-data wipe, reference staging or cloud
inference. --stage-models is restricted to an emulator; use a dedicated QA AVD.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from run import REPO, confined, digest, write_json
from score import score, der
from port_comparison import summarize
from native_policy import PLAN_POLICIES, policy_for_plan, validate_native_policy, validate_word_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default=shutil.which("adb") or "adb")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--allow-physical", action="store_true")
    parser.add_argument("--package", default="ru.replika.offline")
    parser.add_argument("--manifest", type=Path, default=REPO / "benchmark/eval/manifest.json")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=REPO / "model-pack")
    parser.add_argument("--host-run", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, choices=(1, 2, 4), default=2)
    parser.add_argument("--expected-speakers", type=int, default=-1)
    parser.add_argument("--asr-plan", choices=tuple(PLAN_POLICIES), default="v16")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--app-apk", type=Path, default=REPO / "app/build/outputs/apk/debug/app-debug.apk")
    parser.add_argument("--test-apk", type=Path, default=REPO / "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk")
    parser.add_argument("--stage-models", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Disable network on the dedicated emulator before inference")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]+", args.package):
        parser.error("Unsafe package name")
    if args.output.exists():
        parser.error("Choose a fresh output path; existing evidence is never overwritten")
    if args.expected_speakers != -1 and not 1 <= args.expected_speakers <= 20:
        parser.error("Expected speakers must be -1, 1 or 2..20")
    manifest = json.loads(args.manifest.read_text())
    chosen = {case["id"]: case for case in manifest["files"]}
    if len(set(args.cases)) != len(args.cases) or set(args.cases) - set(chosen):
        parser.error("Duplicate or unknown case IDs")
    for case_id in args.cases:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", case_id):
            parser.error("Unsafe case ID")
    host_meta = json.loads((args.host_run / "run.json").read_text())
    if host_meta.get("status") != "COMPLETE":
        parser.error("Host inference must complete before a paired native run")
    host_config = host_meta["config"]
    requested_policy = validate_native_policy(host_config, {
        "threads": args.threads, "expectedSpeakers": args.expected_speakers,
        "asrPlan": args.asr_plan, "asrPolicy": policy_for_plan(args.asr_plan)})
    for case_id in args.cases:
        host_case = json.loads((args.host_run / case_id / "case.json").read_text())
        case = chosen[case_id]
        if host_case["audio_sha256"] != case["audio_sha256"] or host_case["reference_sha256"] != digest(confined(args.manifest.parent, case["reference"])):
            parser.error("Host/native input fingerprints differ: " + case_id)
    args.output.mkdir(parents=True)
    run_id = "eval" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = {"status": "STAGING", "run": run_id, "serial": args.serial, "cases": [],
              "scope": "Actual production Worker; explicit device. x86 emulator is not ARM/phone acceptance.",
              "reference_text_or_counts_staged": False, "new_model_inference": False, "inference_requested": False}
    report.update(requested_asr_plan=args.asr_plan, requested_asr_policy=requested_policy,
                  source_host_run_sha256=digest(args.host_run / "run.json"), word_evidence_cases=[])
    write_json(args.output / "run.json", report)
    command_log = args.output / "commands.jsonl"

    def adb(*arguments, check=True):
        command = [args.adb, "-s", args.serial, *map(str, arguments)]
        with command_log.open("a", encoding="utf-8") as stream:
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

    try:
        if adb("get-state").stdout.strip() != b"device":
            raise ValueError("Selected device is not ready")
        emulator = adb("shell", "getprop", "ro.kernel.qemu").stdout.strip() == b"1"
        if not emulator and not args.allow_physical:
            raise ValueError("Physical device requires explicit --allow-physical")
        if args.stage_models and not emulator:
            raise ValueError("Direct QA model staging is emulator-only; use normal model provisioning on phones")
        if args.offline and not emulator:
            raise ValueError("Automatic offline-mode change is emulator-only")
        if args.install:
            adb("install", "-r", "-g", args.app_apk)
            adb("install", "-r", args.test_apk)
        remote_root = "evaluation/" + run_id
        if adb("shell", "run-as", args.package, "test", "-e", "files/" + remote_root, check=False).returncode == 0:
            raise ValueError("Remote run already exists")
        adb("shell", "mkdir", "-p", "/data/local/tmp/" + run_id)
        if args.stage_models:
            # Dedicated AVD only. Stop the QA app before replacing any model files; no data wipe.
            adb("shell", "am", "force-stop", args.package)
            lock = json.loads((REPO / "app/src/main/assets/models-lock.json").read_text())
            for spec in lock["files"]:
                local = confined(args.model_root, spec["path"])
                if local.stat().st_size != spec["size"] or digest(local) != spec["sha256"]:
                    raise ValueError("Pinned model mismatch: " + spec["path"])
                push_file(local, "models/" + spec["path"])
        rows = []
        for case_id in args.cases:
            case = chosen[case_id]
            audio = confined(args.audio_root, case["audio"])
            if digest(audio) != case["audio_sha256"]:
                raise ValueError("Pinned audio mismatch: " + case_id)
            remote_audio = "audio/" + case_id + ".wav"
            push_file(audio, remote_root + "/" + remote_audio)
            rows.append({"id": case_id, "audio": remote_audio, "sha256": case["audio_sha256"]})
        batch = {"schema_version": 1, "run": run_id, "cases": rows}
        write_json(args.output / "batch.json", batch)
        push_file(args.output / "batch.json", remote_root + "/batch.json")
        if args.offline:
            adb("shell", "cmd", "connectivity", "airplane-mode", "enable")
            adb("shell", "svc", "wifi", "disable")
            adb("shell", "svc", "data", "disable")
            report["airplane_mode_on"] = adb("shell", "settings", "get", "global", "airplane_mode_on").stdout.decode().strip()
            report["wifi_on"] = adb("shell", "settings", "get", "global", "wifi_on").stdout.decode().strip()
            if report["airplane_mode_on"] != "1" or report["wifi_on"] != "0":
                raise ValueError("Requested offline state was not established")
        report.update(status="RUNNING", emulator=emulator, expected_speakers=args.expected_speakers, threads=args.threads, inference_requested=True)
        write_json(args.output / "run.json", report)
        actual = adb("shell", "am", "instrument", "-w", "-r", "-e", "evalRun", run_id,
                     "-e", "evalThreads", args.threads, "-e", "evalExpectedSpeakers", args.expected_speakers,
                     "-e", "evalAsrPlan", args.asr_plan,
                     "-e", "class", "ru.replika.EvaluationBatchTest#stagedCanonicalInputsThroughProductionWorker",
                     args.package + ".test/androidx.test.runner.AndroidJUnitRunner")
        log = actual.stdout.decode("utf-8", "replace") + actual.stderr.decode("utf-8", "replace")
        (args.output / "instrumentation.log").write_text(log, encoding="utf-8")
        if not re.search(r"OK \(1 tests?\)", log) or "FAILURES!!!" in log:
            raise RuntimeError("Android instrumentation did not pass; retain its log and private QA outputs")
        native_report = adb("exec-out", "run-as", args.package, "cat", "files/" + remote_root + "/output/report.json").stdout
        (args.output / "android-report.json").write_bytes(native_report)
        completed = json.loads(native_report)
        if completed["status"] != "COMPLETE" or {r["id"] for r in completed["cases"]} != set(args.cases):
            raise ValueError("Incomplete native evidence")
        report["matched_asr_policy"] = validate_native_policy(host_config, completed)
        report["new_model_inference"] = True
        for case_id in args.cases:
            case = chosen[case_id]
            case_dir = args.output / case_id
            case_dir.mkdir()
            for suffix in ("hypothesis", "diagnostics", "case"):
                content = adb("exec-out", "run-as", args.package, "cat",
                              "files/" + remote_root + "/output/" + case_id + "." + suffix + ".json").stdout
                (case_dir / (suffix + ".json")).write_bytes(content)
            native = json.loads((case_dir / "case.json").read_text())
            if native["audio_sha256"] != case["audio_sha256"]:
                raise ValueError("Native original audio changed: " + case_id)
            reference = json.loads(confined(args.manifest.parent, case["reference"]).read_text())
            write_json(case_dir / "reference.json", reference)
            hypothesis = json.loads((case_dir / "hypothesis.json").read_text())
            diagnostics = json.loads((case_dir / "diagnostics.json").read_text())
            validate_native_policy(host_config, diagnostics)
            metric = score(reference, hypothesis, native["duration_ms"], processing_ms=native["processing_ms"])
            turns = [{"speaker_id": "native_" + str(t["speakerId"]), "start_ms": t["startMs"],
                      "end_ms": t["endMs"], "text": ""} for t in diagnostics["diarizationTurns"]]
            metric["native_der_collar_0ms"] = der(reference["transcript"], turns, native["duration_ms"])
            metric["native_der_collar_250ms"] = der(reference["transcript"], turns, native["duration_ms"], collar_ms=250)
            write_json(case_dir / "metrics.json", metric)
            if requested_policy["pipeline"] == "vad_words_v1":
                evidence = validate_word_evidence(diagnostics)
                report["word_evidence_cases"].append({"id": case_id, **evidence})
            host = json.loads((args.host_run / case_id / "case.json").read_text())
            if host["audio_sha256"] != case["audio_sha256"] or host["reference_sha256"] != digest(confined(args.manifest.parent, case["reference"])):
                raise ValueError("Host/native scoring inputs differ: " + case_id)
            delta = 100 * (metric["wer_raw"]["rate"] - host["metrics"]["wer_raw"]["rate"])
            report["cases"].append({"id": case_id, "split": case["split"], "wer_raw": metric["wer_raw"]["rate"],
                "host_wer_raw": host["metrics"]["wer_raw"]["rate"], "wer_delta_percentage_points": delta,
                "per_file_diagnostic_pass": abs(delta) <= .5, "rtf": metric["rtf"],
                "reference_words": metric["wer_raw"]["reference_tokens"], "native_errors": metric["wer_raw"]["errors"],
                "host_errors": host["metrics"]["wer_raw"]["errors"]})
            write_json(args.output / "run.json", report)
        report["corpus_port_comparison"] = summarize(report["cases"])
        passed = report["corpus_port_comparison"]["gate_pass"]
        report.update(status="COMPLETE" if passed else "PORT_PARITY_FAIL", completed_at=datetime.now(timezone.utc).isoformat())
        write_json(args.output / "run.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if passed else 2
    except BaseException as error:
        report.update(status="FAILED", error=str(error), failed_at=datetime.now(timezone.utc).isoformat())
        write_json(args.output / "run.json", report)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
