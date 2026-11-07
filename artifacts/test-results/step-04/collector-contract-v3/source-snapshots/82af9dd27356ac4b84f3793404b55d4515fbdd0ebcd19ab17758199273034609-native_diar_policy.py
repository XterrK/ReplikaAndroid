"""Strict C2 Android QA contracts and pure replay; no device, audio or NN I/O.

Float32 SDK parameters use exact bit comparisons. Window policy uses exact
Double values/types. Temporal voting in C2 is explicit algorithm behavior;
it must not be confused with an unsupported-refiner/native-turn fallback.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import struct
import uuid

from tools.eval import pipeline as base
from tools.eval.native_policy import policy_for_plan, validate_native_policy, validate_word_evidence
from tools.eval.speaker_refiner import EmbeddingWindow, clean_windows
from tools.eval.vad_words import assign_words, group_words, words_from_tokens
from tools.eval.window_overcluster import WindowClusterConfig, overcluster

PLAN = "eres2net_window_v1"
ASR_PLAN = "vad_words_context600"
WINDOW_CONFIG = {"tau": .36, "method": "average", "grid_ms": 125, "max_speakers": 8,
    "reassign_small": True, "min_cluster_ms": 2000, "min_cluster_fraction": .03,
    "minimum_reassignment_similarity": None, "smooth": True, "smooth_ms": 500}
MODEL_PINS = (
    ("giga-v3/encoder.int8.onnx", 224570820, "369f35a71bf288d3b8e0391fabd8dba5f2314088d440bca474056b7b4b6e66bf"),
    ("giga-v3/decoder.onnx", 4600132, "38fc7475443ea2a26f63211ca350f73ac50fff824ab7a3876ee2bd610c53bbc4"),
    ("giga-v3/joiner.onnx", 2712896, "602ff7017a93311aad34df1437c8d7f49911353c13d6eae7a6ee7b041339465c"),
    ("giga-v3/tokens.txt", 13354, "39abae20e692998290c574e606f11a9edef2902a1995463fcff63d1490cf22b7"),
    ("diar/segmentation.onnx", 5992913, "220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079"),
    ("diar/embedding.onnx", 39593761, "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b"),
    ("vad/silero_vad.onnx", 643854, "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"),
)
EMBEDDING_SHA256 = MODEL_PINS[5][2]
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024


def _fail(message):
    raise ValueError(message)


def strict_json(content):
    """Reject duplicate keys and non-JSON NaN/Infinity instead of hiding them."""
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                _fail("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=pairs,
                      parse_constant=lambda x: _fail("Nonfinite JSON number: " + x))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def equal(actual, expected, label="policy"):
    """Exact canonical JSON policy, rejecting bool/int and int/float coercions."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            _fail(label + " fields differ")
        for key, value in expected.items():
            equal(actual[key], value, label + "." + key)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            _fail(label + " array length differs")
        for i, value in enumerate(expected):
            equal(actual[i], value, label + "." + str(i))
    elif type(actual) is not type(expected) or actual != expected:
        _fail(label + " differs")


def f32_equal(actual, expected, label):
    if not finite(actual):
        _fail(label + " must be finite numeric")
    try:
        same = struct.pack("!f", actual) == struct.pack("!f", expected)
    except (OverflowError, struct.error):
        same = False
    if not same:
        _fail(label + " Float32 bits differ")


def policy_for_diar_plan(plan=PLAN):
    if plan != PLAN:
        _fail("Only the frozen C2 diarization plan is supported")
    return {"plan": PLAN, "algorithm": "window-overcluster-v1", "embedding_path": "diar/embedding.onnx",
            "native_threshold": .3, "window_shift": .1, "min_duration_on": .2,
            "min_duration_off": .5, "window_config": copy.deepcopy(WINDOW_CONFIG)}


def validate_model_lock(lock):
    rows = lock.get("files") if isinstance(lock, dict) else None
    if not isinstance(rows, list) or len(rows) != 7:
        _fail("C2 requires exactly the legacy seven pinned models")
    for row, (path, size, sha) in zip(rows, MODEL_PINS):
        if row.get("path") != path or type(row.get("size")) is not int or row["size"] != size or row.get("sha256") != sha:
            _fail("Legacy model order/size/hash differs: " + path)
        if row.get("group") != path.split("/")[0]:
            _fail("Legacy model group differs: " + path)
    return {path: sha for path, _, sha in MODEL_PINS}


