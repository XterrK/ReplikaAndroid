#!/usr/bin/env python3
"""Summarise sd_speed_sweep.py outputs: pooled DER0 and exact-K per profile."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

GATES = {  # current C2 (STEP_04): correct K and pooled native DER0 per group
    "dev": (7, .18298480576441103), "holdout": (4, .138896), "reserve": (5, .224396)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args(argv)
    groups = defaultdict(list)
    for path in args.files:
        for row in json.loads(path.read_text(encoding="utf-8")):
            groups[(row["split"], row["shift"], row["threshold"], row["tau"])].append(row)
    table = []
    for (split, shift, thr, tau), rows in groups.items():
        err = sum(r["der0_error_ms"] for r in rows)
        ref = sum(r["der0_reference_ms"] for r in rows)
        k = sum(r["k"] == r["ref_k"] for r in rows)
        seen = {r["id"]: r for r in rows}
        sd = sum(r["timings"].get("sd_total_s", 0) for r in seen.values())
        emb = sum(r["timings"].get("refiner_embedding_s", 0) for r in seen.values())
        gate_k, gate_der = GATES[split]
        table.append((split, shift, thr, tau, k, len(rows), err / ref, sd, emb,
                      k >= gate_k and err / ref <= gate_der + 1e-12))
    table.sort(key=lambda r: (r[0], -r[4], r[6]))
    print("split   shift  thr   tau   K      DER0%   SDs    embS  passes-C2-gate")
    for row in table[:args.top] if args.top else table:
        split, shift, thr, tau, k, n, der, sd, emb, ok = row
        print(f"{split:7s} {shift:.2f}  {thr:.2f}  {tau:.2f}  {k}/{n}  {der * 100:7.3f}  {sd:6.1f} {emb:6.1f}  {'PASS' if ok else ''}")


if __name__ == "__main__":
    main()
