"""Pure, strict host/native policy matching; no inference or filesystem access.

Policy floats are compared by exact IEEE-754 Float32 representation because
Sherpa's Android/Python VAD parameters are Float32. This accepts short JSON
decimals and their expanded Float32 forms without a broad epsilon tolerance.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
import struct
from types import MappingProxyType


def _policy(pipeline, punctuation, energy, threshold=.5, speech=.25, silence=.25):
    return {"pipeline": pipeline, "punctuation_mode": punctuation, "energy_split": energy,
            "vad_threshold": threshold, "vad_min_speech_sec": speech,
            "vad_min_silence_sec": silence}


PLAN_POLICIES = MappingProxyType({
    "v16": MappingProxyType(_policy("v16", "none", False)),
    "vad_words_none": MappingProxyType(_policy("vad_words_v1", "none", True)),
    "vad_words_seam": MappingProxyType(_policy("vad_words_v1", "seam", True)),
    "vad_words_short15": MappingProxyType(_policy("vad_words_v1", "none", True, speech=.15, silence=.20)),
    "vad_words_short10": MappingProxyType(_policy("vad_words_v1", "none", True, speech=.10, silence=.12)),
    "vad_words_sensitive": MappingProxyType(_policy("vad_words_v1", "none", True, threshold=.35, speech=.15)),
    "vad_words_short10_seam": MappingProxyType(_policy("vad_words_v1", "seam", True, speech=.10, silence=.12)),
    "vad_words_sensitive_short10": MappingProxyType(_policy("vad_words_v1", "none", True, threshold=.35, speech=.10, silence=.12)),
})
POLICY_FIELDS = frozenset(PLAN_POLICIES["v16"])
VAD_FIELDS = ("vad_threshold", "vad_min_speech_sec", "vad_min_silence_sec")
HOST_COMMON_FIELDS = frozenset({"schema_version", "id", "pipeline", "expected_speakers", "threads", "notes"})


def policy_for_plan(plan_id: str) -> dict:
    """Return an independent canonical policy; unknown plan IDs fail closed."""
    if not isinstance(plan_id, str) or plan_id not in PLAN_POLICIES:
        raise ValueError(f"Unknown native ASR plan: {plan_id!r}")
    return dict(PLAN_POLICIES[plan_id])


def _mapping(value, label):
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _threads(value, label):
    if type(value) is not int or value not in (1, 2, 4):
        raise ValueError(f"{label} must be an integer 1, 2 or 4")
    return value


def _speakers(value, label):
    if type(value) is not int or not (value == -1 or 1 <= value <= 20):
        raise ValueError(f"{label} must be an integer -1 or 1..20")
    return value


def _vad_float(value, field, label):
    low, high = (.1, .9) if field == "vad_threshold" else (.05, 1.)
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(f"{label}.{field} must be a finite number in {low}..{high}")
    return struct.pack("!f", value)


def _validate_policy(value, label):
    value = _mapping(value, label)
    if set(value) != POLICY_FIELDS:
        missing, extra = POLICY_FIELDS - set(value), set(value) - POLICY_FIELDS
        raise ValueError(f"{label} fields differ: missing={sorted(missing)} extra={sorted(extra)}")
    if value["pipeline"] not in ("v16", "vad_words_v1"):
        raise ValueError(f"{label}.pipeline is unsupported")
    if value["punctuation_mode"] not in ("none", "seam"):
        raise ValueError(f"{label}.punctuation_mode must be none or seam")
    if type(value["energy_split"]) is not bool:
        raise ValueError(f"{label}.energy_split must be boolean")
    for field in VAD_FIELDS:
        _vad_float(value[field], field, label)
    return dict(value)


def _same_policy(actual, canonical):
    return all(_vad_float(actual[field], field, "policy") == _vad_float(canonical[field], field, "canonical")
               if field in VAD_FIELDS else actual[field] == canonical[field]
               for field in POLICY_FIELDS)


def _host_policy(config):
    config = _mapping(config, "host config")
    pipeline = config.get("pipeline")
    if pipeline not in ("v16", "vad_words_v1"):
        raise ValueError("Unknown host pipeline")
    if "schema_version" in config and (type(config["schema_version"]) is not int or config["schema_version"] != 1):
        raise ValueError("Unsupported host config schema_version")
    allowed = HOST_COMMON_FIELDS | (POLICY_FIELDS - {"pipeline"} if pipeline == "vad_words_v1" else set())
    if set(config) - allowed:
        raise ValueError("Unsupported/stale host settings: " + str(sorted(set(config) - allowed)))
    _threads(config.get("threads"), "host threads")
    _speakers(config.get("expected_speakers"), "host expected_speakers")
    if pipeline == "v16":
        return policy_for_plan("v16")
    # Punctuation/energy must be explicit for the experimental path; only VAD
    # durations/threshold have backward-compatible defaults.
    value = {"pipeline": pipeline, "punctuation_mode": config.get("punctuation_mode"),
             "energy_split": config.get("energy_split"), "vad_threshold": config.get("vad_threshold", .5),
             "vad_min_speech_sec": config.get("vad_min_speech_sec", .25),
             "vad_min_silence_sec": config.get("vad_min_silence_sec", .25)}
    value = _validate_policy(value, "host policy")
    if not value["energy_split"]:
        raise ValueError("Supported native word plans require energy_split=true")
    return value


def validate_native_policy(host_config, native_report) -> dict:
    """Return canonical policy iff actual report matches config and declared preset.

    Missing asrPlan/asrPolicy is allowed only for an historical V1.6 report.
    An explicit V1.6 plan may omit asrPolicy; if present, it must be complete.
    Word plans always require all policy fields. Outer report metadata is left
    to the caller, but thread/speaker counts are always required and matched.
    """
    host = _host_policy(host_config)
    report = _mapping(native_report, "native report")
    threads = _threads(report.get("threads"), "native threads")
    speakers = _speakers(report.get("expectedSpeakers"), "native expectedSpeakers")
    if threads != host_config["threads"] or speakers != host_config["expected_speakers"]:
        raise ValueError("Native threads/expectedSpeakers differ from host config")
    if "asrPlan" not in report:
        if host["pipeline"] != "v16" or "asrPolicy" in report:
            raise ValueError("Missing native asrPlan; historical policy allowed only for v16")
        return policy_for_plan("v16")
    plan = report["asrPlan"]
    canonical = policy_for_plan(plan)
    if not _same_policy(host, canonical):
        raise ValueError(f"Host config does not match native plan {plan!r}")
    if "asrPolicy" not in report:
        if plan != "v16":
            raise ValueError("Native word report is missing explicit asrPolicy")
    else:
        native = _validate_policy(report["asrPolicy"], "native asrPolicy")
        if not _same_policy(native, canonical):
            raise ValueError(f"Native asrPolicy does not match declared plan {plan!r}")
    return canonical


def validate_word_evidence(diagnostics) -> dict:
    """Require complete, explicitly requested native QA word payloads.

    Structural completeness only: this neither reparses token timing nor scores
    words. Empty asrSlices is valid no-speech evidence with the same explicit QA
    flags. Missing arrays are never replaced with fabricated empty arrays.
    """
    diagnostics = _mapping(diagnostics, "word diagnostics")
    for field in ("wordEvidenceRequested", "wordEvidenceApplicable", "wordAssignmentSupported"):
        if diagnostics.get(field) is not True:
            raise ValueError(f"{field} must be explicitly true for native word QA")
    if diagnostics.get("wordEvidenceTruncated") is not False:
        raise ValueError("wordEvidenceTruncated must be explicitly false")
    if type(diagnostics.get("fallbackChunks")) is not int or diagnostics["fallbackChunks"] != 0:
        raise ValueError("Native word QA requires integer fallbackChunks=0")
    slices = diagnostics.get("asrSlices")
    if not isinstance(slices, list):
        raise ValueError("Native word QA requires an explicit asrSlices array")
    totals = {"tokenCount": 0, "timestampCount": 0, "wordCount": 0}
    for index, raw in enumerate(slices):
        item = _mapping(raw, f"asrSlices[{index}]")
        for flag in ("wordEvidenceIncluded", "wordAssignmentSupported"):
            if item.get(flag) is not True:
                raise ValueError(f"asrSlices[{index}].{flag} must be explicitly true")
        for field, array_name in (("tokenCount", "tokens"), ("timestampCount", "timestamps"), ("wordCount", "words")):
            count, values = item.get(field), item.get(array_name)
            if type(count) is not int or count < 0:
                raise ValueError(f"asrSlices[{index}].{field} must be a nonnegative integer")
            if not isinstance(values, list) or len(values) != count:
                raise ValueError(f"asrSlices[{index}].{array_name} missing or {field} does not match its length")
            totals[field] += count
        if item["tokenCount"] != item["timestampCount"]:
            raise ValueError(f"asrSlices[{index}] token/timestamp counts differ")
        if any(not isinstance(token, str) for token in item["tokens"]):
            raise ValueError(f"asrSlices[{index}].tokens must contain strings")
        try:
            invalid_timestamps = any(type(value) not in (int, float) or not math.isfinite(value) for value in item["timestamps"])
        except OverflowError:
            invalid_timestamps = True
        if invalid_timestamps:
            raise ValueError(f"asrSlices[{index}].timestamps must contain finite numbers")
        if any(not isinstance(word, Mapping) for word in item["words"]):
            raise ValueError(f"asrSlices[{index}].words must contain word objects")
    return {"validated": True, "slices": len(slices), **totals,
            "scope": "Complete native QA payload structure; not token-timing revalidation, word-gold accuracy or microphone acceptance"}
