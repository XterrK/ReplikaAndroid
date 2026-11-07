#!/usr/bin/env python3
"""Strict independent regression audit for explicit frozen C1/C2 cohorts.

Reads saved actual C neural outputs, frozen D words and an automatic V1.6
baseline. Replays only pure functions; no audio/model is opened. Cohorts never
pool: raw WER<=baseline and exact D, native DER0<=baseline, and exact-count cases
>=baseline must all pass on the explicit complete cohort. Previously seen D
holdout/reserve data are regression validations, not blind tests. No Android or
full-pipeline acceptance follows from this audit.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.eval import diar_acceptance as audit
from tools.eval import native_policy
from tools.eval import refine_sweep
from tools.eval.diar_sweep import load_asr, project_asr
from tools.eval.run import REPO, confined
from tools.eval.speaker_refiner import RefineConfig, clean_windows, refine, _unit
from tools.eval.window_overcluster import WindowClusterConfig, overcluster

DEFAULT_DEV_AUDIT = REPO / "artifacts/test-results/step-04/acceptance-resnet34-050-temporal-guard0p7/tau-0p7.json"
VALIDATION_ERRORS = (OSError, KeyError, TypeError, ValueError, AttributeError, OverflowError)


def _aggregate(records, expected):
    result = audit._summary(records)
    result["expected_cases"] = expected
    result["speaker_count_exact_success_fraction"] = result["speaker_count_exact_cases"] / expected
    return result


def _ratio_at_most(left, right, error, denominator):
    if not left[denominator] or not right[denominator]:
        return False
    return (Fraction(str(left[error])) / Fraction(str(left[denominator])) <=
            Fraction(str(right[error])) / Fraction(str(right[denominator])))


def evaluate_records(candidate_records, baseline_records, asr_records, *, expected_ids, cohort):
    """Pure independent-cohort gate on records with observed native counts."""
    ids = list(expected_ids)
    if not ids or len(set(ids)) != len(ids) or not all(isinstance(x, str) for x in ids):
        raise ValueError("Distinct nonempty explicit cohort IDs required")
    tables, errors, paired = {}, [], {"candidate": [], "baseline": []}
    for role, records in (("candidate", candidate_records), ("baseline", baseline_records), ("asr", asr_records)):
        table = {}
        for record in records:
            identifier = record.get("id") if isinstance(record, dict) else None
            if identifier not in ids or identifier in table:
                errors.append({"role": role, "id": identifier, "error": "Missing/extra/duplicate cohort coverage"})
            else:
                table[identifier] = record
        tables[role] = table
    per_case, raw_exact = [], True
    for identifier in ids:
        try:
            c, b, a = (tables[role].get(identifier) for role in ("candidate", "baseline", "asr"))
            if any(r is None for r in (c, b, a)):
                raise ValueError("Missing candidate/baseline/actual D case")
            if c.get("refiner_accepted") is not True:
                raise ValueError("Unsupported candidate refiner")
            for record in (c, b, a):
                if record.get("status", "COMPLETE") not in ("COMPLETE", "SCORED"):
                    raise ValueError("Incomplete case")
                audit._edit(record["metrics"]["wer_raw"])
                if record["metrics"]["wer_raw"]["reference_tokens"] <= 0:
                    raise ValueError("Undefined reference text denominator")
            truth = a["metrics"]["speakers"]["reference"]
            for record in (c, b):
                if (not all(audit._count(record.get(k)) for k in ("native_speaker_count", "reference_speaker_count", "native_speaker_count_error"))
                        or record["reference_speaker_count"] != truth
                        or record["native_speaker_count_error"] != abs(record["native_speaker_count"] - truth)):
                    raise ValueError("Observed native/reference count mismatch")
                audit._edit(record["metrics"]["cpwer_raw"])
                for key in ("wer_raw", "cpwer_raw"):
                    if record["metrics"][key]["reference_tokens"] != a["metrics"]["wer_raw"]["reference_tokens"]:
                        raise ValueError("Paired text reference denominator mismatch")
                for key in audit.DER_KEYS:
                    audit._der(record["metrics"][key])
                    if record["metrics"][key]["reference_speaker_ms"] <= 0:
                        raise ValueError("Undefined native DER denominator")
            for key in audit.DER_KEYS:
                if c["metrics"][key]["reference_speaker_ms"] != b["metrics"][key]["reference_speaker_ms"]:
                    raise ValueError("Paired native DER reference denominator mismatch")
            exact = c["metrics"]["wer_raw"] == a["metrics"]["wer_raw"]
            raw_exact &= exact
            per_case.append({"id": identifier, "valid": True, "raw_exact_d": exact,
                "raw_delta_errors": c["metrics"]["wer_raw"]["errors"] - b["metrics"]["wer_raw"]["errors"],
                "raw_delta_percentage_points": 100 * (c["metrics"]["wer_raw"]["rate"] - b["metrics"]["wer_raw"]["rate"]),
                "native_der0_delta_percentage_points": 100 * (c["metrics"][audit.DER_KEYS[0]]["rate"] - b["metrics"][audit.DER_KEYS[0]]["rate"]),
                "native_der250_delta_percentage_points": 100 * (c["metrics"][audit.DER_KEYS[1]]["rate"] - b["metrics"][audit.DER_KEYS[1]]["rate"]),
                "cpwer_raw_delta_percentage_points": 100 * (c["metrics"]["cpwer_raw"]["rate"] - b["metrics"]["cpwer_raw"]["rate"]),
                "native_count": c["native_speaker_count"], "baseline_native_count": b["native_speaker_count"],
                "reference_count": truth, "count_exact": c["native_speaker_count"] == truth,
                "baseline_count_exact": b["native_speaker_count"] == truth,
                "per_file_deltas_are_gates": False})
            paired["candidate"].append(c)
            paired["baseline"].append(b)
        except VALIDATION_ERRORS as exc:
            errors.append({"id": identifier, "error": str(exc)})
            per_case.append({"id": identifier, "valid": False, "error": str(exc)})
    aggregate = {role: _aggregate(records, len(ids)) for role, records in paired.items()}
    c, b = aggregate["candidate"], aggregate["baseline"]
    complete = not errors and all(len(t) == len(ids) for t in tables.values()) and c["cases"] == len(ids)
    conditions = {
        "complete_exact_cohort": {"pass": complete, "required_cases": len(ids), "observed_cases": c["cases"]},
        "raw_wer_exact_frozen_d": {"pass": complete and raw_exact, "direction": "equal per case"},
        "raw_wer_no_regression": {"pass": complete and _ratio_at_most(c["wer_raw"], b["wer_raw"], "errors", "reference_tokens"), "direction": "lower is better"},
        "native_der0_no_regression": {"pass": complete and _ratio_at_most(c[audit.DER_KEYS[0]], b[audit.DER_KEYS[0]], "error_speaker_ms", "reference_speaker_ms"), "direction": "lower is better"},
        "exact_native_count_no_regression": {"pass": complete and c["speaker_count_exact_cases"] >= b["speaker_count_exact_cases"],
            "direction": "higher is better", "candidate": c["speaker_count_exact_cases"], "baseline": b["speaker_count_exact_cases"], "denominator": len(ids)},
    }
    passed = all(v["pass"] for v in conditions.values())
    return {"schema_version": 1, "status": "PASS" if passed else "FAIL", "gate_pass": passed, "cohort": cohort,
            "expected_ids": ids, "conditions": conditions, "aggregate": aggregate, "per_case": per_case, "errors": errors,
            "full_pipeline_accepted": False, "android_accepted": False,
            "scope": "Separate previously seen D regression cohort; montage interval DER proxy, not blind/natural-dialogue validation or Android acceptance"}


def _instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone required in freeze/run timestamps")
    return result


def _observed(record, evidence, duration):
    count, truth = audit._recompute(evidence, duration, native=True)
    for key, value in (("native_speaker_count", count), ("reference_speaker_count", truth),
                       ("native_speaker_count_error", abs(count - truth))):
        if key in record and record[key] != value:
            raise ValueError("Optional case count copy differs from actual turns: " + key)
    # V1.6 case files need not contain count fields. These audit-only copies are
    # always reconstructed from actual turns, never supplied expected K.
    return {**record, "native_speaker_count": count, "reference_speaker_count": truth,
            "native_speaker_count_error": abs(count - truth)}


def evaluate_saved(candidate, diar_run, asr_run, baseline, manifest, freeze, *, split, expected_cases,
                   cohort, profile="tau-0p7", dev_audit=DEFAULT_DEV_AUDIT, output=None):
    """Validate one explicit full cohort and emit a fresh JSON audit if requested."""
    if split not in ("holdout", "all") or type(expected_cases) is not int or expected_cases <= 0:
        raise ValueError("Explicit holdout/all split and positive expected_cases required")
    tau = audit._profile_threshold(profile)
    if not profile.startswith("tau-"):
        raise ValueError("Frozen refined profile required")
    candidate, diar_run, asr_run, baseline, manifest, freeze = map(Path, (candidate, diar_run, asr_run, baseline, manifest, freeze))
    snapshots, errors, ids, replayed = audit._Snapshots(), [], [], []
    records = {"candidate": [], "baseline": [], "asr": []}
    try:
        chosen, dev = snapshots.json(freeze), snapshots.json(dev_audit)
        required_dev = ("complete_same_eight_dev_cases", "raw_wer_exact_frozen_d", "exact_native_speaker_count",
                        "native_der_0_vs_fixed_v16", "saved_source_integrity")
        if (chosen.get("status") != "FROZEN_FOR_VALIDATION" or chosen.get("dev_audit_sha256") != snapshots.digest(dev_audit)
                or dev.get("gate_pass") is not True or dev.get("status") != "PASS" or dev.get("profile") != profile
                or len(dev.get("expected_dev_ids", [])) != 8 or len(set(dev.get("expected_dev_ids", []))) != 8
                or not all(dev.get("conditions", {}).get(k, {}).get("pass") is True for k in required_dev)):
            raise ValueError("Frozen dev selection/proof is invalid")
        policy = chosen["policy"]
        algorithm = chosen.get("algorithm", audit.CENTROID_ALGORITHM)
        if algorithm == audit.CENTROID_ALGORITHM:
            if (policy["refiner_tau"] != tau or policy["minimum_reassignment_similarity"] != .7
                    or policy["missing_centroid_policy"] != "temporal" or tau != .7):
                raise ValueError("C1 validation requires frozen tau.7/guard.7/temporal")
        elif algorithm == audit.WINDOW_ALGORITHM:
            if chosen["window_config"].get("tau") != tau or policy.get("refiner_tau", tau) != tau:
                raise ValueError("C2 validation requires the exact frozen window tau")
        else:
            raise ValueError("Unknown frozen refiner algorithm")
        devsource = Path(dev["sources"]["candidate"])
        if not devsource.is_absolute():
            devsource = REPO / devsource
        devmeta = snapshots.json(devsource / "run.json")
        if dev.get("source_sha256", {}).get(str((devsource / "run.json").resolve())) != snapshots.digest(devsource / "run.json"):
            raise ValueError("Frozen dev policy run changed after its gate")
        devcfg = devmeta["config"]["refiner_config"]
        if algorithm == audit.CENTROID_ALGORITHM:
            if (devcfg.get("minimum_reassignment_similarity") != policy["minimum_reassignment_similarity"]
                    or devcfg.get("small_missing_centroid_policy") != policy["missing_centroid_policy"]):
                raise ValueError("Frozen dev refiner policy mismatch")
            local_config = RefineConfig(**{**devcfg, "merge_threshold": tau})
            supported_statuses = ("SUPPORTED", "PARTIAL_ACOUSTIC")
        else:
            local_config = WindowClusterConfig(**chosen["window_config"])
            if (devmeta["config"].get("algorithm") != algorithm or asdict(local_config) != {**devcfg, "tau": tau}
                    or devmeta["config"].get("method") != local_config.method):
                raise ValueError("Frozen dev window policy mismatch")
            supported_statuses = ("SUPPORTED", "PARTIAL_TEMPORAL")
        corpus = snapshots.json(manifest)
        cases = [c for c in corpus["files"] if split == "all" or c["split"] == split]
        ids = [c["id"] for c in cases]
        if len(ids) != expected_cases or len(set(ids)) != expected_cases:
            raise ValueError("Missing/extra manifest cohort coverage")
        cm, nm, am, bm = (snapshots.json(root / "run.json") for root in (candidate, diar_run, asr_run, baseline))
        if any(meta.get("status") != "COMPLETE" for meta in (cm, nm, am, bm)):
            raise ValueError("All source runs must be COMPLETE")
        fp = snapshots.json(candidate / "source-fingerprint.json")
        canonical = hashlib.sha256(json.dumps(fp, sort_keys=True, allow_nan=False).encode()).hexdigest()
        mh, ah = snapshots.digest(manifest), snapshots.digest(asr_run / "run.json")
        if (cm.get("source_fingerprint_sha256") != canonical or fp.get("config") != cm["config"]
                or fp.get("manifest") != mh or fp.get("asr_run") != ah or fp.get("diar_run") != snapshots.digest(diar_run / "run.json")
                or cm.get("failures") or cm.get("pending_cases") or set(fp.get("selected_ids", [])) != set(ids)
                or len(fp.get("selected_ids", [])) != expected_cases or set(fp.get("cases", {})) != set(ids)):
            raise ValueError("Refined run source/config/cohort fingerprint mismatch")
        cf = cm["config"]
        config_matches = (cf.get("refiner_config") == devcfg if algorithm == audit.CENTROID_ALGORITHM else
                          {**cf["refiner_config"], "tau": tau} == asdict(local_config))
        if (cf.get("algorithm", audit.CENTROID_ALGORITHM) != algorithm
                or cf.get("profile") != "auto-" + format(policy["native_threshold"], ".2f").replace(".", "p")
                or cf.get("thresholds") != [tau] or not config_matches
                or cf.get("split") != split or cf.get("cases") is not None):
            raise ValueError("Validation changed the frozen global refiner policy")
        if algorithm == audit.WINDOW_ALGORITHM and (cf.get("expected_cases") != expected_cases or cf.get("method") != local_config.method):
            raise ValueError("C2 validation coverage/linkage differs from frozen policy")
        nf = nm["fingerprint"]
        if (nf.get("manifest") != mh or nf.get("asr_run") != ah or nf.get("embedding") != chosen["model"]["sha256"]
                or nf.get("thresholds") != [policy["native_threshold"]] or set(nf.get("selected_ids", [])) != set(ids)
                or len(nf.get("selected_ids", [])) != expected_cases):
            raise ValueError("Actual neural source pins/cohort differ")
        options = nm["options"]
        if (options.get("mode") != "auto" or options.get("model_id") != chosen["model"]["id"]
                or options.get("window_shift") != policy["window_shift"] or options.get("threads") != policy["threads"]
                or options.get("collect_windows") is not True or nf.get("options") != options):
            raise ValueError("Actual neural source policy differs from freeze")
        for root, variant in ((candidate, profile), (diar_run, cf["profile"])):
            if {p.name for p in (root / variant).iterdir() if p.is_dir()} != set(ids):
                raise ValueError("Missing/extra saved cohort case directories")
        if not (_instant(chosen["at"]) <= _instant(nm["started_at"]) <= _instant(nm["completed_at"]) <=
                _instant(cm["started_at"]) <= _instant(cm["completed_at"])):
            raise ValueError("Validation chronology is not after frozen selection")
        for meta in (am, bm):
            if meta["fingerprint"].get("manifest_sha256") != mh or meta["config"].get("expected_speakers") != -1:
                raise ValueError("Actual D or automatic V1.6 manifest/mode differs")
        if (not native_policy._same_policy(native_policy._host_policy(am["config"]), native_policy.policy_for_plan(policy["paired_asr_plan"]))
                or am["config"].get("threads") != policy["threads"] or bm["config"].get("pipeline") != "v16"):
            raise ValueError("Paired D or V1.6 source policy differs")
        helper_files = (("refiner", Path(__file__).with_name("speaker_refiner.py")), ("scorer", Path(audit.scoring.__file__)),
                        ("word_helpers", Path(__file__).with_name("vad_words.py")),
                        ("diar_helpers", Path(__file__).with_name("diar_sweep.py")),
                        ("baseline_helpers", Path(__file__).with_name("pipeline.py"))) if algorithm == audit.CENTROID_ALGORITHM else (
                        ("refiner", Path(__file__).with_name("window_overcluster.py")), ("scorer", Path(audit.scoring.__file__)),
                        ("source_loader", Path(__file__).with_name("refine_sweep.py")),
                        ("asr_replay_helpers", Path(__file__).with_name("refiner_ablation.py")))
        for key, file in helper_files:
            if fp.get(key) != hashlib.sha256(file.read_bytes()).hexdigest():
                raise ValueError("Current frozen helper differs from source: " + key)
        for case in cases:
            try:
                identifier = case["id"]
                reference = confined(manifest.parent, case["reference"])
                snapshots.json(reference)
                rh = snapshots.digest(reference)
                if any(meta["fingerprint"].get("references", {}).get(identifier) != rh for meta in (am, bm)):
                    raise ValueError("Independent reference differs from baseline/actual D pins")
                a, ae, ash = audit._record(snapshots, confined(asr_run, identifier), case, rh)
                b, be, _ = audit._record(snapshots, confined(baseline, identifier), case, rh)
                n, ne, nsh = audit._record(snapshots, confined(diar_run / cf["profile"], identifier), case, rh)
                c, ce, _ = audit._record(snapshots, confined(candidate / profile, identifier), case, rh)
                links = {"diar": nsh, "asr": ash, "reference": rh, "original_audio": case["audio_sha256"]}
                nd, cd, bd = ne["diagnostics.json"], ce["diagnostics.json"], be["diagnostics.json"]
                if (fp["cases"].get(identifier) != links or c.get("source_evidence_sha256") != links or cd.get("sourceEvidence") != links):
                    raise ValueError("Actual C/D source evidence link mismatch")
                if (n.get("mode") != "auto" or n.get("profile") != cf["profile"] or n.get("model_id") != chosen["model"]["id"]
                        or nd.get("mode") != "auto" or type(nd.get("numClustersPassed")) is not int or nd["numClustersPassed"] != -1
                        or nd.get("modelSha256") != chosen["model"]["sha256"] or nd.get("modelId") != chosen["model"]["id"]
                        or nd.get("threshold") != policy["native_threshold"] or nd.get("windowShiftRatio") != policy["window_shift"]
                        or nd.get("threads") != policy["threads"] or nd.get("fixedCountSource") != "none"
                        or nd.get("asrEvidenceSha256") != {k: v for k, v in ash.items() if k != "case.json"}):
                    raise ValueError("Per-file actual C native policy/provenance differs")
                if bd.get("expectedSpeakers") != -1 or bd.get("clusteringMode") != "automatic":
                    raise ValueError("Baseline is not actual automatic V1.6")
                details = cd.get("refiner", {})
                if (c.get("profile") != profile or c.get("source_profile") != cf["profile"] or c.get("stage") != "refined"
                        or c.get("threshold") != tau or c.get("refiner_accepted") is not True or cd.get("refinerAccepted") is not True
                        or details.get("algorithm") != algorithm or details.get("status") not in supported_statuses
                        or cd.get("algorithm", algorithm) != algorithm or c.get("algorithm", algorithm) != algorithm
                        or details.get("config") != asdict(local_config)):
                    raise ValueError("Unsupported/mixed per-file refiner policy")
                native = refine_sweep._turns(nd.get("diarizationTurns"), case["duration_ms"])
                windows = refine_sweep._windows(nd.get("cleanEmbeddingWindows"))
                expected_windows = {(w.start_ms, w.end_ms, w.speaker) for w in clean_windows(native, case["duration_ms"])}
                actual_windows = [(w.start_ms, w.end_ms, w.speaker) for w in windows]
                if set(actual_windows) != expected_windows or len(set(actual_windows)) != len(actual_windows):
                    raise ValueError("Real clean-window coverage differs")
                if any(w.clean is not True or len(w.embedding) != chosen["model"]["embedding_dimension"]
                       or _unit(w.embedding) is None for w in windows):
                    raise ValueError("Measured window dimension/finite/nonzero/clean contract differs")
                # Explicit no-GT boundary: only predicted turns, measured vectors,
                # recording duration and the frozen global config enter replay.
                replay = (refine if algorithm == audit.CENTROID_ALGORITHM else overcluster)(native, windows, case["duration_ms"], local_config)
                refined = refine_sweep._turns(cd.get("diarizationTurns"), case["duration_ms"])
                if not replay.accepted or tuple(refined) != replay.turns:
                    raise ValueError("Refiner turns do not reconstruct from actual native windows")
                if algorithm == audit.WINDOW_ALGORITHM and details.get("status") != replay.diagnostics["status"]:
                    raise ValueError("Window support/fallback status does not reconstruct")
                chunks, _, backend = load_asr(confined(asr_run, identifier), case, rh)
                if project_asr(chunks, refined, backend) != ce["hypothesis.json"]:
                    raise ValueError("Saved hypothesis does not reconstruct from actual D words")
                replayed.append(identifier)
                audit._recompute(ae, case["duration_ms"], native=False)
                _observed(n, ne, case["duration_ms"])
                b = _observed(b, be, case["duration_ms"])
                c = _observed(c, ce, case["duration_ms"])
                for role, record in (("candidate", c), ("baseline", b), ("asr", a)):
                    records[role].append(record)
            except VALIDATION_ERRORS as exc:
                errors.append({"id": case["id"], "error": f"{type(exc).__name__}: {exc}"})
        snapshots.verify_unchanged()
    except VALIDATION_ERRORS as exc:
        errors.append({"stage": "source_policy_validation", "error": f"{type(exc).__name__}: {exc}"})
    if len(ids) == expected_cases and len(set(ids)) == expected_cases:
        result = evaluate_records(records["candidate"], records["baseline"], records["asr"], expected_ids=ids, cohort=cohort)
    else:
        result = {"schema_version": 1, "cohort": cohort, "status": "FAIL", "gate_pass": False, "conditions": {},
                  "aggregate": {}, "per_case": [], "errors": [], "full_pipeline_accepted": False, "android_accepted": False}
    result["conditions"]["source_policy_and_evidence"] = {"pass": not errors, "failures": len(errors), "direction": "all required"}
    result["errors"].extend(errors)
    result["gate_pass"] = all(c["pass"] for c in result["conditions"].values())
    result["status"] = "PASS" if result["gate_pass"] else "FAIL"
    result.update(at=datetime.now(timezone.utc).isoformat(), profile=profile, split=split, expected_cases=expected_cases,
                  new_model_inference=False, pure_refiner_and_word_projection_replayed=len(replayed) == expected_cases,
                  pure_replay_completed_ids=replayed,
                  source_sha256=snapshots.hashes, audit_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  acceptance_helpers_sha256=hashlib.sha256(Path(audit.__file__).read_bytes()).hexdigest())
    result["algorithm"] = chosen.get("algorithm", audit.CENTROID_ALGORITHM) if "chosen" in locals() and isinstance(chosen, dict) else None
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "diar-run", "asr-run", "baseline", "manifest", "freeze", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--dev-audit", type=Path, default=DEFAULT_DEV_AUDIT)
    parser.add_argument("--split", choices=("holdout", "all"), required=True)
    parser.add_argument("--expected-cases", type=int, required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--profile", default="tau-0p7")
    args = parser.parse_args(argv)
    result = evaluate_saved(args.candidate, args.diar_run, args.asr_run, args.baseline, args.manifest, args.freeze,
                            split=args.split, expected_cases=args.expected_cases, cohort=args.cohort,
                            profile=args.profile, dev_audit=args.dev_audit, output=args.output)
    print(json.dumps({key: result[key] for key in ("status", "gate_pass", "cohort", "conditions")}, indent=2))
    return 0 if result["gate_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
