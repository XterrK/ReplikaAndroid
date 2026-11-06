"""Deterministic V1.6 policy/planner parity fixtures; no model inference here."""
import math
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.eval.pipeline import (Span, Turn, Slice, SHORT, UNKNOWN, OVERLAP, EDGE, CUT,
    alignment_slices, context_spans, plan_recognition, stable_turns,
    quiet_gain, rescue_decision, rescue_needs_rms, sample_rms, jury_projection, _verify_models,
    _read_canonical_wav)


class PlannerParityTest(unittest.TestCase):
    def test_original_public_boundary_is_repaired_without_extending_context(self):
        bounded = context_spans([Span(102, 8550)], 11290)
        self.assertEqual([Span(2, 8550)], bounded)
        self.assertEqual([Slice(2, 8550, 0, (EDGE,))], plan_recognition(bounded, [Turn(31, 8485, 0)]))

    def test_legacy_partition_warning_provenance(self):
        self.assertEqual([Slice(2, 31, -1, (UNKNOWN, SHORT)), Slice(31, 8485, 0),
                          Slice(8485, 8550, -1, (UNKNOWN, SHORT))],
                         alignment_slices([Span(2, 8550)], [Turn(31, 8485, 0)]))

    def test_real_speaker_change_and_overlap_are_not_borrowed(self):
        for turns in [[Turn(0, 1000, 0), Turn(1100, 3000, 1)],
                      [Turn(0, 1500, 0), Turn(1000, 3000, 1)]]:
            planned = plan_recognition([Span(0, 3000)], turns)
            self.assertEqual([0, -1, 1], [s.speaker for s in planned])
        overlap = plan_recognition([Span(0, 3000)], [Turn(0, 1500, 0), Turn(1000, 3000, 1)])[1]
        self.assertIn(OVERLAP, overlap.reasons)

    def test_long_unknown_is_not_assigned_and_same_speaker_gap_is(self):
        self.assertEqual([-1, 0], [s.speaker for s in plan_recognition([Span(0, 2000)], [Turn(500, 2000, 0)])])
        result = plan_recognition([Span(0, 2000)], [Turn(0, 800, 0), Turn(1000, 2000, 0)])
        self.assertEqual([Slice(0, 2000, 0, (EDGE,))], result)

    def test_four_minutes_are_covered_once_and_cuts_warn(self):
        spans = context_spans([Span(0, 100000), Span(99900, 240001)], 240000)
        result = plan_recognition(spans, [Turn(0, 240000, 0)])
        self.assertEqual(12, len(result))
        self.assertEqual(240000, sum(s.end_ms - s.start_ms for s in result))
        self.assertTrue(all(a.end_ms == b.start_ms for a, b in zip(result, result[1:])))
        self.assertTrue(all(CUT in s.reasons and s.speaker == 0 for s in result))

    def test_clamping_and_stable_speaker_ids_match_domain(self):
        self.assertEqual([Span(0, 1000)], context_spans([Span(50, 400), Span(500, 950)], 1000, 100, 100))
        self.assertEqual([], context_spans([Span(500, 600)], 100, 0, 0))
        self.assertEqual([0, 1, 0], [t.speaker for t in stable_turns([Turn(30, 40, 8), Turn(0, 10, 8), Turn(10, 30, 2)])])
        self.assertEqual(-1, stable_turns([Turn(0, 10, -1)])[0].speaker)

    def test_invalid_limits_fail(self):
        with self.assertRaises(ValueError):
            plan_recognition([], [], 0)
        with self.assertRaises(ValueError):
            alignment_slices([], [], -1)
        with self.assertRaises(ValueError):
            context_spans([], -1)


