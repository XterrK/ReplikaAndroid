"""Geometric/clock fixtures only; no model, expected speaker count or text."""
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.eval.pipeline import Turn
from tools.eval.speaker_refiner import (EmbeddingWindow, RefineConfig, clean_windows,
                                        estimate_speakers, refine)


def measured(turns, vectors, duration=None):
    duration = duration if duration is not None else max(t.end_ms for t in turns)
    return tuple(replace(w, embedding=tuple(vectors[w.speaker])) for w in clean_windows(turns, duration)
                 if w.speaker in vectors)


def isolated(**kwargs):
    return RefineConfig(merge_similar=False, use_eigengap=False, reassign_small=False, smooth=False, **kwargs)


def activity(turns):
    """Speaker-independent native activity union, preserving pauses."""
    result = []
    for t in sorted(turns, key=lambda t: (t.start_ms, t.end_ms)):
        if result and t.start_ms <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], t.end_ms))
        else:
            result.append((t.start_ms, t.end_ms))
    return result


class CleanWindowsTest(unittest.TestCase):
    def test_full_windows_stride_and_short_actual_island_without_padding(self):
        turns = [Turn(0, 3000, 4), Turn(4000, 5200, 7), Turn(6000, 6999, 8)]
        windows = clean_windows(turns, 7000)
        self.assertEqual([(0, 1500, 4), (750, 2250, 4), (1500, 3000, 4), (4000, 5200, 7)],
                         [(w.start_ms, w.end_ms, w.speaker) for w in windows])
        self.assertTrue(all(w.embedding == () and w.clean for w in windows))

    def test_overlap_and_unknown_activity_exclude_windows_without_changing_clock(self):
        turns = [Turn(0, 5000, 0), Turn(1200, 2600, 1), Turn(4000, 4100, -1)]
        self.assertEqual([(0, 1200, 0), (2600, 4000, 0)],
                         [(w.start_ms, w.end_ms, w.speaker) for w in clean_windows(turns, 6000)])

    def test_same_speaker_overlap_is_unioned_and_pauses_are_never_filled(self):
        turns = [Turn(0, 1000, 3), Turn(500, 2000, 3), Turn(2500, 3500, 3)]
        self.assertEqual([(0, 1500), (2500, 3500)],
                         [(w.start_ms, w.end_ms) for w in clean_windows(turns, 4000)])

    def test_invalid_turns_and_invalid_window_options_are_rejected(self):
        for turns in ([Turn(-1, 1500, 0)], [Turn(0, 1501, 0)], [Turn(0, 0, 0)], [Turn(0, 1, -2)]):
            with self.assertRaises(ValueError):
                clean_windows(turns, 1500)
        for opts in ({"step_ms": 0}, {"min_clean_ms": 1501}, {"window_ms": True}):
            with self.assertRaises(ValueError):
                clean_windows([], 0, **opts)


class EigengapTest(unittest.TestCase):
    def test_two_acoustic_components_and_single_voice(self):
        two = estimate_speakers([(1, 0), (.999, .01), (0, 1), (.01, .999)])
        self.assertEqual(2, two["estimated_k"])
        self.assertAlmostEqual(0, two["eigenvalues"][0])
        self.assertAlmostEqual(0, two["eigenvalues"][1])
        self.assertEqual(1, estimate_speakers([(1, 0)] * 4)["estimated_k"])

    def test_flat_orthogonal_and_weak_cosines_do_not_blindly_choose_one(self):
        self.assertEqual(3, estimate_speakers([(1, 0, 0), (0, 1, 0), (0, 0, 1)])["estimated_k"])
        self.assertEqual(2, estimate_speakers([(1, 0), (.1, math.sqrt(.99))])["estimated_k"])
        self.assertEqual(0, estimate_speakers([])["estimated_k"])
        self.assertEqual(1, estimate_speakers([(1,)])["estimated_k"])

    def test_hard_k_cap_and_dimension_validation(self):
        basis = [tuple(float(i == j) for i in range(10)) for j in range(10)]
        self.assertEqual(8, estimate_speakers(basis)["estimated_k"])
        for vectors in ([(0, 0)], [(1,), (1, 0)], [(float("nan"), 1)]):
            with self.assertRaises(ValueError):
                estimate_speakers(vectors)
        with self.assertRaisesRegex(ValueError, "256"):
            estimate_speakers([(1,)] * 257)


