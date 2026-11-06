"""Numerical reference tests for generic canonical-WAV Android timeline emulation."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.eval.decoder_parity import android_canonical_pcm, scalar_android_canonical_pcm


class DecoderTimelineParityTest(unittest.TestCase):
    def test_vectorized_result_is_bit_exact_to_operation_by_operation_reference(self):
        rng = np.random.default_rng(625)
        source = rng.integers(-32768, 32768, 180000, dtype=np.int16).astype(np.float32) / np.float32(32768)
        before = source.copy()
        for packet in [None, 16384, 4096, 137]:
            expected = scalar_android_canonical_pcm(source, packet)
            actual = android_canonical_pcm(source, packet)
            np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))
        np.testing.assert_array_equal(source.view(np.uint32), before.view(np.uint32))

    def test_zero_dc_and_first_sample_are_preserved(self):
        for value in [0, .125, -.5]:
            source = np.full(200000, value, dtype=np.float32)
            output = android_canonical_pcm(source)
            np.testing.assert_array_equal(source, output)
        self.assertEqual(0, len(android_canonical_pcm(np.zeros(0, dtype=np.float32))))

    def test_invalid_layout_and_packet_sizes_are_rejected(self):
        for packet in [0, -1, True]:
            with self.assertRaises(ValueError):
                android_canonical_pcm([.1], packet)
        for samples in [[[.1]], [float("nan")]]:
            with self.assertRaises(ValueError):
                android_canonical_pcm(samples)


if __name__ == "__main__":
    unittest.main()
