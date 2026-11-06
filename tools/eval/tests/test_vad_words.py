from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.eval.pipeline import Span, Turn
from tools.eval.vad_words import (Word, AssignedWord, SAME_FRAME, NO_SPEAKER, TIED_SPEAKER,
    OVERLAPPING_SPEAKERS, BOUNDARY_SPEAKERS, plan_chunks, words_from_tokens, assign_words,
    group_words, seam_punctuation)
from tools.eval.pipeline_words import frame_stride_from_metadata, make_vad_config, process


class VadChunkTest(unittest.TestCase):
    def test_lowest_energy_window_uses_earliest_tie_and_center(self):
        def energy(a, b):
            return 0.0 if a in (19200, 19240) else 1.0
        self.assertEqual([Span(0, 19220), Span(19220, 25000)], plan_chunks([Span(0, 25000)], energy))

    def test_coverage_is_preserved_once_across_long_and_overlapping_spans(self):
        result = plan_chunks([Span(100, 25000), Span(24900, 45100)], lambda a, b: 0.0)
        self.assertEqual(16020, result[0].end_ms - result[0].start_ms)
        self.assertEqual(45000, sum(p.end_ms - p.start_ms for p in result))
        self.assertTrue(all(0 < p.end_ms - p.start_ms <= 20000 for p in result))
        self.assertTrue(all(a.end_ms == b.start_ms for a, b in zip(result, result[1:])))

    def test_short_spans_and_hard_split_do_not_query_energy(self):
        def unexpected(a, b):
            raise AssertionError("Energy should not be read")
        self.assertEqual([Span(50, 20050)], plan_chunks([Span(50, 20050)], unexpected))
        self.assertEqual([Span(0, 20000), Span(20000, 25000)],
                         plan_chunks([Span(0, 25000)], unexpected, energy_split=False))

    def test_invalid_energy_or_limits_fail(self):
        with self.assertRaises(ValueError):
            plan_chunks([Span(0, 25000)], lambda a, b: float("nan"))
        with self.assertRaises(ValueError):
            plan_chunks([], lambda a, b: 0, max_ms=0)