class RefinementGeometryTest(unittest.TestCase):
    def setUp(self):
        self.turns = [Turn(0, 4000, 40), Turn(5000, 9000, 70), Turn(10000, 14000, 90)]
        self.vectors = {40: (1, 0), 70: (.99, .01), 90: (0, 1)}

    def test_same_voice_merges_and_distinct_identity_is_retained(self):
        result = refine(self.turns, measured(self.turns, self.vectors), 14000)
        self.assertTrue(result.accepted)
        self.assertEqual([0, 0, 1], [t.speaker for t in result.turns])
        self.assertEqual(["cosine"], [m["stage"] for m in result.diagnostics["merges"]])
        self.assertEqual(activity(self.turns), activity(result.turns))

    def test_unit_vectors_then_duration_weighted_mean_and_centroid_renormalization(self):
        turns = [Turn(0, 2250, 0)]
        windows = [EmbeddingWindow(0, 1500, 0, (100, 0)), EmbeddingWindow(750, 2250, 0, (0, 2))]
        result = refine(turns, windows, 2250, isolated())
        self.assertEqual(1, len(result.diagnostics["centroids"]))
        vector = result.diagnostics["centroids"][0]["embedding"]
        self.assertAlmostEqual(math.sqrt(.5), vector[0])
        self.assertAlmostEqual(math.sqrt(.5), vector[1])
        turns = [Turn(0, 1200, 0), Turn(2000, 3500, 0)]
        windows = [EmbeddingWindow(0, 1200, 0, (100, 0)), EmbeddingWindow(2000, 3500, 0, (0, 2))]
        weighted = refine(turns, windows, 4000, isolated()).diagnostics["centroids"][0]["embedding"]
        self.assertAlmostEqual(1200 / math.hypot(1200, 1500), weighted[0])
        self.assertAlmostEqual(1500 / math.hypot(1200, 1500), weighted[1])

    def test_threshold_is_strict_and_spectral_stage_never_splits(self):
        turns = self.turns[:2]
        vectors = {40: (1, 0), 70: (.5, math.sqrt(.75))}
        result = refine(turns, measured(turns, vectors), 9000,
                        replace(isolated(merge_threshold=.5), merge_similar=True))
        self.assertEqual(2, result.diagnostics["output_clusters"])
        # Three directions with a chain: default centroid policy may merge all,
        # despite the premerge eigengap K=2. No invented up-split is permitted.
        vectors = {key: (math.cos(math.radians(angle)), math.sin(math.radians(angle)))
                   for key, angle in zip((40, 70, 90), (0, 35, 70))}
        result = refine(self.turns, measured(self.turns, vectors), 14000,
                        replace(isolated(merge_threshold=.5), merge_similar=True, use_eigengap=True))
        self.assertEqual(1, result.diagnostics["output_clusters"])
        self.assertEqual(2, result.diagnostics["eigengap"]["estimated_k"])

    def test_optional_complete_link_guard_blocks_centroid_chaining(self):
        vectors = {key: (math.cos(math.radians(angle)), math.sin(math.radians(angle)))
                   for key, angle in zip((40, 70, 90), (0, 35, 70))}
        config = replace(isolated(merge_threshold=.5), merge_similar=True, complete_link_guard=True)
        result = refine(self.turns, measured(self.turns, vectors), 14000, config)
        self.assertEqual(2, result.diagnostics["output_clusters"])

    def test_eigengap_stage_reduces_measured_clusters_without_cosine_stage(self):
        result = refine(self.turns, measured(self.turns, self.vectors), 14000,
                        replace(isolated(), use_eigengap=True))
        self.assertEqual([0, 0, 1], [t.speaker for t in result.turns])
        self.assertEqual(["eigengap"], [m["stage"] for m in result.diagnostics["merges"]])

    def test_input_permutation_and_label_values_do_not_change_output_identity(self):
        windows = measured(self.turns, self.vectors)
        baseline = refine(self.turns, windows, 14000)
        rng = random.Random(53)
        for _ in range(10):
            native, samples = list(self.turns), list(windows)
            rng.shuffle(native)
            rng.shuffle(samples)
            self.assertEqual(baseline.turns, refine(native, samples, 14000).turns)
        mapping = {40: 888, 70: 5, 90: 13}
        native = [replace(t, speaker=mapping[t.speaker]) for t in self.turns]
        samples = [replace(w, speaker=mapping[w.speaker]) for w in windows]
        self.assertEqual(baseline.turns, refine(native, samples, 14000).turns)

    def test_simultaneous_source_label_collapse_is_reported_and_never_fills_activity(self):
        turns = [Turn(0, 5000, 0), Turn(3000, 8000, 1)]
        result = refine(turns, measured(turns, {0: (1, 0), 1: (1, 0)}), 9000,
                        replace(isolated(), merge_similar=True))
        self.assertEqual((Turn(0, 8000, 0),), result.turns)
        self.assertEqual(2000, result.diagnostics["overlap_collapses_ms"])
        self.assertEqual(activity(turns), activity(result.turns))

    def test_forced_cap_low_similarity_is_not_hidden_as_cosine_success(self):
        turns = [Turn(i * 4000, i * 4000 + 3000, i) for i in range(9)]
        vectors = {i: tuple(float(i == j) for j in range(9)) for i in range(9)}
        result = refine(turns, measured(turns, vectors), 35000, isolated())
        self.assertTrue(result.accepted)
        self.assertEqual(8, result.diagnostics["output_clusters"])
        self.assertEqual(1, result.diagnostics["forced_cap_merges"])
        self.assertEqual(1, result.diagnostics["low_similarity_merges"])
        self.assertEqual("forced_cap", result.diagnostics["merges"][0]["stage"])