def _asr_host():
    return {**policy_for_plan(ASR_PLAN), "threads": 2, "expected_speakers": -1}


def validate_host_policy(config, paired_asr):
    required = {"schema_version", "id", "pipeline", "expected_speakers", "threads", "model_id",
                "window_shift", "native_threshold", "window_config"}
    if (not isinstance(config, dict) or not required <= set(config)
            or set(config) - required - {"notes", "candidate_freeze_sha256"}):
        _fail("Incomplete/unknown C2 host configuration")
    for key, value in {"schema_version": 1, "pipeline": "window_words_v1", "expected_speakers": -1,
                       "threads": 2, "model_id": "eres2net_zh"}.items():
        equal(config[key], value, "host." + key)
    if not isinstance(config["id"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", config["id"]):
        _fail("Unsafe host configuration ID")
    if "candidate_freeze_sha256" in config and not re.fullmatch(r"[0-9a-f]{64}", str(config["candidate_freeze_sha256"])):
        _fail("Invalid candidate freeze hash")
    f32_equal(config["native_threshold"], .3, "host.native_threshold")
    f32_equal(config["window_shift"], .1, "host.window_shift")
    equal(config["window_config"], WINDOW_CONFIG, "host.window_config")
    expected = {"plan": ASR_PLAN, "vad_threshold": .5, "vad_min_speech_sec": .25,
        "vad_min_silence_sec": .25, "pre_roll_ms": 600, "punctuation_mode": "none",
        "energy_split": True, "threads": 2, "provider": "cpu", "sample_rate": 16000,
        "feature_dim": 80, "dither": 0.0, "model_type": "nemo_transducer",
        "decoding_method": "greedy_search", "max_active_paths": 4, "modeling_unit": "",
        "hotwords_file": "", "blank_penalty": 0.0, "vad_window_samples": 512, "max_asr_ms": 20000}
    equal(paired_asr, expected, "host.paired_asr_policy")
    return policy_for_diar_plan()


def validate_native_diar_policy(config, report, paired_asr):
    expected = validate_host_policy(config, paired_asr)
    validate_native_policy(_asr_host(), report)
    for key in ("diarizationPlanRequested", "diarizationPlan"):
        equal(report.get(key), PLAN, key)
    actual = report.get("diarizationPolicy")
    if not isinstance(actual, dict) or set(actual) != set(expected):
        _fail("Native diarization policy fields differ")
    for key, value in expected.items():
        if key in ("native_threshold", "window_shift", "min_duration_on", "min_duration_off"):
            f32_equal(actual[key], value, "native." + key)
        else:
            equal(actual[key], value, "native." + key)
    return expected


def turns_from_json(rows, duration_ms):
    if not isinstance(rows, list):
        _fail("Native turns must be an array")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"startMs", "endMs", "speakerId"}:
            _fail("Native turn fields differ")
        a, b, speaker = (row[k] for k in ("startMs", "endMs", "speakerId"))
        if any(type(v) is not int for v in (a, b, speaker)) or not 0 <= a < b <= duration_ms or speaker < 0:
            _fail("Invalid native turn interval/speaker")
        result.append(base.Turn(a, b, speaker))
    return result


def turn_json(turns):
    return [{"startMs": t.start_ms, "endMs": t.end_ms, "speakerId": t.speaker} for t in turns]


def _same_integral_double(left, right):
    """Exact JSON int/Double representation bridge, never bool or large BigInt."""
    return (type(left) in (int, float) and type(right) in (int, float)
            and type(left) is not type(right) and finite(left) and finite(right)
            and abs(left) <= 2**53 and abs(right) <= 2**53
            and left == right and int(left) == left and int(right) == right)


def _replay_values(actual, expected, label="refiner"):
    """Port diagnostics: exact structure/integer/string/null, tolerant Double math."""
    # Kotlin's max(Double, Double) always returns Double. Python's max(int,
    # Double) retains int when min_cluster_ms wins. Only this verified Double
    # diagnostic has the known mismatch; policies, clocks and counts stay exact.
    if label == "refiner.small_cluster_cutoff_ms":
        if ((type(actual) is type(expected) and finite(actual) and finite(expected) and actual == expected)
                or _same_integral_double(actual, expected)):
            return
        _fail(label + " exact diagnostic number differs")
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) - {"hierarchy_backend"} != set(expected):
            _fail(label + " replay fields differ")
        for key, value in expected.items():
            _replay_values(actual[key], value, label + "." + key)
    elif isinstance(expected, (list, tuple)):
        if not isinstance(actual, list) or len(actual) != len(expected):
            _fail(label + " replay length differs")
        for i, value in enumerate(expected):
            _replay_values(actual[i], value, label + "." + str(i))
    elif type(expected) is float:
        if not finite(actual) or not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-8):
            _fail(label + " replay Double differs")
    elif type(actual) is not type(expected) or actual != expected:
        _fail(label + " replay differs")


