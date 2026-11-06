#!/usr/bin/env python3
"""Compare paired saved runs without inference; dev-only selection stays blind to holdout.

Writes report.json/report.md to a fresh directory. Exit 0 means a report was
written (inspect gate.status); invalid/unpaired input exits 2. No rates are
averaged across files and unavailable metrics never become perfect scores.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

TOKEN_METRICS = ("wer_raw", "wer_punctuation_tokens", "wer_normalized", "cer_normalized",
                 "cpwer_raw", "cpwer_normalized")
DER_METRICS = ("der_collar_0ms", "der_collar_250ms", "native_der_collar_0ms", "native_der_collar_250ms")
TOKEN_COUNTS = ("errors", "substitutions", "deletions", "insertions", "reference_tokens", "hypothesis_tokens")
DER_COUNTS = ("miss_ms", "false_alarm_ms", "confusion_ms", "reference_speaker_ms")
TIMING_COUNTS = ("matched_pairs", "reference_intervals", "hypothesis_intervals",
                 "unmatched_reference", "unmatched_hypothesis", "pairs_over_250ms")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def invalid(value):
        raise ValueError(f"Nonfinite JSON number in {path}: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid)


def number(value, integer=False):
    return type(value) is int and value >= 0 if integer else type(value) in (int, float) and math.isfinite(value) and value >= 0


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def confined(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes manifest: {relative}")
    return path


def run_ids(run_dir, excluded_ids):
    # Directory names/exists checks do not open excluded holdout case files.
    return {path.name for path in run_dir.iterdir()
            if path.is_dir() and path.name not in excluded_ids and (path / "case.json").is_file()}


def load_case(run_dir, case, reference_hash):
    folder = run_dir / case["id"]
    record = read_json(folder / "case.json")
    for field in ("id", "split", "audio_sha256", "duration_ms"):
        if record.get(field) != case[field]:
            raise ValueError(f"{run_dir.name}/{case['id']}: unpaired {field}")
    if record.get("reference_sha256") != reference_hash:
        raise ValueError(f"{run_dir.name}/{case['id']}: independent reference hash differs")
    if record.get("status") == "FAILED":
        raise ValueError(f"Failed case cannot be paired: {folder}")
    if digest(folder / "reference.json") != reference_hash:
        raise ValueError(f"Saved independent reference changed: {folder}")
    metrics = read_json(folder / "metrics.json")
    if not isinstance(metrics, dict):
        raise ValueError(f"metrics.json must be an object: {folder}")
    if "metrics" in record and record["metrics"] != metrics:
        raise ValueError(f"case.json and metrics.json disagree: {folder}")
    for name, expected in record.get("evidence_sha256", {}).items():
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("Unsafe evidence filename")
        if digest(folder / name) != expected:
            raise ValueError(f"Saved evidence changed: {folder / name}")
    inputs = metrics.get("inputs", {})
    if "duration_ms" in inputs and inputs["duration_ms"] != case["duration_ms"]:
        raise ValueError(f"Scored duration differs: {folder}")
    return {"id": case["id"], "duration_ms": case["duration_ms"], "metrics": metrics,
            "processing_ms": record.get("processing_ms"), "runner_wall_ms": record.get("runner_wall_ms"),
            "case_sha256": digest(folder / "case.json"), "metrics_sha256": digest(folder / "metrics.json")}


def counters(records, field, keys, integer=True):
    observed, missing = [], []
    for record in records:
        metric = record["metrics"].get(field)
        if metric is None or isinstance(metric, dict) and metric.get("available") is False:
            missing.append(record["id"])
            continue
        if not isinstance(metric, dict):
            raise ValueError(f"{record['id']}.{field} must be an object or null")
        # Absent/null components are unavailable, never zero.
        if any(metric.get(key) is None for key in keys):
            missing.append(record["id"])
            continue
        if any(not number(metric[key], integer) for key in keys):
            raise ValueError(f"Invalid nonnegative counters: {record['id']}.{field}")
        observed.append(metric)
    result = {key: sum(value[key] for value in observed) for key in keys}
    result.update(available_cases=len(observed), total_cases=len(records), missing_cases=missing,
                  complete=bool(records) and not missing)
    return result


def aggregate_timing(records):
    result = counters(records, "timing", TIMING_COUNTS)
    all_pairs, missing_pair_cases = [], []
    for record in records:
        timing = record["metrics"].get("timing")
        if not isinstance(timing, dict) or not isinstance(timing.get("pairs"), list):
            missing_pair_cases.append(record["id"])
            continue
        if len(timing["pairs"]) != timing.get("matched_pairs"):
            raise ValueError(f"Timing pair count differs: {record['id']}")
        for pair in timing["pairs"]:
            if any(not number(pair.get(key)) for key in ("start_abs_error_ms", "end_abs_error_ms")):
                raise ValueError(f"Invalid timing pair: {record['id']}")
            all_pairs.append(pair)
    complete_pairs = result["complete"] and not missing_pair_cases
    result["per_pair_complete"] = complete_pairs
    result["missing_pair_cases"] = missing_pair_cases
    for edge in ("start", "end"):
        errors = [pair[f"{edge}_abs_error_ms"] for pair in all_pairs]
        result[f"median_{edge}_abs_error_ms"] = statistics.median(errors) if errors and complete_pairs else None
        result[f"mean_{edge}_abs_error_ms"] = statistics.mean(errors) if errors and complete_pairs else None
    for target, n, d in (("reference_coverage", "matched_pairs", "reference_intervals"),
                         ("hypothesis_coverage", "matched_pairs", "hypothesis_intervals"),
                         ("fraction_over_250ms", "pairs_over_250ms", "matched_pairs")):
        result[target] = ratio(result[n], result[d]) if result["complete"] else None
    result["reference_fraction_over_250ms_or_unmatched"] = ratio(
        result["pairs_over_250ms"] + result["unmatched_reference"], result["reference_intervals"]) if result["complete"] else None
    start, end = (result[f"median_{edge}_abs_error_ms"] for edge in ("start", "end"))
    result["median_both_below_200ms_diagnostic"] = start < 200 and end < 200 if start is not None and end is not None else None
    result["word_timestamp_acceptance"] = None
    result["scope"] = "Utterance/clip-bound reference proxy; global medians across matched pairs. Not word-timestamp acceptance; always inspect coverage."
    return result


def aggregate_speakers(records, native=False):
    values, missing = [], []
    for record in records:
        metric = record["metrics"]
        reference = (metric.get("speakers") or {}).get("reference")
        hypothesis = metric.get("native_speaker_count") if native else (metric.get("speakers") or {}).get("hypothesis")
        if reference is None or hypothesis is None:
            missing.append(record["id"])
            continue
        if not number(reference, True) or not number(hypothesis, True):
            raise ValueError(f"Invalid speaker counts: {record['id']}")
        values.append({"id": record["id"], "reference": reference, "hypothesis": hypothesis,
                       "signed_error": hypothesis - reference, "absolute_error": abs(hypothesis - reference)})
    complete = bool(records) and not missing
    absolute = sum(value["absolute_error"] for value in values)
    exact = sum(value["absolute_error"] == 0 for value in values)
    return {"available_cases": len(values), "total_cases": len(records), "complete": complete,
            "missing_cases": missing, "exact_cases": exact, "absolute_error_sum": absolute,
            "exact_rate": ratio(exact, len(records)) if complete else None,
            "mean_absolute_error": ratio(absolute, len(records)) if complete else None, "cases": values}


def aggregate(records):
    result = {"cases": len(records), "case_ids": [record["id"] for record in records]}
    for field in TOKEN_METRICS:
        metric = counters(records, field, TOKEN_COUNTS)
        for record in records:
            value = record["metrics"].get(field)
            if not isinstance(value, dict) or any(value.get(key) is None for key in TOKEN_COUNTS):
                continue
            if value["errors"] != sum(value[key] for key in ("substitutions", "deletions", "insertions")):
                raise ValueError(f"Errors do not equal S+D+I: {record['id']}.{field}")
        metric["rate"] = ratio(metric["errors"], metric["reference_tokens"]) if metric["complete"] else None
        result[field] = metric
    for field in DER_METRICS:
        metric = counters(records, field, DER_COUNTS, integer=False)
        metric["rate"] = ratio(sum(metric[key] for key in DER_COUNTS[:3]), metric["reference_speaker_ms"]) if metric["complete"] else None
        result[field] = metric
    punctuation = counters(records, "punctuation", ("true_positive", "false_positive", "false_negative"))
    tp, fp, fn = (punctuation[key] for key in ("true_positive", "false_positive", "false_negative"))
    for name, numerator, denominator in (("precision", tp, tp + fp), ("recall", tp, tp + fn), ("f1", 2 * tp, 2 * tp + fp + fn)):
        punctuation[name] = ratio(numerator, denominator) if punctuation["complete"] else None
    result["punctuation"] = punctuation
    initial = counters(records, "initial_case", ("correct", "reference_initials", "aligned_reference_initials", "unmatched_reference_initials"))
    initial["accuracy"] = ratio(initial["correct"], initial["reference_initials"]) if initial["complete"] else None
    initial["conditional_accuracy"] = ratio(initial["correct"], initial["aligned_reference_initials"]) if initial["complete"] else None
    result["initial_case"] = initial
    result["timing"] = aggregate_timing(records)
    result["export_speakers"] = aggregate_speakers(records)
    result["native_speakers"] = aggregate_speakers(records, native=True)
    result["audio_ms"] = sum(record["duration_ms"] for record in records)
    for field in ("processing_ms", "runner_wall_ms"):
        observed = [record.get(field) for record in records]
        if any(value is not None and not number(value) for value in observed):
            raise ValueError(f"Invalid {field}")
        complete = bool(records) and all(value is not None for value in observed)
        result[field] = sum(observed) if complete else None
        result[field + "_available_cases"] = sum(value is not None for value in observed)
    result["rtf"] = ratio(result["processing_ms"], result["audio_ms"]) if result["processing_ms"] is not None else None
    return result


def deletion_axis(baseline, candidate, case_ids):
    base, cand = baseline["wer_raw"], candidate["wer_raw"]
    available = bool(case_ids) and base["complete"] and cand["complete"]
    old, new = (base["deletions"], cand["deletions"]) if available else (None, None)
    reduction = (old - new) / old if old else None
    status = "PASS" if reduction is not None and reduction >= .30 else "FAIL" if reduction is not None else "UNASSESSABLE"
    return {"case_ids": case_ids, "baseline_raw_deletions": old, "candidate_raw_deletions": new,
            "baseline_normalized_deletions": baseline["wer_normalized"]["deletions"] if baseline["wer_normalized"]["complete"] else None,
            "candidate_normalized_deletions": candidate["wer_normalized"]["deletions"] if candidate["wer_normalized"]["complete"] else None,
            "relative_deletion_reduction": reduction, "required_relative_reduction": .30, "status": status,
            "scope": "Additional short-case axis, separate from primary WER gates; zero baseline deletions cannot prove a 30% reduction."}


def check_rate(splits, split, metric, strict):
    if split not in splits:
        return {"status": "NOT_EVALUATED", "baseline": None, "candidate": None}
    old = splits[split]["baseline"][metric]["rate"]
    new = splits[split]["candidate"][metric]["rate"]
    status = "UNASSESSABLE" if old is None or new is None else "PASS" if (new < old if strict else new <= old) else "FAIL"
    return {"status": status, "baseline": old, "candidate": new, "comparison": "strictly_less" if strict else "less_or_equal"}


def gate(splits):
    checks = {"dev_raw_wer_strictly_better": check_rate(splits, "dev", "wer_raw", True),
              "dev_normalized_wer_no_worse": check_rate(splits, "dev", "wer_normalized", False),
              "holdout_raw_wer_no_worse": check_rate(splits, "holdout", "wer_raw", False)}
    states = [value["status"] for value in checks.values()]
    accepted = all(state == "PASS" for state in states)
    status = "PASS" if accepted else "FAIL" if "FAIL" in states else "UNASSESSABLE" if "UNASSESSABLE" in states else "PENDING_UNEVALUATED_SPLIT"
    return {"status": status, "accepted": accepted, "checks": checks,
            "additional_axes": "Short deletion target and coarse timing diagnostics are reported separately; no real word-timestamp acceptance without independent word gold."}


def compare(baseline, candidate, manifest_path, split="dev"):
    baseline, candidate, manifest_path = Path(baseline).resolve(), Path(candidate).resolve(), Path(manifest_path).resolve()
    if split not in ("dev", "holdout", "all"):
        raise ValueError("split must be dev, holdout or all")
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError("Invalid corpus manifest schema")
    all_cases = manifest["files"]
    ids = [case["id"] for case in all_cases]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", identifier) for identifier in ids):
        raise ValueError("Duplicate/unsafe manifest case IDs")
    selected = [case for case in all_cases if split == "all" or case["split"] == split]
    if not selected:
        raise ValueError("Empty selected split")
    expected = {case["id"] for case in selected}
    excluded = set(ids) - expected
    for root in (baseline, candidate):
        actual = run_ids(root, excluded)
        if actual != expected:
            raise ValueError(f"Unpaired case IDs in {root}: missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    paired = []
    for case in selected:
        if not number(case.get("duration_ms"), True) or not case["duration_ms"]:
            raise ValueError("Invalid manifest duration")
        reference_hash = digest(confined(manifest_path.parent, case["reference"]))
        if case.get("reference_sha256", reference_hash) != reference_hash:
            raise ValueError(f"Manifest reference hash differs: {case['id']}")
        old, new = (load_case(root, case, reference_hash) for root in (baseline, candidate))
        if old["metrics"].get("protocol") != new["metrics"].get("protocol"):
            raise ValueError(f"Scoring protocols differ: {case['id']}")
        for metric in TOKEN_METRICS:
            a, b = old["metrics"].get(metric), new["metrics"].get(metric)
            if isinstance(a, dict) and isinstance(b, dict) and a.get("reference_tokens") is not None and b.get("reference_tokens") is not None and a["reference_tokens"] != b["reference_tokens"]:
                raise ValueError(f"Unpaired reference token denominator: {case['id']}.{metric}")
        for metric, denominator in [(name, "reference_speaker_ms") for name in DER_METRICS] + [("speakers", "reference"), ("timing", "reference_intervals")]:
            a, b = old["metrics"].get(metric), new["metrics"].get(metric)
            if isinstance(a, dict) and isinstance(b, dict) and a.get(denominator) is not None and b.get(denominator) is not None and a[denominator] != b[denominator]:
                raise ValueError(f"Unpaired reference denominator: {case['id']}.{metric}.{denominator}")
        paired.append((case, old, new))
    splits = {}
    for name in ("dev", "holdout"):
        group = [(case, old, new) for case, old, new in paired if case["split"] == name]
        if not group:
            continue
        old = aggregate([old for _, old, _ in group])
        new = aggregate([new for _, _, new in group])
        short = [(case, a, b) for case, a, b in group if case.get("conditions", {}).get("short_utterances") is True]
        axis = deletion_axis(aggregate([a for _, a, _ in short]), aggregate([b for _, _, b in short]), [case["id"] for case, _, _ in short])
        deltas = {metric: (new[metric]["rate"] - old[metric]["rate"]) if new[metric]["rate"] is not None and old[metric]["rate"] is not None else None for metric in TOKEN_METRICS + DER_METRICS}
        splits[name] = {"baseline": old, "candidate": new, "rate_deltas_candidate_minus_baseline": deltas, "short_utterance_deletion_axis": axis}
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "selected_split": split,
            "inputs": {"baseline": str(baseline), "candidate": str(candidate), "manifest": str(manifest_path),
                       "manifest_sha256": digest(manifest_path), "selected_case_ids": [case["id"] for case in selected],
                       "validation": "Exact selected IDs, declared original audio SHA against manifest, independent source/copied reference hashes, optional saved evidence hashes; external audio not rehashed by this report"},
            "scope": "Saved host outputs only; no inference, no summary.json reads, no excluded split case/reference reads. Utterance-interval DER/timing proxy is not natural-dialogue or word-timestamp acceptance. Host RTF is not phone performance.",
            "by_split": splits, "all_selected": {"baseline": aggregate([a for _, a, _ in paired]), "candidate": aggregate([b for _, _, b in paired])},
            "gate": gate(splits),
            "paired_evidence": [{"id": case["id"], "audio_sha256": case["audio_sha256"], "baseline": {key: a[key] for key in ("case_sha256", "metrics_sha256")}, "candidate": {key: b[key] for key in ("case_sha256", "metrics_sha256")}} for case, a, b in paired]}


def markdown(report):
    def fmt(value, percent=True):
        return "N/A" if value is None else f"{value * 100:.3f}%" if percent else f"{value:.3f}"
    lines = ["# Saved-run paired A/B report", "", f"Selection: `{report['selected_split']}`. Primary gate: **{report['gate']['status']}**; accepted: **{report['gate']['accepted']}**.", "", report["scope"], ""]
    for name, group in report["by_split"].items():
        old, new = group["baseline"], group["candidate"]
        lines += [f"## {name}", "", "| Metric | Baseline | Candidate |", "| --- | ---: | ---: |"]
        for field in TOKEN_METRICS + DER_METRICS:
            lines.append(f"| {field} | {fmt(old[field]['rate'])} | {fmt(new[field]['rate'])} |")
        for label, field, key, percent in (("Punctuation F1", "punctuation", "f1", True), ("Initial-case accuracy", "initial_case", "accuracy", True),
                                           ("Timing reference coverage", "timing", "reference_coverage", True), ("Median start error (proxy ms)", "timing", "median_start_abs_error_ms", False),
                                           ("Median end error (proxy ms)", "timing", "median_end_abs_error_ms", False)):
            lines.append(f"| {label} | {fmt(old[field][key], percent)} | {fmt(new[field][key], percent)} |")
        lines.append(f"| Host RTF | {fmt(old['rtf'], False)} | {fmt(new['rtf'], False)} |")
        for side in ("export", "native"):
            a, b = old[side + "_speakers"], new[side + "_speakers"]
            lines.append(f"| {side} speaker-count exact rate | {fmt(a['exact_rate'])} | {fmt(b['exact_rate'])} |")
        def sdi(metric):
            return "/".join(str(metric[key]) for key in ("substitutions", "deletions", "insertions")) if metric["complete"] else "N/A (incomplete)"
        lines += ["", f"Raw S/D/I: baseline {sdi(old['wer_raw'])}; candidate {sdi(new['wer_raw'])}. Inspect JSON coverage for missing metrics.",
                  "", "Short-case deletion axis: " + group["short_utterance_deletion_axis"]["status"] + "; relative reduction " + fmt(group["short_utterance_deletion_axis"]["relative_deletion_reduction"]) + ".", ""]
    lines += ["## Primary checks", ""]
    for name, check in report["gate"]["checks"].items():
        lines.append(f"- {name}: **{check['status']}**.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("baseline", "candidate", "manifest", "output"):
        parser.add_argument("--" + argument, type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("Output exists; choose a fresh directory")
    output = args.output.resolve()
    if any(output.is_relative_to(root.resolve()) for root in (args.baseline, args.candidate)):
        raise ValueError("Output must be outside saved input runs")
    report = compare(args.baseline, args.candidate, args.manifest, args.split)
    output.mkdir(parents=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"output": str(output), "gate": report["gate"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