class SmallClusterAndSmoothingTest(unittest.TestCase):
    def test_nearest_centroid_and_tie_use_first_appearance(self):
        turns = [Turn(0, 5000, 8), Turn(6000, 11000, 1), Turn(12000, 13200, 9)]
        vectors = {8: (1, 0), 1: (0, 1), 9: (1, 1)}
        result = refine(turns, measured(turns, vectors), 14000, replace(isolated(), reassign_small=True))
        self.assertEqual([0, 1, 0], [t.speaker for t in result.turns])
        self.assertEqual("centroid", result.diagnostics["small_reassignments"][0]["method"])

    def test_distinct_short_guest_is_not_silently_protected_by_plan_default(self):
        turns = [Turn(0, 5000, 0), Turn(6000, 7200, 1)]
        windows = measured(turns, {0: (1, 0), 1: (0, 1)})
        default = refine(turns, windows, 8000, replace(isolated(), reassign_small=True))
        guarded = refine(turns, windows, 8000,
                         replace(isolated(minimum_reassignment_similarity=.8), reassign_small=True))
        self.assertEqual(1, default.diagnostics["output_clusters"])
        self.assertEqual(0, default.diagnostics["small_reassignments"][0]["cosine"])
        self.assertEqual(2, guarded.diagnostics["output_clusters"])
        self.assertEqual("minimum_similarity_guard", guarded.diagnostics["small_reassignments"][0]["reason"])

    def test_union_duration_threshold_strict_and_recording_fraction(self):
        turns = [Turn(0, 10000, 0), Turn(20000, 23000, 1), Turn(21000, 22000, 1)]
        result = refine(turns, measured(turns, {0: (1, 0), 1: (0, 1)}, 100000), 100000,
                        replace(isolated(), reassign_small=True))
        self.assertEqual(3000, result.diagnostics["small_cluster_cutoff_ms"])
        self.assertEqual([], result.diagnostics["small_reassignments"])
        self.assertEqual(2, result.diagnostics["output_clusters"])

    def test_all_small_anchor_is_explicit_and_deterministic(self):
        turns = [Turn(0, 1200, 9), Turn(2000, 3500, 1)]
        result = refine(turns, measured(turns, {9: (1, 0), 1: (0, 1)}), 4000,
                        replace(isolated(), reassign_small=True))
        self.assertEqual(1, result.diagnostics["all_small_anchor"])
        self.assertEqual(1, result.diagnostics["output_clusters"])

    def test_missing_220ms_fragment_is_retained_or_explicitly_temporal(self):
        turns = [Turn(0, 5000, 0), Turn(6000, 10000, 1), Turn(10000, 10220, 2)]
        windows = measured(turns, {0: (1, 0), 1: (0, 1)})
        strict = refine(turns, windows, 11000, replace(isolated(), reassign_small=True))
        temporal = refine(turns, windows, 11000,
                          replace(isolated(small_missing_centroid_policy="temporal"), reassign_small=True))
        self.assertTrue(strict.accepted)
        self.assertFalse(strict.diagnostics["fully_acoustic_supported"])
        self.assertEqual([2], strict.diagnostics["missing_centroid_labels"])
        self.assertEqual(3, strict.diagnostics["output_clusters"])
        self.assertEqual(2, temporal.diagnostics["output_clusters"])
        decision = temporal.diagnostics["small_reassignments"][0]
        self.assertEqual("temporal", decision["method"])
        self.assertIsNone(decision["cosine"])
        self.assertEqual(1, decision["target"])
        self.assertEqual(activity(turns), activity(temporal.turns))

    def test_missing_guest_temporal_tie_prefers_earlier_real_interval(self):
        turns = [Turn(0, 2000, 7), Turn(2900, 3100, 8), Turn(4000, 6000, 2)]
        result = refine(turns, measured(turns, {7: (1, 0), 2: (0, 1)}), 6000,
                        replace(isolated(small_missing_centroid_policy="temporal"), reassign_small=True))
        self.assertEqual([0, 0, 1], [t.speaker for t in result.turns])
        self.assertEqual(2000, result.diagnostics["small_reassignments"][0]["midpoint_distance_ms"])

    def test_temporal_small_fallback_precedes_cap_without_forcing_unrelated_merge(self):
        turns = [Turn(i * 4000, i * 4000 + 3000, i) for i in range(8)] + [Turn(32000, 32220, 8)]
        vectors = {i: tuple(float(i == j) for j in range(8)) for i in range(8)}
        result = refine(turns, measured(turns, vectors), 35000,
                        replace(isolated(small_missing_centroid_policy="temporal"), reassign_small=True))
        self.assertTrue(result.accepted)
        self.assertEqual(8, result.diagnostics["output_clusters"])
        self.assertEqual(0, result.diagnostics["forced_cap_merges"])
        self.assertEqual("temporal", result.diagnostics["small_reassignments"][0]["method"])

    def test_short_insertion_smooths_but_exact500ms_does_not(self):
        for length, expected in ((499, 1), (500, 0)):
            turns = [Turn(0, 2000, 0), Turn(2000, 2000 + length, 1), Turn(2000 + length, 5000, 0), Turn(6000, 8000, 1)]
            result = refine(turns, measured(turns, {0: (1, 0), 1: (0, 1)}), 9000,
                            replace(isolated(), smooth=True))
            self.assertEqual(expected, len(result.diagnostics["smoothing"]))
            self.assertEqual(activity(turns), activity(result.turns))

    def test_gap_overlap_and_unknown_insertions_are_not_smoothed(self):
        variants = [
            [Turn(0, 1900, 0), Turn(2000, 2300, 1), Turn(2400, 5000, 0), Turn(6000, 8000, 1)],
            [Turn(0, 5000, 0), Turn(2000, 2300, 1), Turn(6000, 8000, 1)],
            [Turn(0, 2000, 0), Turn(2000, 2300, -1), Turn(2300, 5000, 0)],
        ]
        for turns in variants:
            result = refine(turns, measured(turns, {0: (1, 0), 1: (0, 1)}), 9000,
                            replace(isolated(), smooth=True))
            self.assertEqual([], result.diagnostics["smoothing"])
            self.assertEqual(activity(turns), activity(result.turns))


