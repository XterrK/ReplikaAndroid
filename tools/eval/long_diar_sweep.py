#!/usr/bin/env python3
"""Re-stitch saved chunked runs with other global settings (no new inference).

Each chunked report keeps per-window local turns and per-window centroids, so
the global clustering threshold can be swept offline. Use only ``tune`` pool
splices for selection; ``check`` splices are scored once with the frozen value.
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

from tools.eval.long_diar import (ChunkConfig, Centroid, Turn, fast_der, global_clusters,  # noqa: E402
                                  resolve_labels, stitch, stitch_points)


def restitch(report: dict, config: ChunkConfig) -> list[Turn]:
    windows = [tuple(w) for w in report["windows"]]
    local = [[Turn(*t) for t in lt] for lt in report["local_turns"]]
    centroids = [Centroid(c["window"], c["label"], tuple(c["vector"]), c["speech_ms"]) for c in report["centroids"]]
    labels = global_clusters(centroids, config)
    mapping = resolve_labels(local, centroids, labels, len(windows))
    return stitch(windows, local, mapping, stitch_points(windows, local, config))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--taus", type=float, nargs="+", default=[.3, .35, .4, .45, .5, .55, .6, .65, .7])
    parser.add_argument("--audio-root", type=Path, default=Path("C:/R/eval-long-audio"))
    args = parser.parse_args(argv)
    rows = []
    for path in args.reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        audio = Path(report["audio"])
        reference = json.loads((args.audio_root / (audio.stem + ".json")).read_text(encoding="utf-8"))
        base = ChunkConfig(**report["chunk_config"])
        for tau in args.taus:
            turns = restitch(report, replace(base, global_tau=tau))
            der = fast_der(reference["transcript"], turns, report["duration_ms"],
                           1 if report["duration_ms"] <= 3 * 3600_000 else 10)
            k = len({t.speaker for t in turns})
            ref_k = len({r["speaker_id"] for r in reference["transcript"]})
            rows.append({"file": audio.stem, "tau": tau, "der": der["der"], "confusion": der["confusion"], "k": k, "ref_k": ref_k})
            print(f"{audio.stem:28s} tau={tau:.2f} K={k}/{ref_k} DER={der['der'] * 100:6.2f} conf={der['confusion'] * 100:6.2f}")
    print("\nmean over files:")
    for tau in args.taus:
        sel = [r for r in rows if r["tau"] == tau]
        print(f"tau={tau:.2f} meanDER={sum(r['der'] for r in sel) / len(sel) * 100:6.2f} "
              f"exactK={sum(r['k'] == r['ref_k'] for r in sel)}/{len(sel)} "
              f"meanAbsKerr={sum(abs(r['k'] - r['ref_k']) for r in sel) / len(sel):.2f}")


if __name__ == "__main__":
    main()
