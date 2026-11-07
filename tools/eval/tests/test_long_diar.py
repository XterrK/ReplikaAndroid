"""Step 6 pure chunked-diarization policy; also pins the Kotlin parity fixture.

Regenerate the fixture after an intentional policy change with:
  python -m tools.eval.tests.test_long_diar --write-fixture
"""
from dataclasses import replace
import json
from pathlib import Path
import random
import sys
import unittest

from tools.eval.long_diar import (ChunkConfig, Centroid, Turn, fast_der, global_clusters, plan_windows,
                                  resolve_labels, stitch, stitch_points, window_centroids)
from tools.eval.speaker_refiner import clean_windows

FIXTURE = Path(__file__).resolve().parents[3] / "app/src/test/resources/step06/chunked-parity.json"


def _case(seed: int) -> dict:
    rng = random.Random(f"step06-parity-{seed}")
    config = ChunkConfig(min_duration_ms=rng.choice([15, 20]) * 60_000, window_ms=rng.choice([8, 10]) * 60_000,
                         overlap_ms=rng.choice([20_000, 30_000]), global_tau=rng.choice([.3, .5, .7]),
                         max_speakers=rng.choice([3, 8]), stitch_search_ms=rng.choice([5_000, 10_000]))
    duration = rng.randint(config.min_duration_ms + 1, 45 * 60_000)
    windows = plan_windows(duration, config)
    dim = 8
    speakers = rng.randint(2, 6)
    prototypes = [[rng.gauss(0, 1) for _ in range(dim)] for _ in range(speakers)]
    local_turns, measured, centroids = [], [], []
    for k, (start, end) in enumerate(windows):
        length = end - start
        present = rng.sample(range(speakers), rng.randint(1, min(speakers, 4)))
        turns, cursor, label = [], rng.randint(0, 3000), 0
        while cursor < length - 500:
            label = rng.randrange(len(present) + (1 if rng.random() < .05 else 0))
            size = rng.choice([rng.randint(300, 900), rng.randint(1200, 9000)])
            stop = min(length, cursor + size)
            turns.append(Turn(cursor, stop, label))
            if rng.random() < .1 and stop + 400 < length:   # overlapping second speaker
                turns.append(Turn(max(cursor, stop - 400), min(length, stop + 400), (label + 1) % (len(present) + 1)))
            cursor = stop + rng.choice([0, rng.randint(100, 4000), rng.randint(20_000, 40_000) if rng.random() < .05 else 0])
        turns.sort(key=lambda t: (t.start_ms, t.end_ms, t.speaker))
        planned = clean_windows(turns, length)
        windows_k = []
        for w in planned[::4]:   # a subset keeps the fixture small; centroids accept any subset
            source = present[w.speaker] if w.speaker < len(present) else rng.randrange(speakers)
            vector = tuple(round(x + rng.gauss(0, .35), 4) for x in prototypes[source])
            windows_k.append(replace(w, embedding=vector))
        local_turns.append(turns)
        measured.append(windows_k)
        centroids += window_centroids(k, turns, windows_k)
    labels = global_clusters(centroids, config)
    mapping = resolve_labels(local_turns, centroids, labels, len(windows))
    cuts = stitch_points(windows, local_turns, config)
    final = stitch(windows, local_turns, mapping, cuts)
    return {
        "seed": seed, "duration_ms": duration, "config": vars(config),
        "local_turns": [[[t.start_ms, t.end_ms, t.speaker] for t in lt] for lt in local_turns],
        "measured": [[[w.start_ms, w.end_ms, w.speaker, list(w.embedding)] for w in mk] for mk in measured],
        "expected": {
            "windows": [list(w) for w in windows],
            "centroids": [[c.window, c.label, c.speech_ms, list(c.vector)] for c in centroids],
            "labels": labels,
            "mapping": [[[local, glob] for local, glob in sorted(m.items())] for m in mapping],
            "cuts": cuts,
            "turns": [[t.start_ms, t.end_ms, t.speaker] for t in final],
        },
    }