class TokenWordTest(unittest.TestCase):
    def test_actual_ascii_spaces_and_punctuation_keep_lexical_emission_bounds(self):
        result = words_from_tokens("Привет, мир!", [" При", "вет", ",", " ", "мир", "!"],
                                   [0, .04, .08, .12, .16, .2], 1000, 1400, 40)
        self.assertTrue(result.supported)
        self.assertEqual([Word(1000, 1080, "Привет,"), Word(1160, 1200, "мир!")], result.words)

    def test_sentencepiece_prefix_also_works(self):
        result = words_from_tokens("Да, нет.", ["▁Да", ",", "▁нет", "."], [0, .04, .08, .12], 0, 200, 40)
        self.assertTrue(result.supported)
        self.assertEqual(["Да,", "нет."], [w.text for w in result.words])

    def test_separate_punctuation_preserves_normalized_whitespace(self):
        tokens = ["«", " ", "Да", " ", "»", " ", "—", " ", "нет"]
        result = words_from_tokens("« Да » — нет", tokens, [i * .04 for i in range(len(tokens))], 0, 400, 40)
        self.assertTrue(result.supported)
        self.assertEqual(["« Да » —", "нет"], [w.text for w in result.words])

    def test_same_frame_words_are_not_uniformly_redistributed(self):
        result = words_from_tokens("Да нет", [" Да", " нет"], [0, 0], 0, 100, 40)
        self.assertTrue(result.supported)
        self.assertEqual([(0, 40), (0, 40)], [(w.start_ms, w.end_ms) for w in result.words])
        self.assertTrue(all(SAME_FRAME in w.reasons for w in result.words))

    def test_one_model_token_with_multiple_lexical_words_is_unsupported(self):
        result = words_from_tokens("Да нет", [" Да нет"], [0], 0, 100, 40)
        self.assertFalse(result.supported)
        self.assertEqual("multiword_token", result.reason)
        self.assertEqual([], result.words)

    def test_invalid_timing_and_roundtrip_fail_without_fabricated_words(self):
        cases = [([" Да"], [], "token_count_mismatch"),
                 ([" Да"], [float("nan")], "nonfinite_timestamp"),
                 ([" Да"], [-.04], "timestamp_out_of_range"),
                 ([" Да"], [.24], "timestamp_out_of_range"),
                 ([" Да"], [.05], "timestamp_off_grid"),
                 ([" Нет"], [0], "text_roundtrip_mismatch")]
        for tokens, times, reason in cases:
            result = words_from_tokens("Да", tokens, times, 0, 200, 40)
            self.assertFalse(result.supported)
            self.assertEqual(reason, result.reason)
            self.assertEqual([], result.words)
        backwards = words_from_tokens("Да нет", [" Да", " нет"], [.08, .04], 0, 200, 40)
        self.assertEqual("nonmonotonic_timestamps", backwards.reason)

    def test_missing_stride_and_word_at_chunk_end_are_unsupported(self):
        self.assertEqual("unverified_frame_stride", words_from_tokens("Да", [" Да"], [0], 0, 100, None).reason)
        self.assertEqual("word_outside_chunk", words_from_tokens("Да", [" Да"], [.08], 0, 80, 40).reason)

    def test_finite_float_timestamp_that_overflows_scaled_float_is_unsupported(self):
        result = words_from_tokens("Да", [" Да"], [3e38], 0, 100, 40)
        self.assertFalse(result.supported)
        self.assertEqual("nonfinite_timestamp", result.reason)
        self.assertEqual([], result.words)

    def test_blank_result_is_not_a_fake_word(self):
        result = words_from_tokens(" \n", [], [], 0, 100, 40)
        self.assertTrue(result.supported)
        self.assertEqual([], result.words)


class WordSpeakerTest(unittest.TestCase):
    def test_duplicate_same_speaker_turns_are_unioned(self):
        assigned = assign_words([Word(0, 100, "Да")], [Turn(0, 40, 0), Turn(0, 40, 0), Turn(0, 60, 1)])[0]
        self.assertEqual(1, assigned.speaker)
        self.assertIn(OVERLAPPING_SPEAKERS, assigned.reasons)

    def test_transition_and_simultaneous_overlap_get_distinct_warnings(self):
        transition = assign_words([Word(0, 100, "Да")], [Turn(0, 60, 0), Turn(60, 100, 1)])[0]
        self.assertEqual(0, transition.speaker)
        self.assertIn(BOUNDARY_SPEAKERS, transition.reasons)
        self.assertNotIn(OVERLAPPING_SPEAKERS, transition.reasons)
        overlap = assign_words([Word(20, 90, "Да")], [Turn(0, 100, 0), Turn(40, 80, 1)])[0]
        self.assertEqual(0, overlap.speaker)
        self.assertIn(OVERLAPPING_SPEAKERS, overlap.reasons)

    def test_ties_and_missing_speaker_stay_unknown(self):
        tie = assign_words([Word(0, 100, "Да")], [Turn(0, 50, 0), Turn(50, 100, 1)])[0]
        self.assertEqual(-1, tie.speaker)
        self.assertIn(TIED_SPEAKER, tie.reasons)
        missing = assign_words([Word(0, 100, "Да")], [Turn(200, 300, 0)])[0]
        self.assertEqual(-1, missing.speaker)
        self.assertIn(NO_SPEAKER, missing.reasons)

    def test_grouping_preserves_words_and_turn_changes(self):
        words = [AssignedWord(0, 40, "да", 0), AssignedWord(80, 120, "да,", 0), AssignedWord(160, 200, "нет!", 1)]
        result = group_words(words, "Real model")
        self.assertEqual(["да да,", "нет!"], [s["text"] for s in result])
        self.assertEqual([(0, 120), (160, 200)], [(s["startMs"], s["endMs"]) for s in result])
        self.assertEqual(["Да да.", "Нет!"], [s["text"] for s in group_words(words, "Real model", "seam")])

    def test_seam_does_not_rewrite_an_unsplit_single_speaker_chunk(self):
        words = [AssignedWord(0, 40, "да,", 0), AssignedWord(80, 120, "действительно", 0)]
        ordinary = group_words(words, "Real model", "none")
        optional = group_words(words, "Real model", "seam")
        self.assertEqual(ordinary, optional)
        self.assertEqual("да, действительно", optional[0]["text"])


