#!/usr/bin/env python3
"""Full actual C1/C2 host candidates with the frozen D context600 VAD/ASR policy.

The orchestration is an explicit fork of pipeline_words.process. Its canonical
decoder, VAD/rescue, gains, VAD-only energy cuts and greedy GigaAM calls are
unchanged. SD uses a separately catalog-pinned embedder, followed by new clean
window embeddings and an explicit frozen centroid or window refiner. No references or ASR replay exist
in this API. Packaged baseline helpers and Android model policy are not edited.
"""
from __future__ import annotations

from dataclasses import asdict
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import time

from tools.eval import pipeline as base
from tools.eval import pipeline_words as words
from tools.eval import diar_sweep
from tools.eval.run import confined
from tools.eval.speaker_refiner import EmbeddingWindow, RefineConfig, clean_windows, refine
from tools.eval.vad_words import assign_words, group_words, plan_vad_chunks, words_from_tokens
from tools.eval.window_overcluster import WindowClusterConfig, overcluster

PAIRED_ASR_POLICY = {"plan": "vad_words_context600", "vad_threshold": .5,
    "vad_min_speech_sec": .25, "vad_min_silence_sec": .25, "pre_roll_ms": 600,
    "punctuation_mode": "none", "energy_split": True, "threads": 2, "provider": "cpu",
    "sample_rate": 16000, "feature_dim": 80, "dither": 0., "model_type": "nemo_transducer",
    "decoding_method": "greedy_search", "max_active_paths": 4, "modeling_unit": "",
    "hotwords_file": "", "blank_penalty": 0., "vad_window_samples": 512, "max_asr_ms": 20000}

_UNSET = object()
C2_WINDOW_CONFIG = {"tau": .36, "method": "average", "grid_ms": 125, "max_speakers": 8,
    "reassign_small": True, "min_cluster_ms": 2000, "min_cluster_fraction": .03,
    "minimum_reassignment_similarity": None, "smooth": True, "smooth_ms": 500}
C2_EMBEDDING_PIN = {"id": "eres2net_zh", "sha256": "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b",
    "size": 39593761, "embedding_dimension": 512, "repoRelative": True,
    "path": "model-pack/diar/embedding.onnx", "baseline": True}


