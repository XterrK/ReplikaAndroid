#!/usr/bin/env python3
"""Investigate canonical-WAV parity with Android AudioDecoder's PCM timeline.

This is an evaluation helper, not a change to production decoding. The PCM16
sample conversion is exact, but AudioDecoder still advances a Double output
clock by repeated addition and interpolates with Float32 arithmetic. For AOSP
WAV extraction, 32768 input bytes give 16384 mono PCM16 frames per packet.
Actual Android PCM must be compared before adopting this assumption for a host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import wave

import numpy as np

AOSP_WAV_PACKET_FRAMES = 16384
AOSP_WAV_SOURCE = "https://android.googlesource.com/platform/frameworks/av/+/refs/heads/android15-release/media/module/extractors/wav/WAVExtractor.cpp"


def read_pcm16_wav(path):
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() != 16000 or source.getcomptype() != "NONE":
            raise ValueError("This parity helper requires mono 16 kHz PCM16 WAV")
        count = source.getnframes()
        raw = source.readframes(count)
    if len(raw) != count * 2:
        raise ValueError("Truncated WAV")
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / np.float32(32768)


def android_canonical_pcm(samples, packet_frames: int | None = AOSP_WAV_PACKET_FRAMES):
    """Emulate contiguous 16k PCM frames through the unchanged AudioDecoder math.

    No reference text, file identity or hypothesis is accepted. ``packet_frames``
    describes extractor/codec output framing; None models one contiguous packet.
    The default follows AOSP WAV's 32768-byte maximum packet for mono PCM16.
    """
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim != 1 or not np.isfinite(samples).all():
        raise ValueError("Expected a finite mono Float32 sequence")
    if packet_frames is not None and (type(packet_frames) is not int or packet_frames <= 0):
        raise ValueError("packet_frames must be positive or None")
    count = len(samples)
    if not count:
        return samples.copy()
    # AudioDecoder.nextTime starts at 0 and adds 1.0/16000 after every emit.
    output_times = np.empty(count, dtype=np.float64)
    output_times[0] = 0.0
    if count > 1:
        output_times[1:] = np.cumsum(np.full(count - 1, 1.0 / 16000, dtype=np.float64))
    indices = np.arange(count, dtype=np.int64)
    if packet_frames is None:
        input_times = indices.astype(np.float64) / 16000
    else:
        packet_start = (indices // packet_frames) * packet_frames
        # WAVExtractor computes integer-microsecond PTS before MediaCodec delivery.
        pts_us = (packet_start * 1000000) // 16000
        input_times = pts_us.astype(np.float64) / 1000000 + (indices - packet_start).astype(np.float64) / 16000
    # Pick the first input frame satisfying the original while-loop tolerance.
    right = np.searchsorted(input_times + 1e-9, output_times, side="left")
    valid = right < count
    right = right[valid]
    target = output_times[valid]
    left = np.maximum(0, right - 1)
    gap = np.maximum(1e-12, input_times[right] - input_times[left])
    fraction = np.clip((target - input_times[left]) / gap, 0.0, 1.0).astype(np.float32)
    # Keep the three Float32 operations separate; do not replace with Double/FMA.
    difference = np.subtract(samples[right], samples[left], dtype=np.float32)
    scaled = np.multiply(difference, fraction, dtype=np.float32)
    output = np.add(samples[left], scaled, dtype=np.float32)
    # First sample follows previousTime < -0.5 branch and emits the input exactly.
    output[0] = samples[0]
    return output


def scalar_android_canonical_pcm(samples, packet_frames: int | None = AOSP_WAV_PACKET_FRAMES):
    """Small independent loop reference matching Kotlin operation boundaries."""
    output = []
    previous = np.float32(0)
    previous_time = -1.0
    next_time = 0.0
    for index, raw in enumerate(samples):
        value = np.float32(raw)
        if packet_frames is None:
            current_time = index / 16000.0
        else:
            start = (index // packet_frames) * packet_frames
            current_time = ((start * 1000000) // 16000) / 1000000.0 + (index - start) / 16000.0
        if current_time + 1e-8 < previous_time:
            continue
        while next_time <= current_time + 1e-9:
            gap = current_time - previous_time
            if previous_time < -.5 or gap > .1:
                emitted = value if abs(next_time - current_time) < 1.0 / 16000 else np.float32(0)
            else:
                fraction = np.float32(min(1.0, max(0.0, (next_time - previous_time) / max(gap, 1e-12))))
                emitted = np.float32(previous + np.float32(np.float32(value - previous) * fraction))
            output.append(emitted)
            next_time += 1.0 / 16000
        previous = value
        previous_time = current_time
    return np.asarray(output, dtype=np.float32)


def comparison(candidate, actual):
    candidate = np.asarray(candidate, dtype=np.float32)
    actual = np.asarray(actual, dtype=np.float32)
    common = min(len(candidate), len(actual))
    different = candidate[:common].view(np.uint32) != actual[:common].view(np.uint32)
    delta = candidate[:common].astype(np.float64) - actual[:common].astype(np.float64)
    differing_indices = np.flatnonzero(different)
    return {"candidate_samples": len(candidate), "actual_samples": len(actual),
            "bit_exact": len(candidate) == len(actual) and not bool(different.any()),
            "different_samples": int(different.sum()),
            "first_differing_sample": int(differing_indices[0]) if len(differing_indices) else None,
            "maximum_abs_error": float(np.max(np.abs(delta))) if common else None,
            "mean_abs_error": float(np.mean(np.abs(delta))) if common else None,
            "candidate_peak": float(np.max(np.abs(candidate))) if len(candidate) else None,
            "actual_peak": float(np.max(np.abs(actual))) if len(actual) else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--android-pcm", type=Path, help="AudioDecoder Float32 big-endian data")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--packet-frames", type=int, default=AOSP_WAV_PACKET_FRAMES)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve the existing comparison; choose another output")
    raw = read_pcm16_wav(args.audio)
    emulated = android_canonical_pcm(raw, args.packet_frames)
    result = {"scope": "Generic canonical-WAV decoder investigation; no ASR/model/production change",
              "audio_sha256": hashlib.sha256(args.audio.read_bytes()).hexdigest(),
              "aosp_extractor_source": AOSP_WAV_SOURCE, "packet_frames": args.packet_frames,
              "emulated_vs_direct_pcm16": comparison(emulated, raw)}
    if args.android_pcm:
        actual = np.fromfile(args.android_pcm, dtype=">f4").astype(np.float32)
        result["android_pcm_sha256"] = hashlib.sha256(args.android_pcm.read_bytes()).hexdigest()
        result["direct_vs_android"] = comparison(raw, actual)
        result["emulated_vs_android"] = comparison(emulated, actual)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
