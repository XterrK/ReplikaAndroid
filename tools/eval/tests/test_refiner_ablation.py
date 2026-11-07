"""Pure C2 ablation accounting and short-label preservation; no model inference."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.eval import refiner_ablation as ablation
from tools.eval.pipeline import Turn
from tools.eval.speaker_refiner import EmbeddingWindow, RefineConfig, clean_windows, refine


class AblationStagesTest(unittest.TestCase):
    def test_small_guard_changes_only_the_reassignment_stage_on_short_distinct_voice(self):
        turns = [Turn(0, 4000, 0), Turn(4000, 5000, 1)]
        vectors = {0: (1., 0.), 1: (.4, math.sqrt(.84))}
        windows = [replace(window, embedding=vectors[window.speaker]) for window in clean_windows(turns, 5000)]
        full = refine(turns, windows, 5000, ablation.config_for("full", .95, "retain"))
        guarded = refine(turns, windows, 5000, ablation.config_for("full_small_cos_0p5", .95, "retain"))
        a, b = ablation.stage_trace(full), ablation.stage_trace(guarded)
        self.assertEqual((2, 2, 2, 1, 1), tuple(a[key] for key in
            ["input_k", "after_cosine_k", "after_eigengap_k", "after_small_k", "output_k"]))
        self.assertEqual(2, b["output_k"])
        self.assertEqual({"minimum_similarity_guard": 1}, b["small_retention_reasons"])
        self.assertEqual(0, a["eigengap_merges"])
        self.assertEqual([(0, 5000)], [(t.start_ms, t.end_ms) for t in full.turns])
        self.assertEqual(turns, list(guarded.turns))

    def test_merge_only_does_not_apply_short_cluster_or_temporal_rules(self):
        turns = [Turn(0, 4000, 0), Turn(4000, 5000, 1)]
        windows = [replace(window, embedding=(1., 0.) if window.speaker == 0 else (0., 1.))
                   for window in clean_windows(turns, 5000)]
        result = refine(turns, windows, 5000, ablation.config_for("merge_only", .95, "temporal"))
        trace = ablation.stage_trace(result)
        self.assertEqual(2, trace["output_k"])
        self.assertEqual(0, trace["small_reassignments_applied"])
        self.assertEqual(0, trace["smoothing_events"])

    def test_unsupported_cap_reports_rollback_without_inventing_output_merges(self):
        turns = [Turn(0, 500, 0), Turn(500, 1000, 1)]
        result = refine(turns, [], 1000, RefineConfig(max_speakers=1))
        trace = ablation.stage_trace(result)
        self.assertFalse(trace["computation_supported"])
        self.assertTrue(trace["attempted_stages_rolled_back_to_native"])
        self.assertEqual(2, trace["output_k"])
        self.assertEqual("hard_cap_without_valid_centroids", trace["fallback_reason"])
        self.assertIsNone(trace["smoothing_cluster_reduction"])

    def test_global_grid_and_gate_limits_are_preserved(self):
        self.assertEqual(14, len(ablation.TAUS))
        self.assertEqual(7, len(ablation.FAMILIES))
        self.assertEqual(7, ablation.MIN_EXACT)
        self.assertEqual(.288851817, ablation.DER_LIMIT)
        with self.assertRaises(ValueError):
            ablation.config_for("per_case_rule", .5, "retain")
        with self.assertRaises(ValueError):
            ablation.config_for("full", .501, "retain")


if __name__ == "__main__":
    unittest.main()
