import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("ports", Path(__file__).resolve().parents[1]/"port_comparison.py")
ports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports)


class PairedCorpusGateTest(unittest.TestCase):
    def test_corpus_gate_weights_tokens_and_keeps_individual_outlier(self):
        cases = [{"id": "long", "reference_words": 148, "host_errors": 23, "native_errors": 22},
                 {"id": "other", "reference_words": 294, "host_errors": 53, "native_errors": 53}]
        result = ports.summarize(cases)
        self.assertAlmostEqual(-100/442,result["wer_delta_percentage_points"])
        self.assertTrue(result["gate_pass"])
        self.assertFalse(result["per_file_diagnostics"][0]["per_file_within_threshold"])

    def test_corpus_difference_exceeding_threshold_is_not_hidden(self):
        result = ports.summarize([{"id":"test", "reference_words":100, "host_errors":0, "native_errors":1}])
        self.assertFalse(result["gate_pass"])

    def test_missing_reference_or_duplicate_ids_cannot_produce_false_pass(self):
        case = {"id":"test", "reference_words":0, "host_errors":0, "native_errors":0}
        self.assertFalse(ports.summarize([case])["gate_pass"])
        self.assertIsNone(ports.summarize([case])["wer_delta_percentage_points"])
        with self.assertRaises(ValueError):
            ports.summarize([case,case])


if __name__ == "__main__":
    unittest.main()
