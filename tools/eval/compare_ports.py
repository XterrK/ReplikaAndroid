#!/usr/bin/env python3
"""Rescore preserved v16 native outputs against the same inputs on a corrected host port.

No inference and no alteration of the source runs. The user's 0.5pp gate applies to the
weighted fixed corpus; all per-file outliers and the previous gate status remain visible.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from run import digest, write_json, confined
from score import score, der
from port_comparison import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--host-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Existing evidence cannot be overwritten; select a fresh output")
    native = json.loads((args.native_run / "android-report.json").read_text())
    host_run = json.loads((args.host_run / "run.json").read_text())
    if native["status"] != "COMPLETE" or host_run["status"] != "COMPLETE":
        parser.error("Both source inferences must have completed")
    config = host_run["config"]
    if config["pipeline"] != "v16" or native["threads"] != config["threads"] or native["expectedSpeakers"] != config["expected_speakers"]:
        parser.error("This adapter only compares matched, unchanged v16 policies")
    rows = []
    ids = [row["id"] for row in native["cases"]]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids):
        parser.error("Unsafe or duplicate case IDs")
    args.output.mkdir(parents=True)
    for case_id in ids:
        native_dir, host_dir = confined(args.native_run, case_id), confined(args.host_run, case_id)
        native_case = json.loads((native_dir / "case.json").read_text())
        host_case = json.loads((host_dir / "case.json").read_text())
        reference = json.loads((native_dir / "reference.json").read_text())
        if reference != json.loads((host_dir / "reference.json").read_text()) or native_case["audio_sha256"] != host_case["audio_sha256"]:
            raise ValueError("Comparison inputs changed: " + case_id)
        hypothesis = json.loads((native_dir / "hypothesis.json").read_text())
        diagnostic = json.loads((native_dir / "diagnostics.json").read_text())
        metric = score(reference, hypothesis, native_case["duration_ms"], processing_ms=native_case["processing_ms"])
        turns = [{"speaker_id": "native_" + str(t["speakerId"]), "start_ms": t["startMs"], "end_ms": t["endMs"], "text": ""}
                 for t in diagnostic["diarizationTurns"]]
        metric["native_der_collar_0ms"] = der(reference["transcript"], turns, native_case["duration_ms"])
        metric["native_der_collar_250ms"] = der(reference["transcript"], turns, native_case["duration_ms"], collar_ms=250)
        row = {"id": case_id, "reference_words": metric["wer_raw"]["reference_tokens"],
               "native_errors": metric["wer_raw"]["errors"], "host_errors": host_case["metrics"]["wer_raw"]["errors"],
               "native_rtf": metric["rtf"], "host_rtf": host_case["metrics"]["rtf"],
               "source_native_hypothesis_sha256": digest(native_dir / "hypothesis.json"),
               "source_host_hypothesis_sha256": digest(host_dir / "hypothesis.json")}
        if row["reference_words"] != host_case["metrics"]["wer_raw"]["reference_tokens"]:
            raise ValueError("Mismatched WER denominator")
        rows.append(row)
        write_json(args.output / case_id / "metrics.json", metric)
    comparison = summarize(rows)
    result = {"status": "COMPLETE" if comparison["gate_pass"] else "PORT_PARITY_FAIL",
              "created_at": datetime.now(timezone.utc).isoformat(), "new_model_inference": False,
              "scope": "Rescoring unchanged preserved native inference; no replacement of source hypotheses",
              "source_native_run": str(args.native_run), "source_host_run": str(args.host_run),
              "source_native_report_sha256": digest(args.native_run / "android-report.json"),
              "source_host_run_sha256": digest(args.host_run / "run.json"),
              "gate_definition": "User clarified 2026-11-06: fixed-five weighted corpus WER difference <=0.5pp; keep per-file differences",
              "comparison": comparison}
    write_json(args.output / "comparison.json", result)
    with (args.output / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["id", "reference_words", "host_errors", "native_errors", "wer_delta_percentage_points", "per_file_within_threshold", "host_rtf", "native_rtf"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader();writer.writerows(comparison["per_file_diagnostics"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if comparison["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