def validate_options(expected_speakers=-1, threads=2, *, model_id="wespeaker_resnet34_lm",
        window_shift=.1, native_threshold=.5, refiner_tau=_UNSET,
        minimum_reassignment_similarity=_UNSET, missing_centroid_policy=_UNSET,
        strategy="centroid_v1", window_config=None):
    if type(expected_speakers) is not int or expected_speakers != -1:
        raise ValueError("The C candidate is automatic only; known/oracle K is forbidden")
    if type(threads) is not int or threads != 2:
        raise ValueError("The paired D/C policy requires exactly two ASR/SD threads")
    if not isinstance(model_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", model_id):
        raise ValueError("Invalid catalog model ID")
    if type(window_shift) not in (int, float) or window_shift not in (.1, .25, .5):
        raise ValueError("window_shift must be 0.1, 0.25 or 0.5")
    if (type(native_threshold) not in (int, float) or not math.isfinite(native_threshold)
            or not .05 <= native_threshold <= .99):
        raise ValueError("native_threshold must be finite within .05..99")
    if strategy not in ("centroid_v1", "window_v1"):
        raise ValueError("Unknown C refinement strategy")
    if strategy == "window_v1":
        if any(value is not _UNSET for value in
               (refiner_tau, minimum_reassignment_similarity, missing_centroid_policy)):
            raise ValueError("C1 refiner options cannot be mixed with the C2 window strategy")
        if model_id != "eres2net_zh" or window_shift != .1 or native_threshold != .3:
            raise ValueError("C2 requires the frozen ERes2Net native0.3/shift0.1 policy")
        if not isinstance(window_config, dict) or set(window_config) != set(C2_WINDOW_CONFIG):
            raise ValueError("C2 requires the complete frozen window_config")
        config = WindowClusterConfig(**window_config)
        overcluster([], [], 0, config)  # No models, references or audio.
        if asdict(config) != C2_WINDOW_CONFIG:
            raise ValueError("C2 window_config differs from the frozen global candidate")
        return config
    if window_config is not None:
        raise ValueError("C2 window_config cannot be mixed with the C1 strategy")
    # Sentinels preserve C1's historical defaults while detecting any explicit
    # C1-only option in C2, including an explicit value equal to that default.
    config = RefineConfig(merge_threshold=.7 if refiner_tau is _UNSET else refiner_tau,
        minimum_reassignment_similarity=.7 if minimum_reassignment_similarity is _UNSET else minimum_reassignment_similarity,
        small_missing_centroid_policy="temporal" if missing_centroid_policy is _UNSET else missing_centroid_policy)
    refine([], [], 0, config)  # Pure option validation, without model construction.
    return config


def verify_embedding(catalog_path, embedding_root, model_id):
    catalog_path = Path(catalog_path)
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes)
    if catalog.get("schema_version") != 1 or catalog.get("required_runtime") != base.RUNTIME_VERSION:
        raise ValueError("Catalog schema/runtime differs from pinned C research")
    entries = [entry for entry in catalog["models"] if entry.get("id") == model_id]
    if len(entries) != 1:
        raise ValueError("Catalog model ID must be unique and present")
    entry = entries[0]
    if (type(entry.get("repoRelative")) is not bool or type(entry.get("size")) is not int
            or entry["size"] <= 0 or type(entry.get("embedding_dimension")) is not int
            or entry["embedding_dimension"] <= 0 or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
        raise ValueError("Invalid catalog model pin/metadata")
    if not entry["repoRelative"] and embedding_root is None:
        raise ValueError("An explicit embedding_root is required for the external candidate")
    model = confined(base.PROJECT_ROOT if entry["repoRelative"] else Path(embedding_root), entry["path"])
    if model.stat().st_size != entry["size"] or base._sha256(model) != entry["sha256"]:
        raise ValueError("External embedding model SHA/size differs from catalog")
    return model, entry, hashlib.sha256(catalog_bytes).hexdigest()


def validate_embedding_policy(entry, strategy="centroid_v1"):
    if strategy == "window_v1" and any(type(entry.get(key)) is not type(value) or entry[key] != value
                                        for key, value in C2_EMBEDDING_PIN.items()):
        raise ValueError("C2 catalog entry differs from the frozen baseline ERes2Net pin")


def process(audio_path, model_root, expected_speakers=-1, threads=2, *,
        catalog_path=base.PROJECT_ROOT / "configs/eval/diar-models.json", embedding_root=None,
        model_id="wespeaker_resnet34_lm", window_shift=.1, native_threshold=.5,
        refiner_tau=_UNSET, minimum_reassignment_similarity=_UNSET, missing_centroid_policy=_UNSET,
        strategy="centroid_v1", window_config=None):
    refiner_config = validate_options(expected_speakers, threads, model_id=model_id,
        window_shift=window_shift, native_threshold=native_threshold, refiner_tau=refiner_tau,
        minimum_reassignment_similarity=minimum_reassignment_similarity,
        missing_centroid_policy=missing_centroid_policy, strategy=strategy, window_config=window_config)
    started = time.perf_counter_ns()
    import numpy as np
    import sherpa_onnx as sherpa
    from sherpa_onnx.lib import _sherpa_onnx as runtime
    if sherpa.__version__ != base.RUNTIME_VERSION:
        raise RuntimeError("Pinned sherpa-onnx " + base.RUNTIME_VERSION + " required")
    audio_path, model_root = Path(audio_path), Path(model_root)
    stages = {}
    with base._measure(stages, "validationMs"):
        model_files, model_bytes = base._verify_models(model_root, True)
        embedding, entry, catalog_hash = verify_embedding(catalog_path, embedding_root, model_id)
        validate_embedding_policy(entry, strategy)
    stride_error = None
    with base._measure(stages, "timestampMetadataMs"):
        try:
            stride = words.frame_stride_from_metadata(words.encoder_metadata(model_root / "giga-v3/encoder.int8.onnx"))
        except (ValueError, OSError) as error:
            stride_error = str(error)
            stride = {"verified": False, "frame_stride_ms": None, "reason": stride_error}
    with base._measure(stages, "decodeMs"):
        samples = base._read_canonical_wav(audio_path, np)
    duration_ms = len(samples) * 1000 // 16000
    peak = float(np.max(np.abs(samples)))
    recognition_gain = base.quiet_gain(peak)
    # Exact original D VAD settings, including its empty-primary detector-only rescue.
    primary = words._detect_with_durations(samples, recognition_gain, model_root, stages, np, sherpa, .25, .25, .5)
    spans, rms, rms_samples, attempted, rescued, detector_gain = primary, None, 0, False, [], recognition_gain
    decision = base.rescue_decision(len(primary), peak, recognition_gain, None)
    if base.rescue_needs_rms(len(primary), peak, recognition_gain):
        with base._measure(stages, "vadRescueRmsMs"):
            rms, rms_samples = base.sample_rms(samples), len(samples)
        decision = base.rescue_decision(len(primary), peak, recognition_gain, rms)
        if decision.should_retry:
            attempted, detector_gain = True, decision.detector_gain
            with base._measure(stages, "vadRescuePassMs"):
                rescued = words._detect_with_durations(samples, detector_gain, model_root, stages, np, sherpa, .25, .25, .5)
            if rescued:
                spans = rescued

    with base._measure(stages, "diarizationMs"):
        with base._measure(stages, "diarizationLoadMs"):
            config = diar_sweep.make_config(embedding, model_root / "diar/segmentation.onnx", -1,
                                           native_threshold, window_shift, threads, sherpa)
            diarizer = sherpa.OfflineSpeakerDiarization(config)
        try:
            with base._measure(stages, "diarizationInferenceMs"):
                output = diarizer.process(samples)
            raw_turns = [base.Turn(max(0, min(duration_ms, base._kotlin_round_ms(turn.start))),
                                  max(0, min(duration_ms, base._kotlin_round_ms(turn.end))), turn.speaker)
                         for turn in output.sort_by_start_time()]
            raw_turns = [turn for turn in raw_turns if turn.end_ms > turn.start_ms]
            native_turns = base.stable_turns(raw_turns)
            del output
        finally:
            del diarizer
            gc.collect()
    # The SD object is already released before the separate extractor is constructed.
    with base._measure(stages, "cleanEmbeddingStageMs"):
        observations = (diar_sweep.extract_windows(samples, native_turns, embedding, threads, sherpa)
                        if clean_windows(native_turns, duration_ms) else [])
    if any(len(item["embedding"]) != entry["embedding_dimension"] for item in observations):
        raise ValueError("Actual clean embedding dimension differs from catalog")
    measured_windows = [EmbeddingWindow(item["start_ms"], item["end_ms"], item["speaker"],
                                        tuple(item["embedding"]), item["clean"]) for item in observations]
    with base._measure(stages, "refinerMs"):
        refined = (overcluster(native_turns, measured_windows, duration_ms, refiner_config)
                   if strategy == "window_v1" else refine(native_turns, measured_windows, duration_ms, refiner_config))
    turns = list(refined.turns)
    bounded = base.context_spans(spans, duration_ms, 600, 0)
    with base._measure(stages, "alignmentMs"):
        chunks = plan_vad_chunks(bounded, samples, max_ms=20000, energy_split=True)
    segments, slice_results, all_words = [], [], []
    fallback_chunks = 0
    if chunks:
        with base._measure(stages, "asrLoadMs"):
            recognizer = sherpa.OfflineRecognizer.from_transducer(
                encoder=str(model_root / "giga-v3/encoder.int8.onnx"), decoder=str(model_root / "giga-v3/decoder.onnx"),
                joiner=str(model_root / "giga-v3/joiner.onnx"), tokens=str(model_root / "giga-v3/tokens.txt"),
                model_type="nemo_transducer", num_threads=threads, provider="cpu", debug=False,
                sample_rate=16000, feature_dim=80, dither=0.0, decoding_method="greedy_search",
                max_active_paths=4, modeling_unit="", hotwords_file="", blank_penalty=0.0)
        try:
            with base._measure(stages, "asrMs"):
                for chunk_index, chunk in enumerate(chunks):
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
                                                       stride["frame_stride_ms"])
                            assigned = assign_words(parsed.words, turns) if parsed.supported else []
                            rows = [{"startMs": word.start_ms, "endMs": word.end_ms, "text": word.text,
                                     "speakerId": word.speaker, "warnings": list(word.reasons), "chunkIndex": chunk_index}
                                    for word in assigned]
                            all_words.extend(rows)
                            if parsed.supported:
                                segments.extend(group_words(assigned, base.SOURCE, "none"))
                            elif text:
                                fallback_chunks += 1
                                segments.append({"startMs": chunk.start_ms, "endMs": chunk.end_ms,
                                    "speakerId": -1, "text": text, "source": base.SOURCE, "warnings": [words.FALLBACK_WARNING]})
                        slice_results.append({"startMs": chunk.start_ms, "endMs": chunk.end_ms,
                            "speakerId": -1, "text": text, "blank": not bool(text), "inferenceMs": inference_ms,
                            "tokens": tokens, "timestamps": timestamps, "timestampUnit": "seconds within ASR VAD chunk",
                            "words": rows, "wordAssignmentSupported": parsed.supported, "wordAssignmentReason": parsed.reason,
                            "warnings": [] if parsed.supported else [words.FALLBACK_WARNING]})
                        del output
                    finally:
                        del stream
        finally:
            del recognizer
            gc.collect()
    else:
        stages.update(asrLoadMs=0., asrInferenceMs=0., asrMs=0., wordAssignmentMs=0.)

    with base._measure(stages, "diagnosticMetadataMs"):
        source_paths = [Path(__file__), Path(words.__file__), Path(base.__file__), Path(diar_sweep.__file__),
            Path(__file__).with_name("vad_words.py"), Path(__file__).with_name("decoder_parity.py"),
            Path(__file__).with_name("speaker_refiner.py")]
        if strategy == "window_v1":
            source_paths.append(Path(__file__).with_name("window_overcluster.py"))
        source_hashes = {str(path.relative_to(base.PROJECT_ROOT)): base._sha256(path) for path in source_paths}
        audio_hash = base._sha256(audio_path)
        runtime_info = {"version": sherpa.__version__, "git": runtime.git_sha1, "gitDate": runtime.git_date,
            "onnxruntime": runtime.onnxruntime_version, "extensionSha256": base._sha256(Path(runtime.__file__))}
        transcript = base.jury_projection(segments)
    processing_ms = (time.perf_counter_ns() - started) / 1e6
    applied = attempted and bool(rescued)
    diagnostics = {
        "runtime": "sherpa-onnx " + sherpa.__version__, "runtimeBuild": runtime_info,
        "onnxruntimeVersion": runtime.onnxruntime_version, "platform": platform.platform(),
        "pythonVersion": platform.python_version(),
        "pipelineVariant": "window_words_v1" if strategy == "window_v1" else "refined_words_v1",
        "refinementStrategy": strategy,
        "refinementImplementation": "Python/SciPy HC of newly measured windows; not a Kotlin/Android port" if strategy == "window_v1" else "Python centroid refiner",
        "scope": "Full actual host C candidate; not Android/ARM/phone or release acceptance",
        "audioSha256": audio_hash, "audioMs": duration_ms, "sampleRate": 16000,
        "originalPcmPeak": peak, "recognitionInputGain": recognition_gain, "vadDetectorGain": detector_gain,
        "vadPrimarySpanCount": len(primary), "vadPrimarySpans": base._span_json(primary),
        "vadRescueAttempted": attempted, "vadRescueApplied": applied, "vadRescueRms": rms,
        "vadRescueRmsSamples": rms_samples, "vadRescueSpanCount": len(rescued),
        "vadRescueReason": ("retry_applied" if applied else "retry_empty") if attempted else decision.reason,
        "quietGainScope": "Temporary VAD/ASR Float32 arrays; original PCM, playback, SD and clean embeddings preserved",
        "vadRescueScope": "Original empty-primary RMS/headroom detector-only retry; unchanged ASR gain and VAD parameters",
        "vadSpans": base._span_json(spans), "asrSpeechSpans": base._span_json(bounded),
        "asrChunks": base._span_json(chunks), "turnsUsedForAsrSlicing": False,
        "rawDiarizationTurns": base._turn_json(raw_turns), "nativeDiarizationTurns": base._turn_json(native_turns),
        "refinedDiarizationTurns": base._turn_json(turns), "diarizationTurns": base._turn_json(turns),
        "cleanEmbeddingWindows": observations, "refiner": refined.diagnostics, "refinerAccepted": refined.accepted,
        "refinerFallbackToNative": not refined.accepted, "asrSlices": slice_results, "words": all_words,
        "segments": segments, "stagesMs": stages, "backend": base.SOURCE, "clusteringMode": "automatic",
        "nativeConfigString": str(config),
        "expectedSpeakers": -1, "modelFiles": model_files, "modelBytes": model_bytes,
        "externalEmbedding": {"id": model_id, "path": str(embedding), "size": entry["size"],
            "sha256": entry["sha256"], "embeddingDimension": entry["embedding_dimension"], "catalogSha256": catalog_hash},
        "validatedModelBytes": model_bytes + (0 if any(item["sha256"] == entry["sha256"] for item in model_files) else entry["size"]),
        "tokenTimestampPolicy": stride,
        "tokenTimestampError": stride_error, "wordAssignmentSupported": stride["verified"] and fallback_chunks == 0,
        "fallbackChunks": fallback_chunks, "fallbackPolicy": words.FALLBACK_WARNING,
        "pairedAsrPolicy": dict(PAIRED_ASR_POLICY), "config": {
            "provider": "cpu", "threads": threads, "vadThreads": 1, "nativeNumClusters": -1,
            "nativeThreshold": native_threshold, "segmentationWindowShiftRatio": window_shift,
            "diarMinDurationOnSec": .2, "diarMinDurationOffSec": .5,
            "cleanWindowMs": 1500, "cleanWindowStepMs": 750, "cleanMinimumIslandMs": 1000,
            "refiner": asdict(refiner_config), "asr": dict(PAIRED_ASR_POLICY)},
        "newDiarizationInference": True, "newEmbeddingInference": bool(observations),
        "newAsrInference": bool(chunks), "asrForwardCalls": len(chunks), "embeddingForwardCalls": len(observations),
        "asrReplay": False, "nativeModelCacheRetained": False,
        "nativeResourcePolicy": "VAD release → SD release → clean extractor/streams release → pure refiner → ASR/streams release; no retained model cache",
        "embeddingInputScope": "Original decoded PCM, predicted clean windows; no recognition gain or reference inputs",
        "pipelineTimingScope": "Actual per-invocation baseline+external SHA validation, metadata, canonical decode, VAD/rescue, SD, extra embedding load/Compute/release, pure refinement, VAD chunking, new ASR and word projection, audio/code/runtime SHA and jury projection; excludes final diagnostic dict/JSON serialization, CLI startup and persistence",
        "validationScope": "All original packaged groups validated every invocation; active external embedder separately catalog-pinned. Baseline pack/Android policy unchanged.",
        "memoryScope": "Host Float32 WAV is resident; not Android bounded-IO or peak RAM parity",
        "sourceFiles": source_hashes}
    if strategy == "window_v1":
        diagnostics["windowConfig"] = asdict(refiner_config)
        diagnostics["selectedNativePolicy"] = {"model_id": model_id, "threshold": native_threshold,
            "window_shift": window_shift, "threads": threads, "num_clusters": -1}
        diagnostics["validationScope"] = "All seven legacy model files validated every invocation; active ERes2Net is also rehashed against its frozen catalog entry. No added model weights."
    return {"transcript": transcript, "diagnostics": diagnostics, "duration_ms": duration_ms, "processing_ms": processing_ms}
