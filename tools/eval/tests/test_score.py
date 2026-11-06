"""Independent, hand-computable contracts for evaluation metrics; no model calls."""
from __future__ import annotations

import contextlib
import io
import itertools
import json
from pathlib import Path
import random
import tempfile
import types
import unittest
from unittest import mock

from tools.eval import score as scorer


def row(start=0, end=1000, speaker="speaker_1", text="Добрый день!"):
    return {"speaker_id": speaker, "start_ms": start, "end_ms": end, "text": text}


def document(*rows):
    return {"transcript": list(rows)}


class WordMetricsTest(unittest.TestCase):
    def test_exact_primary_keeps_case_punctuation_yo_and_numbers(self):
        result = scorer.score(document(row(text="Добрый день! Ёж 25")),
                              document(row(text="добрый день Еж двадцать пять")), 1000)
        self.assertEqual(4, result["wer_raw"]["reference_tokens"])
        self.assertGreater(result["wer_raw"]["rate"], 0)
        normalized = scorer.score(document(row(text="Добрый день! Ёж")),
                                  document(row(text="добрый день еж")), 1000)
        self.assertEqual(1.0, normalized["wer_raw"]["rate"])
        self.assertEqual(0.0, normalized["wer_normalized"]["rate"])

    def test_sdi_counts_and_denominator_are_known(self):
        result = scorer.score(document(row(text="a b c d e f")),
                              document(row(text="a x c e f extra")), 1000)["wer_raw"]
        self.assertEqual((1, 1, 1), (result["substitutions"], result["deletions"], result["insertions"]))
        self.assertEqual(3, result["errors"])
        self.assertEqual(6, result["reference_tokens"])
        self.assertEqual(.5, result["rate"])

    def test_punctuation_as_tokens_retains_case(self):
        result = scorer.score(document(row(text="Добрый день!")), document(row(text="добрый день")), 1000)
        separated = result["wer_punctuation_tokens"]
        self.assertEqual((1, 1, 0), (separated["substitutions"], separated["deletions"], separated["insertions"]))
        self.assertEqual(3, separated["reference_tokens"])
        self.assertAlmostEqual(2 / 3, separated["rate"])

    def test_normalized_cer_is_not_wer(self):
        result = scorer.score(document(row(text="Кот!")), document(row(text="код")), 1000)
        self.assertEqual(1.0, result["wer_normalized"]["rate"])
        self.assertAlmostEqual(1 / 3, result["cer_normalized"]["rate"])

    def test_whitespace_split_is_the_only_primary_normalization(self):
        result = scorer.score(document(row(text="  Ёж!\n25\t🐈  ")), document(row(text="Ёж! 25 🐈")), 1000)
        self.assertEqual(0.0, result["wer_raw"]["rate"])
        self.assertEqual(3, result["wer_raw"]["reference_tokens"])

    def test_empty_reference_never_reports_zero_wer(self):
        result = scorer.score(document(), document(row(text="one two")), 1000)
        self.assertIsNone(result["wer_raw"]["rate"])
        self.assertEqual(2, result["wer_raw"]["insertions"])
        self.assertEqual(0, result["wer_raw"]["reference_tokens"])
        both_empty = scorer.score(document(), document(), 1000)
        self.assertIsNone(both_empty["wer_raw"]["rate"])
        self.assertIsNone(both_empty["cer_normalized"]["rate"])
        self.assertIsNone(both_empty["cpwer_raw"]["rate"])

    def test_empty_hypothesis_reports_all_deletions(self):
        result = scorer.score(document(row(text="one two three")), document(), 1000)["wer_raw"]
        self.assertEqual(3, result["deletions"])
        self.assertEqual(1.0, result["rate"])

    def test_wer_can_exceed_one_and_is_not_clamped(self):
        result = scorer.score(document(row(text="a")), document(row(text="b c d e")), 1000)
        self.assertEqual(4.0, result["wer_raw"]["rate"])

    def test_chronological_order_is_used_even_if_input_is_unsorted(self):
        result = scorer.score(document(row(500, 1000, text="two"), row(0, 500, text="one")),
                              document(row(0, 1000, text="one two")), 1000)
        self.assertEqual(0.0, result["wer_raw"]["rate"])

    def test_optional_number_dependency_missing_is_explicit(self):
        with mock.patch.object(scorer.importlib, "import_module", side_effect=ImportError):
            result = scorer.score(document(row(text="25")), document(row(text="двадцать пять")), 1000)
        self.assertFalse(result["wer_number_normalized"]["available"])
        self.assertIsNone(result["wer_number_normalized"]["rate"])
        self.assertGreater(result["wer_raw"]["rate"], 0)

    def test_optional_number_expansion_is_separate_from_primary(self):
        fake = types.SimpleNamespace(num2words=lambda number, lang: {25: "двадцать пять"}[number])
        with mock.patch.object(scorer.importlib, "import_module", return_value=fake):
            result = scorer.score(document(row(text="25")), document(row(text="двадцать пять")), 1000)
        self.assertEqual(0.0, result["wer_number_normalized"]["rate"])
        self.assertEqual("ru", result["wer_number_normalized"]["language"])
        self.assertEqual(1, result["wer_number_normalized"]["reference_integer_tokens_converted"])
        self.assertEqual(0, result["wer_number_normalized"]["hypothesis_integer_tokens_converted"])
        self.assertGreater(result["wer_raw"]["rate"], 0)

    def test_backtrace_distance_and_edit_count_invariants(self):
        randomizer = random.Random(104)
        for _ in range(80):
            reference = randomizer.choices("abc", k=randomizer.randrange(10))
            hypothesis = randomizer.choices("abc", k=randomizer.randrange(10))
            metric, _ = scorer._edit(reference, hypothesis)
            self.assertEqual(scorer._distance(reference, hypothesis), metric["errors"])
            self.assertEqual(len(reference), metric["correct"] + metric["substitutions"] + metric["deletions"])
            self.assertEqual(len(hypothesis), metric["correct"] + metric["substitutions"] + metric["insertions"])


