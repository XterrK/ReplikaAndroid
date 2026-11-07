#!/usr/bin/env python3
"""Replay chunked-diarization variants from per-window dumps (no new inference).

Dumps (``long_diar.py chunked --dump``) keep each window's real SD turns and
real clean-window vectors. Variants:

* ``c2``     - the shipped chunked policy: per-window C2 (small clusters folded
               inside the window), window centroids, global clustering.
* ``global-small`` - per-window C2 WITHOUT the in-window small-cluster rule;
               global clustering; then global clusters whose total speech is
               below ``--small-ms`` are folded into the most similar remaining
               cluster. A rare speaker who is small in every window but present
               in many windows survives.
Select on ``tune`` dumps only.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from tools.eval.long_diar import (C2_CONFIG, ChunkConfig, Turn, fast_der, global_clusters, resolve_labels,  # noqa: E402
                                  stitch, stitch_points, window_centroids, _cosine, _unit)
from tools.eval.speaker_refiner import EmbeddingWindow  # noqa: E402
from tools.eval.window_overcluster import overcluster  # noqa: E402


def load(dump_dir: Path, stem: str):
    out = []
    for path in sorted(dump_dir.glob(f"{stem}-w*.npz")):
        z = np.load(path)
        start, end = (int(x) for x in z["start_end"])
        turns = [Turn(int(a), int(b), int(s)) for a, b, s in z["turns"]]
        measured = [EmbeddingWindow(int(a), int(b), int(s), tuple(float(x) for x in v))
                    for (a, b, s), v in zip(z["windows"], z["vectors"])]
        out.append((start, end, turns, measured))
    return out


def fold_small(centroids, labels, small_ms):
    """Fold global clusters below small_ms of speech into the most similar larger one."""
    speech, sums = {}, {}
    for c, g in zip(centroids, labels):
        speech[g] = speech.get(g, 0) + c.speech_ms
        acc = sums.setdefault(g, [0.] * len(c.vector))
        for i, x in enumerate(c.vector):
            acc[i] += x * c.speech_ms
    means = {g: _unit(v) for g, v in sums.items()}
    anchors = [g for g in speech if speech[g] >= small_ms] or [max(speech, key=lambda g: (speech[g], -g))]
    target = {}
    for g in speech:
        if g in anchors or means[g] is None:
            target[g] = g
        else:
            target[g] = max(anchors, key=lambda a: (_cosine(means[g], means[a]) if means[a] else -2, -a))
    order, stable = sorted(set(target.values())), {}
    for g in order:
        stable[g] = len(stable)
    return [stable[target[g]] for g in labels]


def replay(windows_data, variant: str, config: ChunkConfig, small_ms: int):
    windows = [(s, e) for s, e, _, _ in windows_data]
    local, centroids = [], []
    c2 = C2_CONFIG if variant == "c2" else replace(C2_CONFIG, reassign_small=False)
    for k, (start, end, turns, measured) in enumerate(windows_data):
        result = overcluster(turns, measured, end - start, c2)
        refined = list(result.turns)
        local.append(refined)
        centroids += window_centroids(k, refined, measured)
    labels = global_clusters(centroids, config)
    if variant == "global-small":
        labels = fold_small(centroids, labels, small_ms)
    mapping = resolve_labels(local, centroids, labels, len(windows))
    return stitch(windows, local, mapping, stitch_points(windows, local, config))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("stems", nargs="+")
    parser.add_argument("--dump-dir", type=Path, default=Path("C:/R/step06-out/dumps"))
    parser.add_argument("--audio-root", type=Path, default=Path("C:/R/eval-long-audio"))
    parser.add_argument("--variants", nargs="+", default=["c2", "global-small"])
    parser.add_argument("--small-ms", type=int, nargs="+", default=[10_000, 20_000, 40_000, 80_000])
    parser.add_argument("--taus", type=float, nargs="+", default=[.5])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    rows = []
    for stem in args.stems:
        data = load(args.dump_dir, stem)
        reference = json.loads((args.audio_root / f"{stem}.json").read_text(encoding="utf-8"))
        duration = reference["duration_ms"]
        ref_k = len({r["speaker_id"] for r in reference["transcript"]})
        for variant in args.variants:
            for small in (args.small_ms if variant == "global-small" else [0]):
                for tau in args.taus:
                    turns = replay(data, variant, ChunkConfig(global_tau=tau), small)
                    d = fast_der(reference["transcript"], turns, duration, 1 if duration <= 3 * 3600_000 else 10)
                    k = len({t.speaker for t in turns})
                    rows.append({"stem": stem, "variant": variant, "small_ms": small, "tau": tau, "k": k, "ref_k": ref_k, **d})
                    print(f"{stem:26s} {variant:12s} small={small:6d} tau={tau:.2f} K={k}/{ref_k} "
                          f"DER={d['der'] * 100:6.2f} conf={d['confusion'] * 100:6.2f}", flush=True)
    if args.output:
        args.output.write_text(json.dumps(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
