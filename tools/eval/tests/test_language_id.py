from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.eval import language_id as lid  # noqa: E402
from tools.eval import native_diar_policy as policy  # noqa: E402
import tools.prepare_embedded_pack as pack  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def ms(probes):
    return [sum(p.end_ms - p.start_ms for p in probe) for probe in probes]


class LanguageIdPolicyTest(unittest.TestCase):
    """Same cases as app/src/test/java/ru/replika/LanguagePlanTest.kt (Kotlin parity)."""

    def test_probes_first_thirty_seconds(self):
        self.assertEqual([10000, 10000, 10000], ms(lid.probe_windows([(0, 60000)])))
        self.assertEqual([10000, 10000, 5000], ms(lid.probe_windows([(0, 25000)])))
        self.assertEqual([], lid.probe_windows([]))

    def test_probes_concatenate_and_drop_tiny_tail(self):
        probes = lid.probe_windows([(0, 4000), (5000, 9000), (10000, 13000)])
        self.assertEqual([lid.Piece(0, 4000), lid.Piece(5000, 9000), lid.Piece(10000, 12000)], probes[0])
        self.assertEqual([lid.Piece(12000, 13000)], probes[1])
        self.assertEqual([10000], ms(lid.probe_windows([(0, 10500)])))
        self.assertEqual([], lid.probe_windows([(0, 900)]))

    def test_vote_strict_majority(self):
        self.assertEqual("ru", lid.vote([]))
        self.assertEqual("en", lid.vote(["en"]))
        self.assertEqual("ru", lid.vote(["en", "ru"]))
        self.assertEqual("en", lid.vote(["en", "en", "de"]))
        self.assertEqual("ru", lid.vote(["en", "de", "uk"]))

    def test_segment_inherits_when_short(self):
        self.assertEqual("ru", lid.segment_language("en", 1499, "ru"))
        self.assertEqual("en", lid.segment_language("en", 1500, "ru"))
        self.assertEqual("ru", lid.segment_language("de", 5000, "en"))

    def test_parakeet_stride_requires_pinned_metadata(self):
        good = {"model_type": "EncDecRNNTBPEModel", "model_author": "NeMo", "subsampling_factor": "8",
                "url": "https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2"}
        self.assertEqual(80, lid.parakeet_stride_from_metadata(good)["frame_stride_ms"])
        with self.assertRaises(ValueError):
            lid.parakeet_stride_from_metadata({**good, "url": "https://huggingface.co/nvidia/other"})


class LanguageLockTest(unittest.TestCase):
    def setUp(self):
        self.lock = json.loads((REPO / "app/src/main/assets/models-lock.json").read_text(encoding="utf-8"))

    def test_lock_appends_exact_language_pins_after_legacy_seven(self):
        self.assertEqual(14, len(self.lock["files"]))
        self.assertTrue(lid.language_rows_valid(self.lock["files"][7:]))
        policy.validate_model_lock(self.lock)  # legacy seven unchanged and first

    def test_language_extension_must_be_complete_and_pinned(self):
        broken = json.loads(json.dumps(self.lock))
        broken["files"][-1]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            policy.validate_model_lock(broken)
        partial = {"files": self.lock["files"][:10]}
        with self.assertRaises(ValueError):
            policy.validate_model_lock(partial)

    def test_pack_reader_accepts_seven_or_complete_fourteen(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "lock.json"
            for rows, ok in ((self.lock["files"], True), (self.lock["files"][:7], True),
                             (self.lock["files"][:12], False),
                             (self.lock["files"][7:] + self.lock["files"][:7], False)):
                target.write_text(json.dumps({"files": rows}), encoding="utf-8")
                if ok:
                    self.assertEqual(len(rows), len(pack.read_lock(target)[2]))
                else:
                    with self.assertRaises(ValueError):
                        pack.read_lock(target)


if __name__ == "__main__":
    unittest.main()