class PunctuationAndCaseTest(unittest.TestCase):
    def test_punctuation_is_anchored_not_a_bag_of_marks(self):
        result = scorer.score(document(row(text="Да, кот!")), document(row(text="Нет, кот!")), 1000)
        metric = result["punctuation"]
        self.assertEqual((1, 1, 1), (metric["true_positive"], metric["false_positive"], metric["false_negative"]))
        self.assertEqual(.5, metric["f1"])
        self.assertEqual(1.0, metric["by_mark"]["!"]["f1"])
        self.assertEqual(0.0, metric["by_mark"][","]["f1"])

    def test_missing_comma_and_preserved_exclamation(self):
        metric = scorer.score(document(row(text="Да, кот!")), document(row(text="Да кот!")), 1000)["punctuation"]
        self.assertEqual(1.0, metric["precision"])
        self.assertEqual(.5, metric["recall"])
        self.assertAlmostEqual(2 / 3, metric["f1"])

    def test_repeated_words_and_leading_marks(self):
        result = scorer.score(document(row(text="— Да, да.")), document(row(text="— Да да.")), 1000)
        self.assertEqual(2, result["punctuation"]["true_positive"])
        self.assertEqual(1, result["punctuation"]["false_negative"])

    def test_no_punctuation_is_not_artificial_perfect_f1(self):
        metric = scorer.score(document(row(text="Добрый день")), document(row(text="Добрый день")), 1000)["punctuation"]
        self.assertIsNone(metric["precision"])
        self.assertIsNone(metric["recall"])
        self.assertIsNone(metric["f1"])

    def test_initial_case_includes_missing_initials_in_main_denominator(self):
        reference = document(row(0, 400, text="Да."), row(600, 1000, text="Кот."))
        result = scorer.score(reference, document(row(600, 1000, text="Кот.")), 1000)["initial_case"]
        self.assertEqual(.5, result["accuracy"])
        self.assertEqual(1.0, result["conditional_accuracy"])
        self.assertEqual(2, result["reference_initials"])
        self.assertEqual(1, result["unmatched_reference_initials"])

    def test_initial_case_ignores_numeric_prefix_but_not_cased_letter(self):
        metric = scorer.score(document(row(text="25 Котов")), document(row(text="25 котов")), 1000)["initial_case"]
        self.assertEqual(1, metric["reference_initials"])
        self.assertEqual(0.0, metric["accuracy"])


