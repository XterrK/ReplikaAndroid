import copy
from dataclasses import asdict
import json
from pathlib import Path
import unittest
from unittest import mock

from tools.eval import window_overcluster_sweep as runner
from tools.eval import window_overcluster as window
from tools.eval import diar_acceptance
from tools.eval.tests import test_refine_sweep as fixtures

save = fixtures.save


class WindowSweepTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SavedRefinerSweepTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.diar, self.asr, self.manifest = (
            self.fixture.root, self.fixture.diar, self.fixture.asr, self.fixture.manifest)
        self.profile = "auto-0p50"
        for i in range(8):
            identifier = "dev-" + str(i)
            self.fixture.add_case(identifier)
            old = self.diar / "overcluster" / identifier
            new = self.diar / self.profile / identifier
            new.parent.mkdir(exist_ok=True)
            old.rename(new)
            record = runner.saved.read_json(new / "case.json")
            record.update(mode="auto", profile=self.profile, model_id="fixture-model")
            save(new / "case.json", record)
        meta = runner.saved.read_json(self.asr / "run.json")
        meta["fingerprint"] = {"references": {c["id"]: runner.digest(self.manifest.parent / c["reference"])
                                               for c in self.fixture.cases}}
        save(self.asr / "run.json", meta)
        self.diar_meta = {"status": "COMPLETE", "options": {"mode": "auto"},
                          "fingerprint": {"asr_run": runner.digest(self.asr / "run.json")}}
        save(self.diar / "run.json", self.diar_meta)
        self.protocol = self.root / "protocol.json"
        save(self.protocol, {"schema_version": 1, "id": "fixture-only-window-protocol",
                            "initial_global_grid": {"cosine_thresholds": [.65], "linkage": ["complete", "average"]}})

    def load(self):
        return runner.load_inputs(self.diar, self.asr, self.manifest, self.profile)

    def main(self, output, *extra):
        return runner.main(["--diar-run", str(self.diar), "--asr-run", str(self.asr),
            "--manifest", str(self.manifest), "--profile", self.profile, "--method", "complete",
            "--protocol", str(self.protocol), "--output", str(output), *extra])

    def evidence_change(self, identifier, filename, change):
        self.fixture.edit_evidence(self.diar / self.profile / identifier, filename, change)

    def retag_cases(self, split_by_id):
        corpus = runner.saved.read_json(self.manifest)
        for case in corpus["files"]:
            case["split"] = split_by_id.get(case["id"], case["split"])
            for folder in (self.diar / self.profile / case["id"], self.asr / case["id"]):
                record = runner.saved.read_json(folder / "case.json")
                record["split"] = case["split"]
                save(folder / "case.json", record)
        save(self.manifest, corpus)

    def test_loader_requires_full_dev_but_does_not_read_holdout(self):
        corpus = runner.saved.read_json(self.manifest)
        corpus["files"].append({"id": "holdout-secret", "split": "holdout", "reference": "FORBIDDEN.json"})
        save(self.manifest, corpus)
        (self.manifest.parent / "FORBIDDEN.json").write_text("DO NOT PARSE HOLDOUT")
        inputs, fingerprint = self.load()
        self.assertEqual(8, len(inputs))
        self.assertEqual(8, len(fingerprint["selected_ids"]))
        self.assertNotIn("holdout-secret", fingerprint["cases"])
        corpus["files"] = corpus["files"][1:]
        save(self.manifest, corpus)
        with self.assertRaisesRegex(ValueError, "eight-case"):
            self.load()

    def test_generic_256_and_512_dimensions_are_not_baseline_hardcoded(self):
        for dimension in (256, 512):
            for i in range(8):
                def change(d, dimension=dimension):
                    for w in d["cleanEmbeddingWindows"]:
                        w["embedding"] = [1.] + [0.] * (dimension - 1)
                self.evidence_change("dev-" + str(i), "diagnostics.json", change)
            inputs, fingerprint = self.load()
            self.assertEqual(dimension, fingerprint["embedding_dimension"])
            self.assertEqual({dimension}, {len(w.embedding) for c in inputs for w in c.windows})
        self.evidence_change("dev-0", "diagnostics.json",
            lambda d: d["cleanEmbeddingWindows"][0].update(embedding=[1., 0.]))
        with self.assertRaisesRegex(ValueError, "dimensions"):
            self.load()

    def test_nondev_requires_explicit_positive_coverage_before_inputs_or_outputs(self):
        for split in ("holdout", "all"):
            with self.subTest(split=split), mock.patch.object(runner, "load_inputs") as loader:
                output = self.root / ("missing-count-" + split)
                with self.assertRaisesRegex(ValueError, "explicit expected cases"):
                    self.main(output, "--split", split)
                loader.assert_not_called()
                self.assertFalse(output.exists())
        for count in (True, 0, -1, 5.0):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "positive integer"):
                runner.load_inputs(self.diar, self.asr, self.manifest, self.profile, "all", count)
        with self.assertRaisesRegex(ValueError, "eight-case"):
            runner.load_inputs(self.diar, self.asr, self.manifest, self.profile, "dev", 5)

    def test_explicit_five_case_holdout_retains_split_and_never_reads_dev_references(self):
        selected = {"dev-" + str(i) for i in range(5)}
        self.retag_cases({identifier: "holdout" for identifier in selected})
        corpus = runner.saved.read_json(self.manifest)
        for case in corpus["files"]:
            if case["id"] not in selected:
                (self.manifest.parent / case["reference"]).write_text("FORBIDDEN DEV REFERENCE")
        inputs, fingerprint = runner.load_inputs(self.diar, self.asr, self.manifest, self.profile,
                                                 "holdout", 5)
        self.assertEqual(selected, {case.case_id for case in inputs})
        self.assertEqual({"holdout"}, {case.split for case in inputs})
        self.assertEqual(("holdout", 5), (fingerprint["split"], fingerprint["expected_cases"]))
        output = self.root / "holdout-five"
        self.main(output, "--split", "holdout", "--expected-cases", "5")
        summary = runner.saved.read_json(output / "summary.json")["summaries"]["tau-0p65"]
        self.assertEqual(5, summary["expected_cases"])
        self.assertTrue(summary["complete_case_coverage"])
        self.assertEqual(5, summary["refiner_accepted_cases"])
        self.assertTrue(summary["raw_wer_invariant"])
        for path in (output / "tau-0p65").glob("*/case.json"):
            self.assertEqual("holdout", runner.saved.read_json(path)["split"])
        with self.assertRaisesRegex(ValueError, "Full 6-case holdout"):
            runner.load_inputs(self.diar, self.asr, self.manifest, self.profile, "holdout", 6)

    def test_explicit_all_ten_is_complete_and_preserves_actual_mixed_splits(self):
        for i in range(2):
            identifier = "reserve-" + str(i)
            self.fixture.add_case(identifier, split="holdout")
            old, new = self.diar / "overcluster" / identifier, self.diar / self.profile / identifier
            old.rename(new)
            record = runner.saved.read_json(new / "case.json")
            record.update(mode="auto", profile=self.profile, model_id="fixture-model")
            save(new / "case.json", record)
        asr_meta = runner.saved.read_json(self.asr / "run.json")
        asr_meta["fingerprint"]["references"] = {case["id"]: runner.digest(self.manifest.parent / case["reference"])
                                                for case in self.fixture.cases}
        save(self.asr / "run.json", asr_meta)
        diar_meta = copy.deepcopy(self.diar_meta)
        diar_meta["fingerprint"]["asr_run"] = runner.digest(self.asr / "run.json")
        save(self.diar / "run.json", diar_meta)
        output = self.root / "all-ten"
        self.main(output, "--split", "all", "--expected-cases", "10")
        config = runner.saved.read_json(output / "config.json")
        summary = runner.saved.read_json(output / "summary.json")["summaries"]["tau-0p65"]
        records = [runner.saved.read_json(path) for path in (output / "tau-0p65").glob("*/case.json")]
        self.assertEqual(("all", 10), (config["split"], config["expected_cases"]))
        self.assertEqual((10, 10), (summary["cases"], summary["expected_cases"]))
        self.assertTrue(summary["complete_case_coverage"])
        self.assertEqual(8, sum(record["split"] == "dev" for record in records))
        self.assertEqual(2, sum(record["split"] == "holdout" for record in records))
        self.assertFalse(runner.aggregate(records[:-1], 10)["complete_case_coverage"])
        with self.assertRaisesRegex(ValueError, "Full 11-case all"):
            runner.load_inputs(self.diar, self.asr, self.manifest, self.profile, "all", 11)

    def test_source_run_case_reference_and_exact_window_coverage_pins(self):
        source_meta = copy.deepcopy(self.diar_meta)
        source_meta["fingerprint"]["asr_run"] = "f" * 64
        save(self.diar / "run.json", source_meta)
        with self.assertRaisesRegex(ValueError, "run fingerprint"):
            self.load()
        save(self.diar / "run.json", self.diar_meta)
        path = self.diar / self.profile / "dev-0/diagnostics.json"
        original = path.read_bytes()
        self.evidence_change("dev-0", "diagnostics.json",
            lambda d: d["asrEvidenceSha256"].update({"hypothesis.json": "f" * 64}))
        with self.assertRaisesRegex(ValueError, "ASR evidence hashes"):
            self.load()
        save(path, json.loads(original))
        self.evidence_change("dev-0", "diagnostics.json", lambda d: d["cleanEmbeddingWindows"].pop())
        with self.assertRaisesRegex(ValueError, "window coverage"):
            self.load()
        save(path, json.loads(original))
        self.evidence_change("dev-0", "diagnostics.json",
            lambda d: d["cleanEmbeddingWindows"].append(d["cleanEmbeddingWindows"][0]))
        with self.assertRaisesRegex(ValueError, "window coverage"):
            self.load()
        ref = self.manifest.parent / self.fixture.cases[0]["reference"]
        ref.write_bytes(ref.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "Independent reference"):
            self.load()

    def test_complete_matrix_passes_only_turns_vectors_clock_global_config_to_helper(self):
        real = window.overcluster
        calls = []
        def tracked(turns, windows, duration, config):
            if turns:
                calls.append((turns, windows, duration, config))
                self.assertEqual(6000, duration)
                self.assertTrue(all(isinstance(t, runner.base.Turn) for t in turns))
                self.assertTrue(all(isinstance(w, runner.saved.EmbeddingWindow) for w in windows))
                self.assertEqual(.65, config.tau)
            return real(turns, windows, duration, config)
        output = self.root / "matrix"
        with mock.patch.object(window, "overcluster", side_effect=tracked), \
             mock.patch.object(runner.base, "_read_canonical_wav", side_effect=AssertionError("Audio opened")):
            self.main(output)
        self.assertEqual(8, len(calls))
        meta = runner.saved.read_json(output / "run.json")
        self.assertEqual("COMPLETE", meta["status"])
        self.assertEqual([], meta["failures"])
        summary = runner.saved.read_json(output / "summary.json")["summaries"]["tau-0p65"]
        self.assertTrue(summary["complete_case_coverage"])
        self.assertTrue(summary["raw_wer_invariant"])
        self.assertEqual(8, summary["refiner_accepted_cases"])
        self.assertNotIn("rtf_diarization_stage", summary)
        for identifier in ("dev-" + str(i) for i in range(8)):
            folder = output / "tau-0p65" / identifier
            record = runner.saved.read_json(folder / "case.json")
            self.assertEqual(record["evidence_sha256"], runner.evidence_hashes(folder))
            source = runner.saved.read_json(self.asr / identifier / "hypothesis.json")
            self.assertEqual(runner._tokens(source), runner._tokens(runner.saved.read_json(folder / "hypothesis.json")))
        original = (output / "run.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.main(output)
        self.assertEqual(original, (output / "run.json").read_bytes())

    def test_runtime_failure_preserves_completed_cases_and_failed_attempt(self):
        real, count = window.overcluster, 0
        def fail_second(turns, windows, duration, config):
            nonlocal count
            if turns:
                count += 1
                if count == 2:
                    raise RuntimeError("fixture-only clustering failure")
            return real(turns, windows, duration, config)
        output = self.root / "failed-matrix"
        with mock.patch.object(window, "overcluster", side_effect=fail_second), \
             self.assertRaisesRegex(RuntimeError, "fixture-only"):
            self.main(output)
        meta = runner.saved.read_json(output / "run.json")
        self.assertEqual("FAILED", meta["status"])
        self.assertEqual(1, len(meta["failures"]))
        self.assertTrue((output / "tau-0p65/dev-0/case.json").is_file())
        self.assertTrue((output / "failures/tau-0p65-dev-1.json").is_file())
        summary = runner.saved.read_json(output / "summary.json")["summaries"]["tau-0p65"]
        self.assertFalse(summary["complete_case_coverage"])

    def test_raw_and_literal_invariance_failure_is_not_hidden(self):
        output = self.root / "changed-text"
        with mock.patch.object(runner, "score_projection", side_effect=ValueError("Literal ASR token sequence changed")), \
             self.assertRaisesRegex(ValueError, "Literal ASR"):
            self.main(output)
        self.assertEqual("FAILED", runner.saved.read_json(output / "run.json")["status"])
        self.assertTrue((output / "failures/tau-0p65-dev-0.json").is_file())

    def test_unsupported_helper_outputs_cannot_pass_the_independent_gate(self):
        real = window.overcluster
        def unsupported(turns, windows, duration, config):
            if not turns:
                return real(turns, windows, duration, config)
            return window.WindowClusterResult(tuple(turns), False, {
                "algorithm": "window-overcluster-v1", "status": "UNSUPPORTED", "config": asdict(config)})
        output = self.root / "unsupported"
        with mock.patch.object(window, "overcluster", side_effect=unsupported):
            self.main(output)
        records = [runner.saved.read_json(p) for p in sorted((output / "tau-0p65").glob("*/case.json"))]
        summary = runner.saved.read_json(output / "summary.json")["summaries"]["tau-0p65"]
        self.assertEqual(8, summary["speaker_count_exact_cases"])
        self.assertEqual(0, summary["refiner_accepted_cases"])
        asr = [runner.saved.read_json(self.asr / record["id"] / "case.json") for record in records]
        fixed = copy.deepcopy(records)
        gate = diar_acceptance.evaluate_records(records, fixed, asr,
            expected_ids=[r["id"] for r in records], profile="tau-0p65")
        self.assertFalse(gate["gate_pass"])
        self.assertTrue(all("Unsupported" in item["error"] for item in gate["errors"]))

    def test_source_changes_during_matrix_are_failed_after_outputs_are_preserved(self):
        original_load, calls = runner.load_inputs, 0
        def changed_on_final(*args):
            nonlocal calls
            cases, fingerprint = original_load(*args)
            calls += 1
            if calls == 2:
                fingerprint["manifest"] = "f" * 64
            return cases, fingerprint
        output = self.root / "source-changed"
        with mock.patch.object(runner, "load_inputs", side_effect=changed_on_final), \
             self.assertRaisesRegex(ValueError, "source changed"):
            self.main(output)
        self.assertEqual("FAILED", runner.saved.read_json(output / "run.json")["status"])
        self.assertEqual(8, len(list((output / "tau-0p65").glob("*/case.json"))))


if __name__ == "__main__":
    unittest.main()
