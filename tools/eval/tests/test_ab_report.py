import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("ab_report", Path(__file__).resolve().parents[1] / "ab_report.py")
ab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ab)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def token_metric(reference, errors, deletions=0):
    return {"errors": errors, "substitutions": errors - deletions, "deletions": deletions,
            "insertions": 0, "reference_tokens": reference, "hypothesis_tokens": reference - deletions,
            # Deliberately incorrect cached rate: report must derive from counts.
            "rate": .999}


def metrics(reference=100, errors=20, deletions=0, normalized=None):
    result = {name: token_metric(reference, errors, deletions) for name in ab.TOKEN_METRICS}
    result["protocol"] = {"primary_metric": "wer_raw", "raw_wer": "exact whitespace"}
    if normalized is not None:
        result["wer_normalized"] = token_metric(reference, normalized)
    for name in ab.DER_METRICS:
        result[name] = {"miss_ms": 20., "false_alarm_ms": 5., "confusion_ms": 10., "reference_speaker_ms": 100.}
    result.update(punctuation={"true_positive": 2, "false_positive": 1, "false_negative": 1},
                  initial_case={"correct": 1, "reference_initials": 2, "aligned_reference_initials": 1, "unmatched_reference_initials": 1},
                  timing={"matched_pairs": 1, "reference_intervals": 2, "hypothesis_intervals": 1,
                          "unmatched_reference": 1, "unmatched_hypothesis": 0, "pairs_over_250ms": 0,
                          "pairs": [{"start_abs_error_ms": 50, "end_abs_error_ms": 80}]},
                  speakers={"reference": 2, "hypothesis": 3}, native_speaker_count=4)
    return result


class PairedReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.baseline, self.candidate = self.root / "baseline", self.root / "candidate"
        self.manifest = self.root / "corpus/manifest.json"
        self.cases = []

    def add_case(self, identifier, split, old, new, short=False):
        reference = self.manifest.parent / (identifier + ".json")
        save(reference, {"transcript": [{"speaker_id": "speaker_1", "start_ms": 0, "end_ms": 1000, "text": "Авторский эталон!"}]})
        case = {"id": identifier, "split": split, "audio_sha256": "a" * 64, "reference": reference.name,
                "duration_ms": 1000, "conditions": {"short_utterances": short}}
        self.cases.append(case)
        for run, metric in ((self.baseline, old), (self.candidate, new)):
            folder = run / identifier
            folder.mkdir(parents=True)
            shutil.copy2(reference, folder / "reference.json")
            save(folder / "metrics.json", metric)
            save(folder / "case.json", {**case, "reference_sha256": ab.digest(reference),
                 "processing_ms": 100, "runner_wall_ms": 110, "metrics": metric,
                 "evidence_sha256": {"metrics.json": ab.digest(folder / "metrics.json"), "reference.json": ab.digest(reference)}})
        save(self.manifest, {"schema_version": 1, "files": self.cases})
        return case

    def change_metric(self, run, identifier, operation):
        folder = run / identifier
        record = ab.read_json(folder / "case.json")
        metric = ab.read_json(folder / "metrics.json")
        operation(metric)
        save(folder / "metrics.json", metric)
        record["metrics"] = metric
        record["evidence_sha256"]["metrics.json"] = ab.digest(folder / "metrics.json")
        save(folder / "case.json", record)

    def report(self, split="all"):
        return ab.compare(self.baseline, self.candidate, self.manifest, split)

    def test_weighted_raw_gates_ignore_cached_rates(self):
        self.add_case("dev-small", "dev", metrics(1, 1), metrics(1, 0))
        self.add_case("dev-large", "dev", metrics(100, 10), metrics(100, 12))
        self.add_case("holdout", "holdout", metrics(), metrics())
        report = self.report()
        old, new = (report["by_split"]["dev"][name]["wer_raw"] for name in ("baseline", "candidate"))
        self.assertAlmostEqual(old["rate"], 11 / 101)
        self.assertAlmostEqual(new["rate"], 12 / 101)
        # A mean of file WERs improves sharply, but the true token-weighted WER regresses.
        self.assertEqual(report["gate"]["status"], "FAIL")
        self.assertFalse(report["gate"]["accepted"])

    def test_full_pass_requires_all_primary_axes(self):
        self.add_case("dev", "dev", metrics(errors=20, normalized=10), metrics(errors=19, normalized=10))
        self.add_case("holdout", "holdout", metrics(errors=20), metrics(errors=20))
        report = self.report()
        self.assertTrue(report["gate"]["accepted"])
        self.assertEqual(report["gate"]["status"], "PASS")
        self.assertEqual(report["all_selected"]["candidate"]["rtf"], .1)
        self.assertAlmostEqual(report["all_selected"]["candidate"]["punctuation"]["f1"], 2 / 3)
        self.assertEqual(report["all_selected"]["candidate"]["initial_case"]["accuracy"], .5)

    def test_dev_normalized_or_holdout_raw_regression_fails(self):
        self.add_case("dev", "dev", metrics(errors=20, normalized=10), metrics(errors=19, normalized=11))
        self.add_case("holdout", "holdout", metrics(errors=20), metrics(errors=21))
        checks = self.report()["gate"]["checks"]
        self.assertEqual(checks["dev_raw_wer_strictly_better"]["status"], "PASS")
        self.assertEqual(checks["dev_normalized_wer_no_worse"]["status"], "FAIL")
        self.assertEqual(checks["holdout_raw_wer_no_worse"]["status"], "FAIL")

    def test_dev_selection_never_reads_holdout_or_run_summary(self):
        self.add_case("dev", "dev", metrics(errors=20), metrics(errors=19))
        holdout = self.add_case("holdout", "holdout", metrics(), metrics())
        for run in (self.baseline, self.candidate):
            (run / "holdout/case.json").write_text("FORBIDDEN HOLDOUT READ")
            (run / "summary.json").write_text("FORBIDDEN SUMMARY READ")
        (self.manifest.parent / holdout["reference"]).write_text("FORBIDDEN HOLDOUT REFERENCE READ")
        report = self.report("dev")
        self.assertEqual(set(report["by_split"]), {"dev"})
        self.assertEqual(report["gate"]["status"], "PENDING_UNEVALUATED_SPLIT")
        self.assertFalse(report["gate"]["accepted"])
        self.assertEqual(report["gate"]["checks"]["holdout_raw_wer_no_worse"]["status"], "NOT_EVALUATED")

    def test_missing_extra_ids_audio_or_reference_mismatch_rejected(self):
        self.add_case("dev", "dev", metrics(), metrics())
        folder = self.candidate / "dev"
        original = (folder / "case.json").read_bytes()
        for field in ("audio_sha256", "reference_sha256", "id", "split", "duration_ms"):
            record = json.loads(original)
            record[field] = "wrong"
            save(folder / "case.json", record)
            with self.assertRaises(ValueError):
                self.report("dev")
        (folder / "case.json").write_bytes(original)
        save(self.candidate / "extra/case.json", {})
        with self.assertRaisesRegex(ValueError, "Unpaired case IDs"):
            self.report("dev")
        shutil.rmtree(self.candidate / "extra")
        shutil.rmtree(folder)
        with self.assertRaisesRegex(ValueError, "missing"):
            self.report("dev")

    def test_changed_reference_evidence_or_protocol_rejected(self):
        self.add_case("dev", "dev", metrics(), metrics())
        reference = self.candidate / "dev/reference.json"
        original = reference.read_bytes()
        reference.write_text("changed")
        with self.assertRaisesRegex(ValueError, "reference changed"):
            self.report("dev")
        reference.write_bytes(original)
        self.change_metric(self.candidate, "dev", lambda m: m.update(protocol={"raw_wer": "different"}))
        with self.assertRaisesRegex(ValueError, "protocols differ"):
            self.report("dev")

    def test_inconsistent_counts_or_denominators_rejected(self):
        self.add_case("dev", "dev", metrics(), metrics())
        self.change_metric(self.candidate, "dev", lambda m: m["wer_raw"].update(reference_tokens=99))
        with self.assertRaisesRegex(ValueError, "denominator"):
            self.report("dev")
        self.change_metric(self.candidate, "dev", lambda m: m["wer_raw"].update(reference_tokens=100, errors=999))
        with self.assertRaisesRegex(ValueError, "S\\+D\\+I"):
            self.report("dev")

    def test_der_reference_denominator_mismatch_rejected(self):
        self.add_case("dev", "dev", metrics(), metrics())
        self.change_metric(self.candidate, "dev", lambda m: m["native_der_collar_0ms"].update(reference_speaker_ms=999))
        with self.assertRaisesRegex(ValueError, "Unpaired reference denominator"):
            self.report("dev")

    def test_no_punctuation_or_initials_remains_undefined(self):
        metric = metrics()
        metric["punctuation"] = {"true_positive": 0, "false_positive": 0, "false_negative": 0}
        metric["initial_case"] = {"correct": 0, "reference_initials": 0, "aligned_reference_initials": 0, "unmatched_reference_initials": 0}
        result = ab.aggregate([{"id": "none", "duration_ms": 1000, "metrics": metric}])
        self.assertIsNone(result["punctuation"]["f1"])
        self.assertIsNone(result["initial_case"]["accuracy"])

    def test_missing_metrics_and_zero_denominator_are_not_perfect(self):
        missing = metrics(errors=19)
        for key in ("wer_raw", "punctuation", "initial_case", "timing"):
            missing.pop(key)
        missing.pop("native_speaker_count")
        self.add_case("dev", "dev", metrics(errors=20), missing)
        report = self.report("dev")
        candidate = report["by_split"]["dev"]["candidate"]
        for field, key in (("wer_raw", "rate"), ("punctuation", "f1"), ("initial_case", "accuracy"), ("timing", "reference_coverage"), ("native_speakers", "exact_rate")):
            self.assertIsNone(candidate[field][key])
        self.assertEqual(report["gate"]["status"], "UNASSESSABLE")
        zero = ab.aggregate([{"id": "zero", "duration_ms": 1000, "processing_ms": None, "metrics": metrics(reference=0, errors=0)}])
        self.assertIsNone(zero["wer_raw"]["rate"])
        self.assertIsNone(zero["rtf"])

    def test_short_deletion_target_and_no_word_timestamp_claim(self):
        self.add_case("dev-short", "dev", metrics(errors=5, deletions=2), metrics(errors=3, deletions=1), short=True)
        self.add_case("holdout", "holdout", metrics(), metrics())
        report = self.report()
        axis = report["by_split"]["dev"]["short_utterance_deletion_axis"]
        self.assertEqual(axis["status"], "PASS")
        self.assertEqual(axis["relative_deletion_reduction"], .5)
        timing = report["by_split"]["dev"]["candidate"]["timing"]
        self.assertTrue(timing["median_both_below_200ms_diagnostic"])
        self.assertIsNone(timing["word_timestamp_acceptance"])
        self.assertEqual(timing["reference_coverage"], .5)

    def test_timing_global_median_uses_pairs_not_file_medians(self):
        a, b = metrics(), metrics()
        b["timing"].update(matched_pairs=3, reference_intervals=3, hypothesis_intervals=3,
                           unmatched_reference=0, pairs=[{"start_abs_error_ms": 500, "end_abs_error_ms": 600}] * 3)
        records = [{"id": "a", "duration_ms": 1000, "metrics": a}, {"id": "b", "duration_ms": 1000, "metrics": b}]
        result = ab.aggregate(records)
        self.assertEqual(result["timing"]["median_start_abs_error_ms"], 500)
        self.assertEqual(result["timing"]["reference_coverage"], 4 / 5)
        b["timing"].pop("pairs")
        self.assertIsNone(ab.aggregate(records)["timing"]["median_start_abs_error_ms"])

    def test_fresh_output_contract(self):
        self.add_case("dev", "dev", metrics(errors=20), metrics(errors=19))
        output = self.root / "report"
        arguments = ["--baseline", str(self.baseline), "--candidate", str(self.candidate),
                     "--manifest", str(self.manifest), "--output", str(output), "--split", "dev"]
        with mock.patch("builtins.print"):
            self.assertEqual(ab.main(arguments), 0)
        self.assertTrue((output / "report.json").is_file())
        self.assertTrue((output / "report.md").is_file())
        with self.assertRaisesRegex(ValueError, "fresh"):
            ab.main(arguments)


if __name__ == "__main__":
    unittest.main()