def compact_refiner_diagnostic(values):
    """Exact Worker Room projection of the full QA adapter diagnostic.

    config is retained verbatim, refiner maps alone recurse, scalar/null fields
    survive. Every other list/map is QA-only and omitted from Room. This is a
    representation check; full QA vectors/tree still undergo independent replay.
    """
    if not isinstance(values, dict):
        _fail("Full refiner diagnostic must be an object")
    compact = {}
    for key, value in values.items():
        if key == "config":
            compact[key] = copy.deepcopy(value)
        elif key == "refiner" and isinstance(value, dict):
            compact[key] = compact_refiner_diagnostic(value)
        elif value is None or type(value) in (str, int, float, bool):
            compact[key] = value
    return compact


def _compare_room_adapter(room, full_adapter):
    compact = compact_refiner_diagnostic(full_adapter)
    # JSONObject prints an integral Double as an integer, while the bounded QA
    # streaming writer preserves .0. Canonicalize this ONE diagnostic path only.
    if (isinstance(room, dict) and isinstance(room.get("refiner"), dict)
            and isinstance(compact.get("refiner"), dict)):
        actual = room["refiner"].get("small_cluster_cutoff_ms")
        expected = compact["refiner"].get("small_cluster_cutoff_ms")
        if _same_integral_double(actual, expected):
            compact["refiner"]["small_cluster_cutoff_ms"] = actual
    equal(room, compact, "Room compact adapter")


