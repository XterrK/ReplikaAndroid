#!/usr/bin/env python3
"""Step 6: SD/C2 stage breakdown for one file, profiles interleaved and repeated.

Prints segmentation / embedding / clustering inside sherpa SD (from its progress
callback), C2 clean-window embeddings and C2 pure clustering, per window shift.
Host numbers on a shared machine; read them as ratios, not phone timings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from tools.eval.long_diar import Native  # noqa: E402
from tools.eval.pipeline import _read_canonical_wav  # noqa: E402

KEYS = ("sd_load_s", "sd_segmentation_s", "sd_embedding_s", "sd_clustering_s", "sd_total_s",
        "refiner_embedding_s", "refiner_cluster_s", "sd_embedding_chunks", "refiner_windows")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--shifts", type=float, nargs="+", default=[.1, .15, .2])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    samples = _read_canonical_wav(args.audio, np)
    runs = []
    for repeat in range(args.repeats):
        for shift in (args.shifts if repeat % 2 == 0 else list(reversed(args.shifts))):
            native = Native(threads=args.threads, threshold=.3, shift=shift)
            turns = native.sd(samples)
            native.refine(samples, turns)
            runs.append({"shift": shift, "repeat": repeat, **{k: native.timings.get(k, 0) for k in KEYS}})
            print(json.dumps(runs[-1]), flush=True)
    summary = {}
    for shift in args.shifts:
        rows = [r for r in runs if r["shift"] == shift]
        summary[str(shift)] = {k: statistics.median(r[k] for r in rows) for k in KEYS}
    report = {"audio": str(args.audio), "audio_s": len(samples) / 16000, "threads": args.threads,
              "runs": runs, "median": summary}
    args.output.write_text(json.dumps(report, indent=1), encoding="utf-8")
    for shift, row in summary.items():
        print(shift, {k: round(v, 2) for k, v in row.items()})


if __name__ == "__main__":
    main()
