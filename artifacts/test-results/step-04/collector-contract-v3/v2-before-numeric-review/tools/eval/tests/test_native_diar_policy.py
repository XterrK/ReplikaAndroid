"""Synthetic QA payload mutation tests; no native/audio/model inference."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import struct
import unittest
from unittest import mock

from tools.eval import native_diar_policy as p
from tools.eval import pipeline as base
from tools.eval.pipeline_refined import PAIRED_ASR_POLICY
from tools.eval.speaker_refiner import clean_windows
from tools.eval.window_overcluster import WindowClusterConfig, overcluster
from tools.eval.vad_words import words_from_tokens, assign_words

# Explicit Room fixture contract, independently listed from the Kotlin Worker's
# compactRefinerDiagnostic. Full vectors/tree/atoms/eigengap maps are never here.
ROOM_REFINER_SCALARS = ("algorithm", "duration_ms", "new_neural_inference", "eigengap_applied",
    "boundary_timing_scope", "native_input_clusters", "scipy_version", "cut_distance", "cut_inclusive",
    "linkage_method", "canonical_window_order", "window_clusters_at_cut", "window_clusters_after_cap",
    "fully_acoustic_supported", "every_native_label_has_measured_windows", "clusters_after_voting",
    "small_cluster_cutoff_ms", "clusters_after_small", "status", "measured_unique_windows", "embedding_dimension",
    "output_clusters", "original_activity_union_ms", "output_activity_union_ms", "activity_union_preserved",
    "original_speaker_time_ms", "output_speaker_time_ms", "speaker_time_collapsed_ms",
    "grid_boundary_resolution_ms", "max_assignment_atom_ms")


def room_fixture(full):
    # Outer adapter has only these scalar fields plus config and nested refiner.
    outer = {key: deepcopy(full[key]) for key in (
        "algorithm", "config", "status", "computationalSupport", "qualityAcceptance", "originalPcm",
        "sampleRate", "cleanWindowMs", "cleanWindowStepMs", "cleanMinimumIslandMs", "embeddingInferenceCompleted",
        "embeddingScope", "nativeResourcesReleasedBeforeRefiner", "retainedNativeModelCache")}
    outer["refiner"] = {key: deepcopy(full["refiner"][key]) for key in ROOM_REFINER_SCALARS}
    outer["refiner"]["config"] = deepcopy(full["refiner"]["config"])
    return outer


def host():
    return {"schema_version": 1, "id": "C2-test", "pipeline": "window_words_v1", "expected_speakers": -1,
            "threads": 2, "model_id": "eres2net_zh", "window_shift": .1, "native_threshold": .3,
            "window_config": deepcopy(p.WINDOW_CONFIG)}


def native_policy():
    return {"threads": 2, "expectedSpeakers": -1, "asrPlan": p.ASR_PLAN,
            "asrPolicy": p.policy_for_plan(p.ASR_PLAN), "diarizationPlanRequested": p.PLAN,
            "diarizationPlan": p.PLAN, "diarizationPolicy": p.policy_for_diar_plan()}


def evidence_fixture(*, short_missing=False):
    duration = 4000 if short_missing else 3000
    native = [base.Turn(0, 3000, 0)] + ([base.Turn(3500, 3800, 1)] if short_missing else [])
    windows = [replace(w, embedding=(1.,) + (0.,) * 511) for w in clean_windows(native, duration)]
    result = overcluster(native, windows, duration, WindowClusterConfig(**p.WINDOW_CONFIG))
    diagnostic = native_policy()
    diagnostic.update(audioMs=duration, sampleRate=16000, vadThreads=1, clusteringMode="automatic",
        clusterThresholdApplied=True, runtime="sherpa-onnx 2.0.1", backend=base.SOURCE,
        diarizationRefinementApplicable=True, diarizationRefinementAccepted=True,
        diarizationEvidenceRequested=True, diarizationEvidenceTruncated=False,
        diarizationEvidenceOmittedReason=None, preRollMs=600, postRollMs=0,
        maxAsrSegmentMs=20000, vadWindowSamples=512, vadMaxSpeechSec=20, totalMs=120,
        clusterThreshold=base._f32(.3), segmentationWindowShiftRatio=base._f32(.1),
        diarMinDurationOnSec=base._f32(.2), diarMinDurationOffSec=.5,
        vadThreshold=.5, vadMinSpeechSec=.25, vadMinSilenceSec=.25,
        rawDiarizationTurns=p.turn_json(native), nativeDiarizationTurns=p.turn_json(native),
        diarizationTurns=p.turn_json(result.turns))
    adapter = {"algorithm": "window-overcluster-v1", "config": deepcopy(p.WINDOW_CONFIG),
        "status": result.diagnostics["status"], "computationalSupport": True, "originalPcm": True,
        "qualityAcceptance": "not evaluated by this adapter",
        "sampleRate": 16000, "cleanWindowMs": 1500, "cleanWindowStepMs": 750, "cleanMinimumIslandMs": 1000,
        "embeddingScope": "Original decoded PCM; no gain, resampling, padding or normalization",
        "embeddingInferenceCompleted": True, "nativeResourcesReleasedBeforeRefiner": True,
        "retainedNativeModelCache": False, "refiner": deepcopy(result.diagnostics)}
    diagnostic["diarizationRefinement"] = room_fixture(adapter)
    n = len(windows)
    diagnostic["diarizationEmbeddingCounts"] = {k: n for k in ("plannedWindows", "readWindows", "createdStreams",
        "releasedStreams", "computeAttempts", "embeddingForwardCalls", "measuredWindows")}
    diagnostic["diarizationEmbeddingCounts"].update(extractorLoads=1, embeddingDimension=512)
    record = {"id": "fixture", "status": "COMPLETE", "audio_sha256": "a" * 64, "duration_ms": duration,
        "newModelInference": True, "processing_ms": 120,
        "workId": "0ea87d75-0b91-430c-8cac-030f77310b2d",
        "recordingId": "qa-evaluation-5d7a8bac-e184-48e9-a3db-c5206e7232e2"}
    wrapper = {"schema_version": 1, "work_id": record["workId"], "recording_id": record["recordingId"],
        "metadata": {"audioMs": duration, "sampleRate": 16000, "inputAudioSha256": "a" * 64,
            "diarizationPlan": p.PLAN, "diarizationPolicy": diagnostic["diarizationPolicy"],
            "runtime": "sherpa-onnx 2.0.1", "embeddingSha256": p.EMBEDDING_SHA256,
            "rawDiarizationTurns": diagnostic["rawDiarizationTurns"],
            "nativeDiarizationTurns": diagnostic["nativeDiarizationTurns"],
            "refinedDiarizationTurns": diagnostic["diarizationTurns"], "accepted": True},
        "windows": [asdict(w) for w in windows], "diagnostics": adapter, "truncated": False}
    # Convert tuples to actual JSON arrays as the sidecar writer does.
    wrapper = json.loads(json.dumps(wrapper))
    return diagnostic, record, wrapper


def bind(diagnostic, record, wrapper):
    raw = json.dumps(wrapper, ensure_ascii=False, allow_nan=False).encode()
    sha = hashlib.sha256(raw).hexdigest()
    record.update(diarizationEvidenceSha256=sha, diarizationEvidenceBytes=len(raw),
                  diarizationEvidenceFile=record["id"] + ".diarization-evidence.json")
    diagnostic.update(diarizationEvidenceSha256=sha, diarizationEvidenceBytes=len(raw),
        diarizationEvidenceFile="diarization-qa/diarization-" + record["workId"] + ".json")
    return raw


def verify(diagnostic, record, wrapper):
    raw = bind(diagnostic, record, wrapper)
    return p.validate_diarization_evidence(diagnostic, record, raw,
        case_id="fixture", audio_sha256="a" * 64, duration_ms=record["duration_ms"])


def word_fixture():
    duration = 3000
    turns = [base.Turn(0, duration, 0)]
    text, tokens, times = "Привет, мир!", ["▁Привет,", "▁мир!"], [0., base._f32(.48)]
    parsed = words_from_tokens(text, tokens, times, 0, duration, 40)
    assigned = assign_words(parsed.words, turns)
    part = {"startMs": 0, "endMs": duration, "speakerId": -1, "text": text, "blank": False,
        "tokens": tokens, "timestamps": times, "tokenCount": 2, "timestampCount": 2,
        "wordCount": len(assigned), "frameStrideMs": 40, "timestampUnit": "seconds within ASR VAD chunk",
        "wordAssignmentSupported": True, "wordAssignmentReason": parsed.reason, "wordEvidenceIncluded": True,
        "words": [{"startMs": w.start_ms, "endMs": w.end_ms, "text": w.text,
                   "speakerId": w.speaker, "warnings": list(w.reasons)} for w in assigned]}
    return {"wordEvidenceRequested": True, "wordEvidenceApplicable": True, "wordEvidenceTruncated": False,
        "wordAssignmentSupported": True, "fallbackChunks": 0, "asrSlices": [part],
        "backend": base.SOURCE, "diarizationTurns": p.turn_json(turns)}


class NativeDiarPolicyTest(unittest.TestCase):
    def test_canonical_policy_and_fresh_copy(self):
        self.assertEqual(p.policy_for_diar_plan(), p.validate_native_diar_policy(host(), native_policy(), dict(PAIRED_ASR_POLICY)))
        changed = p.policy_for_diar_plan()
        changed["window_config"]["tau"] = .8
        self.assertEqual(.36, p.policy_for_diar_plan()["window_config"]["tau"])

    def test_float32_expansion_allowed_one_bit_difference_rejected(self):
        report = native_policy()
        for key in ("native_threshold", "window_shift", "min_duration_on", "min_duration_off"):
            report["diarizationPolicy"][key] = base._f32(report["diarizationPolicy"][key])
        p.validate_native_diar_policy(host(), report, dict(PAIRED_ASR_POLICY))
        bits = struct.unpack("!I", struct.pack("!f", .3))[0]
        report["diarizationPolicy"]["native_threshold"] = struct.unpack("!f", struct.pack("!I", bits + 1))[0]
        with self.assertRaisesRegex(ValueError, "Float32"):
            p.validate_native_diar_policy(host(), report, dict(PAIRED_ASR_POLICY))

    def test_stale_host_unknown_policy_and_invalid_types_rejected(self):
        for key, value in (("pipeline", "refined_words_v1"), ("threads", True), ("threads", 2.),
                           ("expected_speakers", 2), ("model_id", "resnet34"), ("native_threshold", float("nan"))):
            value_host = host(); value_host[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate_host_policy(value_host, dict(PAIRED_ASR_POLICY))
        for key, value in (("grid_ms", 125.), ("reassign_small", 1), ("tau", base._f32(.36)),
                           ("minimum_reassignment_similarity", .7)):
            value_host = host(); value_host["window_config"][key] = value
            with self.subTest(window=key), self.assertRaises(ValueError):
                p.validate_host_policy(value_host, dict(PAIRED_ASR_POLICY))
        for key in ("asrPolicy", "diarizationPolicy", "diarizationPlanRequested", "diarizationPlan"):
            report = native_policy(); report.pop(key)
            with self.subTest(field=key), self.assertRaises(ValueError):
                p.validate_native_diar_policy(host(), report, dict(PAIRED_ASR_POLICY))
        wrong = dict(PAIRED_ASR_POLICY); wrong["pre_roll_ms"] = 100
        with self.assertRaises(ValueError):
            p.validate_host_policy(host(), wrong)

    def test_legacy_seven_order_and_pin_guard(self):
        rows = [{"group": path.split("/")[0], "path": path, "size": size, "sha256": sha}
                for path, size, sha in p.MODEL_PINS]
        self.assertEqual(7, len(p.validate_model_lock({"files": rows})))
        for changed in (rows[:-1], rows + [rows[0]], list(reversed(rows))):
            with self.assertRaises(ValueError):
                p.validate_model_lock({"files": changed})
        rows[0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            p.validate_model_lock({"files": rows})


class NativeDiarEvidenceTest(unittest.TestCase):
    def test_complete_real_shape_and_partial_temporal_algorithm_replay(self):
        for missing in (False, True):
            d, c, w = evidence_fixture(short_missing=missing)
            result = verify(d, c, w)
            self.assertTrue(result["python_replay_exact_turns"])
            self.assertEqual(512, result["dimension"])
            self.assertEqual("PARTIAL_TEMPORAL" if missing else "SUPPORTED", result["status"])

    def test_identity_hash_size_and_confined_filename_guards(self):
        for mutate in (lambda d,c,w: c.update(workId="../notUUID"),
                       lambda d,c,w: c.update(recordingId=3),
                       lambda d,c,w: w.update(work_id="09d6acee-c3fc-4a97-a6bf-6ed33468f394"),
                       lambda d,c,w: w["metadata"].update(inputAudioSha256="b"*64),
                       lambda d,c,w: w["metadata"].update(embeddingSha256="b"*64)):
            d,c,w = evidence_fixture(); mutate(d,c,w)
            with self.assertRaises(ValueError): verify(d,c,w)
        for field, value in (("diarizationEvidenceSha256", "b"*64), ("diarizationEvidenceBytes", 1),
                             ("diarizationEvidenceFile", "../escape.json")):
            d,c,w = evidence_fixture(); raw=bind(d,c,w); c[field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                p.validate_diarization_evidence(d,c,raw,case_id="fixture",audio_sha256="a"*64,duration_ms=3000)

    def test_missing_null_truncated_resources_and_counters_rejected(self):
        mutations = [lambda d,c,w: d.pop("diarizationEvidenceOmittedReason"),
            lambda d,c,w: w.update(truncated=True), lambda d,c,w: d.update(diarizationEvidenceTruncated=True),
            lambda d,c,w: d["diarizationEmbeddingCounts"].update(releasedStreams=0),
            lambda d,c,w: d["diarizationEmbeddingCounts"].update(extractorLoads=2)]
        for mutation in mutations:
            d,c,w=evidence_fixture();mutation(d,c,w)
            with self.assertRaises(ValueError):verify(d,c,w)
        d,c,w=evidence_fixture()
        d["diarizationRefinement"]["nativeResourcesReleasedBeforeRefiner"]=False
        w["diagnostics"]["nativeResourcesReleasedBeforeRefiner"]=False
        with self.assertRaisesRegex(ValueError, "nativeResourcesReleased"):
            verify(d,c,w)

    def test_embedding_arrays_missing_duplicate_clock_dimension_f32_rejected(self):
        mutations = [lambda w:w["windows"].pop(),lambda w:w["windows"].append(deepcopy(w["windows"][0])),
            lambda w:w["windows"][0].update(clean=False),lambda w:w["windows"][0].update(start_ms=1),
            lambda w:w["windows"][0]["embedding"].pop(),lambda w:w["windows"][0]["embedding"].__setitem__(0,.1),
            lambda w:w["windows"][0].update(embedding=[0.]*512)]
        for mutation in mutations:
            d,c,w=evidence_fixture();mutation(w)
            with self.assertRaises(ValueError):verify(d,c,w)

    def test_matching_forged_turn_copies_fail_actual_python_replay(self):
        d,c,w=evidence_fixture()
        d["diarizationTurns"][0]["endMs"]=2999
        w["metadata"]["refinedDiarizationTurns"]=deepcopy(d["diarizationTurns"])
        with self.assertRaisesRegex(ValueError,"replay differs"):
            verify(d,c,w)

    def test_forged_trace_and_raw_stable_remap_rejected(self):
        d,c,w=evidence_fixture()
        d["diarizationRefinement"]["refiner"]["output_clusters"]=8
        w["diagnostics"]["refiner"]["output_clusters"]=8
        with self.assertRaisesRegex(ValueError,"replay differs"):
            verify(d,c,w)
        d,c,w=evidence_fixture()
        d["nativeDiarizationTurns"][0]["speakerId"]=1
        w["metadata"]["nativeDiarizationTurns"]=deepcopy(d["nativeDiarizationTurns"])
        with self.assertRaisesRegex(ValueError,"stable"):
            verify(d,c,w)

    def test_actual_compact_room_vs_full_qa_distinct_representations(self):
        d,c,w=evidence_fixture()
        full=w["diagnostics"];room=d["diarizationRefinement"]
        self.assertNotEqual(full,room)
        self.assertTrue(full["refiner"]["linkage_tree"])
        self.assertTrue(full["refiner"]["cluster_centroids"])
        for key in ("linkage_tree","cluster_centroids","eigengap_diagnostic","assignment_atoms","assignment_method_speaker_ms"):
            self.assertIn(key,full["refiner"]);self.assertNotIn(key,room["refiner"])
        self.assertIsNone(room["config"]["minimum_reassignment_similarity"])
        self.assertIsNone(room["refiner"]["config"]["minimum_reassignment_similarity"])
        self.assertEqual(room,p.compact_refiner_diagnostic(full))
        self.assertTrue(verify(d,c,w)["python_replay_exact_turns"])

    def test_compact_projection_scalar_null_config_and_recursive_refiner_only(self):
        full={"scalar":1,"flag":True,"nullable":None,"text":"kept","list":[1],"map":{"removed":True},
              "config":{"nullable":None,"array":[{"kept":True}]},
              "refiner":{"scalar":2,"nullable":None,"config":{"nested":None},
                         "tree":[[1,2]],"arbitraryMap":{"removed":True},"refiner":{"nestedScalar":"yes","array":[]}}}
        expected={"scalar":1,"flag":True,"nullable":None,"text":"kept",
              "config":{"nullable":None,"array":[{"kept":True}]},
              "refiner":{"scalar":2,"nullable":None,"config":{"nested":None},"refiner":{"nestedScalar":"yes"}}}
        self.assertEqual(expected,p.compact_refiner_diagnostic(full))

    def test_room_only_missing_extra_scalar_or_config_mutation_rejected(self):
        for mutate in (lambda room:room.pop("status"),
                       lambda room:room["refiner"].update(output_clusters=8),
                       lambda room:room["refiner"].update(cluster_centroids=[]),
                       lambda room:room["config"].pop("minimum_reassignment_similarity")):
            d,c,w=evidence_fixture();mutate(d["diarizationRefinement"])
            with self.assertRaisesRegex(ValueError,"Room compact adapter"):
                verify(d,c,w)

    def test_full_qa_only_tree_or_vector_mutation_survives_compact_but_fails_replay(self):
        for mutate in (lambda refiner:refiner["linkage_tree"][0].__setitem__(2,.25),
                       lambda refiner:refiner["cluster_centroids"][0]["embedding"].__setitem__(0,.25)):
            d,c,w=evidence_fixture();mutate(w["diagnostics"]["refiner"])
            self.assertEqual(d["diarizationRefinement"],p.compact_refiner_diagnostic(w["diagnostics"]))
            with self.assertRaisesRegex(ValueError,"replay Double differs"):
                verify(d,c,w)

    def test_replay_receives_only_activity_measured_vectors_duration_global_config(self):
        d,c,w=evidence_fixture()
        with mock.patch.object(p,"overcluster",wraps=overcluster) as spy:
            verify(d,c,w)
        args,kwargs=spy.call_args
        self.assertEqual(4,len(args));self.assertEqual({},kwargs)
        self.assertTrue(all(isinstance(t,base.Turn) for t in args[0]))
        self.assertEqual(3000,args[2]);self.assertIsInstance(args[3],WindowClusterConfig)

    def test_duplicate_keys_nonfinite_json_rejected(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):p.strict_json(raw)


class NativeWordsTest(unittest.TestCase):
    def test_actual_words_and_jury_reconstructed_with_punctuation_preserved(self):
        d=word_fixture();hyp,summary=p.reconstruct_jury(d,3000)
        self.assertEqual({"transcript":[{"speaker_id":"speaker_1","start_ms":0,"end_ms":520,"text":"Привет, мир!"}]},hyp)
        self.assertEqual(2,summary["wordCount"])

    def test_forged_word_speaker_text_time_or_frame_stride_rejected(self):
        for mutate in (lambda d:d["asrSlices"][0]["words"][0].update(text="gold replacement"),
                       lambda d:d["asrSlices"][0]["words"][0].update(speakerId=8),
                       lambda d:d["asrSlices"][0]["words"][0].update(startMs=1),
                       lambda d:d["asrSlices"][0].update(frameStrideMs=20),
                       lambda d:d["asrSlices"][0].update(endMs=3001),
                       lambda d:d.update(wordEvidenceTruncated=True),
                       lambda d:d.update(fallbackChunks=1)):
            d=word_fixture();mutate(d)
            with self.assertRaises(ValueError):p.reconstruct_jury(d,3000)

    def test_no_speech_does_not_fabricate_arrays_or_perfect_metrics(self):
        d=word_fixture();d["asrSlices"]=[]
        hyp,summary=p.reconstruct_jury(d,3000)
        self.assertEqual({"transcript":[]},hyp)
        self.assertEqual(0,summary["wordCount"])


if __name__ == "__main__":
    unittest.main()
