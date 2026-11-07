#!/usr/bin/env python3
"""Experimental GigaAM VAD-chunk ASR with verified token-frame speaker projection.

Baseline policies/models remain unchanged. This module never reads references.
Word intervals are real token-emission frame proxies, not forced alignment.
"""
from __future__ import annotations

import argparse
import gc
import json
import mmap
from pathlib import Path
import platform
import time

if __package__:
    from . import pipeline as base
    from . import language_id
    from .vad_words import (words_from_tokens, assign_words, group_words, plan_vad_chunks)
else:
    import pipeline as base
    import language_id
    from vad_words import words_from_tokens, assign_words, group_words, plan_vad_chunks

FALLBACK_WARNING = "Время слов недоступно: проверьте говорящего и границы"
FRAME_SHIFT_PROOF = "https://github.com/k2-fsa/sherpa-onnx/blob/v2.0.1/sherpa-onnx/csrc/offline-recognizer-transducer-nemo-impl.h#L208-L211"


def _varint(buffer, position, end):
    value, shift = 0, 0
    while position < end and shift <= 63:
        byte = buffer[position]
        position += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, position
        shift += 7
    raise ValueError("Invalid ONNX protobuf varint")


def _fields(buffer, start=0, end=None):
    end = len(buffer) if end is None else end
    position = start
    while position < end:
        key, position = _varint(buffer, position, end)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, position = _varint(buffer, position, end)
            yield field, wire, value, value
            continue
        if wire == 2:
            size, position = _varint(buffer, position, end)
        elif wire == 1:
            size = 8
        elif wire == 5:
            size = 4
        else:
            raise ValueError("Unsupported ONNX protobuf wire type")
        last = position + size
        if last > end:
            raise ValueError("Truncated ONNX protobuf field")
        yield field, wire, position, last
        position = last


def encoder_metadata(path: Path) -> dict[str, str]:
    """Read ModelProto.metadata_props while skipping graph/weights without copying."""
    result = {}
    with Path(path).open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        for field, wire, first, last in _fields(data):
            if field != 14 or wire != 2:
                continue
            values = {number: bytes(data[a:b]).decode("utf-8")
                      for number, kind, a, b in _fields(data, first, last) if kind == 2 and number in (1, 2)}
            if 1 in values and 2 in values:
                result[values[1]] = values[2]
    return result