def validate_diarization_evidence(diagnostics, native_case, sidecar_bytes, *, case_id, audio_sha256, duration_ms):
    """Verify identities, actual measurement lifecycle, and exact pure C2 replay.

    No transcript, reference text/count, expected K or case identity crosses
    overcluster(). Identity arguments only bind the evidence container.
    """
    if type(duration_ms) is not int or duration_ms <= 0:
        _fail("Positive canonical duration required")
    for key, value in {"id": case_id, "status": "COMPLETE", "audio_sha256": audio_sha256,
                       "duration_ms": duration_ms, "newModelInference": True}.items():
        equal(native_case.get(key), value, "native_case." + key)
    work = native_case.get("workId")
    try:
        if str(uuid.UUID(work)) != work:
            _fail("Noncanonical work UUID")
    except (ValueError, TypeError, AttributeError):
        _fail("Invalid work UUID")
    recording = native_case.get("recordingId")
    if not isinstance(recording, str) or not re.fullmatch(r"qa-evaluation-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", recording):
        _fail("Invalid recording identity")
    if (type(native_case.get("processing_ms")) is not int or native_case["processing_ms"] < 0
            or native_case["processing_ms"] != diagnostics.get("totalMs")):
        _fail("Native processing clock differs")
    if not isinstance(sidecar_bytes, bytes) or not 0 < len(sidecar_bytes) <= MAX_EVIDENCE_BYTES:
        _fail("Sidecar size exceeds bounded QA evidence budget")
    sha = hashlib.sha256(sidecar_bytes).hexdigest()
    for key, value in {"diarizationEvidenceSha256": sha, "diarizationEvidenceBytes": len(sidecar_bytes),
                       "diarizationEvidenceFile": case_id + ".diarization-evidence.json"}.items():
        equal(native_case.get(key), value, "native_case." + key)
    for key, value in {"audioMs": duration_ms, "sampleRate": 16000, "threads": 2, "vadThreads": 1,
        "expectedSpeakers": -1, "clusteringMode": "automatic", "clusterThresholdApplied": True,
        "runtime": "sherpa-onnx 2.0.1", "diarizationRefinementApplicable": True,
        "diarizationRefinementAccepted": True, "diarizationEvidenceRequested": True,
        "diarizationEvidenceTruncated": False, "diarizationEvidenceOmittedReason": None,
        "diarizationEvidenceSha256": sha, "diarizationEvidenceBytes": len(sidecar_bytes),
        "diarizationEvidenceFile": "diarization-qa/diarization-" + work + ".json",
        "preRollMs": 600, "postRollMs": 0, "maxAsrSegmentMs": 20000,
        "vadWindowSamples": 512, "vadMaxSpeechSec": 20}.items():
        if key not in diagnostics:
            _fail("Missing native diagnostic: " + key)
        equal(diagnostics[key], value, "diagnostic." + key)
    for key, value in {"clusterThreshold": .3, "segmentationWindowShiftRatio": .1,
                       "diarMinDurationOnSec": .2, "diarMinDurationOffSec": .5,
                       "vadThreshold": .5, "vadMinSpeechSec": .25, "vadMinSilenceSec": .25}.items():
        f32_equal(diagnostics.get(key), value, key)
    wrapper = strict_json(sidecar_bytes)
    if not isinstance(wrapper, dict) or set(wrapper) != {"schema_version", "work_id", "recording_id", "metadata", "windows", "diagnostics", "truncated"}:
        _fail("Sidecar schema fields differ")
    for key, value in {"schema_version": 1, "work_id": work, "recording_id": recording, "truncated": False}.items():
        equal(wrapper[key], value, "sidecar." + key)
    metadata = wrapper["metadata"]
    expected_metadata = {"audioMs": duration_ms, "sampleRate": 16000, "inputAudioSha256": audio_sha256,
        "diarizationPlan": PLAN, "diarizationPolicy": diagnostics["diarizationPolicy"],
        "runtime": "sherpa-onnx 2.0.1", "embeddingSha256": EMBEDDING_SHA256,
        "rawDiarizationTurns": diagnostics.get("rawDiarizationTurns"),
        "nativeDiarizationTurns": diagnostics.get("nativeDiarizationTurns"),
        "refinedDiarizationTurns": diagnostics.get("diarizationTurns"), "accepted": True}
    equal(metadata, expected_metadata, "sidecar.metadata")
    raw = turns_from_json(metadata["rawDiarizationTurns"], duration_ms)
    native = turns_from_json(metadata["nativeDiarizationTurns"], duration_ms)
    output = turns_from_json(metadata["refinedDiarizationTurns"], duration_ms)
    if base.stable_turns(raw) != native:
        _fail("Raw-to-stable native speaker remap differs")
    adapter = wrapper["diagnostics"]
    _compare_room_adapter(diagnostics.get("diarizationRefinement"), adapter)
    for key, value in {"algorithm": "window-overcluster-v1", "config": WINDOW_CONFIG,
        "computationalSupport": True, "originalPcm": True, "sampleRate": 16000,
        "cleanWindowMs": 1500, "cleanWindowStepMs": 750, "cleanMinimumIslandMs": 1000,
        "embeddingInferenceCompleted": True, "nativeResourcesReleasedBeforeRefiner": True,
        "retainedNativeModelCache": False}.items():
        equal(adapter.get(key), value, "adapter." + key)
    if adapter.get("status") not in ("SUPPORTED", "PARTIAL_TEMPORAL") or any(k in adapter for k in ("reason", "failureStage", "failureClass", "failureWindowIndex")):
        _fail("Unsupported/fallback native refiner")
    rows = wrapper["windows"]
    planned = [(w.start_ms, w.end_ms, w.speaker) for w in clean_windows(native, duration_ms)]
    if not isinstance(rows, list) or not 0 < len(rows) <= 2048 or len(rows) != len(planned):
        _fail("Missing/extra measured windows")
    windows = []
    for row, clock in zip(rows, planned):
        if not isinstance(row, dict) or set(row) != {"start_ms", "end_ms", "speaker", "embedding", "clean"}:
            _fail("Measured window fields differ")
        equal({k: row[k] for k in ("start_ms", "end_ms", "speaker", "clean")},
              dict(zip(("start_ms", "end_ms", "speaker", "clean"), (*clock, True))), "window.clock")
        vector = row["embedding"]
        if not isinstance(vector, list) or len(vector) != 512 or any(not finite(v) for v in vector):
            _fail("Measured embedding must contain 512 finite values")
        try:
            if not any(v != 0 for v in vector) or any(base._f32(v) != v for v in vector):
                _fail("Embedding is zero or not actual promoted Float32 output")
        except (OverflowError, struct.error):
            _fail("Embedding exceeds Float32 output range")
        windows.append(EmbeddingWindow(*clock, tuple(vector), True))
    counts = diagnostics.get("diarizationEmbeddingCounts")
    expected_counts = {k: len(windows) for k in ("plannedWindows", "readWindows", "createdStreams",
        "releasedStreams", "computeAttempts", "embeddingForwardCalls", "measuredWindows")}
    expected_counts.update(extractorLoads=1, embeddingDimension=512)
    equal(counts, expected_counts, "embedding.lifecycle")
    # Only native activities, actual measured vectors, duration and global config.
    replay = overcluster(native, windows, duration_ms, WindowClusterConfig(**WINDOW_CONFIG))
    if not replay.accepted or list(replay.turns) != output:
        _fail("Python C2 replay differs from actual Worker turns")
    _replay_values(adapter["refiner"], replay.diagnostics)
    equal(adapter["status"], replay.diagnostics["status"], "adapter.status")
    return {"sidecar_sha256": sha, "sidecar_bytes": len(sidecar_bytes), "work_id": work,
        "recording_id": recording, "measured_windows": len(windows), "dimension": 512,
        "resources_released": True, "python_replay_exact_turns": True,
        "status": replay.diagnostics["status"], "native_speaker_count": len({t.speaker for t in output}),
        "temporal_voting_is_explicit_algorithm_policy": True}


