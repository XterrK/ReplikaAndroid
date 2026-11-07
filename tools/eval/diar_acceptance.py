#!/usr/bin/env python3
"""Audit one global saved C profile against the frozen eight-dev protocol.

No audio/model is opened. Known K is allowed only in the fixed V1.6 comparator.
Evidence is rehashed and primary metrics are recomputed from saved references,
hypotheses and native turns. Missing/error/unsupported cases fail the gate; they
are never removed from its denominator. This is a montage-proxy DEV gate only,
not holdout, Android, natural-dialogue or full-pipeline acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.eval import score as scoring
from tools.eval.run import REPO, confined

EVIDENCE = ("reference.json", "hypothesis.json", "diagnostics.json", "metrics.json")
DER_KEYS = ("native_der_collar_0ms", "native_der_collar_250ms")
DEFAULT_PROTOCOL = REPO / "configs/eval/diar-protocol.json"
CENTROID_ALGORITHM = "centroid-eigengap-v1"
WINDOW_ALGORITHM = "window-overcluster-v1"
REFINER_POLICIES = {
    CENTROID_ALGORITHM: ("merge_threshold", frozenset(("SUPPORTED", "PARTIAL_ACOUSTIC"))),
    WINDOW_ALGORITHM: ("tau", frozenset(("SUPPORTED", "PARTIAL_TEMPORAL"))),
}


def _profile_threshold(profile):
    if not isinstance(profile, str) or not re.fullmatch(r"(?:auto|tau)-\d+(?:p\d+)?", profile):
        raise ValueError("One auto-* or tau-* global profile is required")
    threshold = float(profile.split("-", 1)[1].replace("p", "."))
    if not 0 < threshold < 1:
        raise ValueError("Profile threshold must be strictly within 0..1")
    return threshold


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _count(value):
    return type(value) is int and value >= 0


def _edit(metric):
    if not isinstance(metric, dict) or not all(_count(metric.get(k)) for k in ("errors", "reference_tokens")):
        raise ValueError("Invalid edit counts")
    expected = metric["errors"] / metric["reference_tokens"] if metric["reference_tokens"] else None
    if metric.get("rate") != expected:
        raise ValueError("Edit rate differs from counts")
    return metric


def _der(metric):
    keys = ("miss_ms", "false_alarm_ms", "confusion_ms", "reference_speaker_ms")
    if not isinstance(metric, dict) or not all(_number(metric.get(k)) for k in keys):
        raise ValueError("Invalid DER components")
    error = sum(metric[k] for k in keys[:3])
    expected = error / metric["reference_speaker_ms"] if metric["reference_speaker_ms"] else None
    if metric.get("rate") != expected or ("error_speaker_ms" in metric and metric["error_speaker_ms"] != error):
        raise ValueError("DER rate differs from components")
    return metric


def _summary(records):
    result = {"cases": len(records)}
    for name in ("wer_raw", "cpwer_raw"):
        errors = sum(r["metrics"][name]["errors"] for r in records)
        words = sum(r["metrics"][name]["reference_tokens"] for r in records)
        result[name] = {"errors": errors, "reference_tokens": words, "rate": errors / words if words else None}
    for name in DER_KEYS:
        values = {k: sum(r["metrics"][name][k] for r in records)
                  for k in ("miss_ms", "false_alarm_ms", "confusion_ms", "reference_speaker_ms")}
        error = sum(values[k] for k in ("miss_ms", "false_alarm_ms", "confusion_ms"))
        result[name] = {**values, "error_speaker_ms": error,
                        "rate": error / values["reference_speaker_ms"] if values["reference_speaker_ms"] else None}
    result["speaker_count_exact_cases"] = sum(r["native_speaker_count"] == r["reference_speaker_count"] for r in records)
    result["speaker_absolute_error_sum"] = sum(abs(r["native_speaker_count"] - r["reference_speaker_count"]) for r in records)
    result["speaker_count_exact_success_fraction"] = result["speaker_count_exact_cases"] / 8
    return result


def evaluate_records(candidate_records, fixed_records, asr_records, *, expected_ids, profile):
    """Pure gate on already validated records; saved-I/O audit is evaluate_saved.

    Eight distinct expected dev IDs are mandatory. Denominators never shrink to
    successful cases. Full per-case metric validation precedes aggregation.
    """
    threshold = _profile_threshold(profile)
    ids = list(expected_ids)
    if len(ids) != 8 or len(set(ids)) != 8 or not all(isinstance(x, str) for x in ids):
        raise ValueError("Exactly eight distinct dev IDs are required")
    errors, per_case, collected = [], [], {"candidate": [], "fixed": [], "asr": []}
    tables = {}
    for role, records in (("candidate", candidate_records), ("fixed", fixed_records), ("asr", asr_records)):
        table = {}
        for record in records:
            identifier = record.get("id") if isinstance(record, dict) else None
            if identifier not in ids or identifier in table:
                errors.append({"role": role, "id": identifier, "error": "Unexpected or duplicate dev record"})
            else:
                table[identifier] = record
        tables[role] = table
    raw_ok = True
    for identifier in ids:
        case_errors = []
        roles = {role: table.get(identifier) for role, table in tables.items()}
        try:
            if any(r is None for r in roles.values()):
                raise ValueError("Missing candidate, fixed or ASR dev case")
            c, b, a = (roles[k] for k in ("candidate", "fixed", "asr"))
            if any(r.get("split") != "dev" or r.get("status", "COMPLETE") not in ("COMPLETE", "SCORED") for r in roles.values()):
                raise ValueError("Case is not a complete dev result")
            if c.get("profile") != profile or c.get("threshold") != threshold:
                raise ValueError("Candidate does not use the selected global profile/threshold")
            if c.get("mode") == "fixed" or c.get("source_profile") == "fixed" or c.get("known_k") is True:
                raise ValueError("Known-K oracle cannot be a candidate")
            refined = profile.startswith("tau-")
            if refined and (c.get("stage") != "refined" or c.get("refiner_accepted") is not True):
                raise ValueError("Unsupported or absent refiner result")
            if refined and c.get("algorithm", CENTROID_ALGORITHM) not in REFINER_POLICIES:
                raise ValueError("Unknown refiner algorithm")
            if not refined and c.get("mode") != "auto":
                raise ValueError("Automatic candidate mode must be auto")
            am = a["metrics"]
            _edit(am["wer_raw"])
            if not am["wer_raw"]["reference_tokens"]:
                raise ValueError("Empty raw reference denominator")
            truth = am["speakers"]["reference"]
            if not _count(truth) or truth < 1:
                raise ValueError("Invalid reference speaker count")
            for record in (c, b):
                metrics = record["metrics"]
                for key in ("wer_raw", "cpwer_raw"):
                    _edit(metrics[key])
                    if metrics[key]["reference_tokens"] != am["wer_raw"]["reference_tokens"]:
                        raise ValueError("Reference token denominator differs")
                for key in DER_KEYS:
                    _der(metrics[key])
                    if metrics[key]["reference_speaker_ms"] <= 0:
                        raise ValueError("Undefined native DER reference denominator")
                if (not all(_count(record.get(k)) for k in ("native_speaker_count", "reference_speaker_count", "native_speaker_count_error"))
                        or record.get("reference_speaker_count") != truth
                        or record.get("native_speaker_count_error") != abs(record["native_speaker_count"] - truth)):
                    raise ValueError("Stored native/reference count mismatch")
            for key in DER_KEYS:
                if c["metrics"][key]["reference_speaker_ms"] != b["metrics"][key]["reference_speaker_ms"]:
                    raise ValueError("Paired DER reference denominator differs")
            case_raw_ok = c["metrics"]["wer_raw"] == am["wer_raw"] and b["metrics"]["wer_raw"] == am["wer_raw"]
            raw_ok &= case_raw_ok
            per_case.append({"id": identifier, "valid": True, "raw_wer_exact_d": case_raw_ok,
                             "native_count": c["native_speaker_count"], "reference_count": truth,
                             "count_exact": c["native_speaker_count"] == truth,
                             "candidate_der_0": c["metrics"][DER_KEYS[0]]["rate"],
                             "fixed_der_0": b["metrics"][DER_KEYS[0]]["rate"],
                             "candidate_der_250": c["metrics"][DER_KEYS[1]]["rate"],
                             "candidate_cpwer_raw": c["metrics"]["cpwer_raw"]["rate"]})
            for role, record in roles.items():
                collected[role].append(record)
        except (KeyError, TypeError, ValueError) as exc:
            case_errors.append(str(exc))
            errors.append({"id": identifier, "error": str(exc)})
            per_case.append({"id": identifier, "valid": False, "errors": case_errors})
    # A profile cannot switch model/source settings independently for each file.
    for key in (("source_profile", "algorithm") if profile.startswith("tau-") else ("model_id", "window_shift")):
        values = {json.dumps(r.get(key, CENTROID_ALGORITHM if key == "algorithm" else None), sort_keys=True)
                  for r in collected["candidate"]}
        if len(values) > 1:
            errors.append({"error": "Mixed per-case global setting: " + key})
    aggregate = {role: _summary(records) for role, records in collected.items() if role != "asr"}
    complete = not errors and all(len(t) == 8 for t in tables.values()) and len(collected["candidate"]) == 8
    cder, bder = (aggregate[k][DER_KEYS[0]] for k in ("candidate", "fixed"))
    defined = cder["reference_speaker_ms"] > 0 and bder["reference_speaker_ms"] > 0
    # Decimal source components and an exact 1/50 threshold avoid a binary-float
    # rejection at exactly +2 percentage points.
    der_pass = defined and (Fraction(str(cder["error_speaker_ms"])) / Fraction(str(cder["reference_speaker_ms"])) <=
                           Fraction(str(bder["error_speaker_ms"])) / Fraction(str(bder["reference_speaker_ms"])) + Fraction(1, 50))
    exact = aggregate["candidate"]["speaker_count_exact_cases"]
    conditions = {
        "complete_same_eight_dev_cases": {"pass": complete, "direction": "all required", "required": 8,
                                         "observed": len(collected["candidate"])},
        "raw_wer_exact_frozen_d": {"pass": complete and raw_ok, "direction": "equal per case"},
        "exact_native_speaker_count": {"pass": complete and exact >= 7, "direction": "higher is better",
                                       "required_exact_cases": 7, "denominator_cases": 8, "observed_exact_cases": exact},
        "native_der_0_vs_fixed_v16": {"pass": complete and bool(der_pass), "direction": "lower is better",
                                      "maximum_increase_percentage_points": 2.0,
                                      "candidate": cder["rate"], "fixed": bder["rate"],
                                      "delta_percentage_points": (cder["rate"] - bder["rate"]) * 100 if defined else None},
    }
    gate = all(c["pass"] for c in conditions.values())
    algorithms = {r.get("algorithm", CENTROID_ALGORITHM) for r in collected["candidate"]} if profile.startswith("tau-") else set()
    return {"schema_version": 1, "status": "PASS" if gate else "FAIL", "gate_pass": gate, "profile": profile,
            "refiner_algorithm": next(iter(algorithms)) if len(algorithms) == 1 else None,
            "expected_dev_ids": ids, "conditions": conditions, "aggregate": aggregate, "per_case": per_case,
            "errors": errors, "full_pipeline_accepted": False,
            "scope": "C eight-dev count/native-DER montage-proxy gate only; no holdout/Android/natural-dialogue/performance acceptance"}


class _Snapshots:
    def __init__(self):
        self.hashes = {}

    def json(self, path):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if str(path) in self.hashes and self.hashes[str(path)] != digest:
            raise ValueError("Input changed during audit: " + str(path))
        self.hashes[str(path)] = digest
        return json.loads(raw, parse_constant=_reject_constant, parse_float=_finite_float)

    def digest(self, path):
        return self.hashes[str(Path(path).resolve())]

    def verify_unchanged(self):
        for path, expected in self.hashes.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise ValueError("Input changed during audit: " + path)


def _reject_constant(value):
    raise ValueError("Nonfinite JSON: " + value)


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite JSON number: " + value)
    return result


def _record(snapshot, folder, case, reference_hash):
    record = snapshot.json(folder / "case.json")
    if not isinstance(record, dict):
        raise ValueError("Case record must be an object")
    evidence = {name: snapshot.json(folder / name) for name in EVIDENCE}
    hashes = {name: snapshot.digest(folder / name) for name in EVIDENCE}
    if record.get("evidence_sha256") != hashes or record.get("metrics") != evidence["metrics.json"]:
        raise ValueError("Evidence hash or embedded metrics mismatch")
    for key in ("id", "split", "duration_ms", "audio_sha256"):
        if record.get(key) != case[key]:
            raise ValueError("Saved case input mismatch: " + key)
    if record.get("reference_sha256") != reference_hash or hashes["reference.json"] != reference_hash:
        raise ValueError("Independent reference hash mismatch")
    if "turns_sha256" in record:
        turns = snapshot.json(folder / "turns.json")
        if record["turns_sha256"] != snapshot.digest(folder / "turns.json") or turns != evidence["diagnostics.json"]["diarizationTurns"]:
            raise ValueError("Saved refined turns mismatch")
    return record, evidence, {"case.json": snapshot.digest(folder / "case.json"), **hashes}


def _recompute(evidence, duration, *, native):
    # These are the exact frozen score() primitives. Recomputing CER, number
    # normalization and unrelated timing would add cost without checking this
    # protocol's metrics. The scorer source hash is part of the audit result.
    duration = scoring._duration(duration)
    reference = scoring._document(evidence["reference.json"], duration)
    hypothesis = scoring._document(evidence["hypothesis.json"], duration)
    raw, _ = scoring._edit(scoring._text(reference).split(), scoring._text(hypothesis).split())
    metrics = {"wer_raw": raw, "cpwer_raw": scoring._cpwer(reference, hypothesis, str.split)}
    truth = len({r.speaker_id for r in reference if r.end_ms > r.start_ms})
    saved = evidence["metrics.json"]
    for name in ("wer_raw", "cpwer_raw"):
        if metrics[name] != saved.get(name):
            raise ValueError("Saved metric does not recompute: " + name)
    if native:
        turns = evidence["diagnostics.json"].get("diarizationTurns")
        if not isinstance(turns, list):
            raise ValueError("Missing native turns")
        for turn in turns:
            if (not isinstance(turn, dict) or set(turn) != {"startMs", "endMs", "speakerId"}
                    or any(type(turn[k]) is not int for k in turn)
                    or not 0 <= turn["startMs"] < turn["endMs"] <= duration or turn["speakerId"] < 0):
                raise ValueError("Invalid native turn")
        rows = [{"start_ms": t["startMs"], "end_ms": t["endMs"], "speaker_id": "native_" + str(t["speakerId"]), "text": ""} for t in turns]
        for name, collar in zip(DER_KEYS, (0, 250)):
            if scoring.der(evidence["reference.json"]["transcript"], rows, duration, collar) != saved.get(name):
                raise ValueError("Saved native DER does not recompute: " + name)
        count = len({t["speakerId"] for t in turns})
        # Native diar_sweep stores this required count in case.json. Refiner
        # reports additionally duplicate it in metrics.json; verify that copy
        # when present. evaluate_saved always checks the mandatory case value.
        if "native_speaker_count" in saved and saved["native_speaker_count"] != count:
            raise ValueError("Saved native count does not recompute")
        return count, truth
    return None, truth


def evaluate_saved(candidate, profile, manifest, asr_run, fixed_baseline, *, protocol=DEFAULT_PROTOCOL, output=None):
    """Read-only evidence audit; output is a new JSON file and never overwritten."""
    threshold = _profile_threshold(profile)
    candidate, manifest, asr_run, fixed_baseline = map(Path, (candidate, manifest, asr_run, fixed_baseline))
    snapshot = _Snapshots()
    errors, records = [], {"candidate": [], "fixed": [], "asr": []}
    expected_ids = []
    try:
        rules = snapshot.json(protocol)
        gate = rules["dev_acceptance"]
        if (gate["minimum_exact_cases_of_eight"] != 7 or gate["speaker_count_exact_success_fraction_minimum"] != .8
                or gate["native_der_0ms_maximum_above_production_v16_fixed_baseline_percentage_points"] != 2.):
            raise ValueError("Protocol differs from frozen eight-dev gate")
        corpus = snapshot.json(manifest)
        cases = [c for c in corpus["files"] if c["split"] == "dev"]
        expected_ids = [c["id"] for c in cases]
        if len(cases) != 8 or len(set(expected_ids)) != 8:
            raise ValueError("Manifest must contain exactly eight distinct dev cases")
        cm, bm, am = (snapshot.json(root / "run.json") for root in (candidate, fixed_baseline, asr_run))
        if not all(isinstance(meta, dict) for meta in (cm, bm, am)):
            raise ValueError("Run metadata must be objects")
        if any(meta.get("status") != "COMPLETE" for meta in (cm, bm, am)):
            raise ValueError("Candidate, fixed baseline and actual D run must be COMPLETE")
        mh, ah = snapshot.digest(manifest), snapshot.digest(asr_run / "run.json")
        if (am.get("config", {}).get("pipeline") != "vad_words_v1" or am["config"].get("punctuation_mode") != "none"
                or am["config"].get("expected_speakers") != -1
                or am["fingerprint"].get("manifest_sha256") != mh):
            raise ValueError("Actual D policy/manifest pin mismatch")
        if bm.get("manifest_sha256") != mh or bm.get("asr_run_sha256") != ah:
            raise ValueError("Production fixed V1.6 comparator pin mismatch")
        refined = profile.startswith("tau-")
        if refined:
            fp = snapshot.json(candidate / "source-fingerprint.json")
            canonical = hashlib.sha256(json.dumps(fp, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if cm.get("source_fingerprint_sha256") != canonical or fp.get("config") != cm.get("config"):
                raise ValueError("Refiner source fingerprint mismatch")
            if fp.get("manifest") != mh or fp.get("asr_run") != ah or cm.get("failures") or cm.get("pending_cases"):
                raise ValueError("Refiner input pins/failures/pending cases invalid")
            if cm["config"].get("profile") == "fixed" or threshold not in cm["config"].get("thresholds", []):
                raise ValueError("Known-K or absent global refiner profile")
            # Historical C1 metadata omitted the algorithm key. C2 is opt-in by
            # its exact declared algorithm, not by guessing a config field.
            algorithm = cm["config"].get("algorithm", CENTROID_ALGORITHM)
            if algorithm not in REFINER_POLICIES:
                raise ValueError("Unknown global refiner algorithm")
            tau_field, supported_statuses = REFINER_POLICIES[algorithm]
            if algorithm == WINDOW_ALGORITHM:
                from dataclasses import fields
                from tools.eval.window_overcluster import WindowClusterConfig
                cfg = cm["config"]["refiner_config"]
                if set(cfg) != {field.name for field in fields(WindowClusterConfig)}:
                    raise ValueError("Window refiner config schema differs")
                if cm["config"].get("method") != cfg.get("method"):
                    raise ValueError("Window linkage method differs from global policy")
        else:
            fp = cm.get("fingerprint", {})
            if (cm.get("options", {}).get("mode") != "auto" or fp.get("manifest") != mh
                    or fp.get("asr_run") != ah or threshold not in fp.get("thresholds", [])):
                raise ValueError("Automatic source mode/profile/ASR/manifest pin mismatch")
        for case in cases:
            try:
                refpath = confined(manifest.parent, case["reference"])
                snapshot.json(refpath)
                rh = snapshot.digest(refpath)
                if am["fingerprint"].get("references", {}).get(case["id"]) != rh:
                    raise ValueError("Reference differs from actual D pin")
                a, ae, ash = _record(snapshot, confined(asr_run, case["id"]), case, rh)
                b, be, _ = _record(snapshot, confined(fixed_baseline, case["id"]), case, rh)
                c, ce, _ = _record(snapshot, confined(candidate / profile, case["id"]), case, rh)
                _recompute(ae, case["duration_ms"], native=False)
                for record, evidence in ((b, be), (c, ce)):
                    count, truth = _recompute(evidence, case["duration_ms"], native=True)
                    if record.get("native_speaker_count") != count or record.get("reference_speaker_count") != truth:
                        raise ValueError("Case native/reference count differs from saved evidence")
                bd, cd = be["diagnostics.json"], ce["diagnostics.json"]
                asr_hashes = {k: v for k, v in ash.items() if k != "case.json"}
                if bd.get("source_asr_evidence_sha256") != asr_hashes:
                    raise ValueError("Fixed comparator actual D evidence differs")
                if a["metrics"]["speakers"]["reference"] == 1 and (bd.get("singleBypass") is not True or
                        bd.get("diarizationTurns") != [{"startMs": 0, "endMs": case["duration_ms"], "speakerId": 0}]):
                    raise ValueError("Fixed comparator lacks production single-speaker bypass")
                if refined:
                    links = c.get("source_evidence_sha256", {})
                    if (links.get("asr") != ash or links.get("reference") != rh or links.get("original_audio") != case["audio_sha256"]
                            or cd.get("sourceEvidence") != links or fp.get("cases", {}).get(case["id"]) != links
                            or c.get("source_profile") != cm["config"]["profile"]):
                        raise ValueError("Refiner actual D case/source link differs")
                    if (cd.get("refinerAccepted") is not True
                            or cd.get("refiner", {}).get("status") not in supported_statuses):
                        raise ValueError("Unsupported/absent refiner diagnostics")
                    if (cd["refiner"].get("algorithm") != algorithm
                            or cd.get("algorithm", algorithm) != algorithm
                            or c.get("algorithm", algorithm) != algorithm):
                        raise ValueError("Mixed/unknown per-case refiner algorithm")
                    if cd["refiner"].get("config") != {**cm["config"]["refiner_config"], tau_field: threshold}:
                        raise ValueError("Per-case refiner configuration differs from global policy")
                    # Annotate the in-memory audit record, leaving the source
                    # bytes/hashes untouched. Pure evaluation checks uniformity.
                    c = {**c, "algorithm": algorithm}
                elif (cd.get("mode") != "auto" or type(cd.get("numClustersPassed")) is not int or cd["numClustersPassed"] != -1
                        or cd.get("fixedCountSource") != "none" or cd.get("asrEvidenceSha256") != asr_hashes
                        or cd.get("threshold") != threshold or c.get("model_id") != cm["options"].get("model_id")
                        or c.get("window_shift") != cm["options"].get("window_shift")):
                    raise ValueError("Automatic candidate has known-K, mixed policy or wrong D evidence")
                for role, record in (("candidate", c), ("fixed", b), ("asr", a)):
                    records[role].append(record)
            except (OSError, KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
                errors.append({"id": case["id"], "error": f"{type(exc).__name__}: {exc}"})
        snapshot.verify_unchanged()
    except (OSError, KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        errors.append({"stage": "run_validation", "error": f"{type(exc).__name__}: {exc}"})
    if len(expected_ids) == 8 and len(set(expected_ids)) == 8:
        result = evaluate_records(records["candidate"], records["fixed"], records["asr"], expected_ids=expected_ids, profile=profile)
    else:
        result = {"schema_version": 1, "profile": profile, "expected_dev_ids": expected_ids,
                  "status": "FAIL", "gate_pass": False, "conditions": {}, "aggregate": {}, "per_case": [],
                  "errors": [], "full_pipeline_accepted": False, "scope": "Invalid dev evidence; no acceptance"}
    result["conditions"]["saved_source_integrity"] = {"pass": not errors, "direction": "all required", "failures": len(errors)}
    result["errors"].extend(errors)
    result["gate_pass"] = all(c["pass"] for c in result["conditions"].values())
    result["status"] = "PASS" if result["gate_pass"] else "FAIL"
    result.update(at=datetime.now(timezone.utc).isoformat(), new_model_inference=False,
                  sources={"candidate": str(candidate), "fixed_baseline": str(fixed_baseline), "manifest": str(manifest), "asr_run": str(asr_run)},
                  source_sha256=snapshot.hashes,
                  audit_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  scorer_code_sha256=hashlib.sha256(Path(scoring.__file__).read_bytes()).hexdigest())
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--asr-run", type=Path, required=True)
    parser.add_argument("--fixed-baseline", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = evaluate_saved(args.candidate, args.profile, args.manifest, args.asr_run, args.fixed_baseline,
                            protocol=args.protocol, output=args.output)
    print(json.dumps({k: result[k] for k in ("status", "gate_pass", "profile", "conditions")}, indent=2))
    return 0 if result["gate_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