class InvalidEvidenceTest(unittest.TestCase):
    def test_empty_unknown_and_invalid_turns_are_explicit(self):
        self.assertTrue(refine([], [], 0).accepted)
        self.assertEqual("UNKNOWN_ONLY", refine([Turn(0, 1000, -1)], [], 1000).diagnostics["status"])
        result = refine([Turn(-1, 1000, 0), Turn(0, 1000, 1)], [], 1000)
        self.assertFalse(result.accepted)
        self.assertEqual((Turn(0, 1000, 1),), result.turns)
        self.assertEqual("invalid_native_turns", result.diagnostics["reason"])

    def test_zero_nonfinite_nonclean_offclock_and_duplicate_observations(self):
        turns = [Turn(0, 3000, 0)]
        good = EmbeddingWindow(0, 1500, 0, (1, 0))
        invalid = [replace(good, embedding=(0, 0)), replace(good, embedding=(float("nan"), 0)),
                   replace(good, embedding=(1, float("inf"))), replace(good, clean=False),
                   replace(good, start_ms=1), replace(good, embedding=("1", 0))]
        result = refine(turns, [good, good, *invalid], 3000, isolated())
        self.assertTrue(result.accepted)
        self.assertEqual(6, len(result.diagnostics["invalid_windows"]))
        self.assertEqual(1, result.diagnostics["window_counts"][0]["count"])
        json.dumps(asdict(result), allow_nan=False)

    def test_dimension_conflict_and_cancelled_centroid_are_not_fabricated(self):
        turns = [Turn(0, 2250, 0)]
        windows = [EmbeddingWindow(0, 1500, 0, (1, 0)), EmbeddingWindow(750, 2250, 0, (1, 0, 0))]
        result = refine(turns, windows, 2250)
        self.assertFalse(result.accepted)
        self.assertEqual("embedding_dimension_mismatch", result.diagnostics["reason"])
        cancelled = refine(turns, [windows[0], replace(windows[1], embedding=(-1, 0))], 2250, isolated())
        self.assertFalse(cancelled.accepted)
        self.assertFalse(cancelled.diagnostics["fully_acoustic_supported"])
        self.assertEqual([0], cancelled.diagnostics["missing_centroid_labels"])
        self.assertEqual([], cancelled.diagnostics["centroids"])

    def test_extreme_finite_embeddings_normalize_and_conflicting_duplicates_do_not_vote(self):
        turns = [Turn(0, 3000, 0)]
        for vector in ((1e308, 1e308), (1e-300, 1e-300)):
            result = refine(turns, [EmbeddingWindow(0, 1500, 0, vector)], 3000, isolated())
            self.assertTrue(result.accepted)
            self.assertAlmostEqual(math.sqrt(.5), result.diagnostics["centroids"][0]["embedding"][0])
        result = refine(turns, [EmbeddingWindow(0, 1500, 0, (1, 0)), EmbeddingWindow(0, 1500, 0, (0, 1))], 3000)
        self.assertFalse(result.accepted)
        self.assertEqual("no_measured_centroids", result.diagnostics["reason"])
        self.assertEqual(2, len(result.diagnostics["invalid_windows"]))

    def test_hard_cap_does_not_ignore_missing_labels(self):
        turns = [Turn(i * 1000, i * 1000 + 220, i) for i in range(9)]
        result = refine(turns, [], 9000, isolated())
        self.assertFalse(result.accepted)
        self.assertEqual(tuple(turns), result.turns)
        self.assertEqual("hard_cap_without_valid_centroids", result.diagnostics["reason"])

    def test_invalid_config_and_ground_truth_argument_have_no_silent_path(self):
        for config in (RefineConfig(merge_threshold=float("nan")), RefineConfig(max_speakers=9),
                       RefineConfig(small_missing_centroid_policy="centroid_guess"), RefineConfig(merge_threshold=".85"),
                       RefineConfig(min_cluster_fraction=False)):
            with self.assertRaises(ValueError):
                refine([], [], 0, config)
        with self.assertRaises(ValueError):
            refine([], [], 1 << 64)
        with self.assertRaises(TypeError):
            refine([], [], 0, expected_speakers=3)
        with self.assertRaises(TypeError):
            refine([], [], 0, reference=[])


if __name__ == "__main__":
    unittest.main()
