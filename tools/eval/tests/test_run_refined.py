"""Fresh full-run evidence tests with a controlled replacement inference API."""
from contextlib import ExitStack, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.eval import run_refined as runner


class FullRunnerContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.audio_root = self.root / "audio"
        self.audio_root.mkdir()
        self.audio = self.audio_root / "fixture.wav"
        self.audio.write_bytes(b"controlled unit fixture, never passed to a real model")
        self.reference = self.root / "reference.json"
        self.reference.write_text(json.dumps({"transcript": [{"speaker_id": "speaker_1",
            "start_ms": 0, "end_ms": 1000, "text": "Привет!"}]}, ensure_ascii=False))
        self.manifest = self.root / "manifest.json"
        # No expected_speakers exists in this manifest: it cannot supply oracle K.
        self.manifest.write_text(json.dumps({"schema_version": 1, "files": [{
            "id": "dev-unit", "split": "dev", "kind": "controlled_unit_fixture", "audio": self.audio.name,
            "reference": self.reference.name, "audio_sha256": runner.digest(self.audio), "duration_ms": 1000}]}))
        self.config = self.root / "config.json"
        config = copy.deepcopy(runner.DEFAULT_CONFIG)
        config["model_id"] = "fixture"
        self.config.write_text(json.dumps(config))
        self.embedding = self.root / "embedding.onnx"
        self.embedding.write_bytes(b"controlled weight fixture")
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps({"schema_version": 1, "required_runtime": "2.0.1", "models": [{
            "id": "fixture", "path": self.embedding.name, "repoRelative": False, "size": self.embedding.stat().st_size,
            "sha256": runner.digest(self.embedding), "embedding_dimension": 2}]}))
        self.lock = self.root / "models-lock.json"
        self.lock.write_text("{}")
        self.args = SimpleNamespace(output=self.root / "output", config=self.config, manifest=self.manifest,
            split="dev", cases=None, audio_root=self.audio_root, model_root=self.root / "models",
            catalog=self.catalog, embedding_root=self.root)
        self.calls = []

    def invoke(self, *, change_reference=False, replay=False, wrong_window=False):
        config = json.loads(self.config.read_text())
        is_window = config["pipeline"] == "window_words_v1"
        pin = json.loads(self.catalog.read_text())["models"][0]
        def controlled_process(audio, model_root, **options):
            self.calls.append((audio, model_root, copy.deepcopy(options)))
            if change_reference:
                self.reference.write_text('{"transcript": []}')
            native = [{"startMs": 0, "endMs": 1000, "speakerId": 0}]
            result = {"duration_ms": 1000, "processing_ms": 25.,
                "transcript": [{"speaker_id": "speaker_1", "start_ms": 0, "end_ms": 1000, "text": "Привет!"}],
                "diagnostics": {"pipelineVariant": "refined_words_v1", "diarizationTurns": native,
                    "nativeDiarizationTurns": native, "newDiarizationInference": True,
                    "newEmbeddingInference": True, "newAsrInference": True, "asrReplay": replay,
                    "modelFiles": [], "externalEmbedding": {"sha256": runner.digest(self.embedding),
                        "catalogSha256": runner.digest(self.catalog)}}}
            if is_window:
                result["diagnostics"].update(pipelineVariant="window_words_v1", refinementStrategy="window_v1",
                    windowConfig=copy.deepcopy(config["window_config"]),
                    refiner={"algorithm": "window-overcluster-v1", "config": copy.deepcopy(config["window_config"])},
                    selectedNativePolicy={"model_id": config["model_id"], "threshold": config["native_threshold"],
                        "window_shift": config["window_shift"], "threads": config["threads"], "num_clusters": -1})
                if wrong_window:
                    result["diagnostics"]["refiner"]["config"]["tau"] = .37
            return result
        with mock.patch.object(runner.pipeline.base, "_verify_models", return_value=([], 0)), \
                mock.patch.object(runner.pipeline.base, "MANIFEST", self.lock), \
                mock.patch.object(runner.pipeline, "C2_EMBEDDING_PIN", pin), \
                mock.patch.object(runner.pipeline, "process", side_effect=controlled_process), redirect_stdout(io.StringIO()):
            return runner.run(self.args)

    def test_only_audio_and_global_automatic_configuration_enter_inference(self):
        summary = self.invoke()
        self.assertEqual(1, len(self.calls))
        audio, model_root, options = self.calls[0]
        self.assertEqual(self.audio, audio)
        self.assertEqual(self.args.model_root, model_root)
        self.assertEqual(set(runner.OPTION_FIELDS) | {"expected_speakers", "threads", "catalog_path", "embedding_root"}, set(options))
        self.assertEqual(-1, options["expected_speakers"])
        self.assertEqual(2, options["threads"])
        self.assertEqual(0, summary["all"]["wer_raw"]["errors"])
        self.assertEqual(1, summary["all"]["native_speaker_count_exact_cases"])
        folder = self.args.output / "dev-unit"
        record = json.loads((folder / "case.json").read_text())
        self.assertFalse(record["asr_replay"])
        self.assertTrue(record["new_asr_inference"])
        self.assertEqual(self.reference.read_bytes(), (folder / "reference.json").read_bytes())
        self.assertEqual(runner.evidence_hashes(folder), record["evidence_sha256"])
        self.assertTrue((self.args.output / "results.csv").is_file())

    def test_replay_payload_is_rejected_and_cannot_claim_a_complete_full_run(self):
        with self.assertRaisesRegex(ValueError, "pinned full C"):
            self.invoke(replay=True)
        meta = json.loads((self.args.output / "run.json").read_text())
        self.assertEqual("FAILED", meta["status"])
        self.assertIsNone(meta["new_model_inference"])
        self.assertFalse((self.args.output / "dev-unit/case.json").exists())

    def test_changed_reference_preserves_actual_output_but_never_scores_it(self):
        with self.assertRaisesRegex(ValueError, "Input changed during"):
            self.invoke(change_reference=True)
        folder = self.args.output / "dev-unit"
        self.assertTrue((folder / "hypothesis.json").is_file())
        self.assertTrue((folder / "diagnostics.json").is_file())
        self.assertFalse((folder / "metrics.json").exists())
        failure = json.loads((folder / "failure.json").read_text())
        self.assertTrue(failure["pipeline_returned"])
        self.assertFalse(failure["scoring_completed"])

    def test_existing_output_is_rejected_before_any_inference(self):
        self.args.output.mkdir()
        with self.assertRaisesRegex(ValueError, "fresh output"):
            self.invoke()
        self.assertEqual([], self.calls)

    def test_known_k_and_unsupported_asr_knobs_are_not_configurable(self):
        for change in [{"expected_speakers": 3}, {"threads": 1}, {"pre_roll_ms": 100}, {"punctuation_mode": "seam"}]:
            config = {**runner.DEFAULT_CONFIG, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.validate_configuration(config)

    def use_window_configuration(self):
        self.config.write_text(json.dumps(copy.deepcopy(runner.WINDOW_CONFIG)))
        catalog = json.loads(self.catalog.read_text())
        catalog["models"][0]["id"] = "eres2net_zh"
        self.catalog.write_text(json.dumps(catalog))

    def test_c2_is_explicit_actual_inference_with_full_frozen_config_and_sources(self):
        self.use_window_configuration()
        summary = self.invoke()
        self.assertEqual(0, summary["all"]["wer_raw"]["errors"])
        self.assertEqual(1, len(self.calls))
        options = self.calls[0][2]
        self.assertEqual("window_v1", options["strategy"])
        self.assertEqual(runner.pipeline.C2_WINDOW_CONFIG, options["window_config"])
        self.assertEqual(-1, options["expected_speakers"])
        self.assertNotIn("refiner_tau", options)
        meta = json.loads((self.args.output / "run.json").read_text())
        self.assertEqual("COMPLETE", meta["status"])
        self.assertEqual("window_words_v1", meta["config"]["pipeline"])
        self.assertIn("tools/eval/window_overcluster.py", meta["fingerprint"]["code"])
        record = json.loads((self.args.output / "dev-unit/case.json").read_text())
        self.assertFalse(record["asr_replay"])
        self.assertTrue(record["new_asr_inference"] and record["new_diarization_inference"])

    def test_c2_rejects_mixed_unknown_or_unfrozen_configuration(self):
        for change in ({"refiner_tau": .7}, {"missing_centroid_policy": "temporal"},
                       {"native_threshold": .5}, {"model_id": "wespeaker_resnet34_lm"},
                       {"window_config": {**runner.WINDOW_CONFIG["window_config"], "tau": .35}},
                       {"expected_speakers": 3}, {"pipeline": "unknown"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.validate_configuration({**runner.WINDOW_CONFIG, **change})
        with self.assertRaises(ValueError):
            runner.validate_configuration({**runner.DEFAULT_CONFIG, "window_config": runner.WINDOW_CONFIG["window_config"]})

    def test_c2_wrong_actual_window_policy_is_preserved_but_not_scored(self):
        self.use_window_configuration()
        with self.assertRaisesRegex(ValueError, "frozen full C2"):
            self.invoke(wrong_window=True)
        folder = self.args.output / "dev-unit"
        self.assertTrue((folder / "diagnostics.json").exists())
        self.assertFalse((folder / "metrics.json").exists())
        self.assertEqual("FAILED", json.loads((self.args.output / "run.json").read_text())["status"])


if __name__ == "__main__":
    unittest.main()
