import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "run.py"
spec = importlib.util.spec_from_file_location("evaluation_runner", MODULE)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerContractTest(unittest.TestCase):
    def test_incomplete_attempts_are_archived_and_artifact_tampering_is_detectable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "sample"
            case.mkdir()
            for name in ("reference.json", "hypothesis.json", "diagnostics.json", "metrics.json"):
                (case / name).write_text("{}")
            before = runner.evidence_hashes(case)
            (case / "metrics.json").write_text('{"changed":true}')
            self.assertNotEqual(before, runner.evidence_hashes(case))
            runner.archive_incomplete(case)
            self.assertFalse(case.exists())
            saved = list((root / "attempts").iterdir())
            self.assertEqual(1, len(saved))
            self.assertEqual('{"changed":true}', (saved[0] / "metrics.json").read_text())

    def test_manifest_paths_cannot_escape_via_parent_or_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "audio"
            root.mkdir()
            outside = Path(directory) / "outside.wav"
            outside.write_bytes(b"outside")
            (root / "linked.wav").symlink_to(outside)
            for unsafe in ("../outside.wav", "linked.wav"):
                with self.assertRaises(ValueError):
                    runner.confined(root, unsafe)
            self.assertEqual(root / "valid.wav", runner.confined(root, "valid.wav"))

    def test_unsupported_or_truth_derived_settings_are_not_silently_ignored(self):
        baseline = {"schema_version": 1, "id": "baseline", "pipeline": "v16", "expected_speakers": -1, "threads": 2}
        runner.validate_configuration(baseline)
        for changes in ({"use_reference_speaker_count": True}, {"threads": True}, {"threads": 3},
                        {"expected_speakers": 0}, {"pipeline": "unaccepted-candidate"}):
            with self.assertRaises(ValueError):
                runner.validate_configuration(dict(baseline, **changes))

    def test_hypothesis_validation_rejects_accidental_diagnostics_and_invalid_timestamps(self):
        row = {"speaker_id": "speaker_1", "start_ms": 0, "end_ms": 100, "text": "Да!"}
        self.assertEqual({"transcript": [row]}, runner.validated_hypothesis([row]))
        for changes in ({"confidence": .99}, {"speaker_id": "speaker_-1"}, {"start_ms": .5},
                        {"text": " "}, {"end_ms": -1}):
            with self.assertRaises(ValueError):
                runner.validated_hypothesis([dict(row, **changes)])


if __name__ == "__main__":
    unittest.main()
