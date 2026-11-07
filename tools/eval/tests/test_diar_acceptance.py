"""Saved-artifact and numerical gate tests; no audio or model inference."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout

from tools.eval import diar_acceptance as gate
from tools.eval import score
from tools.eval.speaker_refiner import RefineConfig
from tools.eval.window_overcluster import WindowClusterConfig


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def primary_records(profile="auto-0p30"):
    result = []
    for i in range(8):
        der = {"miss_ms": 10., "false_alarm_ms": 0., "confusion_ms": 0., "reference_speaker_ms": 100., "rate": .1}
        edits = {"errors": 1, "reference_tokens": 10, "rate": .1}
        result.append({"id": f"dev-{i}", "split": "dev", "profile": profile, "threshold": .3,
                       "mode": "auto", "model_id": "fixture", "window_shift": .1,
                       "native_speaker_count": 2, "reference_speaker_count": 2, "native_speaker_count_error": 0,
                       "metrics": {"wer_raw": deepcopy(edits), "cpwer_raw": deepcopy(edits),
                                   "native_der_collar_0ms": deepcopy(der), "native_der_collar_250ms": deepcopy(der),
                                   "speakers": {"reference": 2}}})
    return result


class NumericalGateTest(unittest.TestCase):
    def setUp(self):
        self.c = primary_records()
        self.b, self.a = deepcopy(self.c), deepcopy(self.c)
        self.ids = [r["id"] for r in self.c]

    def evaluate(self):
        return gate.evaluate_records(self.c, self.b, self.a, expected_ids=self.ids, profile="auto-0p30")

    def test_count80percent_requires7of8_and_directions_remain_separate(self):
        for count, expected in ((6, False), (7, True), (8, True)):
            self.c = primary_records()
            for record in self.c[count:]:
                record.update(native_speaker_count=3, native_speaker_count_error=1)
            result = self.evaluate()
            self.assertEqual(expected, result["gate_pass"])
            condition = result["conditions"]["exact_native_speaker_count"]
            self.assertEqual((count, 7, 8), (condition["observed_exact_cases"], condition["required_exact_cases"], condition["denominator_cases"]))
            self.assertEqual("higher is better", condition["direction"])
            self.assertFalse(result["full_pipeline_accepted"])

    def test_exact2pp_der_boundary_passes_but_any_genuine_excess_fails(self):
        for errors, expected in ((12., True), (12.0001, False)):
            for record in self.c:
                record["metrics"]["native_der_collar_0ms"].update(miss_ms=errors, rate=errors / 100)
            self.assertEqual(expected, self.evaluate()["gate_pass"])

    def test_der_and_cpwer_use_summed_components_not_mean_file_rates(self):
        for i in range(8):
            denominator = 100 if i == 0 else 10000
            for records in (self.c, self.b):
                for key in gate.DER_KEYS:
                    records[i]["metrics"][key].update(miss_ms=0., reference_speaker_ms=denominator, rate=0.)
            self.c[i]["metrics"][gate.DER_KEYS[0]].update(miss_ms=100. if i == 0 else 0., rate=1. if i == 0 else 0.)
            words = 10 if i == 0 else 100
            for records in (self.c, self.b, self.a):
                records[i]["metrics"]["wer_raw"].update(reference_tokens=words, rate=1 / words)
                records[i]["metrics"]["cpwer_raw"].update(reference_tokens=words, errors=0, rate=0.)
            self.c[i]["metrics"]["cpwer_raw"].update(errors=5 if i == 0 else 0, rate=.5 if i == 0 else 0.)
        result = self.evaluate()
        self.assertTrue(result["gate_pass"])
        self.assertAlmostEqual(100 / 70100, result["aggregate"]["candidate"][gate.DER_KEYS[0]]["rate"])
        self.assertAlmostEqual(5 / 710, result["aggregate"]["candidate"]["cpwer_raw"]["rate"])

    def test_missing_failed_duplicate_and_mixed_settings_do_not_shrink_denominator(self):
        for mutation in (lambda: self.c.pop(), lambda: self.c[0].update(status="FAILED"),
                         lambda: self.c.append(deepcopy(self.c[0])), lambda: self.c[0].update(model_id="other")):
            self.c = primary_records()
            mutation()
            result = self.evaluate()
            self.assertFalse(result["gate_pass"])
            self.assertFalse(result["conditions"]["complete_same_eight_dev_cases"]["pass"])
            self.assertEqual(8, result["conditions"]["exact_native_speaker_count"]["denominator_cases"])

    def test_raw_wer_must_be_exact_even_if_candidate_is_numerically_better(self):
        self.c[0]["metrics"]["wer_raw"].update(errors=0, rate=0.)
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertFalse(result["conditions"]["raw_wer_exact_frozen_d"]["pass"])

    def test_fixed_oracle_unsupported_refiner_and_bad_denominators_fail(self):
        self.c[0]["mode"] = "fixed"
        self.assertFalse(self.evaluate()["gate_pass"])
        candidate = primary_records("tau-0p3")
        for record in candidate:
            record.update(stage="refined", source_profile="auto-0p30", refiner_accepted=True)
        candidate[0]["refiner_accepted"] = False
        result = gate.evaluate_records(candidate, self.b, self.a, expected_ids=self.ids, profile="tau-0p3")
        self.assertFalse(result["gate_pass"])
        self.c = primary_records()
        self.c[0]["metrics"][gate.DER_KEYS[0]].update(reference_speaker_ms=0, rate=None)
        self.assertFalse(self.evaluate()["gate_pass"])

    def test_empty_and_non8_expected_cases_are_not_fabricated_success(self):
        with self.assertRaises(ValueError):
            gate.evaluate_records([], [], [], expected_ids=[], profile="auto-0p30")
        result = gate.evaluate_records([], [], [], expected_ids=self.ids, profile="auto-0p30")
        self.assertFalse(result["gate_pass"])
        self.assertIsNone(result["aggregate"]["candidate"][gate.DER_KEYS[0]]["rate"])
        self.assertEqual(8, len(result["per_case"]))


class SavedAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.make_fixture()

    def make_fixture(self, *, refined=False, mono_first=False, algorithm=gate.CENTROID_ALGORITHM):
        self.manifest = self.root / "corpus/manifest.json"
        self.asr, self.baseline, self.candidate = (self.root / p for p in ("asr", "fixed", "candidate"))
        self.profile = "tau-0p35" if refined else "auto-0p30"
        cases, reference_hashes = [], {}
        self.data = []
        for i in range(8):
            identifier = f"dev-{i}"
            turns = [{"startMs": 0, "endMs": 2000, "speakerId": 0}] if mono_first and i == 0 else [
                {"startMs": 0, "endMs": 1000, "speakerId": 0}, {"startMs": 1000, "endMs": 2000, "speakerId": 1}]
            ref = {"transcript": [{"speaker_id": "speaker_1", "start_ms": 0, "end_ms": 2000, "text": "А Б"}]} if len(turns) == 1 else {"transcript": [
                {"speaker_id": "speaker_1", "start_ms": 0, "end_ms": 1000, "text": "А"},
                {"speaker_id": "speaker_2", "start_ms": 1000, "end_ms": 2000, "text": "Б"}]}
            reference = self.manifest.parent / "references" / (identifier + ".json")
            save(reference, ref)
            reference_hashes[identifier] = digest(reference)
            case = {"id": identifier, "split": "dev", "duration_ms": 2000, "audio_sha256": "a" * 64,
                    "reference": "references/" + identifier + ".json", "expected_speakers": len(turns)}
            cases.append(case)
            self.data.append((case, ref, turns))
        # A forbidden/missing holdout reference proves this DEV audit does not read it.
        save(self.manifest, {"schema_version": 1, "files": [*cases, {"id": "holdout-secret", "split": "holdout", "reference": "FORBIDDEN"}]})
        save(self.asr / "run.json", {"status": "COMPLETE", "config": {"pipeline": "vad_words_v1", "punctuation_mode": "none", "expected_speakers": -1},
                                       "fingerprint": {"manifest_sha256": digest(self.manifest), "references": reference_hashes}})
        save(self.baseline / "run.json", {"status": "COMPLETE", "manifest_sha256": digest(self.manifest), "asr_run_sha256": digest(self.asr / "run.json")})
        config = {"profile": "auto-0p30", "thresholds": [.35], "refiner_config": asdict(RefineConfig())}
        if algorithm == gate.WINDOW_ALGORITHM:
            config.update(algorithm=algorithm, method="complete", refiner_config=asdict(WindowClusterConfig()))
        elif algorithm != gate.CENTROID_ALGORITHM:
            config["algorithm"] = algorithm
        links = {}
        for case, ref, turns in self.data:
            metrics = score.score(ref, ref, 2000)
            rows = [{"start_ms": t["startMs"], "end_ms": t["endMs"], "speaker_id": "native_" + str(t["speakerId"]), "text": ""} for t in turns]
            for name, collar in zip(gate.DER_KEYS, (0, 250)):
                metrics[name] = score.der(ref["transcript"], rows, 2000, collar)
            metrics["native_speaker_count"] = len(turns)
            core = {**case, "metrics": metrics, "reference_sha256": reference_hashes[case["id"]],
                    "native_speaker_count": len(turns), "reference_speaker_count": len(turns), "native_speaker_count_error": 0}
            self.write_case(self.asr / case["id"], core, ref, {"actualWordFixture": True})
            ash = self.hashes(self.asr / case["id"], include_case=True)
            self.write_case(self.baseline / case["id"], core, ref,
                            {"diarizationTurns": turns, "source_asr_evidence_sha256": {k: v for k, v in ash.items() if k != "case.json"},
                             "singleBypass": len(turns) == 1})
            if refined:
                link = {"asr": ash, "reference": reference_hashes[case["id"]], "original_audio": case["audio_sha256"], "diar": {"case.json": "b" * 64}}
                links[case["id"]] = link
                record = {**core, "profile": self.profile, "stage": "refined", "threshold": .35,
                          "source_profile": "auto-0p30", "refiner_accepted": True, "source_evidence_sha256": link}
                diagnostic = {"diarizationTurns": turns, "sourceEvidence": link, "refinerAccepted": True,
                              "refiner": {"algorithm": algorithm, "status": "SUPPORTED",
                                          "config": {**config["refiner_config"], "tau" if algorithm == gate.WINDOW_ALGORITHM else "merge_threshold": .35}}}
                if algorithm == gate.WINDOW_ALGORITHM:
                    diagnostic["algorithm"] = algorithm
            else:
                record = {**core, "profile": self.profile, "mode": "auto", "threshold": .3, "model_id": "fixture", "window_shift": .1}
                diagnostic = {"diarizationTurns": turns, "mode": "auto", "numClustersPassed": -1, "fixedCountSource": "none", "threshold": .3,
                              "asrEvidenceSha256": {k: v for k, v in ash.items() if k != "case.json"}}
            self.write_case(self.candidate / self.profile / case["id"], record, ref, diagnostic)
        if refined:
            fp = {"manifest": digest(self.manifest), "asr_run": digest(self.asr / "run.json"), "config": config, "cases": links}
            save(self.candidate / "source-fingerprint.json", fp)
            save(self.candidate / "run.json", {"status": "COMPLETE", "config": config,
                    "source_fingerprint_sha256": hashlib.sha256(json.dumps(fp, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                    "failures": [], "pending_cases": []})
        else:
            save(self.candidate / "run.json", {"status": "COMPLETE", "options": {"mode": "auto", "model_id": "fixture", "window_shift": .1},
                    "fingerprint": {"manifest": digest(self.manifest), "asr_run": digest(self.asr / "run.json"), "thresholds": [.3]}})

    def hashes(self, folder, *, include_case=False):
        return {name: digest(folder / name) for name in (["case.json"] if include_case else []) + list(gate.EVIDENCE)}

    def write_case(self, folder, record, reference, diagnostic):
        for name, data in (("reference", reference), ("hypothesis", reference), ("diagnostics", diagnostic), ("metrics", record["metrics"])):
            save(folder / (name + ".json"), data)
        save(folder / "case.json", {**record, "evidence_sha256": self.hashes(folder)})

    def audit(self, **kwargs):
        return gate.evaluate_saved(self.candidate, self.profile, self.manifest, self.asr, self.baseline, **kwargs)

    def edit(self, path, change):
        data = json.loads(path.read_text())
        change(data)
        save(path, data)

    def rehash_case(self, folder):
        self.edit(folder / "case.json", lambda r: r.update(evidence_sha256=self.hashes(folder)))

    def test_complete_auto_evidence_recomputes_and_never_opens_audio(self):
        with mock.patch("tools.eval.pipeline._read_canonical_wav", side_effect=AssertionError("Audio read")), \
             mock.patch.object(gate.scoring, "score", side_effect=AssertionError("Unrelated full CER/timing score")):
            result = self.audit()
        self.assertTrue(result["gate_pass"], result["errors"])
        self.assertEqual(8, len(result["per_case"]))
        self.assertFalse(result["new_model_inference"])
        self.assertTrue(any(p.endswith("case.json") for p in result["source_sha256"]))

    def test_malformed_and_nonfinite_run_metadata_fail_with_audit(self):
        run = self.candidate / "run.json"
        original = run.read_bytes()
        for content in ('[]', '{"status":"COMPLETE","bad":NaN}', '{"status":"COMPLETE","bad":1e999}',
                        '{"status":"COMPLETE","options":[]}'):
            run.write_text(content)
            result = self.audit()
            self.assertFalse(result["gate_pass"])
            self.assertFalse(result["conditions"]["saved_source_integrity"]["pass"])
        run.write_bytes(original)

    def test_changed_input_during_read_is_detected(self):
        original = gate._Snapshots.verify_unchanged
        target = self.candidate / self.profile / "dev-0/hypothesis.json"
        def tamper(snapshot):
            target.write_text(target.read_text() + " ")
            return original(snapshot)
        with mock.patch.object(gate._Snapshots, "verify_unchanged", tamper):
            result = self.audit()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("changed during audit" in e["error"] for e in result["errors"]))

    def test_hash_tamper_and_embedded_metric_tamper_fail(self):
        folder = self.candidate / self.profile / "dev-0"
        diagnostic = folder / "diagnostics.json"
        diagnostic.write_text(diagnostic.read_text() + " ")
        self.assertFalse(self.audit()["gate_pass"])
        self.rehash_case(folder)
        self.edit(folder / "case.json", lambda r: r["metrics"]["wer_raw"].update(errors=999))
        result = self.audit()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("embedded metrics" in e["error"] for e in result["errors"]))

    def test_standard_native_metrics_keep_count_in_case_without_optional_duplicate(self):
        for case, _, _ in self.data:
            folder = self.candidate / self.profile / case["id"]
            self.edit(folder / "metrics.json", lambda m: m.pop("native_speaker_count"))
            metrics = json.loads((folder / "metrics.json").read_text())
            self.edit(folder / "case.json", lambda r: r.update(metrics=metrics, evidence_sha256=self.hashes(folder)))
        result = self.audit()
        self.assertTrue(result["gate_pass"], result["errors"])
        folder = self.candidate / self.profile / "dev-0"
        self.edit(folder / "case.json", lambda r: r.update(native_speaker_count=999))
        result = self.audit()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("native/reference count differs" in e["error"] for e in result["errors"]))

    def test_rehashed_false_metrics_are_recomputed_not_trusted(self):
        folder = self.candidate / self.profile / "dev-0"
        self.edit(folder / "metrics.json", lambda m: m[gate.DER_KEYS[0]].update(miss_ms=3, rate=.0015))
        metrics = json.loads((folder / "metrics.json").read_text())
        self.edit(folder / "case.json", lambda r: r.update(metrics=metrics, evidence_sha256=self.hashes(folder)))
        result = self.audit()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("does not recompute" in e["error"] for e in result["errors"]))

    def test_wrong_d_run_reference_and_case_provenance_fail(self):
        path = self.candidate / "run.json"
        original = path.read_bytes()
        self.edit(path, lambda r: r["fingerprint"].update(asr_run="f" * 64))
        self.assertFalse(self.audit()["gate_pass"])
        path.write_bytes(original)
        folder = self.candidate / self.profile / "dev-0"
        self.edit(folder / "diagnostics.json", lambda d: d["asrEvidenceSha256"].update(**{"hypothesis.json": "f" * 64}))
        self.rehash_case(folder)
        result = self.audit()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("D evidence" in e["error"] for e in result["errors"]))
        self.edit(self.manifest.parent / "references/dev-0.json", lambda r: r["transcript"][0].update(text="Другой эталон"))
        result = self.audit()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("Reference differs" in e["error"] for e in result["errors"]))

    def test_missing_case_running_run_and_known_k_disguised_as_auto_fail(self):
        folder = self.candidate / self.profile / "dev-0"
        original = (folder / "case.json").read_bytes()
        (folder / "case.json").unlink()
        self.assertFalse(self.audit()["gate_pass"])
        (folder / "case.json").write_bytes(original)
        self.edit(folder / "diagnostics.json", lambda d: d.update(numClustersPassed=2))
        self.rehash_case(folder)
        self.assertFalse(self.audit()["gate_pass"])
        self.edit(self.candidate / "run.json", lambda r: r.update(status="RUNNING"))
        self.assertFalse(self.audit()["gate_pass"])

    def test_refiner_evidence_passes_then_unsupported_and_mixed_config_fail(self):
        self.make_fixture(refined=True)
        result = self.audit()
        self.assertTrue(result["gate_pass"], result["errors"])
        self.assertEqual(gate.CENTROID_ALGORITHM, result["refiner_algorithm"])
        folder = self.candidate / self.profile / "dev-0"
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"]["config"].update(smooth_ms=0))
        self.rehash_case(folder)
        result = self.audit()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("global policy" in e["error"] for e in result["errors"]))
        self.edit(folder / "diagnostics.json", lambda d: d.update(refinerAccepted=False))
        self.rehash_case(folder)
        self.assertFalse(self.audit()["gate_pass"])

    def test_fixed_mono_comparator_requires_real_single_bypass(self):
        self.make_fixture(mono_first=True)
        self.assertTrue(self.audit()["gate_pass"])
        folder = self.baseline / "dev-0"
        self.edit(folder / "diagnostics.json", lambda d: d.update(singleBypass=False))
        self.rehash_case(folder)
        result = self.audit()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("single-speaker bypass" in e["error"] for e in result["errors"]))

    def test_window_algorithm_exact_tau_config_and_partial_temporal_are_known(self):
        self.make_fixture(refined=True, algorithm=gate.WINDOW_ALGORITHM)
        result = self.audit()
        self.assertTrue(result["gate_pass"], result["errors"])
        self.assertEqual(gate.WINDOW_ALGORITHM, result["refiner_algorithm"])
        folder = self.candidate / self.profile / "dev-0"
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"].update(status="PARTIAL_TEMPORAL"))
        self.rehash_case(folder)
        self.assertTrue(self.audit()["gate_pass"])
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"]["config"].update(tau=.4))
        self.rehash_case(folder)
        result = self.audit()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("global policy" in e["error"] for e in result["errors"]))

    def test_unknown_mixed_and_cross_algorithm_statuses_fail(self):
        self.make_fixture(refined=True, algorithm="invented-v1")
        self.assertFalse(self.audit()["gate_pass"])
        self.make_fixture(refined=True, algorithm=gate.WINDOW_ALGORITHM)
        folder = self.candidate / self.profile / "dev-0"
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"].update(algorithm=gate.CENTROID_ALGORITHM))
        self.rehash_case(folder)
        self.assertFalse(self.audit()["gate_pass"])
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"].update(algorithm=gate.WINDOW_ALGORITHM, status="PARTIAL_ACOUSTIC"))
        self.rehash_case(folder)
        self.assertFalse(self.audit()["gate_pass"])
        self.make_fixture(refined=True)
        folder = self.candidate / self.profile / "dev-0"
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"].update(status="PARTIAL_TEMPORAL"))
        self.rehash_case(folder)
        self.assertFalse(self.audit()["gate_pass"])

    def test_window_does_not_weaken_count_raw_or_support_gates(self):
        self.make_fixture(refined=True, algorithm=gate.WINDOW_ALGORITHM)
        folder = self.candidate / self.profile / "dev-0"
        self.edit(folder / "case.json", lambda r: r.update(refiner_accepted=False))
        self.assertFalse(self.audit()["gate_pass"])
        self.edit(folder / "case.json", lambda r: r.update(refiner_accepted=True))
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"]["config"].update(merge_threshold=.35))
        self.rehash_case(folder)
        self.assertFalse(self.audit()["gate_pass"])

    def test_fresh_output_and_cli_success(self):
        output = self.root / "audit.json"
        args = ["--candidate", str(self.candidate), "--profile", self.profile, "--manifest", str(self.manifest),
                "--asr-run", str(self.asr), "--fixed-baseline", str(self.baseline), "--output", str(output)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(0, gate.main(args))
        original = output.read_bytes()
        with self.assertRaises(FileExistsError):
            self.audit(output=output)
        self.assertEqual(original, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