def build_fixture() -> dict:
    return {"schema": 1, "generator": "tools/eval/tests/test_long_diar.py", "cases": [_case(s) for s in range(16)]}


class LongDiarTest(unittest.TestCase):
    def test_short_recordings_stay_single_window(self):
        config = ChunkConfig()
        self.assertEqual([(0, 15 * 60_000)], plan_windows(15 * 60_000, config))
        self.assertEqual([(0, 0)], plan_windows(0, config))

    def test_windows_are_equal_bounded_and_overlap_exactly(self):
        config = ChunkConfig()
        for duration in (15 * 60_000 + 1, 16 * 60_000, 60 * 60_000, 8 * 3600_000 + 17, 8 * 3600_000 * 5 // 4):
            windows = plan_windows(duration, config)
            self.assertEqual(0, windows[0][0])
            self.assertEqual(duration, windows[-1][1])
            self.assertTrue(all(b - a <= config.window_ms for a, b in windows))
            for (a0, b0), (a1, b1) in zip(windows, windows[1:]):
                self.assertEqual(config.overlap_ms, b0 - a1)
            self.assertLessEqual(max(b - a for a, b in windows) - min(b - a for a, b in windows), len(windows))
        self.assertEqual(51, len(plan_windows(8 * 3600_000, config)))

    def test_cannot_link_keeps_two_labels_of_one_window_apart(self):
        same = (1.0, 0.0)
        centroids = [Centroid(0, 0, same, 1000), Centroid(0, 1, same, 1000), Centroid(1, 0, same, 1000)]
        labels = global_clusters(centroids, ChunkConfig(global_tau=.5))
        self.assertNotEqual(labels[0], labels[1])
        self.assertEqual(2, len(set(labels)))

    def test_cap_forces_merges_above_cut_but_never_inside_a_window(self):
        centroids = [Centroid(k, 0, (1.0 if k % 2 else -1.0, k / 10), 1000) for k in range(6)]
        labels = global_clusters(centroids, ChunkConfig(global_tau=.999, max_speakers=2))
        self.assertEqual(2, len(set(labels)))
        within = [Centroid(0, i, (1.0, i / 10), 10) for i in range(4)]
        self.assertEqual(4, len(set(global_clusters(within, ChunkConfig(global_tau=.0, max_speakers=2)))))

    def test_stitch_prefers_silence_near_the_midpoint_and_coalesces_cut_turns(self):
        config = ChunkConfig(stitch_search_ms=5000)
        windows = [(0, 100_000), (70_000, 170_000)]
        local = [[Turn(80_000, 84_000, 0), Turn(84_500, 90_000, 1)], [Turn(10_000, 14_000, 0), Turn(14_500, 20_000, 1)]]
        cuts = stitch_points(windows, local, config)
        self.assertEqual([84_500], cuts)   # midpoint 85000 is speech; nearest silent instant
        merged = stitch(windows, local, [{0: 0, 1: 1}, {0: 0, 1: 1}], cuts)
        self.assertEqual([Turn(80_000, 84_000, 0), Turn(84_500, 90_000, 1)], merged)

    def test_fast_der_matches_interval_definition(self):
        ref = [{"speaker_id": "a", "start_ms": 0, "end_ms": 1000}, {"speaker_id": "b", "start_ms": 1000, "end_ms": 2000}]
        self.assertEqual(0., fast_der(ref, [Turn(0, 1000, 5), Turn(1000, 2000, 6)], 2000, 1)["der"])
        self.assertAlmostEqual(.5, fast_der(ref, [Turn(0, 2000, 5)], 2000, 1)["der"])

    def test_kotlin_parity_fixture_is_current(self):
        self.assertEqual(build_fixture(), json.loads(FIXTURE.read_text(encoding="utf-8")))


if __name__ == "__main__":
    if "--write-fixture" in sys.argv:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(build_fixture(), separators=(",", ":")), encoding="utf-8")
        print("wrote", FIXTURE)
    else:
        unittest.main()