class PunctuationAndStrideTest(unittest.TestCase):
    def test_seam_rules_preserve_existing_question_and_closing_quotes(self):
        cases = {"«да!»": "«Да!»", '"да?"': '"Да?"', "да,": "Да.", "да —": "Да .",
                 "да": "Да.", "«да»": "«Да».", "да:": "Да:", "да;": "Да;", "да…": "Да…"}
        for source, expected in cases.items():
            self.assertEqual(expected, seam_punctuation(source))

    def test_stride_is_derived_from_model_metadata_and_pinned_runtime_conversion(self):
        proof = frame_stride_from_metadata({"is_giga_am": "1", "model_type": "EncDecRNNTBPEModel", "subsampling_factor": "4"})
        self.assertEqual(40, proof["frame_stride_ms"])
        self.assertTrue(proof["verified"])
        for metadata in [{}, {"is_giga_am": "1", "model_type": "EncDecRNNTBPEModel", "subsampling_factor": "0"}]:
            with self.assertRaises(ValueError):
                frame_stride_from_metadata(metadata)


class ExperimentalVadPolicyTest(unittest.TestCase):
    def test_pre_roll_rejects_noninteger_or_unbounded_values_before_model_access(self):
        for value in [-1, 1001, 100.0, float("nan"), True, False, "100", None]:
            with self.subTest(pre_roll_ms=value), self.assertRaisesRegex(ValueError, "pre_roll_ms"):
                process("missing-audio", "missing-model-root", pre_roll_ms=value)

    def test_invalid_durations_are_rejected_before_file_or_model_access(self):
        for value in [.049, 1.01, float("nan"), float("inf"), True, ".1"]:
            for name in ["vad_min_speech_sec", "vad_min_silence_sec"]:
                with self.assertRaises(ValueError):
                    process("missing-audio", "missing-model-root", **{name: value})

    def test_experimental_durations_reach_native_silero_config_without_other_policy_changes(self):
        import sherpa_onnx
        config = make_vad_config(Path("models"), .10, .12, sherpa_onnx)
        self.assertAlmostEqual(.10, config.silero_vad.min_speech_duration, places=6)
        self.assertAlmostEqual(.12, config.silero_vad.min_silence_duration, places=6)
        self.assertEqual(.5, config.silero_vad.threshold)
        self.assertEqual(512, config.silero_vad.window_size)
        self.assertEqual(20, config.silero_vad.max_speech_duration)
        self.assertEqual(16000, config.sample_rate)
        self.assertEqual(1, config.num_threads)

    def test_global_threshold_is_validated_and_reaches_native_config(self):
        import sherpa_onnx
        for value in [.099, .901, float("nan"), float("inf"), True, ".35"]:
            with self.assertRaises(ValueError):
                process("missing-audio", "missing-model-root", vad_threshold=value)
        config = make_vad_config(Path("models"), .15, .25, sherpa_onnx, threshold=.35)
        self.assertAlmostEqual(.35, config.silero_vad.threshold, places=6)
        self.assertAlmostEqual(.15, config.silero_vad.min_speech_duration, places=6)
        self.assertEqual(.25, config.silero_vad.min_silence_duration)
        self.assertEqual(20, config.silero_vad.max_speech_duration)


if __name__ == "__main__":
    unittest.main()
