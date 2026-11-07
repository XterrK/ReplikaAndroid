#!/usr/bin/env python3
"""Pinned V1.6 host baseline, without changing the Android recognition policy.

Input is deliberately restricted to canonical 16 kHz mono PCM16 WAV. Its PCM
timeline emulates AudioDecoder's Double clock and Float32 interpolation using
AOSP WAV packet framing. Python I/O, ONNX Runtime binaries, allocation and timing
still differ from Android; this is not a phone speed claim.
References never enter this module. Native models are released between stages.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, replace
import gc
import hashlib
import json
import os
import math
from pathlib import Path
import platform
import struct
import time
import wave

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = PROJECT_ROOT / "app/src/main/assets/models-lock.json"
ENCODER_LOCK_PATH = "giga-v3/encoder.int8.onnx"
ENCODER_OVERRIDE = os.environ.get("REPLIKA_ENCODER_OVERRIDE", "")


def encoder_file(model_root) -> Path:
    """The GigaAM encoder to load: the pinned INT8 file unless REPLIKA_ENCODER_OVERRIDE is set."""
    return Path(ENCODER_OVERRIDE) if ENCODER_OVERRIDE else Path(model_root) / ENCODER_LOCK_PATH
RUNTIME_VERSION = "2.0.1"
SOURCE = "GigaAM v3 E2E RNNT INT8 / sherpa-onnx 2.0.1"
SHORT = "Короткая реплика возле границы"
UNKNOWN = "Неоднозначный говорящий"
OVERLAP = "Пересечение голосов: слова не разделены"
EDGE = "Короткая граница диаризации: проверьте слова"
CUT = "Разрез длинного интервала: проверьте границу слов"


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


@dataclass(frozen=True)
class Span:
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Turn:
    start_ms: int
    end_ms: int
    speaker: int


@dataclass(frozen=True)
class Slice:
    start_ms: int
    end_ms: int
    speaker: int
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RescueDecision:
    should_retry: bool
    detector_gain: float
    reason: str


def quiet_gain(peak: float) -> float:
    """Float32 arithmetic from QuietAudioGain.forPeak; no signal mutation."""
    peak = _f32(peak)
    if not math.isfinite(peak) or peak <= _f32(1e-6) or peak >= _f32(.01):
        return 1.0
    return min(20.0, _f32(_f32(.1) / peak))


def _rescue_skip_reason(primary_count: int, peak: float, gain: float) -> str | None:
    if primary_count > 0:
        return "primary_nonempty"
    if primary_count < 0:
        return "invalid_primary_span_count"
    if not math.isfinite(peak) or peak < 0:
        return "invalid_peak"
    if peak <= _f32(1e-6):
        return "silence_or_near_silence"
    if not math.isfinite(gain) or gain < 1 or gain > 20:
        return "invalid_recognition_gain"
    if gain >= 20:
        return "gain_at_cap"
    return None


def rescue_needs_rms(primary_count: int, peak: float, recognition_gain: float) -> bool:
    return _rescue_skip_reason(primary_count, _f32(peak), _f32(recognition_gain)) is None


def rescue_decision(primary_count: int, peak: float, recognition_gain: float,
                    rms: float | None) -> RescueDecision:
    peak, recognition_gain = _f32(peak), _f32(recognition_gain)
    unchanged = recognition_gain if math.isfinite(recognition_gain) and 1 <= recognition_gain <= 20 else 1.0
    skip = _rescue_skip_reason(primary_count, peak, recognition_gain)
    if skip:
        return RescueDecision(False, unchanged, skip)
    if rms is None or not math.isfinite(rms) or rms <= 0 or rms > peak * 1.00001:
        return RescueDecision(False, unchanged, "invalid_or_empty_rms")
    gain = max(recognition_gain, min(.02 / rms, 20.0, .95 / peak))
    if gain <= recognition_gain * 1.01:
        return RescueDecision(False, unchanged, "no_meaningful_gain")
    return RescueDecision(True, _f32(gain), "retry_requested")


def sample_rms(samples) -> float | None:
    """Same sequential Double accumulation over Float32 inputs as Kotlin."""
    squares = 0.0
    count = 0
    valid = True
    for sample in samples:
        value = float(sample)
        count += 1
        if not math.isfinite(value):
            valid = False
        else:
            squares += value * value
    return math.sqrt(squares / count) if valid and count and math.isfinite(squares) else None


def merge_spans(spans: list[Span]) -> list[Span]:
    out: list[Span] = []
    for span in sorted((s for s in spans if s.end_ms > s.start_ms), key=lambda s: s.start_ms):
        if out and span.start_ms <= out[-1].end_ms:
            out[-1] = Span(out[-1].start_ms, max(out[-1].end_ms, span.end_ms))
        else:
            out.append(span)
    return out


def context_spans(spans: list[Span], duration_ms: int, pre_ms: int = 100,
                  post_ms: int = 0) -> list[Span]:
    if min(duration_ms, pre_ms, post_ms) < 0:
        raise ValueError("Duration and context must be nonnegative")
    bounded = []
    for span in spans:
        if span.end_ms <= span.start_ms:
            continue
        start = max(0, min(duration_ms, span.start_ms) - min(pre_ms, duration_ms))
        end = max(0, min(duration_ms, span.end_ms))
        end += min(post_ms, duration_ms - end)
        bounded.append(Span(start, end))
    return merge_spans(bounded)


def stable_turns(turns: list[Turn]) -> list[Turn]:
    numbers: dict[int, int] = {}
    out = []
    for turn in sorted(turns, key=lambda t: (t.start_ms, t.speaker)):
        speaker = -1 if turn.speaker < 0 else numbers.setdefault(turn.speaker, len(numbers))
        out.append(replace(turn, speaker=speaker))
    return out


def alignment_slices(speech: list[Span], turns: list[Turn], max_ms: int = 20000) -> list[Slice]:
    """Port of Alignment.slices, including warning provenance and coalescing."""
    if max_ms <= 0:
        raise ValueError("max_ms must be positive")
    out = []
    for span in merge_spans(speech):
        boundaries = sorted({span.start_ms, span.end_ms} | {
            value for turn in turns for value in (turn.start_ms, turn.end_ms)
            if span.start_ms < value < span.end_ms
        })
        partitions: list[Slice] = []
        for start, end in zip(boundaries, boundaries[1:]):
            active = list(dict.fromkeys(t.speaker for t in turns if t.start_ms < end and t.end_ms > start))
            speaker = active[0] if len(active) == 1 else -1
            reasons = tuple(([OVERLAP] if len(active) > 1 else []) + ([UNKNOWN] if speaker < 0 else []))
            if partitions and partitions[-1].end_ms == start and partitions[-1].speaker == speaker and partitions[-1].reasons == reasons:
                partitions[-1] = replace(partitions[-1], end_ms=end)
            else:
                partitions.append(Slice(start, end, speaker, reasons))
        for part in partitions:
            reasons = part.reasons + ((SHORT,) if part.end_ms - part.start_ms < 700 else ())
            start = part.start_ms
            while start < part.end_ms:
                end = start + min(max_ms, part.end_ms - start)
                cuts = (CUT,) if end < part.end_ms or start > part.start_ms else ()
                out.append(Slice(start, end, part.speaker, reasons + cuts))
                start = end
    return out


def plan_recognition(speech: list[Span], turns: list[Turn], max_ms: int = 20000) -> list[Slice]:
    """Exact baseline RecognitionPlanner, not task3's proposed word planner."""
    if max_ms <= 0:
        raise ValueError("max_ms must be positive")
    result = []
    for span in merge_spans(speech):
        original = alignment_slices([span], turns, (1 << 63) - 1)
        repaired = []
        for index, part in enumerate(original):
            left = original[index - 1] if index else None
            right = original[index + 1] if index + 1 < len(original) else None
            candidates = set(t.speaker for t in (left, right) if t is not None and t.speaker >= 0)
            edge = (left is None or left.speaker >= 0) and (right is None or right.speaker >= 0)
            if part.speaker < 0 and part.end_ms - part.start_ms <= 300 and not any(r.startswith("Пересечение") for r in part.reasons) and len(candidates) == 1 and edge:
                repaired.append(replace(part, speaker=next(iter(candidates)), reasons=(EDGE,)))
            else:
                repaired.append(part)
        merged: list[Slice] = []
        for part in repaired:
            if merged and merged[-1].end_ms == part.start_ms and merged[-1].speaker == part.speaker:
                merged[-1] = replace(merged[-1], end_ms=part.end_ms,
                                     reasons=tuple(dict.fromkeys(merged[-1].reasons + part.reasons)))
            else:
                merged.append(part)
        for part in merged:
            start = part.start_ms
            while start < part.end_ms:
                end = start + min(max_ms, part.end_ms - start)
                cuts = (CUT,) if start > part.start_ms or end < part.end_ms else ()
                result.append(replace(part, start_ms=start, end_ms=end, reasons=part.reasons + cuts))
                start = end
    return result