def frame_stride_from_metadata(metadata: dict[str, str]) -> dict:
    if metadata.get("is_giga_am") != "1" or metadata.get("model_type") != "EncDecRNNTBPEModel":
        raise ValueError("Unverified model type for NeMo token timestamp conversion")
    try:
        factor = int(metadata["subsampling_factor"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Missing or invalid model subsampling factor") from error
    if factor <= 0:
        raise ValueError("Invalid model subsampling factor")
    return {"verified": True, "feature_frame_shift_ms": 10, "subsampling_factor": factor,
            "frame_stride_ms": factor * 10, "feature_frame_shift_source": FRAME_SHIFT_PROOF,
            "model_metadata": metadata,
            "precision": "Token emission frame intervals; not acoustic forced-aligned word timestamps"}


def validate_vad_durations(min_speech_sec, min_silence_sec, threshold=.5):
    import math
    for name, value in (("vad_min_speech_sec", min_speech_sec), ("vad_min_silence_sec", min_silence_sec)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not .05 <= value <= 1.0:
            raise ValueError(f"{name} must be a finite duration in 0.05..1.0 seconds")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not .1 <= threshold <= .9:
        raise ValueError("vad_threshold must be finite and in 0.1..0.9")


def make_vad_config(model_root, min_speech_sec, min_silence_sec, sherpa, threshold=.5):
    validate_vad_durations(min_speech_sec, min_silence_sec, threshold)
    return sherpa.VadModelConfig(
        silero_vad=sherpa.SileroVadModelConfig(model=str(Path(model_root) / "vad/silero_vad.onnx"),
            threshold=threshold, min_silence_duration=min_silence_sec, min_speech_duration=min_speech_sec,
            window_size=512, max_speech_duration=20),
        sample_rate=16000, num_threads=1, provider="cpu", debug=False)


def _detect_with_durations(samples, gain, model_root, stages, np, sherpa, min_speech_sec, min_silence_sec, threshold):
    if min_speech_sec == .25 and min_silence_sec == .25 and threshold == .5:
        return base._detect_speech(samples, gain, model_root, stages, np, sherpa)
    with base._measure(stages, "vadLoadMs"):
        detector = sherpa.VoiceActivityDetector(make_vad_config(model_root, min_speech_sec, min_silence_sec, sherpa, threshold),
                                               buffer_size_in_seconds=60)
    found = []
    try:
        with base._measure(stages, "vadMs"):
            def drain():
                while not detector.empty():
                    segment = detector.front
                    found.append(base.Span(segment.start * 1000 // 16000,
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


def process(audio_path, model_root, expected_speakers: int = -1, threads: int = 2,
            punctuation_mode: str = "none", energy_split: bool = True,
            vad_min_speech_sec: float = .25, vad_min_silence_sec: float = .25,
            vad_threshold: float = .5, pre_roll_ms: int = 100, language: str = "ru",
            per_segment_language: bool = False) -> dict:
    if threads not in (1, 2, 4):
        raise ValueError("Current Android policy allows 1, 2 or 4 threads")
    if expected_speakers != -1 and not 1 <= expected_speakers <= 20:
        raise ValueError("expected_speakers must be -1 or 1..20")
    if punctuation_mode not in ("none", "seam"):
        raise ValueError("punctuation_mode must be none or seam")
    if type(energy_split) is not bool:
        raise ValueError("energy_split must be boolean")
    if type(pre_roll_ms) is not int or not 0 <= pre_roll_ms <= 1000:
        raise ValueError("pre_roll_ms must be an integer in 0..1000 milliseconds")
    validate_vad_durations(vad_min_speech_sec, vad_min_silence_sec, vad_threshold)
    if language not in ("ru", "en", "auto") or type(per_segment_language) is not bool:
        raise ValueError("language must be ru, en or auto")
    if per_segment_language and language != "auto":
        raise ValueError("Per-segment language identification requires language=auto")
    import numpy as np
    import sherpa_onnx as sherpa
    if sherpa.__version__ != base.RUNTIME_VERSION:
        raise RuntimeError(f"Need sherpa-onnx {base.RUNTIME_VERSION}; found {sherpa.__version__}")
    audio_path, model_root = Path(audio_path), Path(model_root)
    stages = {}
    started = time.perf_counter_ns()
    mode = "single" if expected_speakers == 1 else "automatic" if expected_speakers == -1 else "fixed"
    with base._measure(stages, "validationMs"):
        model_files, model_bytes = base._verify_models(model_root, mode != "single")
    stride_error = None
    with base._measure(stages, "timestampMetadataMs"):
        try:
            stride = frame_stride_from_metadata(encoder_metadata(model_root / "giga-v3/encoder.int8.onnx"))
        except (ValueError, OSError) as error:
            stride_error = str(error)
            stride = {"verified": False, "frame_stride_ms": None, "reason": stride_error}
    with base._measure(stages, "decodeMs"):
        samples = base._read_canonical_wav(audio_path, np)
    duration_ms = len(samples) * 1000 // 16000
    peak = float(np.max(np.abs(samples)))
    recognition_gain = base.quiet_gain(peak)
    primary = _detect_with_durations(samples, recognition_gain, model_root, stages, np, sherpa,
                                     vad_min_speech_sec, vad_min_silence_sec, vad_threshold)
    spans = primary
    rms = None
    rms_samples = 0
    attempted = False
    rescued = []
    detector_gain = recognition_gain
    decision = base.rescue_decision(len(primary), peak, recognition_gain, None)
    if base.rescue_needs_rms(len(primary), peak, recognition_gain):
        with base._measure(stages, "vadRescueRmsMs"):
            rms = base.sample_rms(samples)
            rms_samples = len(samples)
        decision = base.rescue_decision(len(primary), peak, recognition_gain, rms)
        if decision.should_retry:
            attempted = True
            detector_gain = decision.detector_gain
            with base._measure(stages, "vadRescuePassMs"):
                rescued = _detect_with_durations(samples, detector_gain, model_root, stages, np, sherpa,
                                                 vad_min_speech_sec, vad_min_silence_sec, vad_threshold)
            if rescued:
                spans = rescued
    raw_turns = []
    if mode == "single":
        turns = [base.Turn(0, duration_ms, 0)]
        stages.update(diarizationMs=0.0, diarizationLoadMs=0.0, diarizationInferenceMs=0.0)
    else:
        with base._measure(stages, "diarizationMs"):
            with base._measure(stages, "diarizationLoadMs"):
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
                with base._measure(stages, "diarizationInferenceMs"):
                    output = diarizer.process(samples)
                raw_turns = [base.Turn(max(0, min(duration_ms, base._kotlin_round_ms(t.start))),
                                      max(0, min(duration_ms, base._kotlin_round_ms(t.end))), t.speaker)
                             for t in output.sort_by_start_time()]
                raw_turns = [turn for turn in raw_turns if turn.end_ms > turn.start_ms]
                turns = base.stable_turns(raw_turns)
                del output
            finally:
                del diarizer
                gc.collect()
    bounded = base.context_spans(spans, duration_ms, pre_roll_ms, 0)
    with base._measure(stages, "alignmentMs"):
        chunks = plan_vad_chunks(bounded, samples, max_ms=20000, energy_split=energy_split)
    segments, slice_results = [], []
    fallback_chunks = 0
    all_words = []
    # Language routing (task 07). ru keeps the unchanged GigaAM path; LID only reads audio.
    chunk_languages, strides, language_report = language_id.route(
        language, per_segment_language, chunks, samples, recognition_gain, model_root, threads, stages,
        base._measure, stride, encoder_metadata)

    def make_recognizer(lang):
        if lang == "en":
            return language_id.make_english_recognizer(model_root, threads)
        return sherpa.OfflineRecognizer.from_transducer(
                encoder=str(model_root / "giga-v3/encoder.int8.onnx"),
                decoder=str(model_root / "giga-v3/decoder.onnx"),
                joiner=str(model_root / "giga-v3/joiner.onnx"),
                tokens=str(model_root / "giga-v3/tokens.txt"),
                model_type="nemo_transducer", num_threads=threads, provider="cpu", debug=False,
                sample_rate=16000, feature_dim=80, dither=0.0, decoding_method="greedy_search",
                max_active_paths=4, modeling_unit="", hotwords_file="", blank_penalty=0.0)

    # Russian chunks first, then English; only one recognizer is resident at a time.
    passes = language_id.passes(chunk_languages)
    for pass_language, pass_chunks in passes:
        source = language_id.ENGLISH_SOURCE if pass_language == "en" else base.SOURCE
        stride_ms = strides[pass_language]["frame_stride_ms"]
        with base._measure(stages, "asrLoadMs"):
            recognizer = make_recognizer(pass_language)
        try:
            with base._measure(stages, "asrMs"):
                for chunk_index in pass_chunks:
                    chunk = chunks[chunk_index]
                    with base._measure(stages, "asrReadMs"):
                        pcm = samples[chunk.start_ms * 16:min(chunk.end_ms * 16, len(samples))].copy()
                    if recognition_gain != 1:
                        pcm *= np.float32(recognition_gain)
                    stream = recognizer.create_stream()
                    try:
                        stream.accept_waveform(16000, pcm)
                        inference_start = time.perf_counter_ns()
                        with base._measure(stages, "asrInferenceMs"):
                            recognizer.decode_stream(stream)
                        inference_ms = (time.perf_counter_ns() - inference_start) / 1e6
                        output = stream.result
                        text, tokens, timestamps = output.text.strip(), list(output.tokens), list(output.timestamps)
                        with base._measure(stages, "wordAssignmentMs"):
                            parsed = words_from_tokens(text, tokens, timestamps, chunk.start_ms, chunk.end_ms,
                                                       stride_ms)
                            assigned = assign_words(parsed.words, turns) if parsed.supported else []
                            words_json = [{"startMs": w.start_ms, "endMs": w.end_ms, "text": w.text,
                                           "speakerId": w.speaker, "warnings": list(w.reasons),
                                           "chunkIndex": chunk_index} for w in assigned]
                            all_words.extend(words_json)
                            if parsed.supported:
                                segments.extend(group_words(assigned, source, punctuation_mode))
                            elif text:
                                fallback_chunks += 1
                                # Preserve actual recognition text without inventing word boundaries
                                # or attributing a potentially multispeaker chunk to one voice.
                                segments.append({"startMs": chunk.start_ms, "endMs": chunk.end_ms,
                                                 "speakerId": -1, "text": text, "source": source,
                                                 "warnings": [FALLBACK_WARNING]})
                        slice_results.append({"startMs": chunk.start_ms, "endMs": chunk.end_ms,
                            "speakerId": -1, "text": text, "blank": not bool(text),
                            "inferenceMs": inference_ms, "tokens": tokens, "timestamps": timestamps,
                            "timestampUnit": "seconds within ASR VAD chunk", "words": words_json,
                            "wordAssignmentSupported": parsed.supported, "wordAssignmentReason": parsed.reason,
                            "warnings": [] if parsed.supported else [FALLBACK_WARNING],
                            **({"language": pass_language} if language != "ru" else {})})
                        del output
                    finally:
                        del stream
        finally:
            del recognizer
            gc.collect()
    if len(passes) > 1:
        # Mixed-language order back to the timeline (Python sort is stable).
        segments.sort(key=lambda item: item["startMs"])
        slice_results.sort(key=lambda item: item["startMs"])
        all_words.sort(key=lambda item: (item["startMs"], item["chunkIndex"]))
    if not chunks:
        stages.update(asrLoadMs=0.0, asrInferenceMs=0.0, asrMs=0.0, wordAssignmentMs=0.0)
    processing_ms = (time.perf_counter_ns() - started) / 1e6
    applied = attempted and bool(rescued)
    ort_version = getattr(sherpa, "onnxruntime_version", None)
    if callable(ort_version):
        ort_version = ort_version()
    source_paths = [
        base.PROJECT_ROOT / "app/src/main/java/ru/replika/ml/ProcessingWorker.kt",
        base.PROJECT_ROOT / "app/src/main/java/ru/replika/ml/AsrEngine.kt",
        base.PROJECT_ROOT / "app/src/main/java/ru/replika/ml/AudioDecoder.kt",
        base.PROJECT_ROOT / "app/src/main/java/ru/replika/domain/QuietAudioGain.kt",
        base.PROJECT_ROOT / "app/src/main/java/ru/replika/domain/ZeroSpanVadRescue.kt",
        Path(__file__), Path(__file__).with_name("vad_words.py"),
        Path(__file__).with_name("pipeline.py"), Path(__file__).with_name("decoder_parity.py")]
    diagnostics = {
        "runtime": f"sherpa-onnx {sherpa.__version__}", "onnxruntimeVersion": ort_version,
        "platform": platform.platform(), "pythonVersion": platform.python_version(),
        "scope": "Experimental host VAD-chunk ASR; not enabled production behavior or physical-device acceptance",
        "pipelineVariant": "vad_words_experimental", "turnsUsedForAsrSlicing": False,
        "audioSha256": base._sha256(audio_path), "audioMs": duration_ms, "sampleRate": 16000,
        "originalPcmPeak": peak, "recognitionInputGain": recognition_gain, "vadDetectorGain": detector_gain,
        "vadPrimarySpanCount": len(primary), "vadPrimarySpans": base._span_json(primary),
        "vadRescueAttempted": attempted, "vadRescueApplied": applied,
        "vadRescueRms": rms, "vadRescueRmsSamples": rms_samples, "vadRescueSpanCount": len(rescued),
        "vadRescueReason": ("retry_applied" if applied else "retry_empty") if attempted else decision.reason,
        "vadRescueScope": "detector-only empty-primary retry with the same explicit threshold/min-speech/min-silence policy as primary; ASR gain and original PCM preserved",
        "vadSpans": base._span_json(spans), "asrSpeechSpans": base._span_json(bounded),
        "asrChunks": base._span_json(chunks), "rawDiarizationTurns": base._turn_json(raw_turns),
        "diarizationTurns": base._turn_json(turns), "asrSlices": slice_results,
        "words": all_words, "segments": segments, "stagesMs": stages,
        "backend": language_id.backend_name(chunk_languages, base.SOURCE),
        "clusteringMode": mode, "expectedSpeakers": expected_speakers,
        "modelFiles": model_files, "modelBytes": model_bytes,
        "tokenTimestampPolicy": stride, "tokenTimestampError": stride_error,
        "wordAssignmentSupported": all(strides[x]["verified"] for x in (set(chunk_languages) or {"ru"})) and fallback_chunks == 0,
        "fallbackChunks": fallback_chunks,
        "fallbackPolicy": "Full ASR chunk with unknown speaker and warning; no fabricated word times or second ASR pass",
        "config": {"asrThreads": threads, "vadThreads": 1, "provider": "cpu", "sampleRate": 16000,
                   "featureDim": 80, "dither": 0, "decodingMethod": "greedy_search", "modelType": "nemo_transducer",
                   "vadThreshold": vad_threshold, "vadMinSpeechSec": vad_min_speech_sec, "vadMinSilenceSec": vad_min_silence_sec,
                   "vadWindowSamples": 512, "vadMaxSpeechSec": 20, "preRollMs": pre_roll_ms, "postRollMs": 0,
                   "maxAsrSegmentMs": 20000, "clusterThreshold": .5, "clusterThresholdApplied": mode == "automatic",
                   "segmentationWindowShiftRatio": .1, "diarMinDurationOnSec": .2, "diarMinDurationOffSec": .5,
                   "quietGainTriggerPeak": .01, "quietGainTargetPeak": .1, "quietGainMax": 20,
                   "quietGainSilenceFloor": 1e-6, "rescueTargetRms": .02, "rescuePeakHeadroom": .95,
                   "rescueMinGainRatio": 1.01, "asrSlicing": "bounded VAD only; ignores diarization turns",
                   "energySplit": energy_split, "energyWindowMs": 40, "energySearchMs": 4000,
                   "energyTie": "earliest minimum", "energyCut": "window center", "punctuationMode": punctuation_mode},
        "inputDecoder": {"policy": "unchanged generic AudioDecoder canonical16k timeline emulation",
                         "hostDecoderHelperSha256": base._sha256(Path(__file__).with_name("decoder_parity.py"))},
        "pipelineTimingScope": "per-invocation SHA validation, metadata, canonical decode, unchanged VAD/diarization, VAD chunking, ASR and word assignment; excludes persistence/result JSON serialization",
        "memoryScope": "Host WAV held in memory; not Android bounded-IO/peak RAM parity",
        "validationScope": "Every required file hashed per invocation, unchanged production ModelManager policy",
        "nativeResourcePolicy": "VAD released before diarization; diarizer released before ASR; no retained native model cache",
        "sourceFiles": {str(p.relative_to(base.PROJECT_ROOT)): base._sha256(p) for p in source_paths},
    }
    if language != "ru":
        diagnostics["language"] = language_report
    return {"transcript": base.jury_projection(segments), "diagnostics": diagnostics,
            "duration_ms": duration_ms, "processing_ms": processing_ms}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=base.PROJECT_ROOT / "model-pack")
    parser.add_argument("--expected-speakers", type=int, default=-1)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--punctuation-mode", choices=["none", "seam"], default="none")
    parser.add_argument("--no-energy-split", action="store_true")
    parser.add_argument("--vad-min-speech-sec", type=float, default=.25)
    parser.add_argument("--vad-min-silence-sec", type=float, default=.25)
    parser.add_argument("--vad-threshold", type=float, default=.5)
    parser.add_argument("--pre-roll-ms", type=int, default=100)
    parser.add_argument("--language", choices=["ru", "en", "auto"], default="ru")
    parser.add_argument("--per-segment-language", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve existing evidence; choose a new output")
    result = process(args.audio, args.model_root, args.expected_speakers, args.threads,
                     args.punctuation_mode, not args.no_energy_split,
                     args.vad_min_speech_sec, args.vad_min_silence_sec, args.vad_threshold, args.pre_roll_ms,
                     language=args.language, per_segment_language=args.per_segment_language)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "duration_ms": result["duration_ms"],
        "processing_ms": result["processing_ms"], "segments": len(result["transcript"]),
        "fallback_chunks": result["diagnostics"]["fallbackChunks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
