"""Continue the two observed live grid lanes; never duplicate their inference.

The initial PID is observed until terminal, then its authoritative run must say
COMPLETE. Two lanes each run two remaining embedders sequentially. A failed run
stops that lane and preserves its external log and output directory.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
LOCK = threading.Lock()
STATE = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(), "lanes": {}}


def save(lane, value):
    with LOCK:
        STATE["lanes"][lane] = value
        temporary = OUT / "queue.json.tmp"
        temporary.write_text(json.dumps(STATE, indent=2) + "\n")
        temporary.replace(OUT / "queue.json")


def is_live(pid, model_id):
    folder = Path("/proc") / str(pid)
    try:
        stat = (folder / "stat").read_text().split(") ", 1)[1].split()[0]
        if stat in ("Z", "X"):
            return False
        command = (folder / "cmdline").read_bytes().split(b"\0")
    except FileNotFoundError:
        return False
    if b"tools/eval/diar_sweep.py" not in command or model_id.encode() not in command:
        raise RuntimeError("PID identity changed; refusing to infer from its liveness")
    return True


def lane(name, pid, first_model, jobs, logs):
    try:
        if not is_live(pid, first_model):
            raise RuntimeError("Initial job was not confirmed live at coordinator start")
        save(name, {"status": "WAITING_CONFIRMED_LIVE", "pid": pid, "model_id": first_model})
        while is_live(pid, first_model):
            time.sleep(5)
        initial = OUT / ("auto-eres2net-zh" if first_model == "eres2net_zh" else "auto-wespeaker-resnet34-lm")
        if json.loads((initial / "run.json").read_text())["status"] != "COMPLETE":
            raise RuntimeError("Initial actual run did not complete; no restart or next inference")
        for model_id, folder in jobs:
            command = [sys.executable, "tools/eval/diar_sweep.py", "--audio-root", "/home/egor/replika-toolchain/eval-audio",
                "--asr-run", "artifacts/test-results/step-03/context600-selected-host", "--embedding-root",
                "/home/egor/replika-toolchain/diar-models", "--model-id", model_id, "--mode", "auto", "--thresholds",
                ".30,.35,.40,.45,.50,.55,.60,.65,.70,.75,.80,.85,.90,.95", "--collect-windows", "--window-profiles",
                "auto-0p30", "auto-0p50", "--output", str(OUT / folder)]
            log_path = logs / (folder + ".log")
            save(name, {"status": "RUNNING", "model_id": model_id, "command": command, "log": str(log_path)})
            with log_path.open("x") as log:
                result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode != 0 or json.loads((OUT / folder / "run.json").read_text())["status"] != "COMPLETE":
                raise RuntimeError("Grid failed: " + model_id + "; log " + str(log_path))
            print(json.dumps({"completed": model_id, "lane": name}), flush=True)
        save(name, {"status": "COMPLETE"})
    except BaseException as error:
        save(name, {"status": "FAILED", "error": str(error)})
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eres-pid", type=int, required=True)
    parser.add_argument("--resnet-pid", type=int, required=True)
    parser.add_argument("--logs", type=Path, required=True)
    args = parser.parse_args()
    args.logs.mkdir(parents=True, exist_ok=True)
    if (OUT / "queue.json").exists():
        raise ValueError("Preserved queue cannot be overwritten")
    STATE["coordinator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(lane, "eres", args.eres_pid, "eres2net_zh",
                    [("campplus_en", "auto-campplus-en"), ("titanet_small", "auto-titanet-small")], args.logs),
                 pool.submit(lane, "resnet", args.resnet_pid, "wespeaker_resnet34_lm",
                    [("wespeaker_camplus_lm", "auto-wespeaker-camplus-lm"), ("titanet_large", "auto-titanet-large")], args.logs)]
        failed = False
        for future in tasks:
            try:
                future.result()
            except BaseException:
                failed = True
    STATE["status"] = "FAILED" if failed else "COMPLETE"
    STATE["completed_at"] = datetime.now(timezone.utc).isoformat()
    save("coordinator", {"status": STATE["status"]})
    sys.exit(int(failed))


if __name__ == "__main__":
    main()
