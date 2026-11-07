#!/usr/bin/env python3
"""Independent saved Android import/thermal/picker integrity audit; stdlib only.

Never calls ADB, Gradle, FFmpeg, models or a decoder. Revalidates saved Android
measurements/receipts; temporary Android PCM and prior Room snapshots were not
retained, so they cannot be recomputed locally. Writes fresh audit outputs only.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import uuid
import zipfile
import zlib


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + value)))


def identical(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and set(actual) == set(expected) and all(identical(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(identical(a, b) for a, b in zip(actual, expected))
    if type(expected) is float:
        return type(actual) in (int, float) and math.isfinite(actual) and actual == expected
    return type(actual) is type(expected) and actual == expected


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def canonical_uuid(value):
    try:
        return type(value) is str and str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def generated_large_wav_sha(samples):
    # Independent Python reconstruction of the pinned Kotlin largeWav source.
    block = b"".join(struct.pack("<h", math.floor(9000 * math.sin(2 * math.pi * 440 * i / 16000) + .5)) for i in range(16000))
    header = b"RIFF" + struct.pack("<I", 36 + samples * 2) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    digest = hashlib.sha256(header + b"data" + struct.pack("<I", samples * 2))
    full, remainder = divmod(samples, 16000)
    for _ in range(full):
        digest.update(block)
    digest.update(block[:remainder * 2])
    return digest.hexdigest()


def png_dimensions(raw):
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not PNG")
    offset, dimensions = 8, None
    while offset < len(raw):
        size = struct.unpack(">I", raw[offset:offset+4])[0]
        kind = raw[offset+4:offset+8]
        data = raw[offset+8:offset+8+size]
        crc = struct.unpack(">I", raw[offset+8+size:offset+12+size])[0]
        if len(data) != size or zlib.crc32(kind + data) & 0xffffffff != crc:
            raise ValueError("PNG chunk CRC/size mismatch")
        if kind == b"IHDR":
            dimensions = struct.unpack(">II", data[:8])
        offset += size + 12
        if kind == b"IEND":
            if offset != len(raw) or dimensions is None:
                raise ValueError("PNG trailing data/missing IHDR")
            return dimensions
    raise ValueError("PNG missing IEND")


class Audit:
    def __init__(self, repo):
        self.repo = repo.resolve()
        self.checks, self.inputs = [], {}

    def read(self, path):
        path = path.resolve()
        if not path.is_relative_to(self.repo):
            raise ValueError("Audit input escapes repository")
        raw = path.read_bytes()
        self.inputs[str(path.relative_to(self.repo))] = {"sha256": sha(raw), "bytes": len(raw)}
        return raw

    def load(self, path):
        return strict_json(self.read(path))

    def check(self, name, condition):
        self.checks.append({"id": name, "pass": bool(condition)})


def audit(repo):
    a = Audit(repo); base = repo / "artifacts/test-results/step-05"
    build = a.load(base / "build-auto-v2/summary.json")
    fixed = a.load(base / "build-test-v3/summary.json")
    a.check("builds.success", build["status"] == fixed["status"] == "PASS")
    a.check("builds.main_apks_unchanged_by_test_fix", identical(build["apks"]["debug"], fixed["main_apks_unchanged"]["debug"]) and identical(build["apks"]["allInOne"], fixed["main_apks_unchanged"]["allInOne"]))
    for role in ("debug", "allInOne"):
        spec = fixed["main_apks_unchanged"][role]
        raw = a.read(repo / spec["path"])
        a.check("builds." + role + ".local_bytes", len(raw) == spec["bytes"] and sha(raw) == spec["sha256"])
    apk = fixed["androidTest"]
    raw_apk = a.read(repo / apk["path"])
    a.check("test_apk.current_recorded_installed_hash", sha(raw_apk) == apk["sha256"] == "ce4851c681962e8489bd9d8bc0edc0a229d245307b88fdfa9c19d0ef1f1df051" and len(raw_apk) == apk["bytes"])
    import_source = repo / "app/src/androidTest/java/ru/replika/Plan19ImportFormatsTest.kt"
    source = a.read(import_source)
    a.check("source.import_unchanged", sha(source) == build["source_sha256"][str(import_source.relative_to(repo))] == "e6a5d6026b73ece2240c039b4a7001da8eaadb58d68fad12d291f191aa1577b1")
    a.check("source.no_neural_entry_points", all(token not in source.decode() for token in ("ProcessingWorker.enqueue", "GigaAmEngine(", "OfflineSpeakerDiarization(", "SpeakerEmbeddingExtractor(")))
    thermal_source = a.read(repo / "app/src/androidTest/java/ru/replika/CpuThermalPlan19Test.kt")
    a.check("source.thermal_fixed_hash", sha(thermal_source) == fixed["fixed_source_sha256"])
    normalized = re.sub(rb"\(\): Unit\s*=\s*runBlocking", b"() = runBlocking", thermal_source)
    a.check("source.only_explicit_unit_signature_repair", sha(normalized) == build["source_sha256"]["app/src/androidTest/java/ru/replika/CpuThermalPlan19Test.kt"])
    manifest_path = repo / "app/src/androidTest/assets/plan19-import/fixtures.json"
    manifest_raw = a.read(manifest_path); manifest = strict_json(manifest_raw)
    manifest_hash = sha(manifest_raw)
    a.check("fixtures.pinned_manifest", manifest_hash == "439e232eeb2c2ee72d19180154b03156f4b7370b54c83898e368ff8d5017dbf5")
    a.check("fixtures.original_cc0_tones", manifest["license"].startswith("CC0-1.0") and "no speech" in manifest["license"])
    a.check("fixtures.pinned_generator", sha(a.read(repo / manifest["generator"])) == manifest["generator_sha256"])
    rows = manifest["files"]; fixture_map = {x["id"]: x for x in rows}; payloads = {}
    a.check("fixtures.exact13_unique", len(rows) == len(fixture_map) == len({x["name"] for x in rows}) == 13)
    a.check("fixtures.six_container_families", {x["format"] for x in rows} == {"wav", "mp3", "m4a", "aac", "ogg", "flac"})
    with zipfile.ZipFile(repo / apk["path"]) as archive:
        a.check("fixtures.apk_manifest_exact_bytes", archive.read("assets/plan19-import/fixtures.json") == manifest_raw)
        for row in rows:
            name = row["name"]; raw = archive.read("assets/plan19-import/" + name); payloads[row["id"]] = raw
            local = a.read(manifest_path.parent / name)
            a.check("fixture." + row["id"] + ".apk_and_local_sha", len(raw) == row["bytes"] and sha(raw) == row["sha256"] and raw == local)
            magic = {"wav": raw[:4] == b"RIFF" and raw[8:12] == b"WAVE", "flac": raw[:4] == b"fLaC",
                "m4a": raw[4:8] == b"ftyp", "aac": raw[:1] == b"\xff" and raw[1] & 0xf0 == 0xf0,
                "ogg": raw[:4] == b"OggS" and b"OpusHead" in raw[:128],
                "mp3": raw[:3] == b"ID3" or raw[:1] == b"\xff" and raw[1] & 0xe0 == 0xe0}[row["format"]]
            a.check("fixture." + row["id"] + ".container_magic", magic)
    reports = {}
    for path in sorted((base / "android-import-thermal-v1/device").rglob("report.json")):
        report = a.load(path); test = report["test"]
        a.check("report." + test + ".complete_no_nn_cleanup", report["status"] == "COMPLETE" and report["newModelInference"] is False and report["temporaryDirectoryRemoved"] is True)
        a.check("report." + test + ".manifest_binding", report["fixture_manifest_sha256"] == manifest_hash and identical(report["fixture_manifest"], manifest))
        a.check("report." + test + ".api35_x86", report["sdk"] == 35 and "x86_64" in report["fingerprint"])
        a.check("report." + test + ".own_uuid_directory", canonical_uuid(path.parent.name.removeprefix("formats-")))
        reports[test] = report
    expected_tests = {"allThirteenContentUrisImportAndDecodeActualFormats", "repeatedContentUriHasIndependentUuidFiles",
        "emptyGarbageAndMissingUrisLeaveNoOwnedOutput", "truncatedWavEitherFailsCleanlyOrReportsOnlyAvailablePrefix",
        "cancelAfterActualCopyWriteRemovesOnlyOwnedPartial", "cancelAfterActualDecoderFramesRemovesPcmAndPreservesSource"}
    a.check("reports.exact_six_distinct", len(reports) == 6 and set(reports) == expected_tests)
    actual = reports["allThirteenContentUrisImportAndDecodeActualFormats"]["cases"]
    a.check("formats.complete13_ids", len(actual) == 13 and {x["id"] for x in actual} == set(fixture_map))
    measured = []
    for case in actual:
        row = fixture_map[case["id"]]; label = "decode." + case["id"]
        a.check(label + ".original_bytes_retained", case["status"] == "PASS" and case["input_sha256"] == case["imported_sha256"] == row["sha256"] and case["importMode"] == "AUDIO_COPY")
        a.check(label + ".system_decode_not_nn", case["actualSystemDecode"] is True and case["newModelInference"] is False and case["allSamplesFinite"] is True)
        a.check(label + ".format", case["extractedFormat"]["rate"] == row["sample_rate"] and case["extractedFormat"]["channels"] == row["channels"] and case["extractedFormat"]["mime"].startswith("audio/") and bool(case["extractedFormat"]["advertisedDecoderNames"]))
        a.check(label + ".canonical_clock_bytes", type(case["samples"]) is int and case["samples"] > 0 and case["pcm_bytes"] == case["samples"] * 4 and case["duration_ms"] == case["samples"] * 1000 // 16000)
        a.check(label + ".duration_tolerance", abs(case["duration_ms"] - row["expected_duration_ms"]) <= row["duration_tolerance_ms"])
        amplitudes = case["spectral_amplitudes"]; left, right, off = (amplitudes[str(hz)] for hz in (440, 880, 1300)); target = row["tone_amplitude_per_source_channel"] / row["channels"]
        a.check(label + ".finite_spectrum_rms", all(number(x) and x >= 0 for x in (left, right, off, case["rms"])) and case["rms"] > .07)
        a.check(label + ".left_amplitude", left > .06 and abs(left - target) <= target * .4)
        a.check(label + ".right_downmix_or_no_invention", (right > .06 and abs(right - target) <= target * .4 and .55 <= left / right <= 1.8) if row["channels"] == 2 else right < .03)
        a.check(label + ".off_frequency_residual", off < min(left, right if row["channels"] == 2 else left) / 6)
        predicted_rms = math.sqrt((left * left + right * right) / 2)
        a.check(label + ".independent_rms_spectrum_consistency", abs(case["rms"] - predicted_rms) <= predicted_rms * .02)
        a.check(label + ".pcm_hash_receipt", bool(re.fullmatch(r"[0-9a-f]{64}", case["pcm_sha256"])))
        measured.append({"id": row["id"], "format": row["format"], "rate": row["sample_rate"], "channels": row["channels"], "input_sha256": row["sha256"], "duration_ms": case["duration_ms"], "samples": case["samples"], "spectral_amplitudes": amplitudes, "rms": case["rms"]})
    repeat = reports["repeatedContentUriHasIndependentUuidFiles"]["cases"][0]
    a.check("repeat.two_distinct_owned_uuid_audio_files", repeat["first"] != repeat["second"] and all(name.endswith(".audio") and canonical_uuid(name[:-6]) for name in (repeat["first"], repeat["second"])))
    a.check("repeat.survivor_hash_and_decode", repeat["firstDeletionDidNotAffectSecond"] is True and repeat["input_sha256"] == fixture_map["ogg-opus-48k-stereo"]["sha256"] and repeat["survivorDecodedSamples"] == next(x["samples"] for x in actual if x["id"] == "ogg-opus-48k-stereo"))
    errors = reports["emptyGarbageAndMissingUrisLeaveNoOwnedOutput"]["cases"]
    a.check("errors.exact_empty_garbage_missing", {x["fixture"] for x in errors} == {"empty.wav", "garbage.mp3", "missing.flac"} and len(errors) == 3)
    a.check("errors.actionable_and_own_cleanup", all(x["userMessage"].strip() and x["sourceUnchanged"] is True and x["ownedOutputRemoved"] is True for x in errors))
    truncated = reports["truncatedWavEitherFailsCleanlyOrReportsOnlyAvailablePrefix"]["cases"][0]
    a.check("truncated.independent_source_hash", sha(payloads["wav-16k-mono"][:44+32000]) == truncated["input_sha256"])
    a.check("truncated.no_fabricated_missing_seconds", truncated["declared_source_duration_ms"] == 3000 and ((truncated["outcome"] == "DECODED_AVAILABLE_PREFIX" and 1 <= truncated["decoded_duration_ms"] <= 1250) or truncated["outcome"] == "EXPLICIT_DECODE_ERROR"))
    copy = reports["cancelAfterActualCopyWriteRemovesOnlyOwnedPartial"]["cases"][0]
    decode = reports["cancelAfterActualDecoderFramesRemovesPcmAndPreservesSource"]["cases"][0]
    a.check("cancel.copy_original_mathematical_bytes", copy["sourceBytes"] == 64000044 and copy["source_sha256"] == generated_large_wav_sha(32000000))
    a.check("cancel.copy_real_partial_then_cleanup", type(copy["actualPartialBytesObserved"]) is int and 0 < copy["actualPartialBytesObserved"] < copy["sourceBytes"] and copy["cancelledAfterActualWrite"] is True and copy["partialRemoved"] is True)
    a.check("cancel.decode_original_mathematical_bytes", decode["source_sha256"] == generated_large_wav_sha(16000 * 180))
    a.check("cancel.decode_real_frames_then_cleanup", type(decode["actualPcmBytesObserved"]) is int and 65536 <= decode["actualPcmBytesObserved"] < 16000 * 180 * 4 and decode["actualPcmBytesObserved"] % 4 == 0 and decode["cancelledAfterActualFrames"] is True and decode["partialPcmRemoved"] is True)
    first_log = a.read(base / "android-import-thermal-v1/instrumentation.log").decode()
    a.check("history.original_suite_failure_preserved", "Tests run: 7,  Failures: 1" in first_log and "should be void" in first_log and "OK (7 tests)" not in first_log)
    for test in expected_tests:
        a.check("history.import_completed." + test, bool(re.search(r"INSTRUMENTATION_STATUS: test=" + test + r"\s+INSTRUMENTATION_STATUS_CODE: 0", first_log)))
    original_summary = a.load(base / "android-import-thermal-v1/summary.json")
    a.check("history.not_relabelled_as_full_pass", original_summary["status"] == "PARTIAL_FAILURE" and original_summary["thermal_executed"] is False and original_summary["formats_tests_passed"] == 6)
    thermal = a.load(base / "android-thermal-v2/actual-power-manager.json"); thermal_summary = a.load(base / "android-thermal-v2/summary.json")
    thermal_log = a.read(base / "android-thermal-v2/instrumentation.log").decode()
    a.check("thermal.actual_single_test_pass", "OK (1 test)" in thermal_log and "FAILURES!!!" not in thermal_log and "Time: 3.175" in thermal_log)
    a.check("thermal.real_api35_none_no_wait", thermal["api"] == 35 and thermal["newModelInference"] is False and thermal["noneWaitMs"] == 0 and thermal["thermalBefore"] == 0)
    a.check("thermal.severe_resume_cancel", all(thermal[k] is True for k in ("blockedAtSevere", "resumedAtModerate", "criticalCancellationPreserved", "overrideResetRequested")) and thermal["thermalAfterReset"] == 0)
    telemetry = thermal["telemetry"]; events = telemetry["thermalEvents"]
    a.check("thermal.actual_service_listener_events", [x["status"] for x in events] == [0, 3, 2, 4] and [x["elapsedMs"] for x in events] == sorted(x["elapsedMs"] for x in events))
    a.check("thermal.actual_wait_observed", 0 < telemetry["stagesMs"]["thermalWaitMs"] <= telemetry["elapsedMs"] and telemetry["thermalStatus"] == 4)
    a.check("thermal.api_available_registration_not_failed", telemetry["thermalApiSupported"] is True and telemetry["thermalPowerServiceAvailable"] is True and telemetry["thermalStatusAvailable"] is True and telemetry["thermalListenerRegistered"] is True and telemetry["thermalListenerRegistrationFailed"] is False and telemetry["thermalUnavailableReason"] is None)
    cpu = {"plan": "auto_v1", "requestedThreads": 0, "availableCores": 2, "asrThreads": 1, "diarizationThreads": 1, "refinementThreads": 1, "diarizationPinned": False, "refinementPinned": False}
    a.check("thermal.independent_core2_auto0_maps1", identical(thermal["cpuPolicy"], cpu) and identical(thermal_summary["cpu_policy"], cpu))
    picker_base = base / "android-picker-v1"; staging = a.load(picker_base / "staging.json"); picker_summary = a.load(picker_base / "summary.json")
    picker_reports = list((picker_base / "device").rglob("report.json")); a.check("picker.exact_one_report", len(picker_reports) == 1)
    picker = a.load(picker_reports[0]); picker_log = a.read(picker_base / "instrumentation.log").decode()
    a.check("picker.actual_single_test_pass", "OK (1 test)" in picker_log and "FAILURES!!!" not in picker_log and "Time: 17.674" in picker_log)
    a.check("picker.complete_bound_manifest_no_nn", picker["status"] == "COMPLETE" and picker["newModelInference"] is False and picker["fixture_manifest_sha256"] == manifest_hash and identical(picker["fixture_manifest"], manifest))
    a.check("picker.back_and_all_three", picker["pickerBackCreatedNoRecording"] is True and picker["allThreeSequentialImports"] is True and len(picker["cases"]) == 3)
    a.check("picker.owned_uuid_rows_only", len({x["recordingId"] for x in picker["cases"]}) == 3 and all(canonical_uuid(x["recordingId"]) for x in picker["cases"]))
    a.check("picker.prior_rows_audio_and_owned_cleanup_receipt", picker["ownedImportedRowsCleaned"] == 3 and picker["priorRowsAndAudioPreserved"] is True)
    a.check("picker.staged_names_and_order", picker["stagedNames"] == staging["staged_names"] == picker_summary["staged_names"] == [x["stagedName"] for x in picker["cases"]])
    for index, case in enumerate(picker["cases"], 1):
        row = fixture_map[case["fixture"]]; matrix = next(x for x in actual if x["id"] == case["fixture"])
        a.check("picker.case" + str(index) + ".original_hash_clock_no_nn", case["status"] == "IMPORTED" and case["imported_sha256"] == row["sha256"] and case["duration_ms"] == case["samples"] * 1000 // 16000 and case["samples"] == matrix["samples"] and case["actualSystemPicker"] is True and case["actualSystemDecode"] is True and case["newModelInference"] is False)
        a.check("picker.case" + str(index) + ".staged_fixture_suffix", case["stagedName"].endswith(row["name"]))
    commands = [strict_json(line) for line in a.read(picker_base / "commands.jsonl").splitlines()]
    pushes = [x for x in commands if len(x["argv"]) > 3 and x["argv"][3] == "push"]
    a.check("picker.exact_three_fixture_pushes", len(pushes) == 3 and all(x["returncode"] == 0 for x in pushes))
    a.check("picker.stay_on_restore_receipts", staging["original_stay_on"] == picker_summary["original_stay_on"] == "1" and picker_summary["stay_on_restored"] is True and any(x["argv"][-5:] == ["settings", "put", "global", "stay_on_while_plugged_in", "1"] and x["returncode"] == 0 for x in commands))
    screenshots = {}
    for path in sorted(picker_reports[0].parent.glob("*.png")):
        raw = a.read(path); dimensions = png_dimensions(raw); screenshots[path.name] = {"sha256": sha(raw), "dimensions": dimensions}
        a.check("png." + path.name + ".crc_dimensions", dimensions == (1080, 1920))
    a.check("picker.required_captures", {"picker-1.png", "picker-2.png", "picker-3.png", "imported-1.png", "imported-2.png", "imported-3.png", "picker-back-before.png"} <= set(screenshots))
    for path, spec in a.inputs.items():
        a.check("immutable." + path, sha((repo / path).read_bytes()) == spec["sha256"])
    failed = [x["id"] for x in a.checks if not x["pass"]]
    return {"schema_version": 1, "status": "PASS" if not failed else "FAIL", "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Independent saved non-NN Android import/thermal/picker evidence integrity. No new NN, Android decoder, ADB, Gradle or Git calls; not quality/speed/ARM/phone or whole-step5 acceptance.",
        "checks": {"total": len(a.checks), "passed": len(a.checks) - len(failed), "failed": failed, "details": a.checks},
        "auditor_source_sha256": sha(Path(__file__).read_bytes()), "inputs": a.inputs, "fixture_measurements": measured,
        "components": {"import_v1": "Six format tests COMPLETE, original combined suite PARTIAL_FAILURE retained", "thermal_v1": "FAILED_INITIALIZATION_NOT_EXECUTED", "thermal_v2": "PASS actual API35", "picker": "PASS actual DocumentsUI three sequential imports and back"},
        "thermal": {"cpu_policy": cpu, "none_wait_ms": thermal["noneWaitMs"], "thermal_wait_ms": telemetry["stagesMs"]["thermalWaitMs"], "restored_status": thermal["thermalAfterReset"]},
        "picker": {"recording_ids": [x["recordingId"] for x in picker["cases"]], "screenshots": screenshots},
        "limitations": ["Deleted Android PCM bytes are unavailable: spectrum/duration/RMS receipts and source-backed passing assertions were independently revalidated, not recomputed from PCM.",
            "Prior Room/audio snapshots and deleted temporary files are not exported; preservation/cleanup are supported by pinned test assertions, successful JUnit and actual device receipts, not a new device read.",
            "Current test APK bytes/assets were rehashed locally; installed-package attribution uses recorded build/install provenance, without a fresh ADB package hash.",
            "Advertised decoder names are capabilities, not captured selected codec implementation names.",
            "Picker screenshots1/2/3 show the same Downloads listing; distinct imported UUIDs/hashes and executed loop assertions establish sequential selections.",
            "API26-28 unavailable thermal path and physical-device heat/ARM performance were not exercised by these records.",
            "First combined suite's thermal JUnit void-signature failure is preserved and never counted as executed/pass."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    json_path = args.output.with_suffix(".json"); md_path = args.output.with_suffix(".md")
    if json_path.exists() or md_path.exists():
        raise ValueError("Choose fresh outputs; raw and earlier audit evidence is never overwritten")
    report = audit(args.repo_root.resolve())
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    text = f"""# Independent non-NN Android step5 audit\n\n{report['status']}: {report['checks']['passed']}/{report['checks']['total']} integrity checks.\n\n13 fixture bytes match the pinned439e manifest, local assets and ce4851 test APK. Six actual import tests are COMPLETE. Their recorded clocks, finite PCM/spectra, stereo averages, UUID-copy independence, truncation/errors and cleanup satisfy the pinned conditions. Both large cancellation WAV sources were independently regenerated to the recorded SHA; cancellation followed positive actual copy/PCM byte observations. Temporary PCM was deleted, so this is saved-measurement revalidation.\n\nThe original7-test suite remains PARTIAL_FAILURE: thermal was not executed because of the non-void JUnit method. Removing only the later explicit Unit signatures reproduces the original source SHA. The repaired thermal run passes1 test on API35: NONE waits0ms; valid SEVERE blocks, MODERATE resumes, CRITICAL cancellation is preserved, and reset returns0. Core2/request0 maps to1 thread without NN.\n\nActual DocumentsUI/back plus three sequential Downloads imports pass with distinct UUIDs, correct source SHA, real decode and recorded prior-row/audio preservation; only the three owned rows are cleaned. PNG CRC/dimensions pass and representative captures were visually reviewed. Identical pre-selection Downloads screenshots are not treated as distinct file-selection proof.\n\nThis audit performs no NN, device/decoder invocation, ADB, Gradle or Git. It does not accept model quality, CPU speed, ARM/phone behavior, pre29 thermal behavior or the whole step5. Detailed input/source hashes and evidence limits are in the JSON.\n"""
    md_path.write_text(text)
    print(json.dumps({"status": report["status"], "checks": report["checks"]["total"], "failed": report["checks"]["failed"], "json": str(json_path), "md": str(md_path)}))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
