import importlib.util
import copy
import math
from pathlib import Path
import struct
import unittest


SPEC = importlib.util.spec_from_file_location("native_policy", Path(__file__).resolve().parents[1] / "native_policy.py")
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def host_for(plan):
    value = policy.policy_for_plan(plan)
    result = {"schema_version": 1, "id": "policy-test", "pipeline": value["pipeline"],
              "threads": 2, "expected_speakers": -1}
    if value["pipeline"] != "v16":
        result.update({key: val for key, val in value.items() if key != "pipeline"})
    return result


def report_for(plan):
    return {"threads": 2, "expectedSpeakers": -1, "asrPlan": plan,
            "asrPolicy": policy.policy_for_plan(plan)}


class NativePolicyTest(unittest.TestCase):
    def test_every_explicit_preset_matches(self):
        self.assertEqual(set(policy.PLAN_POLICIES), {"v16", "vad_words_none", "vad_words_seam", "vad_words_short15", "vad_words_short10", "vad_words_sensitive", "vad_words_short10_seam", "vad_words_sensitive_short10", "vad_words_context300", "vad_words_context600"})
        for plan in policy.PLAN_POLICIES:
            with self.subTest(plan=plan):
                self.assertEqual(policy.validate_native_policy(host_for(plan), report_for(plan)), policy.policy_for_plan(plan))

    def test_interaction_presets_have_the_exact_requested_fields(self):
        for plan, punctuation, threshold in (("vad_words_short10_seam", "seam", .5),
                                             ("vad_words_sensitive_short10", "none", .35)):
            self.assertEqual(policy.policy_for_plan(plan), {
                "pipeline": "vad_words_v1", "punctuation_mode": punctuation,
                "energy_split": True, "vad_threshold": threshold,
                "vad_min_speech_sec": .10, "vad_min_silence_sec": .12, "pre_roll_ms": 100})

    def test_context_presets_change_only_integer_pre_roll(self):
        self.assertEqual(len(policy.POLICY_FIELDS), 7)
        base = policy.policy_for_plan("vad_words_none")
        self.assertEqual(100, policy.policy_for_plan("v16")["pre_roll_ms"])
        for plan, milliseconds in (("vad_words_context300", 300), ("vad_words_context600", 600)):
            actual = policy.policy_for_plan(plan)
            self.assertEqual(actual, {**base, "pre_roll_ms": milliseconds})
            self.assertIs(type(actual["pre_roll_ms"]), int)
            self.assertEqual(policy.validate_native_policy(host_for(plan), report_for(plan)), actual)

    def test_legacy_v16_and_explicit_v16_without_policy(self):
        host = host_for("v16")
        for report in ({"threads": 2, "expectedSpeakers": -1},
                       {"threads": 2, "expectedSpeakers": -1, "asrPlan": "v16"}):
            self.assertEqual(policy.validate_native_policy(host, report), policy.policy_for_plan("v16"))
        report = report_for("v16")
        report.pop("asrPlan")
        with self.assertRaisesRegex(ValueError, "Missing native asrPlan"):
            policy.validate_native_policy(host, report)

    def test_defaults_only_apply_to_host_vad_and_preroll_fields(self):
        host = host_for("vad_words_none")
        for key in policy.VAD_FIELDS:
            host.pop(key)
        host.pop("pre_roll_ms")
        self.assertEqual(policy.validate_native_policy(host, report_for("vad_words_none")), policy.policy_for_plan("vad_words_none"))
        for key in ("punctuation_mode", "energy_split"):
            changed = dict(host)
            changed.pop(key)
            with self.assertRaises(ValueError):
                policy.validate_native_policy(changed, report_for("vad_words_none"))

    def test_word_policy_cannot_be_missing_or_partial(self):
        for field in ("asrPlan", "asrPolicy"):
            report = report_for("vad_words_sensitive")
            report.pop(field)
            with self.assertRaises(ValueError):
                policy.validate_native_policy(host_for("vad_words_sensitive"), report)
        for key in policy.POLICY_FIELDS:
            report = report_for("vad_words_short15")
            report["asrPolicy"].pop(key)
            with self.assertRaisesRegex(ValueError, "fields differ"):
                policy.validate_native_policy(host_for("vad_words_short15"), report)

    def test_unknown_plan_pipeline_and_stale_host_fields(self):
        for plan in (None, "vad_words_future", [], 1):
            with self.assertRaises(ValueError):
                policy.policy_for_plan(plan)
        for unknown in (None, "v17", "vad_words_none"):
            host = host_for("v16")
            host["pipeline"] = unknown
            with self.assertRaisesRegex(ValueError, "pipeline"):
                policy.validate_native_policy(host, report_for("v16"))
        for field, value in (("vad_threshold", .35), ("punctuation_mode", "none"), ("energy_split", True), ("pre_roll_ms", 100), ("pre_roll_ms", 300), ("unknown_setting", 1)):
            host = host_for("v16")
            host[field] = value
            with self.assertRaisesRegex(ValueError, "stale host"):
                policy.validate_native_policy(host, report_for("v16"))

    def test_all_cross_preset_mismatches_rejected(self):
        for host_plan in policy.PLAN_POLICIES:
            for native_plan in policy.PLAN_POLICIES:
                if host_plan == native_plan:
                    continue
                with self.subTest(host=host_plan, native=native_plan), self.assertRaises(ValueError):
                    policy.validate_native_policy(host_for(host_plan), report_for(native_plan))

    def test_native_policy_must_match_its_plan_not_just_host_name(self):
        for field, changed in (("punctuation_mode", "seam"), ("energy_split", False),
                               ("vad_threshold", .35), ("vad_min_speech_sec", .15),
                               ("vad_min_silence_sec", .20), ("pre_roll_ms", 300), ("pipeline", "v16")):
            report = report_for("vad_words_none")
            report["asrPolicy"][field] = changed
            with self.assertRaises(ValueError):
                policy.validate_native_policy(host_for("vad_words_none"), report)
        report = report_for("vad_words_none")
        report["asrPolicy"]["extra"] = True
        with self.assertRaisesRegex(ValueError, "fields differ"):
            policy.validate_native_policy(host_for("vad_words_none"), report)

    def test_thread_and_speaker_validation_rejects_bool_float_and_mismatch(self):
        for key, bad_values in (("threads", (None, True, 2., "2", 0, 3, 8)),
                                ("expected_speakers", (None, True, -1., "-1", 0, 21))):
            for bad in bad_values:
                host = host_for("vad_words_none")
                host[key] = bad
                with self.assertRaises(ValueError):
                    policy.validate_native_policy(host, report_for("vad_words_none"))
        for key in ("threads", "expectedSpeakers"):
            for bad in (None, True, 2., "2", 0, 21):
                report = report_for("vad_words_none")
                report[key] = bad
                with self.assertRaises(ValueError):
                    policy.validate_native_policy(host_for("vad_words_none"), report)
        report = report_for("vad_words_none")
        report["threads"] = 4
        with self.assertRaisesRegex(ValueError, "differ"):
            policy.validate_native_policy(host_for("vad_words_none"), report)
        report = report_for("vad_words_none")
        report["expectedSpeakers"] = 2
        with self.assertRaisesRegex(ValueError, "differ"):
            policy.validate_native_policy(host_for("vad_words_none"), report)

    def test_vad_values_reject_invalid_types_nonfinite_and_bounds(self):
        for field in policy.VAD_FIELDS:
            for bad in (None, True, "0.5", math.nan, math.inf, -math.inf, -.5, 2, 10**1000):
                host = host_for("vad_words_none")
                host[field] = bad
                with self.assertRaises(ValueError):
                    policy.validate_native_policy(host, report_for("vad_words_none"))
                report = report_for("vad_words_none")
                report["asrPolicy"][field] = bad
                with self.assertRaises(ValueError):
                    policy.validate_native_policy(host_for("vad_words_none"), report)
        host = host_for("vad_words_none")
        host["energy_split"] = 1
        with self.assertRaises(ValueError):
            policy.validate_native_policy(host, report_for("vad_words_none"))

    def test_exact_float32_equivalence_not_arbitrary_epsilon(self):
        report = report_for("vad_words_sensitive")
        for key in policy.VAD_FIELDS:
            report["asrPolicy"][key] = struct.unpack("!f", struct.pack("!f", report["asrPolicy"][key]))[0]
        self.assertEqual(policy.validate_native_policy(host_for("vad_words_sensitive"), report), policy.policy_for_plan("vad_words_sensitive"))
        report["asrPolicy"]["vad_threshold"] = .35001
        with self.assertRaises(ValueError):
            policy.validate_native_policy(host_for("vad_words_sensitive"), report)

    def test_preroll_requires_exact_bounded_integer_on_both_sides(self):
        for bad in (None, True, False, "100", 100., math.nan, math.inf, -1, 1001, 10**1000):
            host = host_for("vad_words_none")
            host["pre_roll_ms"] = bad
            with self.subTest(side="host", value=bad), self.assertRaisesRegex(ValueError, "pre_roll_ms"):
                policy.validate_native_policy(host, report_for("vad_words_none"))
            report = report_for("vad_words_none")
            report["asrPolicy"]["pre_roll_ms"] = bad
            with self.subTest(side="native", value=bad), self.assertRaisesRegex(ValueError, "pre_roll_ms"):
                policy.validate_native_policy(host_for("vad_words_none"), report)
        for boundary in (0, 1000):
            value = {**policy.policy_for_plan("vad_words_none"), "pre_roll_ms": boundary}
            self.assertEqual(boundary, policy._validate_policy(value, "bounded policy")["pre_roll_ms"])

    def test_stale_native_six_fields_and_wrong_context_are_rejected(self):
        old_report = report_for("vad_words_none")
        old_report["asrPolicy"].pop("pre_roll_ms")
        with self.assertRaisesRegex(ValueError, "fields differ"):
            policy.validate_native_policy(host_for("vad_words_none"), old_report)
        for plan in ("vad_words_context300", "vad_words_context600"):
            report = report_for(plan)
            report["asrPolicy"]["pre_roll_ms"] = 100
            with self.assertRaisesRegex(ValueError, "does not match declared plan"):
                policy.validate_native_policy(host_for(plan), report)
            host = host_for(plan)
            host.pop("pre_roll_ms")
            with self.assertRaisesRegex(ValueError, "Host config does not match native plan"):
                policy.validate_native_policy(host, report_for(plan))
        with self.assertRaisesRegex(ValueError, "Unknown native ASR plan"):
            policy.policy_for_plan("vad_words_context400")

    def test_returned_policies_are_independent_and_inputs_unchanged(self):
        first = policy.policy_for_plan("vad_words_sensitive")
        first["vad_threshold"] = .9
        self.assertEqual(policy.policy_for_plan("vad_words_sensitive")["vad_threshold"], .35)
        host, report = host_for("vad_words_short10"), report_for("vad_words_short10")
        before_host, before_policy = dict(host), dict(report["asrPolicy"])
        returned = policy.validate_native_policy(host, report)
        returned["energy_split"] = False
        self.assertEqual(host, before_host)
        self.assertEqual(report["asrPolicy"], before_policy)
        self.assertTrue(policy.policy_for_plan("vad_words_short10")["energy_split"])


