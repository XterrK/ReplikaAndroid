#!/usr/bin/env python3
"""Compare actual saved ML hypotheses; timing changes are observations, not quality failures.

Only segment UUIDs and transcript titles are ignored in transcript comparison.
Speaker IDs, source, manual flags and warnings remain part of the comparison.
The program does not run models or establish WER/CER/DER without a reference.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RU_SHA = "d8aaaa18a5098d7c6de0595ae7ac1e64cacd0d4022af3595213bdaf23be77e69"
ZH_SHA = "bedf036caed208386c67b4ef4b11f83d74dd0d420b102163a1c33cd09cde7010"
DIAGNOSTIC_FIELDS = (
    "runtime", "backend", "threads", "vadThreads", "sampleRate", "expectedSpeakers",
    "clusterThreshold", "vadThreshold", "maxAsrSegmentMs", "audioMs", "modelBytes",
    "clusteringMode", "clusterThresholdApplied", "segmentationWindowShiftRatio",
    "diarMinDurationOnSec", "diarMinDurationOffSec", "vadMinSpeechSec",
    "vadMinSilenceSec", "vadWindowSamples", "vadMaxSpeechSec", "preRollMs", "postRollMs",
    "pipelineTimingScope", "vadSpans", "asrSpeechSpans", "diarizationTurns", "asrSlices",
)
OBSERVATION_FIELDS = {"inferenceMs", "loadMs", "pssKb", "rtf"}


def read(folder, name):
    with (folder / name).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def differences(left, right, path="$", limit=100):
    """Keep exact differing values, bounded to avoid a malformed file flooding the report."""
    out = []

    def visit(a, b, where):
        if len(out) >= limit:
            return
        if type(a) is not type(b):
            out.append({"path": where, "baseline": a, "candidate": b})
        elif isinstance(a, dict):
            for key in sorted(a.keys() | b.keys()):
                if key not in a or key not in b:
                    out.append({"path": where + "." + key,
                                "baseline": a.get(key, "<missing>"),
                                "candidate": b.get(key, "<missing>")})
                else:
                    visit(a[key], b[key], where + "." + key)
        elif isinstance(a, list):
            if len(a) != len(b):
                out.append({"path": where + ".length", "baseline": len(a), "candidate": len(b)})
            for index, (aa, bb) in enumerate(zip(a, b)):
                visit(aa, bb, f"{where}[{index}]")
        elif a != b:
            out.append({"path": where, "baseline": a, "candidate": b})

    visit(left, right, path)
    return out[:limit]


def without_observations(value):
    if isinstance(value, dict):
        return {k: without_observations(v) for k, v in value.items() if k not in OBSERVATION_FIELDS}
    if isinstance(value, list):
        return [without_observations(v) for v in value]
    return value


def transcript_quality(data):
    return {key: [{k: v for k, v in row.items() if k != "id"} for row in value]
            if key == "segments" else value
            for key, value in data.items() if key != "title"}


def stable_turns(turns):
    """First-appearance labels; do not confuse max(label)+1 with a speaker count."""
    ids = {}
    out = []
    for row in sorted(turns, key=lambda item: (item["startMs"], item["speakerId"])):
        speaker = row["speakerId"]
        if speaker >= 0:
            speaker = ids.setdefault(speaker, len(ids))
        else:
            speaker = -1
        out.append(dict(row, speakerId=speaker))
    return out


def intervals(rows, audio_ms, label, nonoverlap=False, overrun_ms=0):
    issues = []
    last_start = last_end = -1
    for index, row in enumerate(rows):
        a, b = row["startMs"], row["endMs"]
        if not (0 <= a < b <= audio_ms + overrun_ms):
            issues.append(f"{label}[{index}]: invalid bounds {a}..{b}, audio={audio_ms}")
        if a < last_start or (nonoverlap and a < last_end):
            issues.append(f"{label}[{index}]: unordered or overlapping interval")
        last_start, last_end = a, b
    return issues


def merge_intervals(rows):
    merged = []
    for row in rows:
        start, end = row["startMs"], row["endMs"]
        if merged and start <= merged[-1]["endMs"]:
            merged[-1]["endMs"] = max(end, merged[-1]["endMs"])
        else:
            merged.append({"startMs": start, "endMs": end})
    return merged


def diagnostic_quality(data):
    # Missing required metadata must fail, rather than compare two silently absent defaults.
    return {key: without_observations(data[key]) for key in DIAGNOSTIC_FIELDS}


def validate_pipeline(transcript, diagnostic):
    issues = []
    audio = diagnostic["audioMs"]
    if diagnostic["preRollMs"] != 100 or diagnostic["postRollMs"] != 0:
        issues.append("Production context must remain pre100/post0")
    if diagnostic["sampleRate"] != 16000:
        issues.append("Expected 16kHz production input")
    if diagnostic["expectedSpeakers"] != -1 or diagnostic["clusteringMode"] != "automatic":
        issues.append("The public mono regression fixture must retain automatic clustering")
    frame_ms = math.ceil(diagnostic["vadWindowSamples"] * 1000 / diagnostic["sampleRate"])
    issues += intervals(diagnostic["vadSpans"], audio, "rawVAD", True, frame_ms)
    for key in ("asrSpeechSpans", "asrSlices"):
        issues += intervals(diagnostic[key], audio, key, True)
    issues += intervals(diagnostic["diarizationTurns"], audio, "turns")
    issues += intervals(transcript["segments"], audio, "segments", True)
    if not transcript["segments"]:
        issues.append("The mono regression must contain actual nonblank hypotheses")
    if merge_intervals(diagnostic["asrSlices"]) != merge_intervals(diagnostic["asrSpeechSpans"]):
        issues.append("ASR slices do not cover the bounded speech spans exactly once")
    rows = []
    for row in diagnostic["asrSlices"]:
        if row["blank"] != (not row["text"].strip()):
            issues.append("Diagnostic blank flag disagrees with actual text")
        if not row["blank"]:
            rows.append({k: row[k] for k in ("startMs", "endMs", "speakerId", "text", "warnings")})
    actual = []
    for row in transcript["segments"]:
        actual.append({k: row[k] for k in ("startMs", "endMs", "speakerId", "text", "warnings")})
        if row["edited"] or row["reviewed"] or row["source"] != diagnostic["backend"]:
            issues.append("Raw transcript contains manual flags or a different backend")
    if rows != actual:
        issues.append("Raw transcript does not equal the nonblank diagnostic slice hypotheses")
    if "GigaAM" in diagnostic["backend"] and not transcript["segments"][0]["text"].startswith("ничьих"):
        issues.append("Known GigaAM pre-roll prefix regression: missing 'ничьих'")
    return issues


def direct_quality(data):
    selected = {key: data[key] for key in ("audioSha256", "audioMs", "threads", "sampleRate", "scope", "coldDefinition", "WER", "CER")}
    selected["backends"] = without_observations(data["backends"])
    return selected


def validate_direct(data):
    issues = []
    if data["audioSha256"] != RU_SHA:
        issues.append("Direct ASR input is not the pinned public Russian WAV")
    if len(data["backends"]) != 2:
        issues.append("Both existing ASR backends must be present")
    for backend in data["backends"]:
        if len(backend["runs"]) != 3 or [run["run"] for run in backend["runs"]] != [0, 1, 2]:
            issues.append("Expected a new-engine first run and two same-engine warm runs")
        for run in backend["runs"]:
            if not run["text"].strip():
                issues.append("Direct ASR hypothesis is blank")
            if run["inferenceMs"] <= 0 or not math.isclose(run["rtf"], run["inferenceMs"] / data["audioMs"]):
                issues.append("Direct ASR duration/RTF is invalid")
    return issues


def vad_quality(data):
    return {key: without_observations(data[key]) for key in
            ("audioSha256", "audioMs", "threads", "sampleRate", "diarizationTurns", "runs")}


def validate_vad(data):
    issues = []
    if data["audioSha256"] != RU_SHA:
        issues.append("VAD input is not the pinned public Russian WAV")
    for run in data["runs"]:
        if run["name"] == "raw-no-vad-no-diar-crop":
            continue
        # Silero's last padded512-sample frame can exceed EOF; its context must not.
        issues += intervals(run["vadSpans"], data["audioMs"], run["name"] + ".rawVAD", True, 32)
        for key in ("contextSpans", "vadOnly", "alignedSlices"):
            issues += intervals(run[key], data["audioMs"], run["name"] + "." + key, True)
        if merge_intervals(run["alignedSlices"]) != merge_intervals(run["contextSpans"]):
            issues.append(run["name"] + ": slices do not partition contextual speech exactly once")
    return issues


def diar_quality(data):
    result = {key: data[key] for key in ("audioSha256", "audioMs", "threads", "sampleRate", "language", "DER")}
    result["runs"] = [dict(without_observations(row), turns=stable_turns(row["turns"])) for row in data["runs"]]
    return result


def validate_diar(data):
    issues = []
    if data["audioSha256"] != ZH_SHA:
        issues.append("Diarization input is not the pinned public Chinese WAV")
    if len(data["runs"]) != 3:
        issues.append("Expected automatic .5, fixed4 and automatic .65")
    for row in data["runs"]:
        count = len({turn["speakerId"] for turn in row["turns"] if turn["speakerId"] >= 0})
        if row["speakerCount"] != count or count <= 0:
            issues.append("Speaker count differs from the number of distinct nonnegative labels")
        if row["thresholdApplied"] != (row["numClusters"] <= 0):
            issues.append("thresholdApplied disagrees with fixed/automatic configuration")
        if row["numClusters"] > 0 and count != row["numClusters"]:
            issues.append("Fixed cluster count was not retained")
        issues += intervals(row["turns"], data["audioMs"], row["mode"] + ".turns")
    return issues


def raw_diar_quality(data):
    return {key: stable_turns(value) if key == "turns" else value
            for key, value in data.items() if key != "diarizationMsIncludingLoad"}


def validate_provenance(raw, comparison):
    expected = next(row for row in comparison["runs"] if row["mode"] == "automatic" and row["threshold"] == .5)
    a, b = stable_turns(raw["turns"]), stable_turns(expected["turns"])
    issues = []
    if len(a) != len(b) or raw["speakers"] != expected["speakerCount"]:
        issues.append("Native-label and normalized automatic exports have different turn/speaker counts")
    for first, second in zip(a, b):
        if first["speakerId"] != second["speakerId"] or any(abs(first[k] - second[k]) > 1 for k in ("startMs", "endMs")):
            issues.append("Native-label export is not equivalent within documented truncation/rounding1ms")
    return issues


def observations(data):
    if isinstance(data, dict):
        return {k: v if k in OBSERVATION_FIELDS or k in {"totalMs", "stagesMs", "finalPssKb", "pipelineRtf", "asrStageRtf", "asrInferenceRtf", "diarizationMsIncludingLoad"}
                else observations(v) for k, v in data.items()
                if k in OBSERVATION_FIELDS or k in {"totalMs", "stagesMs", "finalPssKb", "pipelineRtf", "asrStageRtf", "asrInferenceRtf", "diarizationMsIncludingLoad"}
                or isinstance(v, (list, dict))}
    if isinstance(data, list):
        return [observations(v) for v in data]
    return {}


def run(baseline, candidate):
    report = {"generatedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "baseline": str(baseline.resolve()), "candidate": str(candidate.resolve()),
              "scope": "Actual saved hypotheses/configuration/bounds; no new model execution, no reference-dependent quality score",
              "timingPolicy": "Observed timings/PSS are retained separately; equality and performance superiority are not asserted",
              "limitations": ["Pipeline JSON itself lacks input SHA; source identity follows pinned test protocol and comparison input SHA",
                              "A matching public mono fixture does not validate a natural Russian multispeaker dialogue or physical arm64",
                              "New warning-crop/UI acceptance is separate from this baseline regression comparison",
                              "Saved JSON equality does not establish fresh execution; successful instrumentation/APK evidence is required"],
              "checks": []}

    def case(label, files, quality, validate):
        entry = {"name": label, "files": files}
        try:
            left = [read(baseline, name) for name in files]
            right = [read(candidate, name) for name in files]
            qa, qb = quality(*left), quality(*right)
            changed = differences(qa, qb)
            problems = {"baseline": validate(*left), "candidate": validate(*right)}
            entry.update(status="FAIL" if changed or any(problems.values()) else "PASS",
                         normalizedBaselineSha256=sha(qa), normalizedCandidateSha256=sha(qb),
                         differences=changed, invariantViolations=problems,
                         observations={"baseline": [observations(value) for value in left],
                                       "candidate": [observations(value) for value in right]})
        except FileNotFoundError as error:
            entry.update(status="UNAVAILABLE", error=str(error))
        except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration) as error:
            entry.update(status="FAIL", error=f"{type(error).__name__}: {error}")
        report["checks"].append(entry)

    for prefix, name in (("android", "GigaAM full Worker"), ("android-whisper", "Whisper full Worker")):
        case(name, [prefix + "-transcript.json", prefix + "-pipeline-diagnostics.json"],
             lambda transcript, diagnostic: {"transcript": transcript_quality(transcript), "diagnostics": diagnostic_quality(diagnostic)},
             validate_pipeline)
    case("Identical full-PCM direct ASR", ["ml-asr-comparison.json"], direct_quality, validate_direct)
    case("VAD contexts and alignment", ["ml-vad-comparison.json"], vad_quality, validate_vad)
    case("Automatic/fixed diarization", ["ml-diarization-comparison.json"], diar_quality, validate_diar)
    case("Native-label export provenance", ["android-diarization.json", "ml-diarization-comparison.json"],
         lambda raw, comparison: raw_diar_quality(raw), validate_provenance)
    report["status"] = "PASS" if all(item["status"] == "PASS" for item in report["checks"]) else "FAIL"
    return report


def exclusive_output(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    chosen = path
    while True:
        try:
            return chosen, chosen.open("x", encoding="utf-8")
        except FileExistsError:
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            chosen = path.with_name(path.stem + "." + stamp + path.suffix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "docs/test-evidence/v1.1")
    parser.add_argument("--candidate", type=Path, default=ROOT / "docs/test-evidence/v1.2")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/test-evidence/v1.2/ml-regression.json")
    args = parser.parse_args()
    report = run(args.baseline, args.candidate)
    output, stream = exclusive_output(args.output)
    with stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(output),
                      "checks": [{"name": c["name"], "status": c["status"]} for c in report["checks"]]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