def jury_projection(segments: list[dict]) -> list[dict]:
    """Same export-only unknown remap and numbering as domain/JuryJson.kt."""
    ordered = sorted((s for s in segments if s["text"].strip()), key=lambda s: (s["startMs"], s["endMs"]))
    if any(s["startMs"] < 0 or s["endMs"] < s["startMs"] for s in ordered):
        raise ValueError("Invalid transcript timestamps")
    known = [s for s in ordered if s["speakerId"] >= 0]
    numbers = {}
    out = []
    for segment in ordered:
        speaker = segment["speakerId"]
        if speaker < 0:
            nearest = min(known, default=None, key=lambda s: (
                max(0, s["startMs"] - segment["endMs"], segment["startMs"] - s["endMs"]), s["startMs"], s["endMs"]))
            speaker = nearest["speakerId"] if nearest is not None else 0
        number = numbers.setdefault(speaker, len(numbers) + 1)
        out.append({"speaker_id": f"speaker_{number}", "start_ms": segment["startMs"],
                    "end_ms": segment["endMs"], "text": segment["text"]})
    return out


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _verify_models(model_root: Path, include_diarization: bool) -> tuple[list[dict], int]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    groups = {"giga-v3", "vad"} | ({"diar"} if include_diarization else set())
    if {f["group"] for f in manifest["files"] if f["group"].startswith("giga-")} != {"giga-v3"}:
        raise ValueError("This baseline requires the pinned GigaAM v3 manifest")
    records = []
    for spec in manifest["files"]:
        if spec["group"] not in groups:
            continue
        path = model_root / spec["path"]
        if spec["path"] == ENCODER_LOCK_PATH and ENCODER_OVERRIDE:
            # Experiment-only: an alternative encoder (e.g. FP32) replaces the pinned INT8 file.
            override = Path(ENCODER_OVERRIDE)
            records.append({"path": spec["path"], "override": str(override), "bytes": override.stat().st_size,
                            "sha256": _sha256(override), "hashValidationCached": False})
            continue
        stat = path.stat()
        if stat.st_size != spec["size"]:
            raise ValueError(f"Model size mismatch: {spec['path']}")
        # Android ModelManager.requireReady hashes every required file on each Worker
        # invocation. Revalidate each host case too, so warm runs do not omit this cost.
        actual = _sha256(path)
        if actual != spec["sha256"]:
            raise ValueError(f"Model SHA-256 mismatch: {spec['path']}")
        records.append({"path": spec["path"], "bytes": stat.st_size, "sha256": actual, "hashValidationCached": False})
    return records, sum(f["size"] for f in manifest["files"])


