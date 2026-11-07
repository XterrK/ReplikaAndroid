#!/usr/bin/env python3
"""Compare step-14 runs pulled by parallel_ab.py: byte equality of jury JSON and processing time.

  py -3.13 tools/eval/parallel_ab_compare.py --seq RUN_DIR [RUN_DIR...] --par RUN_DIR [RUN_DIR...]
"""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median


def load(run):
    out = {}
    for f in sorted(run.glob("*.case.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        hyp = run / f"{case['id']}.hypothesis.json"
        diag = json.loads((run / f"{case['id']}.diagnostics.json").read_text(encoding="utf-8"))
        stages = diag.get("stagesMs", {})
        out[case["id"]] = {"ms": case["processing_ms"], "audio": case["duration_ms"],
                           "sha": hashlib.sha256(hyp.read_bytes()).hexdigest(),
                           "diar": stages.get("diarizationMs"), "asr": stages.get("asrMs"),
                           "pss": diag.get("finalPssKb"), "maxPss": (diag.get("telemetry") or {}).get("observedMaxPssKb"),
                           "parallel": (diag.get("parallelAsrDiarization") or {}).get("enabled")}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seq", nargs="+", type=Path, required=True)
    p.add_argument("--par", nargs="+", type=Path, required=True)
    a = p.parse_args()
    seq = [load(r) for r in a.seq]
    par = [load(r) for r in a.par]
    ids = sorted(set.intersection(*(set(r) for r in seq + par)))
    print("| case | audio s | seq ms (median) | par ms (median) | gain | seq diar/asr ms | jury JSON equal |")
    print("|---|---:|---:|---:|---:|---|---|")
    ts = tp = 0
    all_equal = True
    for i in ids:
        s = median(r[i]["ms"] for r in seq)
        q = median(r[i]["ms"] for r in par)
        shas = {r[i]["sha"] for r in seq + par}
        eq = len(shas) == 1
        all_equal &= eq
        ts += s
        tp += q
        print(f"| {i} | {seq[0][i]['audio']/1000:.1f} | {s:.0f} | {q:.0f} | {100*(s-q)/s:+.1f}% | "
              f"{seq[0][i]['diar']}/{seq[0][i]['asr']} | {'yes' if eq else 'NO'} |")
    print(f"| **total** | {sum(seq[0][i]['audio'] for i in ids)/1000:.1f} | {ts:.0f} | {tp:.0f} | {100*(ts-tp)/ts:+.1f}% | | {'all equal' if all_equal else 'DIFFERENT'} |")
    print()
    print("max observed PSS KB  seq:", max(r[i]["maxPss"] or 0 for r in seq for i in ids),
          " par:", max(r[i]["maxPss"] or 0 for r in par for i in ids))
    print("parallel flags seq:", {r[i]["parallel"] for r in seq for i in ids}, " par:", {r[i]["parallel"] for r in par for i in ids})


if __name__ == "__main__":
    main()
