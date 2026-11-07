#!/usr/bin/env python3
"""Per-file spoken language decision mirrored by domain/LanguagePlan.kt.

Policy (task 07): probes are taken from the first ~30 s of VAD speech, at most three
probes of up to 10 s each, a probe shorter than 1 s is dropped. Whisper tiny labels
every probe; only a strict majority of 'en' gives English. Anything else, including
ties, no usable speech or a missing model, is Russian (priority 1).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

SPEECH_BUDGET_MS = 30000
PROBE_MAX_MS = 10000
PROBE_MIN_MS = 1000
MAX_PROBES = 3
SEGMENT_MIN_MS = 1500
LID_ENCODER = "lid-whisper-tiny/tiny-encoder.int8.onnx"
LID_DECODER = "lid-whisper-tiny/tiny-decoder.int8.onnx"


@dataclass(frozen=True)
class Piece:
    start_ms: int
    end_ms: int


def probe_windows(chunks, budget_ms=SPEECH_BUDGET_MS, probe_max_ms=PROBE_MAX_MS,
                  probe_min_ms=PROBE_MIN_MS, max_probes=MAX_PROBES):
    """Return probes as lists of (start_ms, end_ms) pieces in original order.

    Speech of consecutive chunks is concatenated; a chunk may be split across probes.
    """
    probes, current, current_ms, used = [], [], 0, 0
    for chunk in chunks:
        start, end = int(chunk[0]), int(chunk[1])
        while start < end and used < budget_ms and len(probes) < max_probes:
            take = min(end - start, probe_max_ms - current_ms, budget_ms - used)
            current.append(Piece(start, start + take))
            current_ms += take
            used += take
            start += take
            if current_ms >= probe_max_ms:
                probes.append(current)
                current, current_ms = [], 0
        if used >= budget_ms or len(probes) >= max_probes:
            break
    if current and current_ms >= probe_min_ms and len(probes) < max_probes:
        probes.append(current)
    return probes


def vote(labels):
    """Strict majority of English probes; every other outcome is Russian."""
    english = sum(1 for label in labels if label == "en")
    return "en" if labels and english * 2 > len(labels) else "ru"


def segment_language(label, duration_ms, file_language):
    if duration_ms < SEGMENT_MIN_MS:
        return file_language
    return "en" if label == "en" else "ru"


def make_identifier(model_root, threads=2):
    import sherpa_onnx as sherpa
    root = Path(model_root)
    config = sherpa.SpokenLanguageIdentificationConfig(
        whisper=sherpa.SpokenLanguageIdentificationWhisperConfig(
            encoder=str(root / LID_ENCODER), decoder=str(root / LID_DECODER), tail_paddings=-1),
        num_threads=threads, provider="cpu", debug=False)
    return sherpa.SpokenLanguageIdentification(config)


def label(identifier, samples):
    stream = identifier.create_stream()
    stream.accept_waveform(16000, samples)
    return identifier.compute(stream)


def identify(samples, chunks, model_root, threads=2, per_segment=False, identifier=None):
    """Run the production decision on float32 16 kHz samples and planned ASR chunks."""
    import numpy as np
    started = time.perf_counter()
    own = identifier is None
    load_ms = 0.0
    if own:
        identifier = make_identifier(model_root, threads)
        load_ms = (time.perf_counter() - started) * 1000
    try:
        probes = probe_windows(chunks)
        labels = []
        for probe in probes:
            audio = np.concatenate([samples[p.start_ms * 16:p.end_ms * 16] for p in probe]).astype(np.float32)
            labels.append(label(identifier, audio))
        language = vote(labels)
        file_ms = (time.perf_counter() - started) * 1000 - load_ms
        segments = None
        if per_segment:
            segments = []
            for start, end in chunks:
                if end - start < SEGMENT_MIN_MS:
                    segments.append(language)
                else:
                    segments.append(segment_language(label(identifier, samples[start * 16:end * 16].astype(np.float32)),
                                                     end - start, language))
    finally:
        if own:
            del identifier
    return {"language": language, "probeLabels": labels,
            "probes": [[[p.start_ms, p.end_ms] for p in probe] for probe in probes],
            "segmentLanguages": segments, "loadMs": load_ms, "fileDecisionMs": file_ms,
            "totalMs": (time.perf_counter() - started) * 1000}


ENGLISH_SOURCE = "Parakeet TDT 0.6B v2 INT8 / sherpa-onnx 2.0.1"
ENGLISH_GROUP = "parakeet-en-v2"
LID_GROUP = "lid-whisper-tiny"
# Appended after the unchanged legacy seven rows of models-lock.json (pack v1.6).
LANGUAGE_MODEL_PINS = (
    ("lid-whisper-tiny/tiny-encoder.int8.onnx", 12937772, "d24fb083ae3b1041fc24e97971d60e280c9342201fbb67b0ab428a8b4a51a434"),
    ("lid-whisper-tiny/tiny-decoder.int8.onnx", 89855401, "d2fece8dd42771f1df975c6c0445770d0c292bf7547c2cae04a6c0cc57540925"),
    ("lid-whisper-tiny/tiny-tokens.txt", 816730, "b34b360dbb493e781e479794586d661700670d65564001f23024971d1f2fa126"),
    ("parakeet-en-v2/encoder.int8.onnx", 652282309, "92a10bd9c23936ea0566c29f963bc57c2a5df4261b6a8921c39abea66557ca8b"),
    ("parakeet-en-v2/decoder.int8.onnx", 7257753, "4d097bae3bac5c96018d5293ba39f1b657296102b142affda40378f38b020f41"),
    ("parakeet-en-v2/joiner.int8.onnx", 1739080, "77a29f3e5ac7d37074e0af465391b80f314015d5b97f0f90c6c7767f1d56f428"),
    ("parakeet-en-v2/tokens.txt", 9384, "ec182b70dd42113aff6c5372c75cac58c952443eb22322f57bbd7f53977d497d"),
)


def language_rows_valid(rows):
    """True when rows are exactly the pinned language extension, in order."""
    if len(rows) != len(LANGUAGE_MODEL_PINS):
        return False
    for row, (path, size, sha) in zip(rows, LANGUAGE_MODEL_PINS):
        if (not isinstance(row, dict) or row.get("path") != path or type(row.get("size")) is not int
                or row["size"] != size or row.get("sha256") != sha or row.get("group") != path.split("/")[0]):
            return False
    return True


def verify_language_models(model_root, groups):
    """Hash the requested language groups against the pins (same policy as ModelManager)."""
    import hashlib
    records = []
    for path, size, sha in LANGUAGE_MODEL_PINS:
        if path.split("/")[0] not in groups:
            continue
        target = Path(model_root) / path
        if target.stat().st_size != size:
            raise ValueError("Model size mismatch: " + path)
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            while block := stream.read(1 << 20):
                digest.update(block)
        if digest.hexdigest() != sha:
            raise ValueError("Model SHA-256 mismatch: " + path)
        records.append({"path": path, "bytes": size, "sha256": sha, "hashValidationCached": False})
    return records


def parakeet_stride_from_metadata(metadata):
    """Parakeet TDT v2: NeMo transducer, subsampling 8 over 10 ms features -> 80 ms token grid."""
    if (metadata.get("model_type") != "EncDecRNNTBPEModel" or metadata.get("model_author") != "NeMo"
            or "parakeet-tdt-0.6b-v2" not in metadata.get("url", "")):
        raise ValueError("Unverified model type for Parakeet token timestamp conversion")
    factor = int(metadata["subsampling_factor"])
    if factor <= 0:
        raise ValueError("Invalid model subsampling factor")
    return {"verified": True, "feature_frame_shift_ms": 10, "subsampling_factor": factor,
            "frame_stride_ms": factor * 10, "model_metadata": metadata,
            "precision": "TDT token emission frame intervals; not acoustic forced-aligned word timestamps"}


def make_english_recognizer(model_root, threads):
    import sherpa_onnx as sherpa
    root = Path(model_root) / ENGLISH_GROUP
    return sherpa.OfflineRecognizer.from_transducer(
        encoder=str(root / "encoder.int8.onnx"), decoder=str(root / "decoder.int8.onnx"),
        joiner=str(root / "joiner.int8.onnx"), tokens=str(root / "tokens.txt"),
        model_type="nemo_transducer", num_threads=threads, provider="cpu", debug=False,
        sample_rate=16000, feature_dim=80, dither=0.0, decoding_method="greedy_search",
        max_active_paths=4, modeling_unit="", hotwords_file="", blank_penalty=0.0)


def route(language, per_segment, chunks, samples, recognition_gain, model_root, threads, stages, measure,
          giga_stride, metadata_reader):
    """Shared host routing for pipeline_words/pipeline_refined; mirrors ProcessingWorker + LanguageRouting.

    Returns (chunk_languages, strides, report). LID only reads audio; ru keeps the GigaAM path.
    """
    import numpy as np
    if language not in ("ru", "en", "auto") or type(per_segment) is not bool:
        raise ValueError("language must be ru, en or auto")
    if per_segment and language != "auto":
        raise ValueError("Per-segment language identification requires language=auto")
    report = {"mode": language, "perSegment": per_segment, "decided": language, "lid": None, "lidError": None}
    chunk_languages = ["ru" if language == "auto" else language] * len(chunks)
    if language == "auto" and chunks:
        try:
            with measure(stages, "languageModelValidationMs"):
                report["lidModels"] = verify_language_models(model_root, {LID_GROUP})
            lid_input = samples if recognition_gain == 1 else samples * np.float32(recognition_gain)
            with measure(stages, "languageIdMs"):
                lid = identify(lid_input, [(c.start_ms, c.end_ms) for c in chunks], model_root, threads,
                               per_segment=per_segment)
            report["lid"] = {k: v for k, v in lid.items() if k != "segmentLanguages"}
            report["decided"] = lid["language"]
            chunk_languages = lid["segmentLanguages"] if per_segment else [lid["language"]] * len(chunks)
        except (OSError, ValueError, RuntimeError) as error:
            # Missing/invalid LID never blocks a transcript: Russian is priority 1.
            report["lidError"] = str(error)
            report["decided"] = "ru"
    report["chunkLanguages"] = chunk_languages
    strides = {"ru": giga_stride}
    if "en" in chunk_languages:
        with measure(stages, "languageModelValidationMs"):
            report["englishModels"] = verify_language_models(model_root, {ENGLISH_GROUP})
        try:
            strides["en"] = parakeet_stride_from_metadata(metadata_reader(Path(model_root) / ENGLISH_GROUP / "encoder.int8.onnx"))
        except (ValueError, OSError, KeyError) as error:
            strides["en"] = {"verified": False, "frame_stride_ms": None, "reason": str(error)}
    report["tokenTimestampPolicies"] = {k: {kk: vv for kk, vv in v.items() if kk != "model_metadata"}
                                        for k, v in strides.items()}
    return chunk_languages, strides, report


def passes(chunk_languages):
    """Russian chunks first, then English; one resident recognizer at a time (LanguagePlan.recognitionOrder)."""
    return [(lang, [i for i, value in enumerate(chunk_languages) if value == lang])
            for lang in ("ru", "en") if lang in chunk_languages]


def backend_name(chunk_languages, russian_source):
    used = set(chunk_languages)
    if used <= {"ru"}:
        return russian_source
    return ENGLISH_SOURCE if used == {"en"} else russian_source + " + " + ENGLISH_SOURCE