@contextmanager
def _measure(stages: dict, name: str):
    start = time.perf_counter_ns()
    try:
        yield
    finally:
        stages[name] = stages.get(name, 0.0) + (time.perf_counter_ns() - start) / 1e6


def _read_canonical_wav(path: Path, np):
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getframerate() != 16000 or source.getsampwidth() != 2 or source.getcomptype() != "NONE":
            raise ValueError("Baseline accepts only 16 kHz mono PCM16 WAV; canonicalize explicitly before evaluation")
        count = source.getnframes()
        raw = source.readframes(count)
    if not count or len(raw) != count * 2:
        raise ValueError("Empty or truncated WAV")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / np.float32(32768)
    # Even at matching input/output rates Android AudioDecoder does not bypass
    # its incremental Double output clock and Float32 interpolation. Reproduce
    # that generic policy, rather than feeding the recognizer direct PCM16.
    if __package__:
        from .decoder_parity import android_canonical_pcm
    else:
        from decoder_parity import android_canonical_pcm
    return android_canonical_pcm(samples)


def _detect_speech(samples, gain: float, model_root: Path, stages: dict, np, sherpa) -> list[Span]:
    with _measure(stages, "vadLoadMs"):
        config = sherpa.VadModelConfig(
            silero_vad=sherpa.SileroVadModelConfig(model=str(model_root / "vad/silero_vad.onnx"),
                threshold=.5, min_silence_duration=.25, min_speech_duration=.25,
                window_size=512, max_speech_duration=20),
            sample_rate=16000, num_threads=1, provider="cpu", debug=False)
        detector = sherpa.VoiceActivityDetector(config, buffer_size_in_seconds=60)
    found = []
    try:
        with _measure(stages, "vadMs"):
            def drain():
                while not detector.empty():
                    segment = detector.front
                    found.append(Span(segment.start * 1000 // 16000,
                                      (segment.start + len(segment.samples)) * 1000 // 16000))
                    detector.pop()
            for offset in range(0, len(samples), 512):
                block = np.zeros(512, dtype=np.float32)
                count = min(512, len(samples) - offset)
                block[:count] = samples[offset:offset + count]
                if gain != 1:
                    block *= np.float32(gain)
                detector.accept_waveform(block)
                drain()
            detector.flush()
            drain()
    finally:
        del detector
        gc.collect()
    return found


def _kotlin_round_ms(seconds: float) -> int:
    # Kotlin multiplies Float seconds by 1000 before roundToLong (ties toward +infinity).
    return math.floor(_f32(_f32(seconds) * 1000) + .5)


def _span_json(spans):
    return [{"startMs": s.start_ms, "endMs": s.end_ms} for s in spans]


def _turn_json(turns):
    return [{"startMs": t.start_ms, "endMs": t.end_ms, "speakerId": t.speaker} for t in turns]


def process(audio_path, model_root, expected_speakers: int = -1, threads: int = 2) -> dict:
    """Run one untuned baseline. Does not read references or persist mutable native models."""
    if threads not in (1, 2, 4):
        raise ValueError("Current Android policy allows 1, 2 or 4 threads")
    if expected_speakers != -1 and not 1 <= expected_speakers <= 20:
        raise ValueError("expected_speakers must be -1 or 1..20")
    import numpy as np
    import sherpa_onnx as sherpa
    if sherpa.__version__ != RUNTIME_VERSION:
        raise RuntimeError(f"Need sherpa-onnx {RUNTIME_VERSION}; found {sherpa.__version__}")
    audio_path, model_root = Path(audio_path), Path(model_root)
    stages = {}
    started = time.perf_counter_ns()
    mode = "single" if expected_speakers == 1 else "automatic" if expected_speakers == -1 else "fixed"
    with _measure(stages, "validationMs"):
        model_files, model_bytes = _verify_models(model_root, mode != "single")
    with _measure(stages, "decodeMs"):
        samples = _read_canonical_wav(audio_path, np)
    duration_ms = len(samples) * 1000 // 16000
    peak = float(np.max(np.abs(samples)))
    recognition_gain = quiet_gain(peak)
    primary = _detect_speech(samples, recognition_gain, model_root, stages, np, sherpa)
    spans = primary
    rms = None
    rms_samples = 0
    attempted = False
    rescue_spans = []
    detector_gain = recognition_gain
    decision = rescue_decision(len(primary), peak, recognition_gain, None)
    if rescue_needs_rms(len(primary), peak, recognition_gain):
        with _measure(stages, "vadRescueRmsMs"):
            rms = sample_rms(samples)
            rms_samples = len(samples)
        decision = rescue_decision(len(primary), peak, recognition_gain, rms)
        if decision.should_retry:
            attempted = True
            detector_gain = decision.detector_gain
            with _measure(stages, "vadRescuePassMs"):
                rescue_spans = _detect_speech(samples, detector_gain, model_root, stages, np, sherpa)
            if rescue_spans:
                spans = rescue_spans
    raw_turns = []
    if mode == "single":
        turns = [Turn(0, duration_ms, 0)]
        stages.update(diarizationMs=0.0, diarizationLoadMs=0.0, diarizationInferenceMs=0.0)
    else:
        with _measure(stages, "diarizationMs"):
            with _measure(stages, "diarizationLoadMs"):
                config = sherpa.OfflineSpeakerDiarizationConfig(
                    segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
                        pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(
                            model=str(model_root / "diar/segmentation.onnx"), window_shift_ratio=.1),
                        num_threads=threads, provider="cpu", debug=False),
                    embedding=sherpa.SpeakerEmbeddingExtractorConfig(model=str(model_root / "diar/embedding.onnx"),
                        num_threads=threads, provider="cpu", debug=False),
                    clustering=sherpa.FastClusteringConfig(num_clusters=expected_speakers, threshold=.5, compute_confidence=False),
                    min_duration_on=.2, min_duration_off=.5)
                diarizer = sherpa.OfflineSpeakerDiarization(config)
            try:
                with _measure(stages, "diarizationInferenceMs"):
                    output = diarizer.process(samples)
                raw_turns = [Turn(max(0, min(duration_ms, _kotlin_round_ms(t.start))),
                                  max(0, min(duration_ms, _kotlin_round_ms(t.end))), t.speaker)
                             for t in output.sort_by_start_time()]
                raw_turns = [t for t in raw_turns if t.end_ms > t.start_ms]
                turns = stable_turns(raw_turns)
                del output
            finally:
                del diarizer
                gc.collect()
    bounded = context_spans(spans, duration_ms, 100, 0)
    with _measure(stages, "alignmentMs"):
        slices = plan_recognition(bounded, turns)
    segments = []
    slice_results = []
    if slices:
        with _measure(stages, "asrLoadMs"):
            recognizer = sherpa.OfflineRecognizer.from_transducer(
                encoder=str(model_root / "giga-v3/encoder.int8.onnx"),
                decoder=str(model_root / "giga-v3/decoder.onnx"),
                joiner=str(model_root / "giga-v3/joiner.onnx"),
                tokens=str(model_root / "giga-v3/tokens.txt"),
                model_type="nemo_transducer", num_threads=threads, provider="cpu", debug=False,
                sample_rate=16000, feature_dim=80, dither=0.0, decoding_method="greedy_search",
                max_active_paths=4, modeling_unit="", hotwords_file="", blank_penalty=0.0)
        try:
            with _measure(stages, "asrMs"):
                for part in slices:
                    with _measure(stages, "asrReadMs"):
                        chunk = samples[part.start_ms * 16:min(part.end_ms * 16, len(samples))].copy()
                    if recognition_gain != 1:
                        chunk *= np.float32(recognition_gain)
                    stream = recognizer.create_stream()
                    try:
                        stream.accept_waveform(16000, chunk)
                        inference_started = time.perf_counter_ns()
                        with _measure(stages, "asrInferenceMs"):
                            recognizer.decode_stream(stream)
                        inference_ms = (time.perf_counter_ns() - inference_started) / 1e6
                        output = stream.result
                        text = output.text.strip()
                        row = {"startMs": part.start_ms, "endMs": part.end_ms, "speakerId": part.speaker,
                               "text": text, "blank": not bool(text), "inferenceMs": inference_ms,
                               "warnings": list(part.reasons), "tokens": list(output.tokens),
                               "timestamps": list(output.timestamps), "timestampUnit": "seconds within ASR slice"}
                        durations = getattr(output, "durations", [])
                        if durations:
                            row["durations"] = list(durations)
                        slice_results.append(row)
                        if text:
                            segments.append({"startMs": part.start_ms, "endMs": part.end_ms,
                                             "speakerId": part.speaker, "text": text, "source": SOURCE,
                                             "warnings": list(part.reasons)})
                        del output
                    finally:
                        del stream
        finally:
            del recognizer
            gc.collect()
    else:
        stages.update(asrLoadMs=0.0, asrInferenceMs=0.0, asrMs=0.0)
    processing_ms = (time.perf_counter_ns() - started) / 1e6
    applied = attempted and bool(rescue_spans)
    ort_version = getattr(sherpa, "onnxruntime_version", None)
    if callable(ort_version):
        ort_version = ort_version()
    diagnostics = {
        "runtime": f"sherpa-onnx {sherpa.__version__}", "onnxruntimeVersion": ort_version,
        "platform": platform.platform(), "pythonVersion": platform.python_version(),
        "scope": "Host configuration/planner baseline; canonical PCM16 input; not Android/ARM/phone performance acceptance",
        "audioSha256": _sha256(audio_path), "audioMs": duration_ms, "sampleRate": 16000,
        "inputDecoder": {
            "policy": "canonical mono PCM16/16k through unchanged AudioDecoder timeline math",
            "wavPacketBytes": 32768, "wavPacketFrames": 16384,
            "packetPts": "floor(packetStartFrame*1000000/16000) integer microseconds",
            "outputClock": "Double nextTime=0; repeated nextTime+=1.0/16000 per emit",
            "emitToleranceSeconds": 1e-9,
            "interpolation": "Float32 factor, subtraction, multiplication and addition; no FMA",
            "sourceDecoderSha256": _sha256(PROJECT_ROOT / "app/src/main/java/ru/replika/ml/AudioDecoder.kt"),
            "sourceLowPassSha256": _sha256(PROJECT_ROOT / "app/src/main/java/ru/replika/domain/PcmLowPass.kt"),
            "hostDecoderHelperSha256": _sha256(Path(__file__).with_name("decoder_parity.py")),
            "scope": "AOSP canonical-WAV framing; other rates/formats intentionally rejected; runtime math differences remain independently evaluated"},
        "originalPcmPeak": peak, "recognitionInputGain": recognition_gain, "vadDetectorGain": detector_gain,
        "vadPrimarySpanCount": len(primary), "vadPrimarySpans": _span_json(primary),
        "vadRescueAttempted": attempted, "vadRescueApplied": applied,
        "vadRescueRms": rms, "vadRescueRmsSamples": rms_samples, "vadRescueSpanCount": len(rescue_spans),
        "vadRescueReason": ("retry_applied" if applied else "retry_empty") if attempted else decision.reason,
        "vadRescueScope": "detector-only empty-primary retry; ASR gain and stored input unchanged",
        "vadSpans": _span_json(spans), "asrSpeechSpans": _span_json(bounded),
        "rawDiarizationTurns": _turn_json(raw_turns), "diarizationTurns": _turn_json(turns),
        "asrSlices": slice_results, "segments": segments, "stagesMs": stages,
        "backend": SOURCE, "clusteringMode": mode, "expectedSpeakers": expected_speakers,
        "modelFiles": model_files, "modelBytes": model_bytes,
        "config": {"asrThreads": threads, "vadThreads": 1, "provider": "cpu", "sampleRate": 16000,
                   "featureDim": 80, "dither": 0, "decodingMethod": "greedy_search", "modelType": "nemo_transducer",
                   "vadThreshold": .5, "vadMinSpeechSec": .25, "vadMinSilenceSec": .25,
                   "vadWindowSamples": 512, "vadMaxSpeechSec": 20, "preRollMs": 100, "postRollMs": 0,
                   "maxAsrSegmentMs": 20000, "edgeToleranceMs": 300, "clusterThreshold": .5,
                   "clusterThresholdApplied": mode == "automatic", "segmentationWindowShiftRatio": .1,
                   "diarMinDurationOnSec": .2, "diarMinDurationOffSec": .5,
                   "quietGainTriggerPeak": .01, "quietGainTargetPeak": .1,
                   "quietGainMax": 20, "quietGainSilenceFloor": 1e-6,
                   "rescueTargetRms": .02, "rescuePeakHeadroom": .95, "rescueMinGainRatio": 1.01,
                   "arithmetic": "Float32 gains and buffers; sequential Double RMS"},
        "pipelineTimingScope": "host per-invocation SHA validation, canonical WAV read, VAD, diarization, planner, ASR release; excludes persistence and result JSON serialization",
        "validationScope": "Every required model is hashed on every invocation, matching ModelManager.requireReady; no cross-case SHA cache",
        "memoryScope": "Host WAV held in memory; no claim of Android bounded-IO/peak RAM parity",
        "nativeResourcePolicy": "VAD released before diarization; diarizer released before ASR; no retained native model cache",
        "sourceFiles": {str(p.relative_to(PROJECT_ROOT)): _sha256(p) for p in [
            PROJECT_ROOT / "app/src/main/java/ru/replika/ml/ProcessingWorker.kt",
            PROJECT_ROOT / "app/src/main/java/ru/replika/ml/AsrEngine.kt",
            PROJECT_ROOT / "app/src/main/java/ru/replika/ml/AudioDecoder.kt",
            PROJECT_ROOT / "app/src/main/java/ru/replika/domain/PcmLowPass.kt",
            PROJECT_ROOT / "app/src/main/java/ru/replika/domain/Transcript.kt",
            PROJECT_ROOT / "app/src/main/java/ru/replika/domain/TranscriptPresentation.kt",
            PROJECT_ROOT / "app/src/main/java/ru/replika/domain/QuietAudioGain.kt",
            PROJECT_ROOT / "app/src/main/java/ru/replika/domain/ZeroSpanVadRescue.kt",
            PROJECT_ROOT / "app/src/main/java/ru/replika/domain/JuryJson.kt"]},
    }
    return {"transcript": jury_projection(segments), "diagnostics": diagnostics,
            "duration_ms": duration_ms, "processing_ms": processing_ms}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=PROJECT_ROOT / "model-pack")
    parser.add_argument("--expected-speakers", type=int, default=-1)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; preserve it and choose another path")
    result = process(args.audio, args.model_root, args.expected_speakers, args.threads)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "duration_ms": result["duration_ms"],
                      "processing_ms": result["processing_ms"], "segments": len(result["transcript"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
