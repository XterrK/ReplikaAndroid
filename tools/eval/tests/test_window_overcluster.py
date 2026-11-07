from dataclasses import asdict, replace
import json
import math
import unittest

from tools.eval.pipeline import Turn
from tools.eval.speaker_refiner import EmbeddingWindow, clean_windows
from tools.eval.window_overcluster import WindowClusterConfig, overcluster, _smooth, _activity


def measured(turns, duration, vectors):
    return [replace(w, embedding=tuple(vectors[w.speaker])) for w in clean_windows(turns, duration)]


class WindowOverclusterTest(unittest.TestCase):
    def test_real_window_modes_split_one_native_label_without_silence_or_gold(self):
        native = [Turn(0, 6000, 9)]
        windows = [replace(w, embedding=(1., 0.) if w.start_ms + w.end_ms <= 6000 else (0., 1.))
                   for w in clean_windows(native, 6000)]
        result = overcluster(native, windows, 6000, WindowClusterConfig(tau=.8, smooth=False))
        self.assertTrue(result.accepted)
        self.assertEqual(2, result.diagnostics["output_clusters"])
        self.assertEqual([(0, 6000)], _activity(result.turns))
        self.assertEqual([0, 1], [t.speaker for t in result.turns])
        self.assertEqual(result.turns[0].end_ms, result.turns[1].start_ms)
        self.assertTrue(result.diagnostics["new_internal_grid_boundaries_ms"])
        self.assertTrue(all(x % 125 == 0 for x in result.diagnostics["new_internal_grid_boundaries_ms"]))
        self.assertFalse(result.diagnostics["new_neural_inference"])
        json.dumps(asdict(result), allow_nan=False)
        with self.assertRaises(TypeError):
            overcluster(native, windows, 6000, expected_speakers=2)
        with self.assertRaises(TypeError):
            overcluster(native, windows, 6000, reference={"text": "gold"})

    def test_window_order_and_identical_duplicate_do_not_change_votes(self):
        native = [Turn(0, 6000, 4)]
        windows = [replace(w, embedding=(1., 0.) if w.start_ms < 3000 else (0., 1.)) for w in clean_windows(native, 6000)]
        config = WindowClusterConfig(tau=.8, smooth=False)
        a = overcluster(native, windows, 6000, config)
        b = overcluster(native, list(reversed(windows)) + [windows[0]], 6000, config)
        self.assertEqual(a.turns, b.turns)
        self.assertEqual(a.diagnostics["window_labels"], b.diagnostics["window_labels"])
        self.assertEqual(1, len(b.diagnostics["duplicate_windows"]))

    def test_inclusive_threshold_tie_is_explicit(self):
        native = [Turn(0, 1500, 3), Turn(2000, 3500, 7)]
        windows = measured(native, 3500, {3: (1., 0.), 7: (0., 1.)})
        at = overcluster(native, windows, 3500, WindowClusterConfig(tau=0., smooth=False))
        above = overcluster(native, windows, 3500, WindowClusterConfig(tau=.000001, smooth=False))
        self.assertEqual(1, at.diagnostics["output_clusters"])
        self.assertEqual(2, above.diagnostics["output_clusters"])
        self.assertTrue(at.diagnostics["cut_inclusive"])
        self.assertEqual(1., at.diagnostics["cut_distance"])

    def test_complete_and_average_use_different_official_linkage_distances(self):
        native = [Turn(i * 2000, i * 2000 + 1500, i) for i in range(3)]
        vectors = {i: (math.cos(math.pi * i / 6), math.sin(math.pi * i / 6)) for i in range(3)}
        windows = measured(native, 5500, vectors)
        complete = overcluster(native, windows, 5500, WindowClusterConfig(tau=.65, method="complete", smooth=False))
        average = overcluster(native, windows, 5500, WindowClusterConfig(tau=.65, method="average", smooth=False))
        self.assertEqual(2, complete.diagnostics["output_clusters"])
        self.assertEqual(1, average.diagnostics["output_clusters"])

    def test_hard_cap_continues_same_tree_and_reports_forced_merge(self):
        native = [Turn(i * 2000, i * 2000 + 1500, i) for i in range(9)]
        windows = measured(native, 17500, {i: tuple(float(i == j) for j in range(9)) for i in range(9)})
        result = overcluster(native, windows, 17500, WindowClusterConfig(tau=.9, smooth=False))
        self.assertTrue(result.accepted)
        self.assertEqual(9, result.diagnostics["window_clusters_at_cut"])
        self.assertEqual(8, result.diagnostics["window_clusters_after_cap"])
        self.assertEqual(8, result.diagnostics["output_clusters"])
        self.assertEqual(1, len(result.diagnostics["forced_cap_merges"]))
        self.assertTrue(result.diagnostics["forced_cap_merges"][0]["above_cut"])

    def test_gap_endpoints_and_partial_grid_atoms_preserve_exact_activity(self):
        native = [Turn(13, 2151, 8), Turn(3003, 4599, 8)]
        result = overcluster(native, measured(native, 5000, {8: (1., 0.)}), 5000)
        self.assertTrue(result.accepted)
        self.assertEqual([(13, 2151), (3003, 4599)], _activity(result.turns))
        self.assertTrue(result.diagnostics["activity_union_preserved"])
        self.assertLessEqual(result.diagnostics["max_assignment_atom_ms"], 125)
        self.assertTrue(any(f["method"] == "nearest_same_source_time" for f in result.diagnostics["fallbacks"]))

    def test_overlap_collapse_is_counted_without_filling_or_removing_speech(self):
        native = [Turn(0, 3000, 0), Turn(1000, 4000, 1)]
        windows = measured(native, 4000, {0: (1., 0.), 1: (1., 0.)})
        self.assertEqual(2, len(windows))
        result = overcluster(native, windows, 4000)
        self.assertTrue(result.accepted)
        self.assertEqual([(0, 4000)], _activity(result.turns))
        self.assertEqual(2000, result.diagnostics["speaker_time_collapsed_ms"])
        self.assertEqual(6000, result.diagnostics["original_speaker_time_ms"])
        self.assertEqual(4000, result.diagnostics["output_speaker_time_ms"])

    def test_missing_short_fragment_uses_explicit_global_time_not_fake_vector(self):
        native = [Turn(0, 3000, 5), Turn(4000, 4300, 9)]
        windows = measured(native, 4300, {5: (1., 0.), 9: (0., 1.)})
        result = overcluster(native, windows, 4300)
        self.assertTrue(result.accepted)
        self.assertEqual("PARTIAL_TEMPORAL", result.diagnostics["status"])
        self.assertFalse(result.diagnostics["every_native_label_has_measured_windows"])
        fallback = [x for x in result.diagnostics["fallbacks"] if x["source_speaker"] == 9]
        self.assertEqual(300, sum(x["end_ms"] - x["start_ms"] for x in fallback))
        self.assertTrue(all(x["method"] == "nearest_global_time_missing_source_windows" for x in fallback))
        self.assertEqual([(0, 3000), (4000, 4300)], _activity(result.turns))
        self.assertEqual(len(windows), result.diagnostics["measured_unique_windows"])

    def test_small_guest_stage_is_optional_and_similarity_guard_protects_it(self):
        native = [Turn(0, 5000, 0), Turn(6000, 7500, 1)]
        windows = measured(native, 7500, {0: (1., 0.), 1: (0., 1.)})
        plain = overcluster(native, windows, 7500, WindowClusterConfig(smooth=False))
        small = overcluster(native, windows, 7500, WindowClusterConfig(reassign_small=True, smooth=False))
        guarded = overcluster(native, windows, 7500, WindowClusterConfig(
            reassign_small=True, minimum_reassignment_similarity=.8, smooth=False))
        self.assertEqual(2, plain.diagnostics["output_clusters"])
        self.assertEqual(1, small.diagnostics["output_clusters"])
        self.assertEqual(2, guarded.diagnostics["output_clusters"])
        self.assertEqual("minimum_similarity_guard", guarded.diagnostics["small_reassignments"][0]["reason"])
        self.assertEqual(0., small.diagnostics["small_reassignments"][0]["cosine"])

    def test_smoothing_requires_enclosed_touching_insertion_strictly_under_500ms(self):
        for length, count in ((499, 1), (500, 0)):
            turns = [Turn(0, 2000, 0), Turn(2000, 2000 + length, 1), Turn(2000 + length, 5000, 0)]
            diagnostic = {}
            smoothed = _smooth(turns, WindowClusterConfig(), diagnostic)
            self.assertEqual(count, len(diagnostic["smoothing"]))
            self.assertEqual(_activity(turns), _activity(smoothed))
        for turns in ([Turn(0, 1900, 0), Turn(2000, 2300, 1), Turn(2400, 5000, 0)],
                      [Turn(0, 2000, 0), Turn(2000, 2300, 1), Turn(2000, 2500, 2), Turn(2300, 5000, 0)]):
            diagnostic = {}
            self.assertEqual(turns, _smooth(turns, WindowClusterConfig(), diagnostic))
            self.assertEqual([], diagnostic["smoothing"])

    def test_invalid_windows_dimensions_and_conflicting_duplicates_are_unsupported(self):
        native = [Turn(0, 3000, 0)]
        valid = measured(native, 3000, {0: (1., 0.)})
        variants = [[replace(valid[0], start_ms=1)], [replace(valid[0], clean=False)],
                    [replace(valid[0], embedding=(float("nan"), 0.))],
                    [replace(valid[0], embedding=(0., 0.))],
                    [replace(valid[0], embedding=(True, 1.))],
                    [valid[0], replace(valid[0], embedding=(0., 1.))],
                    [valid[0], replace(valid[1], embedding=(1., 0., 0.))]]
        for windows in variants:
            result = overcluster(native, windows, 3000)
            self.assertFalse(result.accepted)
            self.assertEqual(tuple(native), result.turns)
        self.assertFalse(overcluster([Turn(-1, 2000, 0)], [], 3000).accepted)
        self.assertFalse(overcluster([Turn(0, 2000, -1)], [], 3000).accepted)

    def test_empty_and_all_missing_are_distinct_and_config_is_strict(self):
        self.assertTrue(overcluster([], [], 0).accepted)
        native = [Turn(0, 500, 4)]
        result = overcluster(native, [], 500)
        self.assertFalse(result.accepted)
        self.assertEqual(tuple(native), result.turns)
        self.assertEqual("no_real_clean_windows", result.diagnostics["reason"])
        for config in (WindowClusterConfig(tau=float("nan")), WindowClusterConfig(tau=1.),
                       WindowClusterConfig(method="ward"), WindowClusterConfig(grid_ms=True),
                       WindowClusterConfig(max_speakers=9), WindowClusterConfig(min_cluster_fraction=False),
                       WindowClusterConfig(smooth=1), WindowClusterConfig(minimum_reassignment_similarity=float("inf"))):
            with self.assertRaises(ValueError):
                overcluster([], [], 0, config)


if __name__ == "__main__":
    unittest.main()
