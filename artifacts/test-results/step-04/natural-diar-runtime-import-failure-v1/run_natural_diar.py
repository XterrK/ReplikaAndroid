#!/usr/bin/env python3
"""Fresh, automatic diarization only on the three metadata-frozen AMI crops.

Runs the existing legacy/C1/C2 profiles without tuning, ASR, VAD or language ID.
Gold files enter scoring only after each inference returns. Paired microphones
and shared participants are explicitly related samples, not independent splits.
This diagnostic cannot promote a candidate or establish corpus generalization.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sys
import time
import wave

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.eval import pipeline as base, score as scoring, prepare_natural_ami as preparation
from tools.eval import speaker_refiner, window_overcluster, prepare_diar_models
from tools.eval.diar_sweep import make_config

ROOT = Path(__file__).resolve().parents[2]
PROFILE_IDS = ("legacy-v16", "c1-centroid", "c2-window")
CATALOG_IDS = {"eres2net_zh", "wespeaker_resnet34_lm", "campplus_en", "wespeaker_camplus_lm", "titanet_small", "titanet_large"}
CASE_IDS = ("ami-natural-en2002a-headset-first60", "ami-natural-en2002a-array-first60",
            "ami-natural-en2002c-headset-first60")
LOCK_PATHS = {"giga-v3/encoder.int8.onnx", "giga-v3/decoder.onnx", "giga-v3/joiner.onnx",
              "giga-v3/tokens.txt", "diar/segmentation.onnx", "diar/embedding.onnx", "vad/silero_vad.onnx"}
C1_CONFIG = asdict(speaker_refiner.RefineConfig(merge_threshold=.7,
    minimum_reassignment_similarity=.7, small_missing_centroid_policy="temporal"))
C2_CONFIG = asdict(window_overcluster.WindowClusterConfig(tau=.36, method="average", reassign_small=True))
SCOPE = ("Separate natural-meeting diarization diagnostic: EN2002a headset/array share a reference; "
         "EN2002a/c share participants; training overlap unknown. Not independent splits, English ASR task E, "
         "Android/phone timing, a new dev gate or corpus-general acceptance.")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_new(path, value):
    with path.open("xb") as stream:
        stream.write(encoded(value))


def safe_path(root, relative):
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("Expected a contained relative path")
    path, root = Path(relative), Path(root).resolve()
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Path escapes input root")
    result = (root / path).resolve()
    if not result.is_relative_to(root):
        raise ValueError("Path escapes input root")
    return result


def source_paths():
    return [ROOT / "tools/eval" / name for name in (
        "run_natural_diar.py", "pipeline.py", "decoder_parity.py", "diar_sweep.py", "run.py",
        "speaker_refiner.py", "window_overcluster.py", "score.py", "prepare_natural_ami.py",
        "prepare_diar_models.py", "vad_words.py")]


def _check_file(path, spec):
    if type(spec.get("size")) is not int or spec["size"] <= 0 or not re.fullmatch("[0-9a-f]{64}", spec.get("sha256", "")):
        raise ValueError("Invalid file pin")
    if path.stat().st_size != spec["size"] or digest(path) != spec["sha256"]:
        raise ValueError("Pinned file differs: " + str(path))


def preflight(args, *, project_root=ROOT):
    """Read/hash metadata and PCM format only; never instantiate a native model."""
    if args.output.exists():
        raise FileExistsError("Choose a fresh output; no overwrite/resume")
    project_root, metadata_root = Path(project_root), args.manifest.parent
    tracked = {}
    def track(path):
        path = Path(path).resolve()
        tracked[str(path)] = digest(path)
        return path
    def document(path):
        return json.loads(track(path).read_bytes())
    manifest = document(args.manifest)
    provenance = document(metadata_root / "provenance.json")
    audit = document(metadata_root / "preparation-audit.json")
    frozen_path = project_root / "artifacts/test-results/step-04/natural-probe-freeze.json"
    freeze = document(frozen_path)
    if track(metadata_root / "selection-freeze.json").read_bytes() != frozen_path.read_bytes():
        raise ValueError("Natural selection freeze differs")
    if (manifest.get("schema_version") != 1 or manifest.get("status") != "PREPARED"
            or manifest.get("audio_fetch_completed") is not True or manifest.get("new_model_inference") is not False
            or provenance.get("status") != "PREPARED" or provenance.get("new_model_inference") is not False
            or provenance.get("whole_source_audio_sha256") is not None
            or freeze.get("status") != "METADATA_ONLY_FROZEN_BEFORE_AUDIO_AND_INFERENCE"
            or manifest.get("freeze_sha256") != digest(frozen_path) or provenance.get("freeze_sha256") != digest(frozen_path)
            or provenance.get("manifest_sha256") != digest(args.manifest)
            or audit.get("status") != "PASS" or not audit.get("checks")
            or audit.get("count") != len(audit["checks"])
            or any(check.get("passed") is not True for check in audit["checks"])
            or audit.get("manifest_sha256") != digest(args.manifest)
            or audit.get("original_freeze_sha256") != digest(frozen_path)
            or manifest.get("inference_policy") != {"expected_speakers": -1, "reference_inputs": []}):
        raise ValueError("Natural preparation/freeze/audit provenance differs")
    if (manifest.get("license") != freeze.get("license") or not manifest.get("training_overlap")
            or not manifest.get("related_samples") or manifest.get("total_audio_ms") != 180000
            or manifest.get("unique_meeting_crop_ms") != 120000):
        raise ValueError("Natural licensing/related-sample scope differs")
    if track(metadata_root / "ATTRIBUTION.md").read_bytes() != preparation.NOTICE.encode("utf-8"):
        raise ValueError("Retain exact AMI attribution")
    license_path = track(metadata_root / "sources/AMI-diarization-setup-LICENSE")
    _check_file(license_path, {"size": preparation.LICENSE_SPEC["bytes"], "sha256": preparation.LICENSE_SPEC["sha256"]})
    if provenance.get("setup_license") != preparation.LICENSE_SPEC:
        raise ValueError("Pinned setup license metadata differs")
    files, frozen_cases, prepared = manifest.get("files", []), freeze.get("cases", []), provenance.get("cases", [])
    for values in (files, frozen_cases, prepared):
        if len(values) != 3 or {row["id"] for row in values} != set(CASE_IDS):
            raise ValueError("Need exactly the three frozen natural diagnostic cases")
    if len(audit.get("cases", [])) != 3 or {row["id"] for row in audit["cases"]} != set(CASE_IDS):
        raise ValueError("Preparation audit coverage differs")
    audited = {row["id"]: row for row in audit["cases"]}
    frozen_cases, prepared = ({row["id"]: row for row in values} for values in (frozen_cases, prepared))
    cases = []
    for row in files:
        origin, saved = frozen_cases[row["id"]], prepared[row["id"]]
        audio, reference = track(safe_path(args.audio_root, row["audio"])), track(safe_path(metadata_root, row["reference"]))
        if (row.get("duration_ms") != 60000 or row.get("split") != "diagnostic"
                or row.get("allowed_task") != "speaker_diarization_only" or row.get("language") != "en"
                or row.get("audio_sha256") != digest(audio) or row.get("reference_sha256") != digest(reference)
                or saved.get("canonical_crop_sha256") != digest(audio) or saved.get("reference_sha256") != digest(reference)
                or saved.get("status") != "PREPARED" or row.get("whole_source_audio_sha256") is not None
                or saved.get("whole_source_audio_sha256") is not None
                or (origin["crop_start_ms"], origin["crop_end_ms"]) != (0, 60000)
                or row.get("reference_group") != origin["reference_group"] or row.get("channel") != origin["channel"]
                or row.get("paired_session") != origin["meeting"]
                or row.get("related_participants_group") != "AMI-EN2002"):
            raise ValueError("Natural audio/reference/clock identity differs")
        with wave.open(str(audio)) as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes(), stream.getcomptype()) != (1, 2, 16000, 960000, "NONE"):
                raise ValueError("Natural WAV is not exact canonical60s PCM16mono16k")
            pcm = stream.readframes(960001)
        if len(pcm) != 1920000 or hashlib.sha256(pcm).hexdigest() != saved.get("pcm_crop_sha256"):
            raise ValueError("Natural PCM payload differs")
        rttm = track(metadata_root / "sources" / (origin["meeting"] + ".rttm"))
        _check_file(rttm, {"size": origin["rttm_bytes"], "sha256": origin["rttm_sha256"]})
        if (saved.get("rttm_sha256") != origin["rttm_sha256"] or saved.get("rttm_url") != origin["rttm_url"]
                or saved.get("source_http_url") != origin["audio_url"] or saved.get("pcm_crop_frames") != 960000):
            raise ValueError("Source RTTM/audio provenance differs")
        responses = saved.get("http_partial_responses", [])
        if not responses:
            raise ValueError("Missing bounded HTTP source evidence")
        for response in responses:
            start, end = response["start_byte"], response["end_byte_inclusive"]
            headers = response["headers"]
            if (type(start) is not int or type(end) is not int or not 0 <= start <= end < origin["content_length"]
                    or response.get("status") != 206 or response.get("body_bytes") != end - start + 1
                    or response.get("url") != origin["audio_url"] or headers.get("etag") != origin["etag"]
                    or headers.get("last-modified") != origin["last_modified"]
                    or headers.get("content-range") != f"bytes {start}-{end}/{origin['content_length']}"
                    or headers.get("content-encoding") not in (None, "identity")
                    or headers.get("content-type", "").split(";", 1)[0].strip().lower() not in
                        ("audio/x-wav", "audio/wav", "audio/wave", "audio/vnd.wave", "application/octet-stream")
                    or headers.get("content-length") is not None and int(headers["content-length"]) != end - start + 1
                    or not re.fullmatch("[0-9a-f]{64}", response.get("sha256", ""))):
                raise ValueError("Bounded HTTP source evidence differs")
        header = saved["source_header"]
        case_audit = audited[row["id"]]
        if (case_audit.get("audio_sha256") != row["audio_sha256"]
                or case_audit.get("reference_sha256") != row["reference_sha256"]
                or case_audit.get("source_data_offset") != header.get("data_offset")
                or case_audit.get("crop_frames") != 960000
                or case_audit.get("reference_speakers") != row.get("reference_speaker_count")
                or row.get("reference_speaker_count") != len(origin["reference_speaker_seconds"])):
            raise ValueError("Preparation audit case pins differ")
        if ((header.get("channels"), header.get("sample_rate"), header.get("bits_per_sample"), header.get("block_align")) != (1, 16000, 16, 2)
                or header.get("format_code") != 1 or header.get("source_bytes") != origin["content_length"]
                or header.get("riff_bytes") != origin["content_length"] or header.get("source_frames", 0) < 960000
                or header.get("data_bytes") != header["source_frames"] * 2):
            raise ValueError("Original source PCM format differs")
        if not any(part["start_byte"] == header["data_offset"] and part["body_bytes"] == 1920000
                   and part["sha256"] == saved["pcm_crop_sha256"] for part in responses):
            raise ValueError("Crop is not bound to the original PCM range")
        cases.append({"id": row["id"], "audio": audio, "reference": reference,
            "audio_sha256": row["audio_sha256"], "reference_sha256": row["reference_sha256"],
            "reference_group": row["reference_group"], "related_participants_group": row["related_participants_group"],
            "duration_ms": 60000, "source_provenance_id": row["id"]})
    if cases[0]["reference_group"] != cases[1]["reference_group"] or cases[0]["reference_sha256"] != cases[1]["reference_sha256"]:
        raise ValueError("Paired EN2002a channels must share one gold reference")

    lock_path = track(project_root / "app/src/main/assets/models-lock.json")
    lock = json.loads(lock_path.read_bytes())
    if len(lock.get("files", [])) != 7 or {spec["path"] for spec in lock["files"]} != LOCK_PATHS:
        raise ValueError("Require the unchanged complete seven-file main model lock")
    for spec in lock["files"]:
        _check_file(track(safe_path(args.model_root, spec["path"])), spec)
    catalog_path = track(args.catalog)
    catalog = prepare_diar_models.load_catalog(catalog_path)
    if catalog.get("required_runtime") != base.RUNTIME_VERSION or catalog.get("baseline_id") != "eres2net_zh":
        raise ValueError("Pinned catalog runtime/baseline differs")
    models = {model["id"]: model for model in catalog["models"]}
    if set(models) != CATALOG_IDS:
        raise ValueError("Require the complete frozen six-model catalog")
    paths = {}
    for identifier, model in models.items():
        path = prepare_diar_models.model_path(model, args.embedding_root, project_root)
        _check_file(track(path), model)
        paths[identifier] = path
    c1_path = project_root / "artifacts/test-results/step-04/candidate-c1-validation-freeze.json"
    c2_path = project_root / "artifacts/test-results/step-04/candidate-c2-validation-freeze.json"
    c1, c2 = document(c1_path), document(c2_path)
    c1_selected = document(project_root / "configs/eval/c1-refined-selected.json")
    c2_selected = document(project_root / "configs/eval/c2-window-selected-full.json")
    if (c1.get("status") != "FROZEN_FOR_VALIDATION" or c2.get("status") != "FROZEN_FOR_VALIDATION"
            or c1.get("model") != models.get("wespeaker_resnet34_lm") or c2.get("model") != models.get("eres2net_zh")
            or c1.get("policy") != {"native_threshold": .5, "window_shift": .1, "threads": 2,
                "refiner_tau": .7, "minimum_reassignment_similarity": .7,
                "missing_centroid_policy": "temporal", "paired_asr_plan": "vad_words_context600"}
            or c2.get("algorithm") != "window-overcluster-v1" or c2.get("window_config") != C2_CONFIG
            or c2.get("policy") != {"native_threshold": .3, "window_shift": .1, "threads": 2,
                "paired_asr_plan": "vad_words_context600"}
            or c1_selected.get("candidate_freeze_sha256") != digest(c1_path)
            or c2_selected.get("candidate_freeze_sha256") != digest(c2_path)
            or any(config.get("expected_speakers") != -1 or config.get("threads") != 2 for config in (c1_selected, c2_selected))
            or c1_selected.get("model_id") != "wespeaker_resnet34_lm" or c1_selected.get("native_threshold") != .5
            or c1_selected.get("window_shift") != .1 or c2_selected.get("window_shift") != .1
            or c1_selected.get("pipeline") != "refined_words_v1" or c2_selected.get("pipeline") != "window_words_v1"
            or c1_selected.get("refiner_tau") != .7 or c1_selected.get("minimum_reassignment_similarity") != .7
            or c1_selected.get("missing_centroid_policy") != "temporal"
            or c2_selected.get("model_id") != "eres2net_zh" or c2_selected.get("native_threshold") != .3
            or c2_selected.get("window_config") != C2_CONFIG):
        raise ValueError("Frozen C1/C2 model/global policy differs")
    profiles = [
        {"id": "legacy-v16", "model_id": "eres2net_zh", "native_threshold": .5, "algorithm": "none", "config": None},
        {"id": "c1-centroid", "model_id": "wespeaker_resnet34_lm", "native_threshold": .5,
         "algorithm": "centroid-eigengap-v1", "config": C1_CONFIG},
        {"id": "c2-window", "model_id": "eres2net_zh", "native_threshold": .3,
         "algorithm": "window-overcluster-v1", "config": C2_CONFIG},
    ]
    for profile in profiles:
        model = models[profile["model_id"]]
        profile.update(threads=2, expected_speakers=-1, window_shift=.1,
            min_duration_on=.2, min_duration_off=.5, embedding_dimension=model["embedding_dimension"],
            embedding_sha256=model["sha256"])
    for path in source_paths():
        track(path)
    return {"cases": cases, "profiles": profiles, "embedding_paths": paths, "tracked_sha256": tracked,
            "manifest": manifest, "catalog": catalog, "model_lock": lock,
            "preparation_provenance": provenance, "selection_freeze": freeze, "preparation_audit": audit,
            "provenance_path": str(metadata_root / "provenance.json"), "scope": SCOPE}


def assert_unchanged(plan):
    for path, expected in plan["tracked_sha256"].items():
        if digest(path) != expected:
            raise ValueError("Frozen source/config/model/input changed: " + path)


class NativeRuntime:
    """Only this adapter imports sherpa; no recognizer/VAD/LID API is used."""
    def __init__(self):
        import numpy as np
        import scipy
        from scipy.cluster import hierarchy, _hierarchy
        from numpy._core import _multiarray_umath
        import sherpa_onnx as sherpa
        from sherpa_onnx.lib import _sherpa_onnx as extension
        if sherpa.__version__ != base.RUNTIME_VERSION:
            raise ValueError("Pinned sherpa-onnx2.0.1 required")
        if scipy.__version__ != "1.18.1" or np.__version__ != "2.5.4":
            raise ValueError("Pinned SciPy1.18.1/NumPy2.5.4 numerical policy required")
        self.np, self.sherpa = np, sherpa
        self.info = {"sherpa_version": sherpa.__version__, "git_sha1": extension.git_sha1,
            "git_date": extension.git_date, "onnxruntime": extension.onnxruntime_version,
            "extension_file": str(extension.__file__), "extension_sha256": digest(extension.__file__),
            "numpy_version": np.__version__, "scipy_version": scipy.__version__,
            "scipy_hierarchy_source_file": str(hierarchy.__file__), "scipy_hierarchy_source_sha256": digest(hierarchy.__file__),
            "scipy_hierarchy_extension_file": str(_hierarchy.__file__), "scipy_hierarchy_extension_sha256": digest(_hierarchy.__file__),
            "numpy_core_extension_file": str(_multiarray_umath.__file__), "numpy_core_extension_sha256": digest(_multiarray_umath.__file__),
            "python": platform.python_version(), "platform": platform.platform()}

    def diarization(self, embedding, segmentation, profile):
        sherpa = self.sherpa
        native = sherpa.OfflineSpeakerDiarization(make_config(embedding, segmentation, -1,
            profile["native_threshold"], .1, 2, sherpa))
        class Session:
            def process(self, samples):
                output = native_holder[0].process(samples)
                try:
                    return [(float(row.start), float(row.end), int(row.speaker)) for row in output.sort_by_start_time()]
                finally:
                    del output
            def close(self):
                native_holder[0] = None
                gc.collect()
        native_holder = [native]
        del native
        return Session()

    def embedding(self, model):
        extractor = self.sherpa.SpeakerEmbeddingExtractor(self.sherpa.SpeakerEmbeddingExtractorConfig(
            model=str(model), num_threads=2, provider="cpu", debug=False))
        class Session:
            @property
            def dimension(self):
                return holder[0].dim
            def create_stream(self):
                stream_holder = [holder[0].create_stream()]
                class Stream:
                    def accept(self, samples):
                        stream_holder[0].accept_waveform(16000, samples)
                        stream_holder[0].input_finished()
                    def ready(self):
                        return holder[0].is_ready(stream_holder[0])
                    def compute(self):
                        return holder[0].compute(stream_holder[0])
                    def close(self):
                        stream_holder[0] = None
                        gc.collect()
                return Stream()
            def close(self):
                holder[0] = None
                gc.collect()
        holder = [extractor]
        del extractor
        return Session()


def rows(turns):
    return [{"speaker_id": "native_" + str(t.speaker), "start_ms": t.start_ms, "end_ms": t.end_ms, "text": ""} for t in turns]


def infer_profile(audio_path, model_root, embedding_path, profile, runtime):
    """No case metadata, reference path/text/activity/K or score crosses this API."""
    expected = {
        "legacy-v16": ("eres2net_zh", .5, "none", None, 512),
        "c1-centroid": ("wespeaker_resnet34_lm", .5, "centroid-eigengap-v1", C1_CONFIG, 256),
        "c2-window": ("eres2net_zh", .3, "window-overcluster-v1", C2_CONFIG, 512),
    }.get(profile.get("id"))
    if (expected is None or set(profile) != {"id", "model_id", "native_threshold", "algorithm", "config",
            "embedding_dimension", "embedding_sha256", "threads", "expected_speakers", "window_shift",
            "min_duration_on", "min_duration_off"}
            or tuple(profile[key] for key in ("model_id", "native_threshold", "algorithm", "config", "embedding_dimension")) != expected
            or profile["expected_speakers"] != -1 or type(profile["expected_speakers"]) is not int
            or profile["threads"] != 2 or type(profile["threads"]) is not int
            or (profile["window_shift"], profile["min_duration_on"], profile["min_duration_off"]) != (.1, .2, .5)):
        raise ValueError("Only frozen automatic profiles supported")
    began, stages = time.perf_counter_ns(), {}
    with base._measure(stages, "decode_ms"):
        samples = base._read_canonical_wav(Path(audio_path), runtime.np)
    duration = len(samples) * 1000 // 16000
    if duration != 60000 or len(samples) != 960000 or not runtime.np.isfinite(samples).all():
        raise ValueError("Need exact60s finite original decoded PCM")
    counts = {"diarizer_loads": 0, "diarizer_releases": 0, "diarization_forward_calls": 0,
        "extractor_loads": 0, "extractor_releases": 0, "planned_windows": 0, "read_windows": 0,
        "created_streams": 0, "released_streams": 0, "compute_attempts": 0,
        "embedding_forward_calls": 0, "measured_windows": 0,
        "new_asr_inference": False, "new_vad_inference": False, "new_lid_inference": False}
    with base._measure(stages, "diarizer_load_ms"):
        session = runtime.diarization(embedding_path, Path(model_root) / "diar/segmentation.onnx", profile)
        counts["diarizer_loads"] += 1
    try:
        with base._measure(stages, "diarization_inference_ms"):
            native = session.process(samples)
            counts["diarization_forward_calls"] += 1
        raw = []
        for start, end, speaker in native:
            if not all(math.isfinite(x) for x in (start, end)) or type(speaker) is not int or speaker < 0 or end <= start:
                raise ValueError("Invalid actual native interval/label")
            a, b = max(0, min(duration, base._kotlin_round_ms(start))), max(0, min(duration, base._kotlin_round_ms(end)))
            if b > a:
                raw.append(base.Turn(a, b, speaker))
    finally:
        with base._measure(stages, "diarizer_release_ms"):
            session.close()
            counts["diarizer_releases"] += 1
    stable = base.stable_turns(raw)
    measured = []
    if profile["algorithm"] != "none":
        planned = speaker_refiner.clean_windows(stable, duration)
        counts["planned_windows"] = len(planned)
        if planned:
            with base._measure(stages, "extractor_load_ms"):
                extractor = runtime.embedding(embedding_path)
                counts["extractor_loads"] += 1
            try:
                if extractor.dimension != profile["embedding_dimension"]:
                    raise ValueError("Actual embedding dimension differs from catalog")
                with base._measure(stages, "extra_embedding_ms"):
                    for window in planned:
                        stream = extractor.create_stream()
                        counts["created_streams"] += 1
                        try:
                            pcm = samples[window.start_ms * 16:window.end_ms * 16]
                            if len(pcm) != (window.end_ms - window.start_ms) * 16:
                                raise ValueError("Clean-window crop exceeds original PCM; no padding allowed")
                            counts["read_windows"] += 1
                            stream.accept(pcm)
                            if not stream.ready():
                                raise ValueError("Extractor not ready on actual clean window")
                            counts["compute_attempts"] += 1
                            vector = tuple(float(value) for value in stream.compute())
                            counts["embedding_forward_calls"] += 1
                            if (len(vector) != profile["embedding_dimension"] or not all(math.isfinite(x) for x in vector)
                                    or math.hypot(*vector) <= 1e-12):
                                raise ValueError("Invalid actual clean embedding")
                            measured.append(speaker_refiner.EmbeddingWindow(window.start_ms, window.end_ms,
                                window.speaker, vector, True))
                            counts["measured_windows"] += 1
                        finally:
                            stream.close()
                            counts["released_streams"] += 1
            finally:
                with base._measure(stages, "extractor_release_ms"):
                    extractor.close()
                    counts["extractor_releases"] += 1
    with base._measure(stages, "pure_refiner_ms"):
        if profile["algorithm"] == "centroid-eigengap-v1":
            refined = speaker_refiner.refine(stable, measured, duration, speaker_refiner.RefineConfig(**profile["config"]))
        elif profile["algorithm"] == "window-overcluster-v1":
            refined = window_overcluster.overcluster(stable, measured, duration, window_overcluster.WindowClusterConfig(**profile["config"]))
        else:
            refined = None
    final = stable if refined is None else list(refined.turns)
    return {"duration_ms": duration, "raw_native_seconds": [list(value) for value in native],
        "raw_turns": rows(raw), "stable_turns": rows(stable), "final_turns": rows(final),
        "clean_embedding_windows": [asdict(window) for window in measured],
        "refiner": {"algorithm": "none", "status": "NOT_APPLICABLE"} if refined is None else refined.diagnostics,
        "refiner_accepted": None if refined is None else refined.accepted,
        "input_pcm_scope": "Unmodified base canonical Android-clock Float32 decode; original source clock, no gain/padding/resampling added by this runner",
        "native_resources_released": True, "counts": counts, "stages_ms": stages,
        "processing_ms": (time.perf_counter_ns() - began) / 1e6,
        "timing_scope": "Host canonical decode + SD load/process/release + extra clean embeddings load/process/release + pure refinement; excludes preflight rehashes, scoring and artifact JSON persistence; not Android/phone timing"}


def score_result(reference, actual):
    duration = actual["duration_ms"]
    gold = scoring._document(reference, duration)
    if any(row.text for row in gold):
        raise ValueError("Natural gold must contain blank text; ASR is outside scope")
    positive = [row for row in gold if row.end_ms > row.start_ms]
    reference_count = len({row.speaker_id for row in positive})
    result = {"reference_speakers": reference_count, "scope": SCOPE}
    for stage in ("raw", "stable", "final"):
        hypothesis = actual[stage + "_turns"]
        count = len({row["speaker_id"] for row in hypothesis if row["end_ms"] > row["start_ms"]})
        result[stage] = {"speakers": count, "speaker_count_error": abs(count - reference_count),
            "speaker_count_exact": count == reference_count,
            **{f"der_collar_{collar}ms": scoring.der(reference["transcript"], hypothesis, duration, collar) for collar in (0, 250)}}
    return result


def summarize(records):
    result = {}
    for profile in PROFILE_IDS:
        selected = [r for r in records if r["profile"] == profile]
        summary = {"cases": len(selected), "speaker_count_exact_cases": sum(r["metrics"]["final"]["speaker_count_exact"] for r in selected),
            "refiner_applicable_cases": sum(r["refiner_accepted"] is not None for r in selected),
            "refiner_supported_cases": sum(r["refiner_accepted"] is True for r in selected),
            "unsupported_case_ids": [r["id"] for r in selected if r["refiner_accepted"] is False],
            "audio_ms": sum(r["duration_ms"] for r in selected),
            "processing_ms": sum(r["processing_ms"] for r in selected)}
        for collar in (0, 250):
            key = f"der_collar_{collar}ms"
            totals = {field: sum(r["metrics"]["final"][key][field] for r in selected)
                for field in ("miss_ms", "false_alarm_ms", "confusion_ms", "reference_speaker_ms")}
            denominator = totals["reference_speaker_ms"]
            totals["rate"] = sum(totals[field] for field in ("miss_ms", "false_alarm_ms", "confusion_ms")) / denominator if denominator else None
            summary[key] = totals
        summary["host_rtf"] = summary["processing_ms"] / summary["audio_ms"] if summary["audio_ms"] else None
        result[profile] = summary
    return {"profiles": result, "scope": SCOPE, "acceptance_gate": None, "candidate_selection": None,
        "related_sample_warning": "Weighted channel-time descriptions only; EN2002a is counted twice by microphone, not as two independent conversations"}


def run(args, *, project_root=ROOT, runtime_factory=NativeRuntime, inference=infer_profile):
    began = time.perf_counter_ns()
    plan = preflight(args, project_root=project_root)
    runtime = runtime_factory()  # imports/version metadata only; native constructors come later
    if runtime.info.get("sherpa_version") != base.RUNTIME_VERSION:
        raise ValueError("Pinned runtime differs before output/NN")
    for key in ("extension", "scipy_hierarchy_source", "scipy_hierarchy_extension", "numpy_core_extension"):
        filename = runtime.info.get(key + "_file")
        if filename:
            actual_sha = digest(filename)
            if actual_sha != runtime.info.get(key + "_sha256"):
                raise ValueError("Loaded numerical/runtime module fingerprint changed")
            plan["tracked_sha256"][str(Path(filename).resolve())] = actual_sha
    assert_unchanged(plan)
    args.output.mkdir(parents=True, exist_ok=False)
    meta = {"schema_version": 1, "status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
        "scope": SCOPE, "runtime": runtime.info, "profiles": plan["profiles"],
        "tracked_sha256": plan["tracked_sha256"], "source_provenance": plan["provenance_path"],
        "preflight_ms": (time.perf_counter_ns() - began) / 1e6, "completed_cases": 0, "expected_profile_cases": 9,
        "new_model_inference": False, "new_asr_inference": False, "new_vad_inference": False,
        "new_lid_inference": False, "automatic_expected_speakers": -1, "threads": 2,
        "reference_inputs_to_inference": [], "whole_source_audio_sha256": None}
    # run.json is the only mutable progress marker; all case artifacts are fresh-write-only.
    def progress():
        temporary = args.output / "run.json.tmp"
        temporary.write_bytes(encoded(meta))
        temporary.replace(args.output / "run.json")
    progress()
    write_new(args.output / "input-manifest.json", plan["manifest"])
    write_new(args.output / "model-catalog.json", plan["catalog"])
    write_new(args.output / "model-lock.json", plan["model_lock"])
    write_new(args.output / "natural-preparation-provenance.json", plan["preparation_provenance"])
    write_new(args.output / "selection-freeze.json", plan["selection_freeze"])
    write_new(args.output / "preparation-audit.json", plan["preparation_audit"])
    records = []
    try:
        for profile in plan["profiles"]:
            profile_root = args.output / profile["id"]
            profile_root.mkdir()
            for case in plan["cases"]:
                assert_unchanged(plan)
                folder = profile_root / case["id"]
                folder.mkdir()
                try:
                    if meta["new_model_inference"] is not True:
                        meta["new_model_inference"] = None  # interrupted call may have partly inferred
                    progress()
                    actual = inference(case["audio"], args.model_root, plan["embedding_paths"][profile["model_id"]], profile, runtime)
                    write_new(folder / "diagnostics.json", actual)
                    assert_unchanged(plan)
                    if (actual.get("duration_ms") != 60000 or actual.get("native_resources_released") is not True
                            or any(actual["counts"].get(key) is not False for key in
                                   ("new_asr_inference", "new_vad_inference", "new_lid_inference"))):
                        raise ValueError("Actual inference scope/clock/resource contract differs")
                    # First parsing of reference content occurs after actual inference has returned.
                    reference_bytes = case["reference"].read_bytes()
                    reference = json.loads(reference_bytes)
                    metric = score_result(reference, actual)
                    with (folder / "reference.json").open("xb") as stream:
                        stream.write(reference_bytes)
                    write_new(folder / "hypothesis.json", {"transcript": actual["final_turns"]})
                    write_new(folder / "metrics.json", metric)
                    record = {"id": case["id"], "profile": profile["id"], "policy": profile, "status": "COMPLETE",
                        "duration_ms": 60000, "processing_ms": actual["processing_ms"], "metrics": metric,
                        "audio_sha256": case["audio_sha256"], "reference_sha256": case["reference_sha256"],
                        "source_provenance_id": case["source_provenance_id"], "reference_group": case["reference_group"],
                        "related_participants_group": case["related_participants_group"],
                        "refiner_accepted": actual["refiner_accepted"], "new_model_inference": True,
                        "new_asr_inference": False, "counts": actual["counts"], "stages_ms": actual["stages_ms"],
                        "evidence_sha256": {name: digest(folder / name) for name in
                            ("diagnostics.json", "reference.json", "hypothesis.json", "metrics.json")}}
                    write_new(folder / "case.json", record)
                    records.append(record)
                    meta.update(completed_cases=len(records), new_model_inference=True)
                    progress()
                    print(json.dumps({"profile": profile["id"], "case": case["id"],
                        "der0": metric["final"]["der_collar_0ms"]["rate"], "speakers": metric["final"]["speakers"],
                        "refiner_accepted": actual["refiner_accepted"]}), flush=True)
                except BaseException as error:
                    write_new(folder / "failure.json", {"type": type(error).__name__, "message": str(error),
                        "reference_inputs_to_inference": [], "scoring_completed": False})
                    raise
        assert_unchanged(plan)
        summary = summarize(records)
        summary.update(status="COMPLETE", profile_cases=len(records), new_asr_inference=False)
        write_new(args.output / "summary.json", summary)
        with (args.output / "results.csv").open("x", newline="", encoding="utf-8") as stream:
            fields = ("profile", "case", "der0", "der250", "reference_speakers", "final_speakers", "count_error", "processing_ms", "refiner_accepted")
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in records:
                metric = row["metrics"]
                writer.writerow({"profile": row["profile"], "case": row["id"],
                    "der0": metric["final"]["der_collar_0ms"]["rate"], "der250": metric["final"]["der_collar_250ms"]["rate"],
                    "reference_speakers": metric["reference_speakers"], "final_speakers": metric["final"]["speakers"],
                    "count_error": metric["final"]["speaker_count_error"], "processing_ms": row["processing_ms"], "refiner_accepted": row["refiner_accepted"]})
        meta.update(status="COMPLETE", completed_at=datetime.now(timezone.utc).isoformat())
        progress()
        return summary
    except BaseException as error:
        meta.update(status="FAILED", error_type=type(error).__name__, error=str(error), completed_at=datetime.now(timezone.utc).isoformat())
        progress()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "benchmark/eval-natural-ami/manifest.json")
    parser.add_argument("--model-root", type=Path, default=ROOT / "model-pack")
    parser.add_argument("--catalog", type=Path, default=ROOT / "configs/eval/diar-models.json")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--embedding-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
