"""Controlled replay/runner contracts. Native model constructors are replaced in CLI tests."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.eval import diar_sweep as sweep
from tools.eval import pipeline, score, speaker_refiner
from tools.eval import collect_diar_windows as collector


class ReplayFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.audio = self.root / "audio" / "dev.wav"
        self.audio.parent.mkdir()
        self.audio.write_bytes(b"controlled unit fixture, never decoded by a native model")
        self.reference = {"transcript": [{"speaker_id": "speaker_1", "start_ms": 0,
            "end_ms": 600, "text": "Раз. Два!"}]}
        self.manifest_case = {"id": "dev-fixture", "split": "dev", "audio": "dev.wav",
            "reference": "reference.json", "duration_ms": 1000, "audio_sha256": sweep.digest(self.audio),
            "kind": "controlled_unit_fixture"}
        sweep.write_json(self.root / "reference.json", self.reference)
        self.reference_hash = sweep.digest(self.root / "reference.json")
        self.asr_run = self.root / "asr"
        self.asr_folder = self.asr_run / self.manifest_case["id"]
        self.hypothesis = copy.deepcopy(self.reference)
        self.metric = score.score(self.reference, self.hypothesis, 1000, processing_ms=1)
        self.diagnostic = {"wordAssignmentSupported": True, "fallbackChunks": 0,
            "audioMs": 1000, "audioSha256": self.manifest_case["audio_sha256"],
            "tokenTimestampPolicy": {"verified": True, "frame_stride_ms": 40},
            "backend": "controlled replay fixture", "asrSlices": [{
                "startMs": 0, "endMs": 600, "text": "Раз. Два!",
                "tokens": [" Раз", ".", " Два", "!"], "timestamps": [.08, .12, .32, .36],
                "wordAssignmentSupported": True, "timestampUnit": "seconds within ASR VAD chunk",
                # Stale IDs/reasons must never be used for new C speaker assignment.
                "words": [{"speakerId": 999, "warnings": ["stale speaker assignment"]}]}]}
        self.record = {"id": self.manifest_case["id"], "duration_ms": 1000,
            "audio_sha256": self.manifest_case["audio_sha256"], "reference_sha256": self.reference_hash,
            "metrics": self.metric, "new_model_inference": False}
        self.save_source()
        sweep.write_json(self.asr_run / "run.json", {"status": "COMPLETE",
            "config": {"pipeline": "vad_words_v1", "punctuation_mode": "none"},
            "fingerprint": {"references": {self.manifest_case["id"]: self.reference_hash}}})
        self.manifest = self.root / "manifest.json"
        self.save_manifest()
        self.embedding_root = self.root / "embeddings"
        self.embedding_root.mkdir()
        embedding = self.embedding_root / "fixture.bin"
        embedding.write_bytes(b"not a model; native constructor is replaced")
        self.catalog = self.root / "catalog.json"
        sweep.write_json(self.catalog, {"models": [{"id": "fixture", "path": embedding.name,
            "repoRelative": False, "size": embedding.stat().st_size, "sha256": sweep.digest(embedding)}]})
        self.model_root = self.root / "models"
        segmentation = self.model_root / "diar" / "segmentation.onnx"
        segmentation.parent.mkdir(parents=True)
        segmentation.write_bytes(b"not a segmentation model")
        sweep.write_json(self.root / "app/src/main/assets/models-lock.json", {"files": [{
            "path": "diar/segmentation.onnx", "size": segmentation.stat().st_size,
            "sha256": sweep.digest(segmentation)}]})

    def save_source(self):
        sweep.write_json(self.asr_folder / "reference.json", self.reference)
        sweep.write_json(self.asr_folder / "hypothesis.json", self.hypothesis)
        sweep.write_json(self.asr_folder / "metrics.json", self.metric)
        sweep.write_json(self.asr_folder / "diagnostics.json", self.diagnostic)
        self.record["evidence_sha256"] = sweep.evidence_hashes(self.asr_folder)
        sweep.write_json(self.asr_folder / "case.json", self.record)

    def save_manifest(self):
        # Actual corpus manifests pin references in ASR run metadata, not a per-case field.
        sweep.write_json(self.manifest, {"schema_version": 1, "files": [self.manifest_case]})

    def load(self):
        return sweep.load_asr(self.asr_folder, self.manifest_case, self.reference_hash)

    def run_cli(self, output, mode="auto", resume=False, threshold="0.50"):
        import numpy as np
        import sherpa_onnx
        calls = []

        class NoNativeDiarizer:
            def __init__(self, config):
                self.config = config

            def set_config(self, config):
                self.config = config

            def process(self, samples):
                calls.append({"num_clusters": self.config.clustering.num_clusters,
                    "threshold": self.config.clustering.threshold, "sample_count": len(samples)})
                return SimpleNamespace(sort_by_start_time=lambda: [
                    SimpleNamespace(start=0., end=1., speaker=0)])

        argv = ["diar_sweep.py", "--manifest", str(self.manifest), "--audio-root", str(self.audio.parent),
            "--asr-run", str(self.asr_run), "--catalog", str(self.catalog),
            "--embedding-root", str(self.embedding_root), "--model-root", str(self.model_root),
            "--model-id", "fixture", "--mode", mode, "--thresholds", threshold, "--output", str(output)]
        if resume:
            argv.append("--resume")
        with mock.patch.object(sys, "argv", argv), mock.patch.object(sweep, "REPO", self.root), \
                mock.patch.object(sherpa_onnx, "OfflineSpeakerDiarization", NoNativeDiarizer), \
                mock.patch.object(sweep.base, "_read_canonical_wav", return_value=np.zeros(16000, dtype=np.float32)), \
                redirect_stdout(io.StringIO()):
            sweep.main()
        return calls


class ReplayContractTest(ReplayFixture):
    def test_real_token_clock_is_replayed_and_new_turns_replace_old_speaker_ids(self):
        chunks, record, source = self.load()
        self.assertEqual([(80, 120), (320, 360)], [(word.start_ms, word.end_ms) for word in chunks[0]])
        projected = sweep.project_asr(chunks, [pipeline.Turn(0, 200, 7), pipeline.Turn(200, 1000, 8)], source)
        self.assertEqual(["speaker_1", "speaker_2"], [row["speaker_id"] for row in projected["transcript"]])
        self.assertEqual("Раз. Два!", " ".join(row["text"] for row in projected["transcript"]))
        self.assertEqual(record["metrics"]["wer_raw"], score.score(self.reference, projected, 1000)["wer_raw"])

    def test_changed_saved_file_hash_is_rejected(self):
        with (self.asr_folder / "hypothesis.json").open("a") as stream:
            stream.write(" ")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            self.load()

    def test_embedded_metrics_cannot_override_the_hashed_metric_file(self):
        self.record["metrics"] = {"wer_raw": {"errors": 99}}
        self.save_source()
        with self.assertRaisesRegex(ValueError, "embedded metrics"):
            self.load()

    def test_bad_clock_metadata_and_truthy_flags_fail_with_coherent_file_hashes(self):
        original = copy.deepcopy(self.diagnostic)
        bad = [dict(wordAssignmentSupported="true"), dict(fallbackChunks=False), dict(fallbackChunks=None),
            dict(tokenTimestampPolicy={"verified": False, "frame_stride_ms": 40}),
            dict(tokenTimestampPolicy={"verified": True, "frame_stride_ms": 80}),
            dict(audioMs=999), dict(audioSha256="0" * 64)]
        for changed in bad:
            with self.subTest(changed=changed):
                self.diagnostic = {**original, **changed}
                self.save_source()
                with self.assertRaises(ValueError):
                    self.load()

    def test_case_identity_and_duration_are_part_of_replay_contract(self):
        for field, value in [("id", "other-case"), ("duration_ms", 999)]:
            with self.subTest(field=field):
                self.record[field] = value
                self.save_source()
                with self.assertRaisesRegex(ValueError, "inputs differ"):
                    self.load()
                self.record[field] = self.manifest_case[field]


class RunnerContractTest(ReplayFixture):
    def test_auto_runs_without_any_manifest_expected_speaker_count(self):
        self.assertNotIn("expected_speakers", self.manifest_case)
        output = self.root / "auto-output"
        calls = self.run_cli(output)
        self.assertEqual([-1], [call["num_clusters"] for call in calls])
        saved = json.loads((output / "auto-0p50/dev-fixture/case.json").read_text())
        self.assertTrue(saved["new_diarization_inference"])
        self.assertFalse(saved["new_asr_inference"])
        self.assertEqual(0, saved["metrics"]["wer_raw"]["errors"])
        self.assertIsNone(saved["metrics"]["rtf"])

    def test_fixed_k_one_exercises_diarizer_and_stays_an_oracle_diagnostic(self):
        self.manifest_case["expected_speakers"] = 1
        self.save_manifest()
        output = self.root / "fixed-output"
        calls = self.run_cli(output, mode="fixed")
        self.assertEqual([1], [call["num_clusters"] for call in calls])
        diagnostic = json.loads((output / "fixed/dev-fixture/diagnostics.json").read_text())
        self.assertIn("oracle", diagnostic["fixedCountSource"])
        self.assertFalse(diagnostic["singleBypass"])
        record = json.loads((output / "fixed/dev-fixture/case.json").read_text())
        self.assertTrue(record["new_diarization_inference"])

    def test_full_cache_resume_rebuilds_missing_csv_without_model_call(self):
        output = self.root / "resume-output"
        self.run_cli(output)
        original = (output / "results.csv").read_bytes()
        (output / "results.csv").unlink()
        self.assertEqual([], self.run_cli(output, resume=True))
        self.assertEqual(original, (output / "results.csv").read_bytes())

    def test_bad_audio_hash_fails_before_native_constructor_or_process(self):
        self.audio.write_bytes(b"changed controlled input")
        with self.assertRaisesRegex(ValueError, "Audio pin"):
            self.run_cli(self.root / "invalid-audio-output")

    def test_bad_embedding_hash_fails_before_native_constructor_or_process(self):
        (self.embedding_root / "fixture.bin").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Embedding model pin"):
            self.run_cli(self.root / "invalid-model-output")


class ConfigurationContractTest(unittest.TestCase):
    def test_threshold_grid_cannot_alias_rounded_output_profiles(self):
        expected = [value / 100 for value in range(30, 100, 5)]
        self.assertEqual(expected, sweep.thresholds(",".join(map(str, expected))))
        for invalid in ["0.501,0.504", "0.5,0.50", "nan", "inf", "0.049", "1.0"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                sweep.thresholds(invalid)

    def test_native_config_retains_current_segmentation_policy_and_requested_k(self):
        import sherpa_onnx
        config = sweep.make_config(Path("embed.onnx"), Path("seg.onnx"), 3, .65, .1, 2, sherpa_onnx)
        self.assertEqual(3, config.clustering.num_clusters)
        self.assertAlmostEqual(.65, config.clustering.threshold, places=6)
        self.assertAlmostEqual(.2, config.min_duration_on, places=6)
        self.assertEqual(.5, config.min_duration_off)
        self.assertAlmostEqual(.1, config.segmentation.pyannote.window_shift_ratio, places=6)
        self.assertEqual(2, config.segmentation.num_threads)
        self.assertEqual(2, config.embedding.num_threads)

    def test_direct_script_import_uses_same_turn_type_as_refiner(self):
        namespace = runpy.run_path(str(Path(sweep.__file__)))
        self.assertIs(namespace["base"].Turn, pipeline.Turn)
        self.assertIs(speaker_refiner.Turn, pipeline.Turn)


class WindowEmbeddingContractTest(unittest.TestCase):
    def test_invalid_vectors_fail_before_any_nonfinite_evidence_is_saved(self):
        import numpy as np
        window = SimpleNamespace(start_ms=0, end_ms=1500, speaker=0)
        stream = SimpleNamespace(accept_waveform=lambda *args: None, input_finished=lambda: None)
        for vector in [[], [0., 0.], [float("nan"), 1.], [float("inf"), 1.]]:
            extractor = SimpleNamespace(create_stream=lambda: stream, is_ready=lambda _: True,
                compute=lambda _, value=vector: value)
            sherpa = SimpleNamespace(SpeakerEmbeddingExtractorConfig=lambda **kwargs: kwargs,
                SpeakerEmbeddingExtractor=lambda _: extractor)
            with self.subTest(vector=vector), mock.patch.object(speaker_refiner, "clean_windows", return_value=[window]):
                with self.assertRaisesRegex(ValueError, "invalid clean-window vector"):
                    sweep.extract_windows(np.zeros(24000, dtype=np.float32), [], Path("fixture"), 2, sherpa)


class CollectorContractTest(ReplayFixture):
    def prepare_source_d(self):
        from sherpa_onnx.lib import _sherpa_onnx as native
        lock_path = self.root / "app/src/main/assets/models-lock.json"
        lock = json.loads(lock_path.read_text())
        embedding = self.embedding_root / "fixture.bin"
        target = self.model_root / "diar/embedding.onnx"
        target.write_bytes(embedding.read_bytes())
        lock["files"].append({"path": "diar/embedding.onnx", "size": target.stat().st_size,
                              "sha256": sweep.digest(target)})
        sweep.write_json(lock_path, lock)
        chunks, _, source = self.load()
        turns = [pipeline.Turn(0, 1000, 0)]
        self.hypothesis = sweep.project_asr(chunks, turns, source)
        self.metric = score.score(self.reference, self.hypothesis, 1000, processing_ms=1)
        raw = [{"speaker_id": "native_0", "start_ms": 0, "end_ms": 1000, "text": ""}]
        for collar in [0, 250]:
            self.metric["native_der_collar_" + str(collar) + "ms"] = score.der(
                self.reference["transcript"], raw, 1000, collar_ms=collar)
        self.record["metrics"] = self.metric
        self.diagnostic.update(clusteringMode="automatic", expectedSpeakers=-1,
            runtime="sherpa-onnx " + pipeline.RUNTIME_VERSION, onnxruntimeVersion=native.onnxruntime_version,
            config={"clusterThreshold": .5, "segmentationWindowShiftRatio": .1,
                    "diarMinDurationOnSec": .2, "diarMinDurationOffSec": .5},
            modelFiles=[{"path": spec["path"], "bytes": spec["size"], "sha256": spec["sha256"]} for spec in lock["files"]],
            rawDiarizationTurns=pipeline._turn_json(turns), diarizationTurns=pipeline._turn_json(turns))
        self.save_source()
        fingerprint = {"models": {spec["path"]: spec["sha256"] for spec in lock["files"]},
            "runtime": pipeline.RUNTIME_VERSION, "references": {self.manifest_case["id"]: self.reference_hash},
            "model_lock_sha256": sweep.digest(lock_path), "baseline_helpers_sha256": sweep.digest(pipeline.__file__),
            "decoder_code_sha256": sweep.digest(Path(pipeline.__file__).with_name("decoder_parity.py")),
            "scorer_code_sha256": sweep.digest(score.__file__),
            "word_planner_code_sha256": sweep.digest(Path(pipeline.__file__).with_name("vad_words.py"))}
        meta = {"status": "COMPLETE", "config": {"pipeline": "vad_words_v1", "punctuation_mode": "none",
            "expected_speakers": -1}, "fingerprint": fingerprint}
        sweep.write_json(self.asr_run / "run.json", meta)
        return meta, lock["files"]

    def test_derived_metrics_clear_historical_rtf_without_mutating_source(self):
        derived = collector.derived_metrics(self.metric)
        self.assertIsNone(derived["rtf"])
        self.assertIsNone(derived["inputs"]["processing_ms"])
        self.assertEqual(1, self.metric["inputs"]["processing_ms"])
        self.assertEqual(self.metric["wer_raw"], derived["wer_raw"])

    def test_fixed_or_changed_model_sources_are_rejected_before_embedding_stage(self):
        meta, specs = self.prepare_source_d()
        collector.source_run_policy(meta, specs)
        for altered in [dict(expected_speakers=1), dict(pipeline="v16")]:
            bad = copy.deepcopy(meta)
            bad["config"].update(altered)
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                collector.source_run_policy(bad, specs)
        bad = copy.deepcopy(meta)
        bad["fingerprint"]["models"]["diar/embedding.onnx"] = "0" * 64
        with self.assertRaises(ValueError):
            collector.source_run_policy(bad, specs)

    def test_collector_marks_only_embedding_stage_new_and_preserves_original_metrics(self):
        import numpy as np
        self.prepare_source_d()
        output = self.root / "collection-output"
        original_metrics = (self.asr_folder / "metrics.json").read_bytes()
        controlled_windows = [{"start_ms": 0, "end_ms": 1000, "speaker": 0,
            "clean": True, "embedding": [1., 0.]}]
        argv = ["--asr-run", str(self.asr_run), "--manifest", str(self.manifest),
            "--audio-root", str(self.audio.parent), "--model-root", str(self.model_root), "--output", str(output)]
        with mock.patch.object(sweep, "REPO", self.root), \
                mock.patch.object(sweep, "extract_windows", return_value=controlled_windows) as extract, \
                mock.patch.object(pipeline, "_read_canonical_wav", return_value=np.zeros(16000, dtype=np.float32)), \
                redirect_stdout(io.StringIO()):
            collector.main(argv)
        self.assertEqual(1, extract.call_count)
        folder = output / "auto-0p50/dev-fixture"
        record = json.loads((folder / "case.json").read_text())
        self.assertFalse(record["new_diarization_inference"])
        self.assertFalse(record["new_asr_inference"])
        self.assertTrue(record["new_embedding_inference"])
        self.assertIsNone(record["processing_ms"])
        self.assertIsNone(record["metrics"]["rtf"])
        self.assertEqual(0, record["diarization_inference_ms"])
        self.assertEqual(original_metrics, (folder / "source-metrics.json").read_bytes())
        self.assertEqual((self.asr_folder / "hypothesis.json").read_bytes(), (folder / "hypothesis.json").read_bytes())
        self.assertEqual(sweep.evidence_hashes(folder), record["evidence_sha256"])


if __name__ == "__main__":
    unittest.main()
