from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.eval import refine_sweep as sweep
from tools.eval.pipeline import Turn
from tools.eval.speaker_refiner import clean_windows


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SavedRefinerSweepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.diar, self.asr = self.root / "diar", self.root / "asr"
        self.manifest = self.root / "corpus/manifest.json"
        self.cases = []
        save(self.asr / "run.json", {"status": "COMPLETE", "config": {
            "pipeline": "vad_words_v1", "punctuation_mode": "none"}})
        self.diar_meta = {"status": "COMPLETE", "options": {"mode": "overcluster"},
                          "fingerprint": {"asr_run": sweep.digest(self.asr / "run.json")}}
        save(self.diar / "run.json", self.diar_meta)

    def add_case(self, identifier="dev-a", split="dev", reference_text=None, identical=True):
        turns = [Turn(0, 3000, 0), Turn(3000, 6000, 1)]
        if reference_text is None:
            reference = {"transcript": [
                {"speaker_id": "speaker_1", "start_ms": 0, "end_ms": 3000, "text": "А"},
                {"speaker_id": "speaker_2", "start_ms": 3000, "end_ms": 6000, "text": "Б"}]}
        else:
            reference = {"transcript": [{"speaker_id": "speaker_1", "start_ms": 0, "end_ms": 6000, "text": reference_text}]}
        ref_path = self.manifest.parent / "references" / (identifier + ".json")
        save(ref_path, reference)
        case = {"id": identifier, "split": split, "duration_ms": 6000,
                "audio_sha256": "a" * 64, "reference": "references/" + identifier + ".json",
                # Impossible gold K intentionally must never enter refinement.
                "expected_speakers": 777, "audio": "not-present.wav"}
        self.cases.append(case)
        save(self.manifest, {"schema_version": 1, "files": self.cases})
        asr_diagnostic = {"wordAssignmentSupported": True, "fallbackChunks": 0, "backend": "fixture",
            "audioMs": 6000, "audioSha256": case["audio_sha256"],
            "tokenTimestampPolicy": {"verified": True, "frame_stride_ms": 40},
            "asrSlices": [{"text": "А Б", "tokens": ["▁А", "▁Б"], "timestamps": [.2, 3.2],
                           "startMs": 0, "endMs": 6000, "wordAssignmentSupported": True,
                           "timestampUnit": "seconds within ASR VAD chunk"}]}
        temporary = self.root / "fixture-asr.json"
        save(temporary, asr_diagnostic)
        from tools.eval.vad_words import words_from_tokens
        chunks = [words_from_tokens("А Б", ["▁А", "▁Б"], [.2, 3.2], 0, 6000, 40).words]
        hypothesis = sweep.project_asr(chunks, turns, "fixture")
        metrics = sweep.scoring.score(reference, hypothesis, 6000)
        windows = [{"start_ms": w.start_ms, "end_ms": w.end_ms, "speaker": w.speaker,
                    "embedding": [1., 0.] if identical or w.speaker == 0 else [0., 1.], "clean": True}
                   for w in clean_windows(turns, 6000)]
        diar_diagnostic = {"diarizationTurns": sweep.base._turn_json(turns), "cleanEmbeddingWindows": windows}
        for folder, diagnostic, extra in (
            (self.asr / identifier, asr_diagnostic, {}),
            (self.diar / "overcluster" / identifier, diar_diagnostic, {"profile": "overcluster", "mode": "overcluster"}),
        ):
            if folder.parent.name == "overcluster":
                diagnostic["asrEvidenceSha256"] = sweep.evidence_hashes(self.asr / identifier)
            for name, data in (("reference", reference), ("hypothesis", hypothesis),
                               ("metrics", metrics), ("diagnostics", diagnostic)):
                save(folder / (name + ".json"), data)
            save(folder / "case.json", {**case, **extra, "reference_sha256": sweep.digest(ref_path),
                "metrics": metrics, "evidence_sha256": sweep.evidence_hashes(folder)})
        return case

    def report(self, **kwargs):
        return sweep.score_saved(self.diar, self.asr, self.manifest, profile="overcluster",
                                 thresholds=[.85], **kwargs)

    def edit_evidence(self, folder, filename, change):
        item = sweep.read_json(folder / filename)
        change(item)
        save(folder / filename, item)
        record = sweep.read_json(folder / "case.json")
        record["evidence_sha256"] = sweep.evidence_hashes(folder)
        if filename == "metrics.json":
            record["metrics"] = item
        save(folder / "case.json", record)

    def test_real_saved_windows_change_count_without_raw_text_or_nn_calls(self):
        self.add_case()
        original = sweep.refine
        calls = []
        def tracked(turns, windows, duration, config):
            calls.append((turns, windows, duration, config))
            self.assertIn(duration, (0, 6000))
            self.assertTrue(all(isinstance(t, Turn) for t in turns))
            self.assertTrue(all(isinstance(w, sweep.EmbeddingWindow) for w in windows))
            self.assertEqual(4, len((turns, windows, duration, config)))
            return original(turns, windows, duration, config)
        with mock.patch.object(sweep, "refine", side_effect=tracked), \
             mock.patch.object(sweep.base, "_read_canonical_wav", side_effect=AssertionError("Audio opened")):
            result = self.report()
        self.assertEqual("COMPLETE", result["status"])
        baseline, refined = result["summaries"]["baseline"], result["summaries"]["tau-0p85"]
        self.assertEqual(1, baseline["speaker_count_exact_cases"])
        self.assertEqual(0, refined["speaker_count_exact_cases"])
        self.assertEqual(baseline["wer_raw"], refined["wer_raw"])
        self.assertTrue(refined["raw_wer_invariant"])
        self.assertGreater(refined["native_der_collar_0ms"]["rate"], 0)
        self.assertNotIn("rtf_diarization_stage", refined)
        self.assertFalse(result["new_diarization_inference"])
        # One empty-option validation plus exactly one real refinement.
        self.assertEqual(1, sum(bool(turns) for turns, *_ in calls))

    def test_complete_output_hashes_turns_and_never_overwrites(self):
        self.add_case()
        output = self.root / "result"
        result = self.report(output=output)
        record = sweep.read_json(output / "tau-0p85/dev-a/case.json")
        self.assertEqual(record["evidence_sha256"], sweep.evidence_hashes(output / "tau-0p85/dev-a"))
        self.assertEqual(record["turns_sha256"], sweep.digest(output / "tau-0p85/dev-a/turns.json"))
        self.assertEqual(result["source_fingerprint"], sweep.read_json(output / "source-fingerprint.json"))
        saved = (output / "run.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.report(output=output)
        self.assertEqual(saved, (output / "run.json").read_bytes())
        self.assertTrue((output / "results.csv").is_file())

    def test_aggregation_uses_token_sums_and_preserves_undefined_empty_rates(self):
        self.add_case("dev-a", reference_text="А")
        self.add_case("dev-b", reference_text="А Б А Б")
        result = self.report()
        metric = result["summaries"]["tau-0p85"]["wer_raw"]
        self.assertEqual((3, 5), (metric["errors"], metric["reference_tokens"]))
        self.assertAlmostEqual(.6, metric["rate"])
        empty = sweep._summarize([], 2)
        self.assertIsNone(empty["wer_raw"]["rate"])
        self.assertIsNone(empty["native_der_collar_0ms"]["rate"])
        self.assertFalse(empty["complete_case_coverage"])

    def test_dev_only_never_reads_holdout_case_or_gold(self):
        self.add_case()
        holdout = self.add_case("holdout-secret", "holdout")
        (self.diar / "overcluster/holdout-secret/case.json").write_text("FORBIDDEN")
        (self.asr / "holdout-secret/case.json").write_text("FORBIDDEN")
        (self.manifest.parent / holdout["reference"]).write_text("FORBIDDEN GOLD")
        result = self.report()
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(["dev-a"], result["source_fingerprint"]["selected_ids"])
        self.assertEqual({"dev-a"}, {r["id"] for r in result["records"]})

    def test_tampered_inputs_are_failed_and_preserved_not_aggregated(self):
        self.add_case()
        source = self.diar / "overcluster/dev-a/diagnostics.json"
        source.write_text(source.read_text() + " ")
        output = self.root / "failure"
        result = self.report(output=output)
        self.assertEqual("FAILED", result["status"])
        self.assertIn("hashes changed", result["failures"][0]["error"])
        self.assertEqual([], result["records"])
        self.assertTrue((output / "failures/inputs/dev-a.json").is_file())
        self.assertEqual(0, result["summaries"]["baseline"]["cases"])

    def test_reference_and_original_audio_hash_must_match(self):
        self.add_case()
        record_path = self.asr / "dev-a/case.json"
        record = sweep.read_json(record_path)
        record["audio_sha256"] = "b" * 64
        save(record_path, record)
        self.assertIn("audio_sha256", self.report()["failures"][0]["error"])
        record["audio_sha256"] = "a" * 64
        record["reference_sha256"] = "b" * 64
        save(record_path, record)
        self.assertIn("reference hash", self.report()["failures"][0]["error"])

    def test_running_source_pending_is_explicit_but_completed_missing_fails(self):
        self.add_case()
        case_record = self.diar / "overcluster/dev-a/case.json"
        case_record.unlink()
        save(self.diar / "run.json", {**self.diar_meta, "status": "RUNNING"})
        result = self.report()
        self.assertEqual("PARTIAL_SOURCE", result["status"])
        self.assertEqual(["dev-a"], result["pending_cases"])
        self.assertFalse(result["summaries"]["baseline"]["complete_case_coverage"])
        save(self.diar / "run.json", self.diar_meta)
        self.assertEqual("FAILED", self.report()["status"])

    def test_missing_arrays_unknown_native_label_and_fixed_source_rejected(self):
        self.add_case()
        folder = self.diar / "overcluster/dev-a"
        original = (folder / "diagnostics.json").read_bytes()
        self.edit_evidence(folder, "diagnostics.json", lambda d: d.pop("cleanEmbeddingWindows"))
        self.assertIn("no embeddings", self.report()["failures"][0]["error"])
        save(folder / "diagnostics.json", json.loads(original))
        self.edit_evidence(folder, "diagnostics.json", lambda d: d["diarizationTurns"][0].update(speakerId=-1))
        self.assertIn("bounds/label", self.report()["failures"][0]["error"])
        record = sweep.read_json(folder / "case.json")
        record["mode"] = "fixed"
        save(folder / "case.json", record)
        self.assertIn("Known-K", self.report()["failures"][0]["error"])

    def test_unsupported_real_evidence_is_scored_explicitly_without_fake_vectors(self):
        self.add_case()
        folder = self.diar / "overcluster/dev-a"
        self.edit_evidence(folder, "diagnostics.json", lambda d: d.update(cleanEmbeddingWindows=[]))
        result = self.report(stages=("refined",))
        record = result["records"][0]
        self.assertFalse(record["refiner_accepted"])
        self.assertTrue(record["raw_wer_invariant"])
        self.assertEqual(1, result["summaries"]["tau-0p85"]["refiner_unsupported_cases"])
        self.assertEqual(2, record["native_speaker_count"])

    def test_text_projection_failure_is_saved_and_not_silenced(self):
        self.add_case()
        with mock.patch.object(sweep, "project_asr", return_value={"transcript": []}):
            result = self.report(output=self.root / "bad-projection")
        self.assertEqual("FAILED", result["status"])
        self.assertEqual(2, len(result["failures"]))
        self.assertTrue(all("Raw WER invariant" in f["error"] for f in result["failures"]))
        self.assertEqual([], result["records"])

    def test_bad_options_fail_before_reading_evidence_and_missing_manifest_is_recorded(self):
        for values in ([float("nan")], [.5, .5], [True], [1.]):
            with self.assertRaises(ValueError):
                sweep.score_saved(self.diar, self.asr, self.manifest, profile="overcluster", thresholds=values)
        with self.assertRaises(ValueError):
            self.report(missing_policy="guess")
        result = self.report(output=self.root / "missing-manifest")
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("run_validation", result["failures"][0]["stage"])
        self.assertTrue((self.root / "missing-manifest/failures/run.json").is_file())

    def test_c_source_must_bind_exact_d_run_and_per_case_evidence(self):
        self.add_case()
        save(self.diar / "run.json", {**self.diar_meta, "fingerprint": {"asr_run": "f" * 64}})
        result = self.report(output=self.root / "wrong-source-run")
        self.assertEqual("FAILED", result["status"])
        self.assertIn("ASR run fingerprint differs", result["failures"][0]["error"])
        self.assertEqual([], result["records"])
        save(self.diar / "run.json", self.diar_meta)
        self.edit_evidence(self.diar / "overcluster/dev-a", "diagnostics.json",
                           lambda d: d["asrEvidenceSha256"].update({"hypothesis.json": "f" * 64}))
        result = self.report(output=self.root / "wrong-source-case")
        self.assertEqual("FAILED", result["status"])
        self.assertIn("ASR evidence hashes differ", result["failures"][0]["error"])
        self.assertTrue((self.root / "wrong-source-case/failures/inputs/dev-a.json").is_file())
        self.assertEqual([], result["records"])

    def collector_source(self):
        folder = self.diar / "overcluster/dev-a"
        source = self.asr / "dev-a"
        record = sweep.read_json(source / "case.json")
        proof = {"case_sha256": sweep.digest(source / "case.json"),
                 "evidence_sha256": record["evidence_sha256"]}
        fingerprint = {"source_D_run": sweep.digest(self.asr / "run.json"),
                       "source_cases": {"dev-a": proof}}
        save(self.diar / "run.json", {"status": "COMPLETE", "fingerprint": fingerprint})
        def change(d):
            d.pop("asrEvidenceSha256")
            d.update(sourceDRunSha256=fingerprint["source_D_run"], sourceDEvidence=proof)
        self.edit_evidence(folder, "diagnostics.json", change)
        (folder / "source-metrics.json").write_bytes((source / "metrics.json").read_bytes())
        derived = sweep.read_json(folder / "case.json")
        derived.update(source_D_run_sha256=fingerprint["source_D_run"],
                       source_metrics_sha256=sweep.digest(source / "metrics.json"))
        save(folder / "case.json", derived)
        return folder

    def test_collector_format_matches_exact_d_case_not_a_loose_fallback(self):
        self.add_case()
        folder = self.collector_source()
        result = self.report()
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual("collect_diar_windows_v1", result["source_fingerprint"]["source_format"])
        self.edit_evidence(folder, "diagnostics.json", lambda d: d["sourceDEvidence"].update(case_sha256="f" * 64))
        result = self.report()
        self.assertEqual("FAILED", result["status"])
        self.assertIn("Collector C source D run/case", result["failures"][0]["error"])

    def test_unknown_mixed_or_incomplete_source_formats_rejected(self):
        self.add_case()
        for fingerprint in ({}, {"other_asr_key": "a" * 64},
                            {"asr_run": sweep.digest(self.asr / "run.json"),
                             "source_D_run": sweep.digest(self.asr / "run.json")}):
            save(self.diar / "run.json", {"status": "COMPLETE", "fingerprint": fingerprint})
            self.assertIn("provenance format", self.report()["failures"][0]["error"])
        save(self.diar / "run.json", self.diar_meta)
        folder = self.diar / "overcluster/dev-a"
        self.edit_evidence(folder, "diagnostics.json", lambda d: d.update(sourceDRunSha256="f" * 64))
        self.assertIn("Mixed C source", self.report()["failures"][0]["error"])

    def test_collector_original_metrics_and_run_links_are_pinned(self):
        self.add_case()
        folder = self.collector_source()
        original = (folder / "source-metrics.json").read_bytes()
        (folder / "source-metrics.json").write_bytes(original + b" ")
        self.assertIn("source metrics hash", self.report()["failures"][0]["error"])
        (folder / "source-metrics.json").write_bytes(original)
        self.edit_evidence(folder, "diagnostics.json", lambda d: d.update(sourceDRunSha256="f" * 64))
        self.assertIn("D run/case evidence", self.report()["failures"][0]["error"])


if __name__ == "__main__":
    unittest.main()
