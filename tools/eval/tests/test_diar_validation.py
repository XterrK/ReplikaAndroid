"""Independent-cohort gates and real pure replay; no audio/neural inference."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tools.eval import diar_validation as validation
from tools.eval import diar_acceptance as audit
from tools.eval import score
from tools.eval.pipeline import Turn
from tools.eval.speaker_refiner import EmbeddingWindow, RefineConfig, clean_windows, refine
from tools.eval.vad_words import words_from_tokens
from tools.eval.window_overcluster import WindowClusterConfig, overcluster


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(count=5):
    result = []
    for i in range(count):
        edits = {"errors": 1, "reference_tokens": 10, "rate": .1}
        der = {"miss_ms": 10., "false_alarm_ms": 0., "confusion_ms": 0., "reference_speaker_ms": 100., "rate": .1}
        result.append({"id": f"case-{i}", "refiner_accepted": True, "native_speaker_count": 2,
                       "reference_speaker_count": 2, "native_speaker_count_error": 0,
                       "metrics": {"wer_raw": deepcopy(edits), "cpwer_raw": deepcopy(edits),
                                   "native_der_collar_0ms": deepcopy(der), "native_der_collar_250ms": deepcopy(der),
                                   "speakers": {"reference": 2}}})
    return result


class CohortMathTest(unittest.TestCase):
    def check(self, candidate, baseline, asr):
        return validation.evaluate_records(candidate, baseline, asr, expected_ids=[r["id"] for r in baseline], cohort="fixture")

    def test_five_and_ten_cohorts_do_not_inherit_eight_dev_denominator(self):
        for count in (5, 10):
            records = numeric(count)
            result = self.check(records, records, records)
            self.assertTrue(result["gate_pass"])
            self.assertEqual(count, result["conditions"]["exact_native_count_no_regression"]["denominator"])
            self.assertEqual(1, result["aggregate"]["candidate"]["speaker_count_exact_success_fraction"])

    def test_raw_der_and_count_regressions_block_independently(self):
        baseline = numeric()
        for axis in ("raw", "der", "count"):
            candidate, asr = deepcopy(baseline), deepcopy(baseline)
            if axis == "raw":
                for records in (candidate, asr):
                    records[0]["metrics"]["wer_raw"].update(errors=2, rate=.2)
            elif axis == "der":
                candidate[0]["metrics"]["native_der_collar_0ms"].update(miss_ms=11., rate=.11)
            else:
                candidate[0].update(native_speaker_count=3, native_speaker_count_error=1)
            result = self.check(candidate, baseline, asr)
            self.assertFalse(result["gate_pass"], axis)

    def test_per_file_regressions_are_retained_without_becoming_extra_gates(self):
        baseline, candidate = numeric(), numeric()
        candidate[0]["metrics"]["wer_raw"].update(errors=2, rate=.2)
        candidate[1]["metrics"]["wer_raw"].update(errors=0, rate=0.)
        candidate[0]["metrics"]["native_der_collar_0ms"].update(miss_ms=20., rate=.2)
        candidate[1]["metrics"]["native_der_collar_0ms"].update(miss_ms=0., rate=0.)
        candidate[0]["metrics"]["native_der_collar_250ms"].update(miss_ms=40., rate=.4)
        candidate[0]["metrics"]["cpwer_raw"].update(errors=4, rate=.4)
        result = self.check(candidate, baseline, deepcopy(candidate))
        self.assertTrue(result["gate_pass"])
        self.assertGreater(result["per_case"][0]["raw_delta_percentage_points"], 0)
        self.assertGreater(result["per_case"][0]["native_der250_delta_percentage_points"], 0)
        self.assertGreater(result["per_case"][0]["cpwer_raw_delta_percentage_points"], 0)
        self.assertFalse(result["per_case"][0]["per_file_deltas_are_gates"])

    def test_missing_extra_unsupported_and_changed_d_word_score_fail(self):
        baseline = numeric()
        variants = [baseline[:-1], [*baseline, deepcopy(baseline[0])], deepcopy(baseline), deepcopy(baseline)]
        variants[2][0]["refiner_accepted"] = False
        variants[3][0]["metrics"]["wer_raw"].update(errors=0, rate=0.)
        for candidate in variants:
            self.assertFalse(self.check(candidate, baseline, baseline)["gate_pass"])


class SavedValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prepare(5, "holdout")

    def hashes(self, folder):
        return {"case.json": digest(folder / "case.json"), **{name: digest(folder / name) for name in audit.EVIDENCE}}

    def write_case(self, folder, descriptor, reference, hypothesis, diagnostic, metrics, *, count_fields=False, extra=None):
        for name, data in (("reference", reference), ("hypothesis", hypothesis), ("diagnostics", diagnostic), ("metrics", metrics)):
            save(folder / (name + ".json"), data)
        record = {**descriptor, "reference_sha256": digest(folder / "reference.json"), "metrics": metrics,
                  "evidence_sha256": {name: digest(folder / name) for name in audit.EVIDENCE}, **(extra or {})}
        if count_fields:
            record.update(native_speaker_count=2, reference_speaker_count=2, native_speaker_count_error=0)
        save(folder / "case.json", record)

    def metric(self, reference, hypothesis, turns):
        result = score.score(reference, hypothesis, 6000)
        native = [{"start_ms": t.start_ms, "end_ms": t.end_ms, "speaker_id": "native_" + str(t.speaker), "text": ""} for t in turns]
        for name, collar in zip(audit.DER_KEYS, (0, 250)):
            result[name] = score.der(reference["transcript"], native, 6000, collar)
        result["native_speaker_count"] = len({t.speaker for t in turns})
        return result

    def prepare(self, count, split, *, algorithm=audit.CENTROID_ALGORITHM, uneven=False):
        self.count, self.split, self.algorithm = count, split, algorithm
        window = algorithm == audit.WINDOW_ALGORITHM
        self.tau = .36 if window else .7
        self.profile = "tau-0p36" if window else "tau-0p7"
        native_threshold = .3 if window else .5
        native_profile = "auto-0p30" if window else "auto-0p50"
        self.manifest, self.freeze = self.root / "corpus/manifest.json", self.root / "freeze.json"
        self.candidate, self.neural, self.asr, self.baseline = (self.root / x for x in ("candidate", "neural", "asr", "baseline"))
        self.devsource, self.dev_audit = self.root / "dev-candidate", self.root / "dev-audit.json"
        self.cfg = WindowClusterConfig(method="average", reassign_small=True) if window else RefineConfig(minimum_reassignment_similarity=.7, small_missing_centroid_policy="temporal")
        local = replace(self.cfg, tau=self.tau) if window else replace(self.cfg, merge_threshold=self.tau)
        reference = {"transcript": [{"speaker_id": "speaker_1", "start_ms": 0, "end_ms": 3000, "text": "А"},
                                    {"speaker_id": "speaker_2", "start_ms": 3000, "end_ms": 6000, "text": "Б"}]}
        boundary = 3050 if uneven else 3000
        native = [Turn(0, boundary, 0), Turn(boundary, 6000, 1)]
        windows = [replace(w, embedding=(1., 0.) if w.speaker == 0 else (0., 1.)) for w in clean_windows(native, 6000)]
        chunks = [words_from_tokens("А Б", ["▁А", "▁Б"], [.2, 3.2], 0, 6000, 40).words]
        replay = (overcluster if window else refine)(native, windows, 6000, local)
        hypothesis = validation.project_asr(chunks, replay.turns, "fixture")
        cases, refs = [], {}
        for i in range(count):
            identifier = f"holdout-{i}"
            case = {"id": identifier, "split": "holdout", "duration_ms": 6000, "audio_sha256": "a" * 64,
                    "reference": "references/" + identifier + ".json"}
            cases.append(case)
            save(self.manifest.parent / case["reference"], reference)
            refs[identifier] = digest(self.manifest.parent / case["reference"])
        self.ids = [c["id"] for c in cases]
        save(self.manifest, {"files": cases})
        devconfig = {"refiner_config": asdict(self.cfg)}
        if window:devconfig.update(algorithm=algorithm, method=self.cfg.method)
        save(self.devsource / "run.json", {"config": devconfig})
        dev_records = []
        for i in range(8):
            record = numeric(1)[0]
            record.update(id=f"dev-{i}", split="dev", profile=self.profile, threshold=self.tau, stage="refined", source_profile=native_profile, algorithm=algorithm)
            dev_records.append(record)
        dev = audit.evaluate_records(dev_records, dev_records, dev_records, expected_ids=[r["id"] for r in dev_records], profile=self.profile)
        dev["conditions"]["saved_source_integrity"] = {"pass": True}
        dev.update(sources={"candidate": str(self.devsource)}, source_sha256={str((self.devsource / "run.json").resolve()): digest(self.devsource / "run.json")})
        save(self.dev_audit, dev)
        save(self.freeze, {"status": "FROZEN_FOR_VALIDATION", "at": "2026-01-01T00:00:00Z", "dev_audit_sha256": digest(self.dev_audit),
                          "model": {"id": "fixture", "sha256": "b" * 64, "embedding_dimension": 2}, "policy": {"native_threshold": .5, "window_shift": .1, "threads": 2,
                          "refiner_tau": .7, "minimum_reassignment_similarity": .7, "missing_centroid_policy": "temporal", "paired_asr_plan": "vad_words_context600"}})
        if window:
            chosen = json.loads(self.freeze.read_text())
            chosen.update(algorithm=algorithm, window_config=asdict(local))
            chosen["policy"] = {"native_threshold": native_threshold, "window_shift": .1, "threads": 2, "paired_asr_plan": "vad_words_context600"}
            save(self.freeze, chosen)
        commonfp = {"manifest_sha256": digest(self.manifest), "references": refs}
        save(self.asr / "run.json", {"status": "COMPLETE", "fingerprint": commonfp,
             "config": {"pipeline": "vad_words_v1", "expected_speakers": -1, "threads": 2, "punctuation_mode": "none", "energy_split": True, "pre_roll_ms": 600}})
        save(self.baseline / "run.json", {"status": "COMPLETE", "fingerprint": commonfp,
             "config": {"pipeline": "v16", "expected_speakers": -1, "threads": 2}})
        options = {"mode": "auto", "model_id": "fixture", "window_shift": .1, "threads": 2, "collect_windows": True}
        save(self.neural / "run.json", {"status": "COMPLETE", "started_at": "2026-01-01T00:00:01Z", "completed_at": "2026-01-01T00:00:02Z", "options": options,
             "fingerprint": {"manifest": digest(self.manifest), "asr_run": digest(self.asr / "run.json"), "embedding": "b" * 64,
                             "thresholds": [native_threshold], "selected_ids": self.ids, "options": options}})
        links = {}
        for case in cases:
            identifier = case["id"]
            metrics = self.metric(reference, hypothesis, native)
            ad = {"wordAssignmentSupported": True, "fallbackChunks": 0, "backend": "fixture", "audioMs": 6000, "audioSha256": case["audio_sha256"],
                  "tokenTimestampPolicy": {"verified": True, "frame_stride_ms": 40}, "asrSlices": [{"text": "А Б", "tokens": ["▁А", "▁Б"],
                   "timestamps": [.2, 3.2], "startMs": 0, "endMs": 6000, "wordAssignmentSupported": True, "timestampUnit": "seconds within ASR VAD chunk"}]}
            self.write_case(self.asr / identifier, case, reference, hypothesis, ad, metrics)
            ash = self.hashes(self.asr / identifier)
            bd = {"expectedSpeakers": -1, "clusteringMode": "automatic", "diarizationTurns": validation.refine_sweep.base._turn_json(native)}
            # Historical baselines contain counts only in metrics, not case.
            self.write_case(self.baseline / identifier, case, reference, hypothesis, bd, metrics)
            nd = {"diarizationTurns": bd["diarizationTurns"], "cleanEmbeddingWindows": [asdict(w) for w in windows], "mode": "auto", "numClustersPassed": -1,
                  "modelSha256": "b" * 64, "modelId": "fixture", "threshold": native_threshold, "windowShiftRatio": .1, "threads": 2,
                  "fixedCountSource": "none", "asrEvidenceSha256": {k: v for k, v in ash.items() if k != "case.json"}}
            # Standard native C source has the mandatory case count but need
            # not duplicate it in metrics; this shape must remain supported.
            nm = deepcopy(metrics); nm.pop("native_speaker_count")
            self.write_case(self.neural / native_profile / identifier, case, reference, hypothesis, nd, nm, count_fields=True,
                            extra={"profile": native_profile, "mode": "auto", "model_id": "fixture"})
            nsh = self.hashes(self.neural / native_profile / identifier)
            link = {"diar": nsh, "asr": ash, "reference": refs[identifier], "original_audio": case["audio_sha256"]}
            links[identifier] = link
            cd = {"diarizationTurns": validation.refine_sweep.base._turn_json(replay.turns), "sourceEvidence": link,
                  "refinerAccepted": True, "refiner": replay.diagnostics}
            if window:cd["algorithm"] = algorithm
            candidate_metrics = self.metric(reference, hypothesis, replay.turns)
            self.write_case(self.candidate / self.profile / identifier, case, reference, hypothesis, cd, candidate_metrics, count_fields=True,
                            extra={"profile": self.profile, "source_profile": native_profile, "stage": "refined", "threshold": self.tau,
                                   "refiner_accepted": True, "source_evidence_sha256": link})
        settings = {"profile": native_profile, "thresholds": [self.tau], "split": split, "cases": None, "refiner_config": asdict(self.cfg)}
        if window:settings.update(algorithm=algorithm, method=self.cfg.method, expected_cases=count)
        fp = {"manifest": digest(self.manifest), "asr_run": digest(self.asr / "run.json"), "diar_run": digest(self.neural / "run.json"),
              "selected_ids": self.ids, "cases": links, "config": settings,
              "refiner": digest(Path(refine.__code__.co_filename)), "scorer": digest(Path(score.__file__)),
              **{key: digest(Path(validation.__file__).with_name(file)) for key, file in
                 [("word_helpers", "vad_words.py"), ("diar_helpers", "diar_sweep.py"), ("baseline_helpers", "pipeline.py")]}}
        if window:
            for key in ("word_helpers", "diar_helpers", "baseline_helpers"):fp.pop(key)
            fp.update(refiner=digest(Path(overcluster.__code__.co_filename)),
                      source_loader=digest(Path(validation.__file__).with_name("refine_sweep.py")),
                      asr_replay_helpers=digest(Path(validation.__file__).with_name("refiner_ablation.py")))
        save(self.candidate / "source-fingerprint.json", fp)
        save(self.candidate / "run.json", {"status": "COMPLETE", "started_at": "2026-01-01T00:00:03Z", "completed_at": "2026-01-01T00:00:04Z",
             "config": settings, "source_fingerprint_sha256": hashlib.sha256(json.dumps(fp, sort_keys=True, allow_nan=False).encode()).hexdigest(), "failures": [], "pending_cases": []})

    def evaluate(self, **kwargs):
        return validation.evaluate_saved(self.candidate, self.neural, self.asr, self.baseline, self.manifest, self.freeze,
             split=self.split, expected_cases=self.count, cohort="fixture", profile=self.profile, dev_audit=self.dev_audit, **kwargs)

    def edit(self, path, change):
        data = json.loads(path.read_text()); change(data); save(path, data)

    def rehash(self, folder):
        self.edit(folder / "case.json", lambda r: r.update(evidence_sha256={name: digest(folder / name) for name in audit.EVIDENCE}))

    def test_five_actual_style_cases_replay_without_audio_or_gold_to_refiner(self):
        original, calls = validation.refine, []
        def tracked(turns, windows, duration, config):
            calls.append((turns, windows, duration, config))
            self.assertTrue(all(isinstance(t, Turn) for t in turns))
            self.assertTrue(all(isinstance(w, EmbeddingWindow) for w in windows))
            self.assertEqual(.7, config.merge_threshold)
            self.assertEqual(.7, config.minimum_reassignment_similarity)
            return original(turns, windows, duration, config)
        with mock.patch.object(validation, "refine", tracked), mock.patch("tools.eval.pipeline._read_canonical_wav", side_effect=AssertionError("Audio read")):
            result = self.evaluate()
        self.assertTrue(result["gate_pass"], result["errors"])
        self.assertEqual(5, len(calls))
        self.assertEqual(5, result["aggregate"]["baseline"]["speaker_count_exact_cases"])
        self.assertTrue(result["pure_refiner_and_word_projection_replayed"])
        self.assertFalse(result["full_pipeline_accepted"])

    def test_ten_reserve_cases_all_selection_has_separate_denominator(self):
        self.prepare(10, "all")
        result = self.evaluate()
        self.assertTrue(result["gate_pass"], result["errors"])
        self.assertEqual(10, result["conditions"]["exact_native_count_no_regression"]["denominator"])

    def test_bad_freeze_dev_gate_model_or_global_policy_blocks(self):
        freeze = self.freeze.read_bytes()
        self.edit(self.freeze, lambda f: f["policy"].update(refiner_tau=.65))
        self.assertFalse(self.evaluate()["gate_pass"])
        self.freeze.write_bytes(freeze)
        self.edit(self.devsource / "run.json", lambda r: r["config"]["refiner_config"].update(smooth_ms=0))
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("dev policy run changed" in e["error"] for e in result["errors"]))

    def test_missing_extra_directory_or_case_and_reference_tamper_fail(self):
        extra = self.candidate / "tau-0p7/extra-case"; extra.mkdir()
        self.assertFalse(self.evaluate()["gate_pass"])
        extra.rmdir()
        folder = self.candidate / "tau-0p7/holdout-0"
        (folder / "diagnostics.json").write_text((folder / "diagnostics.json").read_text() + " ")
        self.assertFalse(self.evaluate()["gate_pass"])

    def test_chronology_model_dimension_and_old_baseline_count_copy_are_checked(self):
        raw = self.freeze.read_bytes()
        self.edit(self.freeze, lambda f: f.update(at="2026-01-01T00:00:03Z"))
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("chronology" in e["error"] for e in result["errors"]))
        self.freeze.write_bytes(raw)
        self.edit(self.freeze, lambda f: f["model"].update(embedding_dimension=999))
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("dimension" in e["error"] for e in result["errors"]))
        self.freeze.write_bytes(raw)
        folder = self.baseline / "holdout-0"
        self.edit(folder / "metrics.json", lambda m: m.update(native_speaker_count=999))
        metrics = json.loads((folder / "metrics.json").read_text())
        self.edit(folder / "case.json", lambda r: r.update(metrics=metrics))
        self.rehash(folder)
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("native count does not recompute" in e["error"] for e in result["errors"]))

    def test_source_reference_and_changed_d_word_cache_fail_independently(self):
        reference = self.manifest.parent / "references/holdout-0.json"
        raw = reference.read_bytes()
        self.edit(reference, lambda r: r["transcript"][0].update(text="Иной эталон"))
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("reference differs" in e["error"] for e in result["errors"]))
        reference.write_bytes(raw)
        folder = self.asr / "holdout-0"
        self.edit(folder / "diagnostics.json", lambda d: d["asrSlices"][0].update(text="Подмена"))
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("Evidence hash" in e["error"] for e in result["errors"]))

    def test_rehashed_wrong_refined_turns_cannot_pass_by_saved_metrics(self):
        folder = self.candidate / "tau-0p7/holdout-0"
        self.edit(folder / "diagnostics.json", lambda d: d["diarizationTurns"][0].update(speakerId=99))
        self.rehash(folder)
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("do not reconstruct" in e["error"] for e in result["errors"]))

    def test_wrong_word_hypothesis_and_unsupported_result_fail(self):
        folder = self.candidate / "tau-0p7/holdout-0"
        self.edit(folder / "hypothesis.json", lambda d: d["transcript"][0].update(text="Подмена"))
        self.rehash(folder)
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("hypothesis does not reconstruct" in e["error"] for e in result["errors"]))
        self.edit(folder / "case.json", lambda r: r.update(refiner_accepted=False))
        self.assertFalse(self.evaluate()["gate_pass"])

    def test_window_five_and_ten_cases_dispatch_only_known_pure_window_helper(self):
        for count, split in ((5, "holdout"), (10, "all")):
            self.prepare(count, split, algorithm=audit.WINDOW_ALGORITHM)
            with mock.patch.object(validation, "refine", side_effect=AssertionError("C1 used for C2")), \
                 mock.patch("tools.eval.pipeline._read_canonical_wav", side_effect=AssertionError("Audio read")):
                result = self.evaluate()
            self.assertTrue(result["gate_pass"], result["errors"])
            self.assertEqual(audit.WINDOW_ALGORITHM, result["algorithm"])
            self.assertEqual(count, len(result["pure_replay_completed_ids"]))

    def test_window_actual_partial_temporal_status_reconstructs(self):
        self.prepare(5, "holdout", algorithm=audit.WINDOW_ALGORITHM, uneven=True)
        diagnostic = json.loads((self.candidate / self.profile / "holdout-0/diagnostics.json").read_text())
        self.assertEqual("PARTIAL_TEMPORAL", diagnostic["refiner"]["status"])
        result = self.evaluate()
        self.assertTrue(result["gate_pass"], result["errors"])
        self.assertTrue(result["pure_refiner_and_word_projection_replayed"])

    def test_window_unknown_mixed_algorithm_and_cross_status_are_rejected(self):
        self.prepare(5, "holdout", algorithm=audit.WINDOW_ALGORITHM)
        raw = self.freeze.read_bytes()
        self.edit(self.freeze, lambda f: f.update(algorithm="invented-window-v2"))
        self.assertFalse(self.evaluate()["gate_pass"])
        self.freeze.write_bytes(raw)
        folder = self.candidate / self.profile / "holdout-0"
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"].update(algorithm=audit.CENTROID_ALGORITHM))
        self.rehash(folder)
        self.assertFalse(self.evaluate()["gate_pass"])
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"].update(algorithm=audit.WINDOW_ALGORITHM, status="PARTIAL_ACOUSTIC"))
        self.rehash(folder)
        self.assertFalse(self.evaluate()["gate_pass"])

    def test_window_default_tau_and_changed_linkage_do_not_replace_frozen_policy(self):
        self.prepare(5, "holdout", algorithm=audit.WINDOW_ALGORITHM)
        folder = self.candidate / self.profile / "holdout-0"
        self.edit(folder / "diagnostics.json", lambda d: d["refiner"]["config"].update(tau=.65))
        self.rehash(folder)
        self.assertFalse(self.evaluate()["gate_pass"])
        self.edit(self.freeze, lambda f: f["window_config"].update(method="complete"))
        result = self.evaluate()
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any("Frozen dev window policy mismatch" in e["error"] for e in result["errors"]))

    def test_fresh_json_never_overwrites_and_cli_is_explicit(self):
        output = self.root / "audit.json"
        args = ["--candidate", str(self.candidate), "--diar-run", str(self.neural), "--asr-run", str(self.asr),
                "--baseline", str(self.baseline), "--manifest", str(self.manifest), "--freeze", str(self.freeze),
                "--dev-audit", str(self.dev_audit), "--split", self.split, "--expected-cases", str(self.count), "--cohort", "fixture", "--output", str(output)]
        with redirect_stdout(io.StringIO()):self.assertEqual(0, validation.main(args))
        raw = output.read_bytes()
        with self.assertRaises(FileExistsError):self.evaluate(output=output)
        self.assertEqual(raw, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