class GainParityTest(unittest.TestCase):
    def test_threshold_invalid_and_digital_silence_keep_gain_one(self):
        for peak in [0, 1e-7, float("nan"), float("inf"), -1, .01, 1]:
            self.assertEqual(1, quiet_gain(peak))
        self.assertEqual(20, quiet_gain(.004))

    def test_empty_primary_rms_retry_matches_measured_fixture(self):
        decision = rescue_decision(0, .102049887, 1, .0018098881701007485)
        self.assertTrue(decision.should_retry)
        self.assertAlmostEqual(9.309172, decision.detector_gain, delta=.0001)
        self.assertAlmostEqual(.95, decision.detector_gain * .102049887, delta=.00001)

    def test_nonempty_primary_silence_and_gain_cap_skip_rms_scan(self):
        self.assertFalse(rescue_needs_rms(1, .102, 1))
        self.assertEqual("primary_nonempty", rescue_decision(1, .102, 1, .0018).reason)
        for peak in [0, 1e-8, 1e-6]:
            self.assertFalse(rescue_needs_rms(0, peak, 1))
        self.assertFalse(rescue_needs_rms(0, .001, 20))

    def test_headroom_and_negligible_or_invalid_statistics(self):
        self.assertEqual(20, rescue_decision(0, .001, 1, .00001).detector_gain)
        self.assertAlmostEqual(.95, rescue_decision(0, .8, 1, .01).detector_gain * .8, delta=.00001)
        self.assertFalse(rescue_decision(0, .96, 1, .01).should_retry)
        self.assertFalse(rescue_decision(0, .1, 1, .02 / 1.005).should_retry)
        for rms in [None, float("nan"), float("inf"), -.1, 0, .2]:
            self.assertFalse(rescue_decision(0, .1, 1, rms).should_retry)

    def test_rms_is_sample_weighted_and_never_mutates(self):
        source = [.1, -.1, 0, 0, 0, 0, 0, 0]
        before = list(source)
        self.assertAlmostEqual(.05, sample_rms(source), delta=1e-8)
        self.assertEqual(before, source)
        self.assertIsNone(sample_rms([]))
        self.assertIsNone(sample_rms([.01, float("nan")]))


class JuryParityTest(unittest.TestCase):
    def test_unknown_assignment_precedes_first_appearance_numbering(self):
        rows = [dict(startMs=20, endMs=30, speakerId=55, text="Позже."),
                dict(startMs=0, endMs=10, speakerId=-1, text="Раньше!"),
                dict(startMs=100, endMs=110, speakerId=7, text="Ещё.")]
        result = jury_projection(rows)
        self.assertEqual(["speaker_1", "speaker_1", "speaker_2"], [r["speaker_id"] for r in result])
        self.assertEqual(-1, rows[1]["speakerId"])
        self.assertEqual({"speaker_id", "start_ms", "end_ms", "text"}, set(result[0]))

    def test_interval_distance_not_midpoint_and_unknown_fallback(self):
        rows = [dict(startMs=0, endMs=100, speakerId=8, text="Да."),
                dict(startMs=110, endMs=120, speakerId=-1, text="Нет!"),
                dict(startMs=121, endMs=100000, speakerId=4, text="Почему?")]
        self.assertEqual("speaker_2", jury_projection(rows)[1]["speaker_id"])
        self.assertEqual("speaker_1", jury_projection([dict(startMs=0, endMs=1, speakerId=-1, text="Ёж.")])[0]["speaker_id"])
        self.assertEqual([], jury_projection([dict(startMs=0, endMs=1, speakerId=0, text=" \n")]))


class ModelValidationTest(unittest.TestCase):
    def test_each_invocation_hashes_content_even_when_size_and_mtime_stay_equal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / "encoder.onnx"
            model.write_bytes(b"first")
            original_stat = model.stat()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"files": [{"group": "giga-v3", "path": "encoder.onnx",
                "size": 5, "sha256": hashlib.sha256(b"first").hexdigest()}]}))
            with patch("tools.eval.pipeline.MANIFEST", manifest):
                records, _ = _verify_models(root, False)
                self.assertFalse(records[0]["hashValidationCached"])
                model.write_bytes(b"other")
                os.utime(model, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    _verify_models(root, False)


class DecoderIntegrationTest(unittest.TestCase):
    def test_canonical_reader_uses_android_timeline_instead_of_direct_pcm16(self):
        import numpy as np
        from tools.eval.decoder_parity import scalar_android_canonical_pcm
        integers = np.random.default_rng(625).integers(-32768, 32768, 100000, dtype=np.int16)
        direct = integers.astype(np.float32) / np.float32(32768)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "canonical.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                wav.writeframes(integers.astype("<i2").tobytes())
            actual = _read_canonical_wav(path, np)
        expected = scalar_android_canonical_pcm(direct)
        np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))
        self.assertFalse(np.array_equal(actual.view(np.uint32), direct.view(np.uint32)))


if __name__ == "__main__":
    unittest.main()
