import copy
import io
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np
from tools.eval import run_natural_diar as runner


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(runner.encoded(value))


class Fixture:
    """Synthetic weights/audio in a temp tree; original metadata and gold remain unchanged."""
    def __init__(self, root):
        self.root = root
        self.metadata = root / "benchmark/eval-natural-ami"
        self.audio = root / "audio"
        self.models = root / "model-pack"
        self.external = root / "embeddings"
        self.source_metadata = runner.ROOT / "benchmark/eval-natural-ami"
        shutil.copytree(self.source_metadata, self.metadata)
        manifest = json.loads((self.metadata / "manifest.json").read_bytes())
        provenance = json.loads((self.metadata / "provenance.json").read_bytes())
        freeze = json.loads((self.metadata / "selection-freeze.json").read_bytes())
        pcm = np.arange(960000, dtype=np.int32).astype("<i2").tobytes()
        output = io.BytesIO()
        with wave.open(output, "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000); stream.writeframes(pcm)
        audio_bytes = output.getvalue()
        import hashlib
        def sha(raw):
            return hashlib.sha256(raw).hexdigest()
        for row, origin, saved in zip(manifest["files"], freeze["cases"], provenance["cases"]):
            audio_path = self.audio / row["audio"]
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(audio_bytes)
            row["audio_sha256"] = saved["canonical_crop_sha256"] = sha(audio_bytes)
            saved["pcm_crop_sha256"] = sha(pcm)
            origin["content_length"] = len(audio_bytes)
            saved["source_bytes"] = len(audio_bytes)
            saved["source_header"].update(source_bytes=len(audio_bytes), riff_bytes=len(audio_bytes),
                data_offset=44, data_bytes=len(pcm), source_frames=960000)
            responses = []
            for a, b in ((0, 11), (12, 19), (20, 35), (36, 43), (44, len(audio_bytes) - 1)):
                responses.append({"start_byte": a, "end_byte_inclusive": b, "body_bytes": b-a+1,
                    "sha256": sha(audio_bytes[a:b+1]), "status": 206, "url": origin["audio_url"],
                    "headers": {"etag": origin["etag"], "last-modified": origin["last_modified"],
                        "content-range": f"bytes {a}-{b}/{len(audio_bytes)}", "content-type": "audio/x-wav"}})
            saved["http_partial_responses"] = responses
        freeze_path = root / "artifacts/test-results/step-04/natural-probe-freeze.json"
        save(freeze_path, freeze)
        save(self.metadata / "selection-freeze.json", freeze)
        manifest["freeze_sha256"] = provenance["freeze_sha256"] = runner.digest(freeze_path)
        save(self.metadata / "manifest.json", manifest)
        provenance["manifest_sha256"] = runner.digest(self.metadata / "manifest.json")
        save(self.metadata / "provenance.json", provenance)
        audit = json.loads((self.metadata / "preparation-audit.json").read_bytes())
        audit.update(original_freeze_sha256=runner.digest(freeze_path), manifest_sha256=runner.digest(self.metadata / "manifest.json"))
        for row, case_audit in zip(manifest["files"], audit["cases"]):
            case_audit["audio_sha256"] = row["audio_sha256"]
        save(self.metadata / "preparation-audit.json", audit)
        lock = json.loads((runner.ROOT / "app/src/main/assets/models-lock.json").read_bytes())
        for spec in lock["files"]:
            path = self.models / spec["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("synthetic test model:" + spec["path"]).encode())
            spec.update(size=path.stat().st_size, sha256=runner.digest(path))
        save(root / "app/src/main/assets/models-lock.json", lock)
        catalog = json.loads((runner.ROOT / "configs/eval/diar-models.json").read_bytes())
        for entry in catalog["models"]:
            path = (root if entry["repoRelative"] else self.external) / entry["path"]
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(("synthetic test embedding:" + entry["id"]).encode())
            entry.update(size=path.stat().st_size, sha256=runner.digest(path))
        save(root / "configs/eval/diar-models.json", catalog)
        by_id = {row["id"]: row for row in catalog["models"]}
        for name, model_id, config_name in (("c1", "wespeaker_resnet34_lm", "c1-refined-selected.json"),
                ("c2", "eres2net_zh", "c2-window-selected-full.json")):
            relative = f"artifacts/test-results/step-04/candidate-{name}-validation-freeze.json"
            frozen = json.loads((runner.ROOT / relative).read_bytes())
            frozen["model"] = by_id[model_id]
            save(root / relative, frozen)
            selected = json.loads((runner.ROOT / "configs/eval" / config_name).read_bytes())
            selected["candidate_freeze_sha256"] = runner.digest(root / relative)
            save(root / "configs/eval" / config_name, selected)
        self.args = SimpleNamespace(manifest=self.metadata / "manifest.json", audio_root=self.audio,
            model_root=self.models, embedding_root=self.external, catalog=root / "configs/eval/diar-models.json",
            output=root / "output")


class FakeRuntime:
    def __init__(self, *, fail_sd=False, fail_compute=False, ready=True):
        self.np = np
        self.info = {"sherpa_version": "2.0.1", "scope": "controlled fake; no native/model calls"}
        self.events, self.accepted, self.profiles = [], [], []
        self.fail_sd, self.fail_compute, self.ready = fail_sd, fail_compute, ready

    def diarization(self, embedding, segmentation, profile):
        self.profiles.append(copy.deepcopy(profile))
        self.events.append("sd_open")
        parent = self
        class Session:
            def process(self, samples):
                parent.events.append("sd_compute")
                if parent.fail_sd:
                    raise RuntimeError("controlled SD failure")
                return [(0.0, 1.5, 9), (3.0, 4.5, 17)]
            def close(self):
                parent.events.append("sd_close")
        return Session()

    def embedding(self, model):
        self.assert_closed_before_embedding()
        self.events.append("embedding_open")
        parent = self
        dimension = 256 if "resnet34" in str(model) else 512
        class Session:
            def __init__(self):
                self.dimension = dimension
            def create_stream(self):
                parent.events.append("stream_open")
                class Stream:
                    def accept(self, samples):
                        parent.accepted.append(samples.copy())
                    def ready(self):
                        return parent.ready
                    def compute(self):
                        parent.events.append("embedding_compute")
                        if parent.fail_compute:
                            raise RuntimeError("controlled embedding failure")
                        result = np.zeros(dimension, dtype=np.float32)
                        result[0] = 1
                        return result
                    def close(self):
                        parent.events.append("stream_close")
                return Stream()
            def close(self):
                parent.events.append("embedding_close")
        return Session()

    def assert_closed_before_embedding(self):
        if not self.events or self.events[-1] != "sd_close":
            raise AssertionError("SD must close before the additional extractor opens")


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def test_complete_fixture_pins_all_models_natural_sources_and_exact_profiles(self):
        plan = runner.preflight(self.fixture.args, project_root=self.fixture.root)
        self.assertFalse(self.fixture.args.output.exists())
        self.assertEqual([profile["id"] for profile in plan["profiles"]], list(runner.PROFILE_IDS))
        self.assertEqual(len(plan["cases"]), 3)
        self.assertEqual(len(plan["catalog"]["models"]), 6)
        for profile in plan["profiles"]:
            self.assertEqual((profile["expected_speakers"], profile["threads"], profile["window_shift"]), (-1, 2, .1))
            self.assertNotIn("reference", profile)
            self.assertNotIn("reference_speaker_count", profile)
        self.assertTrue(any("EN2002a.rttm" in path for path in plan["tracked_sha256"]))
        self.assertTrue(any("run_natural_diar.py" in path for path in plan["tracked_sha256"]))
        runner.assert_unchanged(plan)

    def test_mutated_audio_reference_license_unused_model_and_main_pack_fail_before_runtime_or_output(self):
        candidates = [self.fixture.audio / "diagnostic" / (runner.CASE_IDS[0] + ".wav"),
            self.fixture.metadata / "references" / (runner.CASE_IDS[0] + ".json"),
            self.fixture.metadata / "sources/AMI-diarization-setup-LICENSE",
            self.fixture.metadata / "sources/EN2002a.rttm",
            self.fixture.external / "3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx",
            self.fixture.models / "giga-v3/tokens.txt"]
        for path in candidates:
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"tampered")
                factory = unittest.mock.Mock(side_effect=AssertionError("runtime must not open"))
                try:
                    with self.assertRaises(ValueError):
                        runner.run(self.fixture.args, project_root=self.fixture.root, runtime_factory=factory)
                    factory.assert_not_called()
                    self.assertFalse(self.fixture.args.output.exists())
                finally:
                    path.write_bytes(original)

    def test_rogue_policy_fixed_k_and_path_escape_reject(self):
        path = self.fixture.root / "configs/eval/c2-window-selected-full.json"
        original = path.read_bytes()
        for changed in ({"expected_speakers": 4}, {"native_threshold": .4}, {"window_shift": .25},
                        {"window_config": {**runner.C2_CONFIG, "tau": .37}}):
            with self.subTest(changed=changed):
                config = json.loads(original); config.update(changed); save(path, config)
                with self.assertRaises(ValueError):
                    runner.preflight(self.fixture.args, project_root=self.fixture.root)
        path.write_bytes(original)
        catalog = json.loads(self.fixture.args.catalog.read_bytes())
        catalog["models"][2]["path"] = "../escape.onnx"
        save(self.fixture.args.catalog, catalog)
        with self.assertRaises(ValueError):
            runner.preflight(self.fixture.args, project_root=self.fixture.root)
        self.assertFalse(self.fixture.args.output.exists())

    def test_inconsistent_preparation_audit_cannot_claim_valid_source_pins(self):
        path = self.fixture.metadata / "preparation-audit.json"
        audit = json.loads(path.read_bytes())
        audit["cases"][0]["audio_sha256"] = "0" * 64
        save(path, audit)
        with self.assertRaisesRegex(ValueError, "audit case pins"):
            runner.preflight(self.fixture.args, project_root=self.fixture.root)
        self.assertFalse(self.fixture.args.output.exists())

    def test_existing_output_is_never_overwritten(self):
        self.fixture.args.output.mkdir()
        sentinel = self.fixture.args.output / "sentinel"
        sentinel.write_text("old evidence")
        factory = unittest.mock.Mock()
        with self.assertRaises(FileExistsError):
            runner.run(self.fixture.args, project_root=self.fixture.root, runtime_factory=factory)
        factory.assert_not_called()
        self.assertEqual(sentinel.read_text(), "old evidence")

    def test_runtime_version_mismatch_fails_before_output_and_nn(self):
        runtime = FakeRuntime(); runtime.info["sherpa_version"] = "wrong"
        with self.assertRaises(ValueError):
            runner.run(self.fixture.args, project_root=self.fixture.root, runtime_factory=lambda: runtime)
        self.assertEqual(runtime.events, [])
        self.assertFalse(self.fixture.args.output.exists())

    def test_runtime_binary_fingerprint_mismatch_fails_before_output_and_nn(self):
        binary = self.fixture.root / "synthetic-runtime.so"
        binary.write_bytes(b"controlled fixture, never loaded")
        runtime = FakeRuntime()
        runtime.info.update(extension_file=str(binary), extension_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            runner.run(self.fixture.args, project_root=self.fixture.root, runtime_factory=lambda: runtime)
        self.assertEqual(runtime.events, [])
        self.assertFalse(self.fixture.args.output.exists())


class InferenceTests(unittest.TestCase):
    def profile(self, identifier="c2-window"):
        index = runner.PROFILE_IDS.index(identifier)
        return {"id": identifier, "model_id": "wespeaker_resnet34_lm" if index == 1 else "eres2net_zh",
            "native_threshold": .3 if index == 2 else .5,
            "algorithm": ("none", "centroid-eigengap-v1", "window-overcluster-v1")[index],
            "config": (None, runner.C1_CONFIG, runner.C2_CONFIG)[index],
            "embedding_dimension": 256 if index == 1 else 512, "embedding_sha256": "a" * 64,
            "threads": 2, "expected_speakers": -1, "window_shift": .1, "min_duration_on": .2, "min_duration_off": .5}

    def invoke(self, runtime, profile=None):
        samples = np.linspace(-.001, .002, 960000, dtype=np.float32)
        with patch.object(runner.base, "_read_canonical_wav", return_value=samples):
            actual = runner.infer_profile(Path("audio-only.wav"), Path("models"), Path("embedding.onnx"),
                self.profile() if profile is None else profile, runtime)
        return actual, samples

    def test_original_samples_exact_no_gain_pad_and_resources_close_before_pure_refiner(self):
        runtime = FakeRuntime()
        original = runner.window_overcluster.overcluster
        def pure(*args):
            self.assertEqual(runtime.events[-1], "embedding_close")
            return original(*args)
        with patch.object(runner.window_overcluster, "overcluster", side_effect=pure):
            actual, samples = self.invoke(runtime)
        self.assertTrue(actual["native_resources_released"])
        self.assertTrue(actual["refiner_accepted"])
        self.assertEqual(actual["counts"]["created_streams"], actual["counts"]["released_streams"])
        np.testing.assert_array_equal(runtime.accepted[0], samples[0:24000])
        np.testing.assert_array_equal(runtime.accepted[1], samples[48000:72000])
        self.assertEqual(actual["counts"]["new_asr_inference"], False)
        self.assertEqual(actual["counts"]["new_vad_inference"], False)
        self.assertEqual(actual["counts"]["new_lid_inference"], False)
        self.assertEqual([row["speaker_id"] for row in actual["raw_turns"]], ["native_9", "native_17"])
        self.assertEqual([row["speaker_id"] for row in actual["stable_turns"]], ["native_0", "native_1"])
        self.assertEqual(len(actual["clean_embedding_windows"][0]["embedding"]), 512)

    def test_legacy_does_not_load_extra_extractor(self):
        runtime = FakeRuntime()
        actual, _ = self.invoke(runtime, self.profile("legacy-v16"))
        self.assertEqual(runtime.events, ["sd_open", "sd_compute", "sd_close"])
        self.assertEqual(actual["counts"]["extractor_loads"], 0)
        self.assertEqual(actual["clean_embedding_windows"], [])
        self.assertIsNone(actual["refiner_accepted"])

    def test_sd_and_embedding_failures_close_resources_and_do_not_score(self):
        for runtime in (FakeRuntime(fail_sd=True), FakeRuntime(fail_compute=True), FakeRuntime(ready=False)):
            with self.subTest(runtime=runtime), self.assertRaises((RuntimeError, ValueError)):
                self.invoke(runtime)
            self.assertIn("sd_close", runtime.events)
            if "embedding_open" in runtime.events:
                self.assertEqual(runtime.events[-2:], ["stream_close", "embedding_close"])

    def test_modified_profile_or_gold_field_rejects_before_decode_or_models(self):
        for changed in ({"expected_speakers": 4}, {"native_threshold": .31},
                        {"config": {**runner.C2_CONFIG, "tau": .37}}, {"reference_count": 4}):
            profile = self.profile(); profile.update(changed)
            runtime = FakeRuntime()
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.invoke(runtime, profile)
            self.assertEqual(runtime.events, [])


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def actual(self):
        turns = [{"speaker_id": "native_opaque", "start_ms": 0, "end_ms": 60000, "text": ""}]
        return {"duration_ms": 60000, "processing_ms": 1.0, "native_resources_released": True,
            "raw_turns": turns, "stable_turns": turns, "final_turns": turns, "refiner_accepted": True,
            "counts": {"new_asr_inference": False, "new_vad_inference": False, "new_lid_inference": False},
            "stages_ms": {"mock_only": 1.0}}

    def test_all_three_profiles_gold_is_scored_only_after_inference_and_no_acceptance_claim(self):
        events, calls = [], []
        original_score = runner.score_result
        def inference(audio, model_root, embedding, profile, runtime):
            self.assertNotIn("reference", str(audio))
            self.assertEqual(profile["expected_speakers"], -1)
            self.assertNotIn("reference_speaker_count", profile)
            self.assertEqual(events.count("inference"), events.count("score"))
            events.append("inference"); calls.append((audio, model_root, embedding, copy.deepcopy(profile)))
            return self.actual()
        def score(reference, actual):
            self.assertEqual(events[-1], "inference")
            events.append("score")
            return original_score(reference, actual)
        with patch.object(runner, "score_result", side_effect=score), patch("sys.stdout", new=io.StringIO()), \
                patch("urllib.request.urlopen", side_effect=AssertionError("Offline runner must not fetch")):
            summary = runner.run(self.fixture.args, project_root=self.fixture.root,
                runtime_factory=FakeRuntime, inference=inference)
        self.assertEqual(len(calls), 9)
        self.assertEqual(summary["status"], "COMPLETE")
        self.assertIsNone(summary["acceptance_gate"])
        self.assertIsNone(summary["candidate_selection"])
        self.assertEqual(len(list(self.fixture.args.output.glob("*/*/case.json"))), 9)
        for case in self.fixture.args.output.glob("*/*/case.json"):
            record = json.loads(case.read_bytes())
            for name, expected in record["evidence_sha256"].items():
                self.assertEqual(runner.digest(case.parent / name), expected)
            self.assertIn("false_alarm_ms", record["metrics"]["final"]["der_collar_0ms"])
        report = json.loads((self.fixture.args.output / "run.json").read_bytes())
        self.assertEqual(report["reference_inputs_to_inference"], [])
        self.assertFalse(report["new_asr_inference"])
        self.assertIn("Unknown", json.loads((self.fixture.args.output / "input-manifest.json").read_bytes())["training_overlap"])

    def test_blank_text_keeps_real_overlap_silence_and_count_without_asr_metrics(self):
        reference = {"transcript": [
            {"speaker_id": "A", "start_ms": 0, "end_ms": 1000, "text": ""},
            {"speaker_id": "B", "start_ms": 500, "end_ms": 1500, "text": ""}]}
        actual = self.actual()
        actual["raw_turns"] = actual["stable_turns"] = actual["final_turns"] = [
            {"speaker_id": "hyp", "start_ms": 0, "end_ms": 1500, "text": ""}]
        metric = runner.score_result(reference, actual)
        self.assertEqual(metric["reference_speakers"], 2)
        self.assertEqual(metric["final"]["speaker_count_error"], 1)
        der = metric["final"]["der_collar_0ms"]
        self.assertEqual((der["miss_ms"], der["false_alarm_ms"], der["confusion_ms"]), (500, 0, 500))
        self.assertEqual(der["reference_speaker_ms"], 2000)
        self.assertEqual(der["evaluated_duration_ms"], 60000)
        self.assertEqual(der["reference_overlap_ms"], 500)
        self.assertNotIn("wer_raw", metric)

    def test_source_mutation_during_inference_preserves_unscored_diagnostic_and_fails(self):
        code = self.fixture.root / "synthetic-helper.py"
        code.write_text("old source")
        def inference(*_):
            code.write_text("changed source")
            return self.actual()
        with patch.object(runner, "source_paths", return_value=[code]), self.assertRaisesRegex(ValueError, "changed"):
            runner.run(self.fixture.args, project_root=self.fixture.root, runtime_factory=FakeRuntime, inference=inference)
        report = json.loads((self.fixture.args.output / "run.json").read_bytes())
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["completed_cases"], 0)
        self.assertEqual(len(list(self.fixture.args.output.glob("*/*/diagnostics.json"))), 1)
        self.assertEqual(list(self.fixture.args.output.glob("*/*/metrics.json")), [])
        self.assertFalse((self.fixture.args.output / "summary.json").exists())

    def test_inference_failure_is_fresh_failed_evidence_without_scoring(self):
        inference = unittest.mock.Mock(side_effect=RuntimeError("controlled no-NN fixture failure"))
        with self.assertRaises(RuntimeError):
            runner.run(self.fixture.args, project_root=self.fixture.root, runtime_factory=FakeRuntime, inference=inference)
        self.assertEqual(inference.call_count, 1)
        failure = json.loads(next(self.fixture.args.output.glob("*/*/failure.json")).read_bytes())
        self.assertFalse(failure["scoring_completed"])
        self.assertEqual(failure["reference_inputs_to_inference"], [])
        self.assertEqual(list(self.fixture.args.output.glob("*/*/metrics.json")), [])
        with self.assertRaises(FileExistsError):
            runner.run(self.fixture.args, project_root=self.fixture.root, runtime_factory=FakeRuntime, inference=inference)


class RuntimeMetadataTests(unittest.TestCase):
    def test_installed_runtime_metadata_imports_without_constructing_models(self):
        # Deliberately after the fifteen fixture/fake-session tests. Import real installed
        # runtime modules and inspect/hash their metadata; forbid every used model constructor.
        import sherpa_onnx as sherpa
        with patch.object(sherpa, "OfflineSpeakerDiarization", side_effect=AssertionError("No model construction")) as sd, \
                patch.object(sherpa, "SpeakerEmbeddingExtractor", side_effect=AssertionError("No model construction")) as embedding, \
                patch.object(sherpa, "OfflineRecognizer", side_effect=AssertionError("No ASR construction")) as asr, \
                patch.object(sherpa, "VoiceActivityDetector", side_effect=AssertionError("No VAD construction")) as vad:
            runtime = runner.NativeRuntime()
        for constructor in (sd, embedding, asr, vad):
            constructor.assert_not_called()
        self.assertEqual(runtime.info["sherpa_version"], "2.0.1")
        self.assertEqual(runtime.info["scipy_version"], "1.18.1")
        self.assertEqual(runtime.info["numpy_version"], "2.5.4")
        extension = Path(runtime.info["scipy_hierarchy_extension_file"])
        self.assertEqual(extension.parent.name, "hierarchy")
        self.assertTrue(extension.name.startswith("_hierarchy."))
        for key in ("extension", "scipy_hierarchy_source", "scipy_hierarchy_extension", "numpy_core_extension"):
            self.assertEqual(runner.digest(runtime.info[key + "_file"]), runtime.info[key + "_sha256"])


if __name__ == "__main__":
    unittest.main()