def word_diagnostics():
    return {"wordEvidenceRequested": True, "wordEvidenceApplicable": True,
            "wordEvidenceTruncated": False, "wordAssignmentSupported": True,
            "fallbackChunks": 0, "asrSlices": [
                {"wordEvidenceIncluded": True, "wordAssignmentSupported": True,
                 "tokenCount": 2, "timestampCount": 2, "wordCount": 1,
                 "tokens": ["▁Привет", "!"], "timestamps": [.04, .08],
                 "words": [{"startMs": 40, "endMs": 80, "text": "Привет!"}]}]}


class NativeWordEvidenceTest(unittest.TestCase):
    def test_complete_payload_and_inputs_unchanged(self):
        value = word_diagnostics()
        before = copy.deepcopy(value)
        result = policy.validate_word_evidence(value)
        self.assertTrue(result["validated"])
        self.assertEqual((result["slices"], result["tokenCount"], result["timestampCount"], result["wordCount"]), (1, 2, 2, 1))
        self.assertEqual(value, before)

    def test_no_speech_with_explicit_qa_flags_is_valid(self):
        value = word_diagnostics()
        value["asrSlices"] = []
        result = policy.validate_word_evidence(value)
        self.assertEqual((result["slices"], result["tokenCount"], result["wordCount"]), (0, 0, 0))
        value.pop("wordEvidenceRequested")
        with self.assertRaises(ValueError):
            policy.validate_word_evidence(value)

    def test_global_flags_missing_truncated_unsupported_or_fallback_rejected(self):
        for field, invalid in (("wordEvidenceRequested", False), ("wordEvidenceApplicable", False),
                               ("wordEvidenceTruncated", True), ("wordAssignmentSupported", False),
                               ("fallbackChunks", 1)):
            for replacement in (invalid, None, 1 if field != "fallbackChunks" else False):
                value = word_diagnostics()
                value[field] = replacement
                with self.subTest(field=field, value=replacement), self.assertRaises(ValueError):
                    policy.validate_word_evidence(value)
            value = word_diagnostics()
            value.pop(field)
            with self.assertRaises(ValueError):
                policy.validate_word_evidence(value)

    def test_slice_payload_or_support_cannot_be_missing(self):
        for field in ("wordEvidenceIncluded", "wordAssignmentSupported", "tokens", "timestamps", "words",
                      "tokenCount", "timestampCount", "wordCount"):
            value = word_diagnostics()
            value["asrSlices"][0].pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                policy.validate_word_evidence(value)
        for flag in ("wordEvidenceIncluded", "wordAssignmentSupported"):
            value = word_diagnostics()
            value["asrSlices"][0][flag] = False
            with self.assertRaises(ValueError):
                policy.validate_word_evidence(value)

    def test_counts_are_exact_nonnegative_integers_and_match_arrays(self):
        for field in ("tokenCount", "timestampCount", "wordCount"):
            for invalid in (True, -1, 1., 99):
                value = word_diagnostics()
                value["asrSlices"][0][field] = invalid
                with self.subTest(field=field, value=invalid), self.assertRaises(ValueError):
                    policy.validate_word_evidence(value)
        value = word_diagnostics()
        value["asrSlices"][0].update(timestampCount=1, timestamps=[.04])
        with self.assertRaisesRegex(ValueError, "token/timestamp counts differ"):
            policy.validate_word_evidence(value)

    def test_no_fabricated_empty_arrays_when_payload_omitted(self):
        value = word_diagnostics()
        item = value["asrSlices"][0]
        item.update(tokenCount=0, timestampCount=0, wordCount=0)
        for key in ("tokens", "timestamps", "words"):
            item.pop(key)
        with self.assertRaises(ValueError):
            policy.validate_word_evidence(value)

    def test_array_shapes_and_nonfinite_timestamp_entries_rejected(self):
        for invalid in (None, {}, (), "slices"):
            value = word_diagnostics()
            value["asrSlices"] = invalid
            with self.assertRaises(ValueError):
                policy.validate_word_evidence(value)
        for field, values in (("tokens", ["word", None]), ("timestamps", [.04, None]),
                              ("timestamps", [.04, math.nan]), ("timestamps", [.04, math.inf]),
                              ("timestamps", [.04, 10**1000]),
                              ("timestamps", [.04, True]), ("words", [None])):
            value = word_diagnostics()
            value["asrSlices"][0][field] = values
            with self.subTest(field=field, values=values), self.assertRaises(ValueError):
                policy.validate_word_evidence(value)


if __name__ == "__main__":
    unittest.main()
