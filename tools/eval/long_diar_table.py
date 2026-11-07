#!/usr/bin/env python3
"""Markdown/CSV table of long_diar.py reports: length -> time / peak memory / DER / K."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args(argv)
    rows = []
    for path in args.reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        if "skipped" in report:
            continue
        cfg = report.get("chunk_config") or {}
        rows.append({
            "file": Path(report["audio"]).stem, "variant": path.stem.split(Path(report["audio"]).stem + "-")[-1],
            "minutes": round(report["duration_ms"] / 60000, 1), "path": report["path"],
            "windows": len(report.get("windows", [])), "window_min": cfg.get("window_ms", 0) / 60000 or None,
            "wall_s": round(report["wall_s"], 1), "rtf": round(report["rtf"], 3),
            "peak_ws_mb": round(report["memory"]["peak_working_set_mb"]),
            "peak_private_mb": round(report["memory"].get("peak_private_mb", 0)),
            "k": report["speakers"], "ref_k": report.get("reference_speakers"),
            "der_pct": round(report["der"]["der"] * 100, 2), "confusion_pct": round(report["der"]["confusion"] * 100, 2),
            "c2_applied": report.get("refined_reason") != "too_many_windows_for_quadratic_hc",
            "cpu_note": report.get("note", "")})
    rows.sort(key=lambda r: (r["file"], r["path"], r["variant"]))
    print("| Файл | Мин | Путь | Окон | Время, с | RTF | Пик WS, МБ | Пик private, МБ | K / эталон | DER, % | Путаница, % | Загрузка CPU |")
    print("|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in rows:
        print(f"| {r['file']} ({r['variant']}) | {r['minutes']} | {r['path']} | {r['windows']} | {r['wall_s']} | {r['rtf']} | "
              f"{r['peak_ws_mb']} | {r['peak_private_mb']} | {r['k']} / {r['ref_k']} | {r['der_pct']} | {r['confusion_pct']} | "
              f"{r['cpu_note'].replace('cpu_load_at_start=', '')}% |")
    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
