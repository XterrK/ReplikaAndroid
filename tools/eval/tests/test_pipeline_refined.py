"""Controlled full-candidate contracts; every neural constructor is replaced."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.eval import pipeline_refined as pipeline


class RefinedPipelineContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.embedding = self.root / "embedding.onnx"
        self.embedding.write_bytes(b"weight-A")
        self.catalog = self.root / "catalog.json"
        self.entry = {"id": "fixture", "path": self.embedding.name, "repoRelative": False,
            "size": self.embedding.stat().st_size, "sha256": pipeline.base._sha256(self.embedding), "embedding_dimension": 2}
        self.catalog.write_text(json.dumps({"schema_version": 1, "required_runtime": "2.0.1", "models": [self.entry]}))
        self.audio = self.root / "audio.wav"
        self.audio.write_bytes(b"controlled waveform fixture; canonical reader is replaced")

    def invoke(self, *, missing_times=False, fail_asr=False, window=False):
        import numpy as np
        import sherpa_onnx
        events, asr_inputs, decoder_calls, sd_inputs, embedding_inputs, sd_configs = [], [], [], [], [], []
        source_pcm = np.full(64000, .005, dtype=np.float32)

        class FakeSD:
            def __init__(self, config):
                self.config = config
                sd_configs.append(config)
                self_count = config.clustering.num_clusters
                if self_count != -1:
                    raise AssertionError("Known K reached SD")
                events.append("sd_load")

            def process(self, samples):
                sd_inputs.append(samples.copy())
                return SimpleNamespace(sort_by_start_time=lambda: [
                    SimpleNamespace(start=0., end=2., speaker=0), SimpleNamespace(start=2., end=4., speaker=1)])

            def __del__(self):
                events.append("sd_release")

        class EmbeddingStream:
            def accept_waveform(self, rate, samples):
                if rate != 16000:
                    raise AssertionError("Unexpected resampling")
                embedding_inputs.append(samples.copy())

            def input_finished(self):
                pass

            def __del__(self):
                events.append("embedding_stream_release")

        class FakeExtractor:
            def __init__(self, config):
                if "sd_release" not in events:
                    raise AssertionError("SD model overlaps extractor lifetime")
                self.calls = 0
                events.append("embedding_load")

            def create_stream(self):
                return EmbeddingStream()

            def is_ready(self, stream):
                return True

            def compute(self, stream):
                self.calls += 1
                return [1., 0.] if self.calls == 1 else [0., 1.]

            def __del__(self):
                events.append("embedding_release")

        class AsrStream:
            def __init__(self):
                self.result = SimpleNamespace(text="Привет, мир!", tokens=[" Привет", ",", " мир", "!"],
                    timestamps=[] if missing_times else [.2, .24, 2.2, 2.24])

            def accept_waveform(self, rate, samples):
                asr_inputs.append(samples.copy())

            def __del__(self):
                events.append("asr_stream_release")

        class FakeRecognizer:
            @classmethod
            def from_transducer(cls, **config):
                if "embedding_release" not in events:
                    raise AssertionError("Extractor lifetime overlaps ASR")
                if config["num_threads"] != 2 or config["dither"] != 0 or config["decoding_method"] != "greedy_search":
                    raise AssertionError("Frozen GigaAM settings changed")
                events.append("asr_load")
                return cls()

            def create_stream(self):
                return AsrStream()

            def decode_stream(self, stream):
                decoder_calls.append(1)
                if fail_asr:
                    raise RuntimeError("controlled ASR failure")

            def __del__(self):
                events.append("asr_release")

        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(pipeline.base, "_verify_models", return_value=([], 0)))
        stack.enter_context(mock.patch.object(pipeline.base, "_read_canonical_wav", return_value=source_pcm))
        stack.enter_context(mock.patch.object(pipeline.words, "encoder_metadata", return_value={
            "is_giga_am": "1", "model_type": "EncDecRNNTBPEModel", "subsampling_factor": "4"}))
        stack.enter_context(mock.patch.object(pipeline.words, "_detect_with_durations", return_value=[pipeline.base.Span(600, 4000)]))
        stack.enter_context(mock.patch.object(sherpa_onnx, "OfflineSpeakerDiarization", FakeSD))
        stack.enter_context(mock.patch.object(sherpa_onnx, "SpeakerEmbeddingExtractor", FakeExtractor))
        stack.enter_context(mock.patch.object(sherpa_onnx, "OfflineRecognizer", FakeRecognizer))
        options = {"model_id": "fixture"}
        self.window_calls = []
        if window:
            entry = {**self.entry, "id": "eres2net_zh"}
            self.catalog.write_text(json.dumps({"schema_version": 1, "required_runtime": "2.0.1", "models": [entry]}))
            stack.enter_context(mock.patch.object(pipeline, "C2_EMBEDDING_PIN", entry))
            stack.enter_context(mock.patch.object(pipeline, "refine", side_effect=AssertionError("C1 refiner reached C2")))
            real_overcluster = pipeline.overcluster
            def trace(turns, windows, duration, config):
                if turns:
                    self.window_calls.append((turns, windows, duration, config))
                return real_overcluster(turns, windows, duration, config)
            stack.enter_context(mock.patch.object(pipeline, "overcluster", side_effect=trace))
            options = {"strategy": "window_v1", "model_id": "eres2net_zh", "native_threshold": .3,
                       "window_config": copy.deepcopy(pipeline.C2_WINDOW_CONFIG)}
        self.events = events
        self.decoder_calls = decoder_calls
        self.asr_inputs = asr_inputs
        self.embedding_inputs = embedding_inputs
        self.sd_inputs = sd_inputs
        self.source_pcm = source_pcm
        self.sd_configs = sd_configs
        return pipeline.process(self.audio, self.root, catalog_path=self.catalog,
            embedding_root=self.root, **options)

    def test_lifetimes_original_pcm_and_one_actual_decode_per_vad_chunk(self):
        import numpy as np
        actual = self.invoke()
        diagnostic = actual["diagnostics"]
        self.assertEqual([1], self.decoder_calls)
        self.assertEqual(1, diagnostic["asrForwardCalls"])
        self.assertEqual(2, diagnostic["embeddingForwardCalls"])
        self.assertEqual(2, len(diagnostic["nativeDiarizationTurns"]))
        self.assertEqual([{"startMs": 0, "endMs": 4000}], diagnostic["asrChunks"])
        self.assertEqual(["speaker_1", "speaker_2"], [row["speaker_id"] for row in actual["transcript"]])
        self.assertFalse(diagnostic["turnsUsedForAsrSlicing"])
        self.assertFalse(diagnostic["asrReplay"])
        self.assertTrue(diagnostic["newAsrInference"])
        self.assertEqual(0, diagnostic["fallbackChunks"])
        self.assertLess(self.events.index("sd_release"), self.events.index("embedding_load"))
        self.assertLess(self.events.index("embedding_release"), self.events.index("asr_load"))
        self.assertIn("asr_release", self.events)
        np.testing.assert_array_equal(self.sd_inputs[0], self.source_pcm)
        self.assertTrue(all(np.all(block == np.float32(.005)) for block in self.embedding_inputs))
        self.assertTrue(np.all(self.source_pcm == np.float32(.005)))
        np.testing.assert_array_equal(self.asr_inputs[0], self.source_pcm * np.float32(20))

    def test_unsupported_token_times_keep_actual_text_and_whole_chunk_unknown(self):
        actual = self.invoke(missing_times=True)
        diagnostic = actual["diagnostics"]
        self.assertEqual([1], self.decoder_calls)
        self.assertEqual(1, diagnostic["fallbackChunks"])
        self.assertFalse(diagnostic["wordAssignmentSupported"])
        self.assertEqual([], diagnostic["words"])
        self.assertEqual([], diagnostic["asrSlices"][0]["timestamps"])
        self.assertEqual(-1, diagnostic["segments"][0]["speakerId"])
        self.assertEqual({"speaker_id": "speaker_1", "start_ms": 0, "end_ms": 4000,
            "text": "Привет, мир!"}, actual["transcript"][0])

    def test_error_releases_models_and_streams_without_second_asr_pass(self):
        with self.assertRaisesRegex(RuntimeError, "controlled ASR failure"):
            self.invoke(fail_asr=True)
        self.assertEqual([1], self.decoder_calls)
        self.assertIn("sd_release", self.events)
        self.assertIn("embedding_release", self.events)
        self.assertIn("asr_stream_release", self.events)
        self.assertIn("asr_release", self.events)

    def test_known_k_or_policy_changes_fail_before_any_file_access(self):
        for options in [{"expected_speakers": 1}, {"expected_speakers": True}, {"threads": 1},
                        {"threads": True}, {"window_shift": .15}, {"minimum_reassignment_similarity": True}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                pipeline.process("missing", "missing", **options)

    def test_external_hash_is_rechecked_even_with_unchanged_size_and_mtime(self):
        pipeline.verify_embedding(self.catalog, self.root, "fixture")
        stat = self.embedding.stat()
        self.embedding.write_bytes(b"weight-B")
        os.utime(self.embedding, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, "SHA/size"):
            pipeline.verify_embedding(self.catalog, self.root, "fixture")

    def test_c2_uses_real_new_windows_before_one_new_asr_pass_with_identical_pcm_policy(self):
        import numpy as np
        actual = self.invoke(window=True)
        d = actual["diagnostics"]
        self.assertEqual("window_words_v1", d["pipelineVariant"])
        self.assertEqual("window_v1", d["refinementStrategy"])
        self.assertEqual("window-overcluster-v1", d["refiner"]["algorithm"])
        self.assertEqual(pipeline.C2_WINDOW_CONFIG, d["windowConfig"])
        self.assertEqual(pipeline.C2_WINDOW_CONFIG, d["refiner"]["config"])
        self.assertTrue(d["refinerAccepted"])
        self.assertEqual(1, len(self.window_calls))
        turns, windows, duration, config = self.window_calls[0]
        self.assertEqual(4000, duration)
        self.assertEqual(2, len(windows))
        self.assertEqual([1], self.decoder_calls)
        self.assertTrue(d["newDiarizationInference"] and d["newEmbeddingInference"] and d["newAsrInference"])
        self.assertFalse(d["asrReplay"] or d["turnsUsedForAsrSlicing"])
        self.assertEqual(float(np.float32(.3)), self.sd_configs[0].clustering.threshold)
        self.assertEqual(-1, self.sd_configs[0].clustering.num_clusters)
        self.assertEqual(pipeline.PAIRED_ASR_POLICY, d["pairedAsrPolicy"])
        self.assertEqual("Привет, мир!", " ".join(row["text"] for row in actual["transcript"]))
        self.assertLess(self.events.index("sd_release"), self.events.index("embedding_load"))
        self.assertLess(self.events.index("embedding_release"), self.events.index("asr_load"))
        np.testing.assert_array_equal(self.sd_inputs[0], self.source_pcm)
        np.testing.assert_array_equal(self.asr_inputs[0], self.source_pcm * np.float32(20))
        self.assertTrue(all(np.all(pcm == np.float32(.005)) for pcm in self.embedding_inputs))
        self.assertIn("tools/eval/window_overcluster.py", d["sourceFiles"])

    def test_c2_rejects_partial_mixed_or_changed_policy_before_file_access(self):
        valid = {"strategy": "window_v1", "model_id": "eres2net_zh", "native_threshold": .3,
                 "window_config": copy.deepcopy(pipeline.C2_WINDOW_CONFIG)}
        invalid = [dict(valid, strategy="unknown"), dict(valid, model_id="wespeaker_resnet34_lm"),
            dict(valid, native_threshold=.5), dict(valid, window_shift=.25),
            dict(valid, refiner_tau=.7), dict(valid, minimum_reassignment_similarity=None),
            dict(valid, missing_centroid_policy="temporal"), dict(valid, window_config=None),
            dict(valid, expected_speakers=3), dict(valid, threads=1)]
        for change in ({"tau": .37}, {"grid_ms": 125.0}, {"smooth": 1}, {"unknown": 0}):
            invalid.append(dict(valid, window_config={**valid["window_config"], **change}))
        partial = copy.deepcopy(valid["window_config"])
        partial.pop("tau")
        invalid.append(dict(valid, window_config=partial))
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(ValueError):
                pipeline.process("missing", "missing", **options)
        with self.assertRaisesRegex(ValueError, "mixed"):
            pipeline.validate_options(window_config=valid["window_config"])

    def test_c1_defaults_and_explicit_no_similarity_guard_remain_compatible(self):
        defaults = pipeline.validate_options()
        self.assertEqual((.7, .7, "temporal"), (defaults.merge_threshold,
            defaults.minimum_reassignment_similarity, defaults.small_missing_centroid_policy))
        self.assertIsNone(pipeline.validate_options(minimum_reassignment_similarity=None).minimum_reassignment_similarity)

    def test_c2_catalog_metadata_must_match_frozen_model_not_only_a_self_declared_hash(self):
        pipeline.validate_embedding_policy(copy.deepcopy(pipeline.C2_EMBEDDING_PIN), "window_v1")
        for change in ({"sha256": "f"*64}, {"embedding_dimension": 256}, {"baseline": False}, {"baseline": 1},
                       {"repoRelative": False}, {"size": 1}, {"path": "other.onnx"}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "frozen baseline"):
                pipeline.validate_embedding_policy({**pipeline.C2_EMBEDDING_PIN, **change}, "window_v1")


if __name__ == "__main__":
    unittest.main()