def reconstruct_jury(diagnostics, duration_ms):
    """Rebuild actual QA tokens -> timed words -> speakers -> exported JuryJSON."""
    summary = validate_word_evidence(diagnostics)
    turns = turns_from_json(diagnostics.get("diarizationTurns"), duration_ms)
    chunks, previous = [], 0
    source = diagnostics.get("backend")
    if source != base.SOURCE:
        _fail("Unexpected ASR backend")
    for part in diagnostics["asrSlices"]:
        a, b = part.get("startMs"), part.get("endMs")
        if type(a) is not int or type(b) is not int or not previous <= a < b <= duration_ms or b - a > 20000:
            _fail("ASR chunk clock overlaps or exceeds canonical duration")
        previous = b
        if part.get("timestampUnit") != "seconds within ASR VAD chunk" or type(part.get("frameStrideMs")) is not int or part["frameStrideMs"] != 40:
            _fail("Unverified token clock/frame stride")
        text = part.get("text")
        if not isinstance(text, str) or type(part.get("blank")) is not bool or part["blank"] != (not text.strip()):
            _fail("Invalid ASR text/blank marker")
        parsed = words_from_tokens(text, part["tokens"], part["timestamps"], a, b, 40)
        if not parsed.supported or part.get("wordAssignmentReason") != parsed.reason:
            _fail("Actual tokens cannot reconstruct supported words")
        assigned = assign_words(parsed.words, turns)
        expected = [{"startMs": w.start_ms, "endMs": w.end_ms, "text": w.text,
                     "speakerId": w.speaker, "warnings": list(w.reasons)} for w in assigned]
        equal(part["words"], expected, "assigned.words")
        chunks.extend(group_words(assigned, source, "none"))
    return {"transcript": base.jury_projection(chunks)}, summary