class DiarizationTest(unittest.TestCase):
    def test_optimal_permutation_and_overlap(self):
        reference = [row(0, 1000, "A", ""), row(500, 1500, "B", "")]
        hypothesis = [row(0, 1000, "Y", ""), row(500, 1500, "X", "")]
        result = scorer.der(reference, hypothesis, 1500)
        self.assertEqual(0.0, result["rate"])
        self.assertEqual(2000, result["reference_speaker_ms"])
        self.assertEqual(500, result["reference_overlap_ms"])
        self.assertEqual({"Y": "A", "X": "B"}, result["mapping_hypothesis_to_reference"])

    def test_miss_false_alarm_and_global_permutation(self):
        result = scorer.der([row(0, 1000, "A", "")], [row(500, 1500, "X", "")], 1500)
        self.assertEqual(500, result["miss_ms"])
        self.assertEqual(500, result["false_alarm_ms"])
        self.assertEqual(0, result["confusion_ms"])
        self.assertEqual(1.0, result["rate"])

    def test_confusion_after_collapsing_two_speakers(self):
        result = scorer.der([row(0, 1000, "A", ""), row(1000, 2000, "B", "")],
                            [row(0, 2000, "X", "")], 2000)
        self.assertEqual(.5, result["rate"])
        self.assertEqual(1000, result["confusion_ms"])
        self.assertEqual(0, result["miss_ms"])

    def test_overlap_missing_second_voice_counts_speaker_time(self):
        result = scorer.der([row(0, 1000, "A", ""), row(500, 1500, "B", "")],
                            [row(0, 1500, "X", "")], 1500)
        self.assertEqual(500, result["miss_ms"])
        self.assertEqual(500, result["confusion_ms"])
        self.assertEqual(.5, result["rate"])

    def test_extra_overlapping_speaker_is_false_alarm(self):
        result = scorer.der([row(0, 1000, "A", "")],
                            [row(0, 1000, "X", ""), row(0, 1000, "Y", "")], 1000)
        self.assertEqual(1000, result["false_alarm_ms"])
        self.assertEqual(1.0, result["rate"])

    def test_same_speaker_overlapping_rows_are_a_union(self):
        result = scorer.der([row(0, 1000, "A", ""), row(500, 1500, "A", "")],
                            [row(0, 1500, "X", "")], 1500)
        self.assertEqual(1500, result["reference_speaker_ms"])
        self.assertEqual(0, result["reference_overlap_ms"])
        self.assertEqual(0.0, result["rate"])

    def test_collar_is_total_width_not_half_width(self):
        reference, hypothesis = [row(0, 1000, "A", "")], [row(100, 1100, "X", "")]
        raw = scorer.der(reference, hypothesis, 1200)
        result = scorer.der(reference, hypothesis, 1200, collar_ms=250)
        self.assertEqual(.2, raw["rate"])
        self.assertEqual(125, result["collar_half_width_ms"])
        self.assertEqual(375, result["excluded_duration_ms"])
        self.assertEqual(750, result["reference_speaker_ms"])
        self.assertEqual(0.0, result["rate"])
        beyond = scorer.der(reference, [row(150, 1150, "X", "")], 1200, collar_ms=250)
        self.assertEqual(25, beyond["miss_ms"])
        self.assertEqual(25, beyond["false_alarm_ms"])

    def test_collar_can_remove_all_reference_and_then_der_is_undefined(self):
        result = scorer.der([row(100, 200, "A", "")], [row(100, 200, "X", "")], 500, collar_ms=250)
        self.assertEqual(0, result["reference_speaker_ms"])
        self.assertIsNone(result["rate"])

    def test_blank_text_rows_are_retained_for_der_and_speaker_count(self):
        result = scorer.score(document(row(text="")), document(row(speaker="other", text="")), 1000)
        self.assertIsNone(result["wer_raw"]["rate"])
        self.assertEqual(0.0, result["der_collar_0ms"]["rate"])
        self.assertEqual({"reference": 1, "hypothesis": 1, "signed_error": 0, "absolute_error": 0}, result["speakers"])

    def test_no_reference_speech_is_not_false_zero_der(self):
        result = scorer.der([], [row(text="")], 1000)
        self.assertIsNone(result["rate"])
        self.assertEqual(1000, result["false_alarm_ms"])


