#!/usr/bin/env python3
"""Step 6, item 3: SD time breakdown and a joint shift x SD-threshold x tau sweep.

For every (shift, native threshold) the real SD runs once per file and the C2
clean-window embeddings are measured once; tau is then swept on those saved
vectors (pure, no inference). Audio goes through the Android decoder parity
path exactly like the C2 acceptance runs; references are used only for scoring.
Selection uses dev only; holdout/reserve are scored for the frozen candidates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from tools.eval.long_diar import Native  # noqa: E402
from tools.eval.pipeline import _read_canonical_wav  # noqa: E402
from tools.eval.score import der  # noqa: E402
from tools.eval.window_overcluster import WindowClusterConfig, overcluster  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CORPORA = {"dev": ("benchmark/eval", Path("C:/R/eval-audio")), "holdout": ("benchmark/eval", Path("C:/R/eval-audio")),
           "reserve": ("benchmark/eval-reserve", Path("C:/R/eval-reserve-audio"))}


def cases(split: str):
    folder, audio_root = CORPORA[split]
    manifest = json.loads((REPO / folder / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        if split == "reserve" or row["split"] == split:
            yield row, audio_root / row["audio"], REPO / folder / row["reference"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=sorted(CORPORA), required=True)
    parser.add_argument("--shift", type=float, required=True)
    parser.add_argument("--thresholds", type=float, nargs="+", required=True)
    parser.add_argument("--taus", type=float, nargs="+", default=[round(.28 + .02 * i, 2) for i in range(9)])
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = []
    for threshold in args.thresholds:
        for meta, audio, reference_path in cases(args.split):
            samples = _read_canonical_wav(audio, np)
            native = Native(threads=args.threads, threshold=threshold, shift=args.shift)
            began = time.perf_counter()
            turns = native.sd(samples)
            # tau only affects pure clustering; measure embeddings once via a tau-.36 call.
            _, measured, _, _ = native.refine(samples, turns)
            elapsed = time.perf_counter() - began
            reference = json.loads(reference_path.read_text(encoding="utf-8"))["transcript"]
            duration = meta["duration_ms"]
            for tau in args.taus:
                result = overcluster(turns, measured, duration, WindowClusterConfig(
                    tau=tau, method="average", grid_ms=125, max_speakers=8, reassign_small=True))
                out = list(result.turns)
                hyp = [{"speaker_id": f"s{t.speaker}", "start_ms": t.start_ms, "end_ms": t.end_ms, "text": ""} for t in out]
                score = der(reference, hyp, duration)
                rows.append({"split": args.split, "id": meta["id"], "shift": args.shift, "threshold": threshold, "tau": tau,
                             "k": len({t.speaker for t in out}), "ref_k": meta["expected_speakers"],
                             "der0_error_ms": score["error_speaker_ms"], "der0_reference_ms": score["reference_speaker_ms"],
                             "der0": score["rate"], "accepted": result.accepted, "duration_ms": duration,
                             "timings": native.timings, "native_turns": len(turns), "windows": len(measured),
                             "elapsed_s": elapsed})
            print(f"{args.split} shift={args.shift} thr={threshold} {meta['id']:28s} "
                  f"sd={native.timings.get('sd_total_s', 0):.2f}s emb={native.timings.get('refiner_embedding_s', 0):.2f}s", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
