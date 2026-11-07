#!/usr/bin/env python3
"""Step 14 A/B: the same installed APK, sequential vs parallel ASR+diarization, through the production Worker.

Stages canonical WAVs into files/evaluation/<run>/ of the QA package on ONE explicit emulator, runs
EvaluationBatchTest#stagedCanonicalInputsThroughProductionWorker with evalParallel=false|true and pulls
<case>.hypothesis.json / <case>.case.json / <case>.diagnostics.json. No app-data wipe, no reference text.

Example:
  py -3.13 tools/eval/parallel_ab.py --serial emulator-5620 --out C:/R/step14 --label seq --parallel false \
     C:/R/eval-audio/dev/dev-01-two-clean.wav ...
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb", default="adb")
    p.add_argument("--serial", required=True)
    p.add_argument("--package", default="ru.replika.offline.aioqa")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--parallel", choices=("true", "false"), required=True)
    p.add_argument("--asr-plan", default="vad_words_context600")
    p.add_argument("--diar-plan", default="eres2net_window_chunked_v1")
    p.add_argument("--cpu-plan", default="auto_v1")
    p.add_argument("--threads", default="0")
    p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("audio", nargs="+", type=Path)
    a = p.parse_args()

    def adb(*args, check=True, timeout=600):
        r = subprocess.run([a.adb, "-s", a.serial, *map(str, args)], capture_output=True, timeout=timeout)
        if check and r.returncode:
            raise RuntimeError(f"adb {args} failed: {r.stderr.decode('utf-8', 'replace')}{r.stdout.decode('utf-8', 'replace')}")
        return r

    if adb("shell", "getprop", "ro.kernel.qemu").stdout.strip() != b"1":
        raise SystemExit("Refusing: the selected device is not an emulator")
    run = f"step14{a.label}{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    out = a.out / run
    out.mkdir(parents=True)
    cases = []
    tmp = f"/data/local/tmp/{run}"
    adb("shell", "mkdir", "-p", tmp)
    adb("shell", "run-as", a.package, "mkdir", "-p", f"files/evaluation/{run}/audio")
    for wav in a.audio:
        case_id = wav.stem
        sha = hashlib.sha256(wav.read_bytes()).hexdigest()
        adb("push", wav, f"{tmp}/{case_id}.wav")
        adb("shell", "run-as", a.package, "cp", f"{tmp}/{case_id}.wav", f"files/evaluation/{run}/audio/{case_id}.wav")
        cases.append({"id": case_id, "audio": f"audio/{case_id}.wav", "sha256": sha})
    batch = out / "batch.json"
    batch.write_text(json.dumps({"schema_version": 1, "run": run, "cases": cases}, indent=2), encoding="utf-8")
    adb("push", batch, f"{tmp}/batch.json")
    adb("shell", "run-as", a.package, "cp", f"{tmp}/batch.json", f"files/evaluation/{run}/batch.json")
    adb("shell", "rm", "-rf", tmp)
    started = datetime.now(timezone.utc)
    r = adb("shell", "am", "instrument", "-w", "-r",
            "-e", "class", "ru.replika.EvaluationBatchTest#stagedCanonicalInputsThroughProductionWorker",
            "-e", "evalRun", run, "-e", "evalAsrPlan", a.asr_plan, "-e", "evalDiarPlan", a.diar_plan,
            "-e", "evalCpuPlan", a.cpu_plan, "-e", "evalThreads", a.threads, "-e", "evalCollectEvidence", "false",
            "-e", "evalParallel", a.parallel,
            f"{a.package}.test/androidx.test.runner.AndroidJUnitRunner", check=False, timeout=a.timeout)
    (out / "instrument.txt").write_bytes(r.stdout + r.stderr)
    names = ["report.json"] + [f"{c['id']}.{kind}.json" for c in cases for kind in ("hypothesis", "case", "diagnostics")]
    for name in names:
        got = adb("exec-out", "run-as", a.package, "cat", f"files/evaluation/{run}/output/{name}", check=False)
        if got.returncode == 0 and got.stdout:
            (out / name).write_bytes(got.stdout)
    summary = {"run": run, "label": a.label, "parallel": a.parallel, "started": started.isoformat(),
               "instrument_ok": b"OK (1 test)" in r.stdout, "cases": []}
    for c in cases:
        f = out / f"{c['id']}.case.json"
        if f.is_file():
            case = json.loads(f.read_text(encoding="utf-8"))
            summary["cases"].append({k: case.get(k) for k in ("id", "duration_ms", "processing_ms", "worker_wall_ms", "segments")}
                                    | {"parallel": (case.get("parallelAsrDiarization") or {}).get("enabled")})
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