class SpeakerTextAndTimingTest(unittest.TestCase):
    def test_cpwer_permutation_ignores_id_names(self):
        ref = document(row(0, 500, "A", "hello"), row(500, 1000, "B", "world"))
        hyp = document(row(0, 500, "Y", "hello"), row(500, 1000, "X", "world"))
        result = scorer.score(ref, hyp, 1000)
        self.assertEqual(0.0, result["cpwer_raw"]["rate"])
        self.assertEqual(2, len(result["cpwer_raw"]["speaker_pairs"]))

    def test_cpwer_extra_speaker_is_insertion(self):
        result = scorer.score(document(row(0, 500, "A", "hello")),
                              document(row(0, 500, "X", "hello"), row(500, 1000, "Y", "noise")), 1000)
        self.assertEqual(1, result["cpwer_raw"]["insertions"])
        self.assertEqual(1.0, result["cpwer_raw"]["rate"])
        self.assertEqual(1, result["speakers"]["absolute_error"])

    def test_cpwer_missing_speaker_is_deletion(self):
        result = scorer.score(document(row(0, 500, "A", "hello"), row(500, 1000, "B", "world")),
                              document(row(0, 500, "X", "hello")), 1000)
        self.assertEqual(1, result["cpwer_raw"]["deletions"])
        self.assertEqual(.5, result["cpwer_raw"]["rate"])
        self.assertEqual(-1, result["speakers"]["signed_error"])

    def test_cpwer_penalizes_merging_distinct_speakers(self):
        result = scorer.score(document(row(0, 500, "A", "hello"), row(500, 1000, "B", "world")),
                              document(row(0, 1000, "X", "hello world")), 1000)
        self.assertEqual(0.0, result["wer_raw"]["rate"])
        self.assertEqual(2, result["cpwer_raw"]["errors"])
        self.assertEqual(1.0, result["cpwer_raw"]["rate"])

    def test_timing_reports_coverage_and_mean_absolute_errors(self):
        result = scorer.score(document(row(0, 1000)), document(row(100, 1100)), 1200, processing_ms=600)
        metric = result["timing"]
        self.assertEqual(1, metric["matched_pairs"])
        self.assertEqual(100, metric["mean_start_abs_error_ms"])
        self.assertEqual(100, metric["mean_end_abs_error_ms"])
        self.assertEqual(1.0, metric["reference_coverage"])
        self.assertEqual(0.0, metric["fraction_over_250ms"])
        self.assertEqual(.5, result["rtf"])

    def test_nonintersecting_rows_are_not_forced_into_timing_pairs(self):
        result = scorer.score(document(row(0, 1000)), document(row(2000, 3000)), 3000)["timing"]
        self.assertEqual(0, result["matched_pairs"])
        self.assertEqual(0.0, result["reference_coverage"])
        self.assertIsNone(result["mean_start_abs_error_ms"])
        self.assertEqual(1.0, result["reference_fraction_over_250ms_or_unmatched"])

    def test_timing_uses_global_assignment_not_greedy_matching(self):
        result = scorer.score(document(row(0, 100, text="a"), row(50, 150, text="b")),
                              document(row(0, 150, text="a"), row(0, 50, text="b")), 150)["timing"]
        self.assertEqual(2, result["matched_pairs"])
        self.assertAlmostEqual(7 / 6, sum(pair["iou"] for pair in result["pairs"]))

    def test_hungarian_matches_bruteforce_on_small_matrices(self):
        randomizer = random.Random(62026)
        for n in range(1, 6):
            for _ in range(5):
                costs = [[randomizer.randrange(-9, 10) for _ in range(n)] for _ in range(n)]
                assignment = scorer._assignment(costs)
                actual = sum(costs[i][j] for i, j in enumerate(assignment))
                exact = min(sum(costs[i][j] for i, j in enumerate(permutation)) for permutation in itertools.permutations(range(n)))
                self.assertEqual(exact, actual)
                self.assertEqual(n, len(set(assignment)))


class ValidationAndCliTest(unittest.TestCase):
    def test_invalid_times_root_shape_and_types_are_rejected(self):
        for bad in (document(row(-1, 100)), document(row(0, 1001)), document(row(10, 9)),
                    document(row(True, 100)), {"transcript": [], "metadata": {}},
                    document({**row(), "confidence": .5}), document(row(speaker=""))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                scorer.score(bad, document(), 1000)
        for bad_duration in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                scorer.score(document(), document(), bad_duration)
        for bad_processing in (-1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                scorer.score(document(), document(), 1000, bad_processing)

    def test_empty_and_zero_duration_data_do_not_fabricate_timing(self):
        result = scorer.score(document(row(0, 0, text="слово")), document(), 1000)
        self.assertEqual(1, result["inputs"]["reference_zero_duration_segments"])
        self.assertEqual(1.0, result["wer_raw"]["rate"])
        self.assertIsNone(result["der_collar_0ms"]["rate"])
        self.assertIsNone(result["timing"]["reference_coverage"])
        self.assertIsNone(result["rtf"])

    def test_cli_writes_utf8_json_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            reference, hypothesis, output = (folder / name for name in ("ref.json", "hyp.json", "result.json"))
            reference.write_text(json.dumps(document(row(text="Ёж, да!")), ensure_ascii=False), encoding="utf-8")
            hypothesis.write_text(reference.read_text(encoding="utf-8"), encoding="utf-8")
            args = ["--reference", str(reference), "--hypothesis", str(hypothesis), "--duration-ms", "1000", "--processing-ms", "250", "--output", str(output)]
            self.assertEqual(0, scorer.main(args))
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(0.0, data["wer_raw"]["rate"])
            self.assertEqual(.25, data["rtf"])
            self.assertFalse(output.read_bytes().startswith(b"\xef\xbb\xbf"))
            before = output.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                scorer.main(args)
            self.assertEqual(2, error.exception.code)
            self.assertEqual(before, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
