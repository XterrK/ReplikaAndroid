"""Controlled CPU provenance mutations; real pure C2 math, no NN/audio/ADB.

Synthetic embeddings/words are explicit fixtures. These tests establish schema,
pairing, replay and failure behavior, never native model quality or performance.
"""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.eval import native_diar_policy as policy
from tools.eval import pull_refined_android as collector
from tools.eval.pipeline_refined import PAIRED_ASR_POLICY
from tools.eval.tests import test_pull_refined_android as collector_fixtures
from tools.eval.tests.test_native_diar_policy import evidence_fixture, bind, host, native_policy, word_fixture


def cpu_map(threads, *, plan="auto_v1", cores=2, requested=0):
    """Explicit controlled outcome; mapping itself is independently tested below."""
    pin = plan == "v16"
    return {"plan": plan, "requestedThreads": requested, "availableCores": cores,
        "asrThreads": threads, "diarizationThreads": 2 if pin else threads,
        "refinementThreads": 2 if pin else threads, "diarizationPinned": pin, "refinementPinned": pin}


def host_pair(threads=1, plan="auto_v1"):
    config = host()
    config.update(cpu_plan=plan, threads=threads)
    paired = {**PAIRED_ASR_POLICY, "threads": threads}
    return config, paired


def native_cpu_report(threads=1, *, plan="auto_v1", cores=2, requested=0):
    report = native_policy()
    report.update(threads=threads, cpuPlan=plan, requestedThreads=requested,
                  cpuPolicy=cpu_map(threads, plan=plan, cores=cores, requested=requested))
    return report


def cpu_evidence(threads=1, *, plan="auto_v1", cores=2, requested=0):
    diagnostic, record, wrapper = evidence_fixture()
    apply_cpu(diagnostic, wrapper, threads, plan=plan, cores=cores, requested=requested)
    return diagnostic, record, wrapper


def apply_cpu(diagnostic, wrapper, threads, *, plan, cores, requested):
    resolution = cpu_map(threads, plan=plan, cores=cores, requested=requested)
    diagnostic.update(threads=threads, cpuPolicy=deepcopy(resolution))
    wrapper["metadata"]["cpuPolicy"] = deepcopy(resolution)
    for adapter in (diagnostic["diarizationRefinement"], wrapper["diagnostics"]):
        adapter.update(cpuPlan=plan, embeddingThreads=resolution["refinementThreads"])


def validate_evidence(diagnostic, record, wrapper, *, plan="auto_v1", threads=1, requested=0):
    raw = bind(diagnostic, record, wrapper)
    return policy.validate_diarization_evidence(diagnostic, record, raw,
        case_id=record["id"], audio_sha256=record["audio_sha256"], duration_ms=record["duration_ms"],
        cpu_plan=plan, threads=threads, requested_threads=requested)


class CpuResolutionTest(unittest.TestCase):
    def test_automatic_core_mapping_matches_kotlin_bucket_contract(self):
        for cores, effective in ((1, 1), (2, 1), (3, 2), (4, 2), (5, 4), (8, 4), (2**31-1, 4)):
            actual = cpu_map(effective, cores=cores)
            self.assertEqual(actual, policy.validate_cpu_resolution(actual, cpu_plan="auto_v1",
                threads=effective, requested_threads=0))

    def test_explicit_overrides_are_preserved_even_on_one_core(self):
        for effective in (1, 2, 4):
            actual = cpu_map(effective, cores=1, requested=effective)
            self.assertEqual(actual, policy.validate_cpu_resolution(actual, cpu_plan="auto_v1", threads=effective))

    def test_default_legacy_two_has_both_policy_pins_true(self):
        actual = cpu_map(2, plan="v16", requested=2)
        self.assertEqual(actual, policy.validate_cpu_resolution(actual, cpu_plan="v16", threads=2))
        for field in ("diarizationPinned", "refinementPinned"):
            changed = deepcopy(actual); changed[field] = False
            with self.assertRaises(ValueError):
                policy.validate_cpu_resolution(changed, cpu_plan="v16", threads=2)

    def test_wrong_mapping_and_mixed_stage_counts_are_rejected(self):
        for field, changed in (("availableCores", 3), ("requestedThreads", 4), ("asrThreads", 4),
                               ("diarizationThreads", 2), ("refinementThreads", 2),
                               ("diarizationPinned", True), ("refinementPinned", True), ("plan", "v16")):
            value = cpu_map(1); value[field] = changed
            with self.subTest(field=field), self.assertRaises(ValueError):
                policy.validate_cpu_resolution(value, cpu_plan="auto_v1", threads=1, requested_threads=0)

    def test_non_integer_bool_missing_extra_and_impossible_kotlin_cores_rejected(self):
        for bad in (None, True, False, 0, -1, 2., "2", 2**31, 2**63):
            value = cpu_map(4, cores=bad)
            with self.subTest(cores=bad), self.assertRaises(ValueError):
                policy.validate_cpu_resolution(value, cpu_plan="auto_v1", threads=4, requested_threads=0)
        for field in ("requestedThreads", "asrThreads", "diarizationThreads", "refinementThreads"):
            for bad in (True, 1., "1", None):
                value = cpu_map(1); value[field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                    policy.validate_cpu_resolution(value, cpu_plan="auto_v1", threads=1, requested_threads=0)
        for changed in ({k:v for k,v in cpu_map(1).items() if k!="refinementPinned"},
                        {**cpu_map(1), "hiddenExpectedK": 2}):
            with self.assertRaises(ValueError):
                policy.validate_cpu_resolution(changed, cpu_plan="auto_v1", threads=1, requested_threads=0)

    def test_auto_request_requires_opt_in_and_execution_types_remain_strict(self):
        for plan, threads, requested in (("v16", 2, 0), ("v16", 1, 1), ("future", 1, 0),
                                         ("auto_v1", True, 0), ("auto_v1", 1., 0),
                                         ("auto_v1", 1, True), ("auto_v1", 1, 3)):
            with self.assertRaises(ValueError):
                policy.validate_cpu_resolution(cpu_map(1), cpu_plan=plan, threads=threads, requested_threads=requested)


class CpuHostNativePairTest(unittest.TestCase):
    def test_auto_one_and_four_explicit_host_native_pair_and_frozen_ml_policy(self):
        old_policy = policy.policy_for_diar_plan()
        for threads, cores in ((1, 2), (2, 4), (4, 8)):
            config, paired = host_pair(threads)
            report = native_cpu_report(threads, cores=cores)
            self.assertEqual(old_policy, policy.validate_native_diar_policy(config, report, paired,
                cpu_plan="auto_v1", threads=threads, requested_threads=0))
        self.assertEqual(old_policy, policy.policy_for_diar_plan())

    def test_host_opt_in_paired_threads_and_native_cpu_metadata_are_mandatory(self):
        config, paired = host_pair()
        report = native_cpu_report()
        for mutate_config, mutate_pair, mutate_report in (
                (lambda x:x.pop("cpu_plan"), lambda x:None, lambda x:None),
                (lambda x:x.update(cpu_plan="v16"), lambda x:None, lambda x:None),
                (lambda x:x.update(threads=4), lambda x:None, lambda x:None),
                (lambda x:None, lambda x:x.update(threads=2), lambda x:None),
                (lambda x:None, lambda x:None, lambda x:x.pop("cpuPolicy")),
                (lambda x:None, lambda x:None, lambda x:x.update(threads=4))):
            cfg, pair, native = deepcopy(config), deepcopy(paired), deepcopy(report)
            mutate_config(cfg); mutate_pair(pair); mutate_report(native)
            with self.assertRaises(ValueError):
                policy.validate_native_diar_policy(cfg, native, pair, cpu_plan="auto_v1", threads=1, requested_threads=0)
        with self.assertRaises(ValueError):
            policy.validate_native_diar_policy(config, report, paired)

    def test_present_top_level_report_cpu_copies_cannot_contradict_policy(self):
        config, paired = host_pair()
        for key, changed in (("cpuPlan", "v16"), ("requestedThreads", 4), ("requestedThreads", True)):
            report = native_cpu_report(); report[key] = changed
            with self.subTest(field=key), self.assertRaises(ValueError):
                policy.validate_native_diar_policy(config, report, paired, cpu_plan="auto_v1", threads=1, requested_threads=0)

    def test_cpu_change_never_relaxes_window_vad_or_model_policy(self):
        for mutate in (lambda x:x["window_config"].update(tau=.35),
                       lambda x:x.update(native_threshold=.5), lambda x:x.update(model_id="other")):
            config, paired = host_pair(); mutate(config)
            with self.assertRaises(ValueError):
                policy.validate_host_policy(config, paired, cpu_plan="auto_v1", threads=1)
        config, paired = host_pair(); paired["pre_roll_ms"] = 100
        with self.assertRaises(ValueError):
            policy.validate_host_policy(config, paired, cpu_plan="auto_v1", threads=1)

    def test_saved_host_actual_stage_map_is_checked_after_rehash_not_only_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); folder=root/"fixture"; folder.mkdir()
            diagnostic,_,wrapper=cpu_evidence()
            diagnostic.update(word_fixture())
            config,paired=host_pair()
            diagnostic.update(config={"provider":"cpu","threads":1,"vadThreads":1,"nativeNumClusters":-1,
                "nativeThreshold":.3,"segmentationWindowShiftRatio":.1,"diarMinDurationOnSec":.2,
                "diarMinDurationOffSec":.5,"cleanWindowMs":1500,"cleanWindowStepMs":750,"cleanMinimumIslandMs":1000,
                "refiner":deepcopy(policy.WINDOW_CONFIG),"asr":deepcopy(paired)},
                selectedNativePolicy={"model_id":"eres2net_zh","threshold":.3,"window_shift":.1,"threads":1,"num_clusters":-1},
                windowConfig=deepcopy(policy.WINDOW_CONFIG),pairedAsrPolicy=deepcopy(paired),
                cpuExecutionPolicy={"plan":"auto_v1","asrThreads":1,"diarizationThreads":1,"refinementThreads":1,"vadThreads":1},
                pipelineVariant="window_words_v1",audioSha256="a"*64,refinerAccepted=True,refinerFallbackToNative=False,
                nativeModelCacheRetained=False,newDiarizationInference=True,newEmbeddingInference=True,newAsrInference=True,
                cleanEmbeddingWindows=deepcopy(wrapper["windows"]),
                refinedDiarizationTurns=deepcopy(diagnostic["diarizationTurns"]),
                modelFiles=[{"path":path,"bytes":size,"sha256":sha} for path,size,sha in policy.MODEL_PINS],
                tokenTimestampPolicy={"verified":True,"frame_stride_ms":40})
            reference={"transcript":[{"speaker_id":"speaker_1","start_ms":0,"end_ms":3000,"text":"Привет, мир!"}]}
            independent=root/"independent-reference.json";collector.write_json(independent,reference)
            hypothesis,_=policy.reconstruct_jury(diagnostic,3000)
            metrics=collector.score_case(reference,hypothesis,diagnostic,3000,120)
            (folder/"reference.json").write_bytes(independent.read_bytes())
            collector.write_json(folder/"hypothesis.json",hypothesis)
            collector.write_json(folder/"metrics.json",metrics)
            case={"id":"fixture","audio_sha256":"a"*64,"duration_ms":3000}
            record={**case,"reference_sha256":collector.digest(independent),"processing_ms":120,"metrics":metrics,
                "asr_replay":False,"new_model_inference":True,"new_diarization_inference":True,
                "new_embedding_inference":True,"new_asr_inference":True}
            def save_actual(value):
                collector.write_json(folder/"diagnostics.json",value)
                record["evidence_sha256"]=collector.evidence_hashes(folder)
                collector.write_json(folder/"case.json",record)
            save_actual(diagnostic)
            self.assertEqual(record,collector._host_case(root,case,independent,{"config":config,"paired_asr_policy":paired}))
            for key,value in (("vadThreads",True),("vadThreads",2),("asrThreads",4),
                              ("diarizationThreads",2),("refinementThreads",True),("plan","v16")):
                changed=deepcopy(diagnostic);changed["cpuExecutionPolicy"][key]=value
                save_actual(changed)
                with self.subTest(stage=key,value=value),self.assertRaisesRegex(ValueError,"actual CPU stage policy"):
                    collector._host_case(root,case,independent,{"config":config,"paired_asr_policy":paired})


class CpuSidecarTest(unittest.TestCase):
    def test_controlled_actual_shape_512_vectors_replay_one_and_four_threads(self):
        for threads, cores, requested in ((1, 2, 0), (4, 8, 0), (4, 1, 4)):
            diagnostic, record, wrapper = cpu_evidence(threads, cores=cores, requested=requested)
            result = validate_evidence(diagnostic, record, wrapper, threads=threads, requested=requested)
            self.assertTrue(result["python_replay_exact_turns"])
            self.assertEqual(512, result["dimension"])
            self.assertTrue(result["resources_released"])

    def test_legacy_historical_absent_cpu_metadata_still_valid(self):
        diagnostic, record, wrapper = evidence_fixture()
        raw = bind(diagnostic, record, wrapper)
        result = policy.validate_diarization_evidence(diagnostic, record, raw,
            case_id="fixture", audio_sha256="a"*64, duration_ms=3000)
        self.assertTrue(result["python_replay_exact_turns"])
        diagnostic, record, wrapper = cpu_evidence(2, plan="v16", requested=2)
        self.assertTrue(validate_evidence(diagnostic, record, wrapper, plan="v16", threads=2, requested=2)["resources_released"])

    def test_sidecar_cpu_map_or_adapter_disagreement_is_rejected(self):
        for mutate in (lambda d,w:w["metadata"]["cpuPolicy"].update(availableCores=8),
                       lambda d,w:w["metadata"].pop("cpuPolicy"),
                       lambda d,w:w["diagnostics"].update(cpuPlan="v16"),
                       lambda d,w:w["diagnostics"].update(embeddingThreads=2),
                       lambda d,w:d["diarizationRefinement"].update(embeddingThreads=2)):
            diagnostic, record, wrapper = cpu_evidence(); mutate(diagnostic, wrapper)
            with self.assertRaises(ValueError): validate_evidence(diagnostic, record, wrapper)

    def test_missing_new_adapter_policy_or_cpu_fields_cannot_look_like_old_raw(self):
        for mutate in (lambda d,w:w["diagnostics"].pop("cpuPlan"),
                       lambda d,w:w["diagnostics"].pop("embeddingThreads"),
                       lambda d,w:d.pop("cpuPolicy")):
            diagnostic, record, wrapper = cpu_evidence(); mutate(diagnostic, wrapper)
            with self.assertRaises(ValueError): validate_evidence(diagnostic, record, wrapper)

    def test_present_adapter_cpu_fields_cannot_bypass_legacy_when_map_missing(self):
        diagnostic, record, wrapper = evidence_fixture()
        for adapter in (diagnostic["diarizationRefinement"], wrapper["diagnostics"]):
            adapter.update(cpuPlan="auto_v1", embeddingThreads=1)
        raw = bind(diagnostic, record, wrapper)
        with self.assertRaises(ValueError):
            policy.validate_diarization_evidence(diagnostic, record, raw,
                case_id="fixture", audio_sha256="a"*64, duration_ms=3000)

    def test_new_cpu_policy_never_weakens_resource_counts_or_measured_vectors(self):
        for mutate in (lambda d,w:d["diarizationEmbeddingCounts"].update(releasedStreams=0),
                       lambda d,w:d["diarizationEmbeddingCounts"].update(computeAttempts=True),
                       lambda d,w:d["diarizationEmbeddingCounts"].update(extractorLoads=2),
                       lambda d,w:w["windows"][0].update(embedding=[0.]*512),
                       lambda d,w:w["windows"][0]["embedding"].pop()):
            diagnostic, record, wrapper = cpu_evidence(); mutate(diagnostic, wrapper)
            with self.assertRaises(ValueError): validate_evidence(diagnostic, record, wrapper)


class CpuCollectorTest(unittest.TestCase):
    def fixture(self):
        source = collector_fixtures.CollectorTest("test_full_synthetic_collector_checks_replay_scores_fixed5_dev_and_restores")
        source.setUp(); self.addCleanup(source.doCleanups)
        return source

    def test_invalid_cpu_cli_combination_fails_before_output_or_adb(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/"fresh"
            for options in (("--threads","1"), ("--request-auto",),
                            ("--cpu-plan","auto_v1","--threads","3")):
                args = collector.parser().parse_args(["--serial","do-not-adb","--audio-root",temp,
                    "--host-run",temp,"--output",str(output),*options])
                with mock.patch.object(collector.subprocess,"run") as adb, self.assertRaises(ValueError):
                    collector.run(args)
                adb.assert_not_called(); self.assertFalse(output.exists())

    def cpu_fake(self, threads, cores, *, requested=0):
        source = self.fixture()
        args, checked, old_process, calls, state = source.full_fake()
        args.cpu_plan="auto_v1"; args.threads=threads; args.request_auto=requested==0
        checked["host"]["config"].update(cpu_plan="auto_v1",threads=threads)
        checked["host"]["paired_asr_policy"]["threads"]=threads
        buffers, cases = {}, []
        for case in checked["cases"]:
            identifier=case["id"]
            def fetch(suffix):
                command=[args.adb,"-s",args.serial,"exec-out","run-as",args.package,"cat",
                    "files/evaluation/fixture/output/"+identifier+"."+suffix+".json"]
                return old_process(command).stdout
            diagnostic=json.loads(fetch("diagnostics")); record=json.loads(fetch("case")); wrapper=json.loads(fetch("diarization-evidence"))
            apply_cpu(diagnostic,wrapper,threads,plan="auto_v1",cores=cores,requested=requested)
            raw=bind(diagnostic,record,wrapper)
            buffers[(identifier,"diarization-evidence")]=raw
            for suffix,value in (("diagnostics",diagnostic),("case",record)):
                buffers[(identifier,suffix)]=json.dumps(value).encode()
            cases.append(record)
        calls.clear()
        def process(command,**kwargs):
            result=old_process(command,**kwargs)
            arguments=tuple(map(str,command[3:]))
            if arguments[:4]==("exec-out","run-as",args.package,"cat"):
                name=Path(arguments[-1]).name
                if name=="report.json":
                    report=json.loads(result.stdout)
                    report.update(threads=threads,cpuPlan="auto_v1",requestedThreads=requested,
                                  cpuPolicy=cpu_map(threads,cores=cores,requested=requested),cases=cases)
                    return subprocess.CompletedProcess(command,0,json.dumps(report).encode(),b"")
                identifier,suffix=name[:-5].split(".",1)
                if (identifier,suffix) in buffers:
                    return subprocess.CompletedProcess(command,0,buffers[(identifier,suffix)],b"")
            return result
        return args,checked,process,calls,state

    def test_controlled_full_collector_auto_request_passes_zero_to_android_and_scores_ten(self):
        args,checked,process,calls,state=self.cpu_fake(1,2)
        with mock.patch.object(collector,"preflight",return_value=checked),mock.patch.object(collector.subprocess,"run",side_effect=process),redirect_stdout(io.StringIO()):
            self.assertEqual(0,collector.run(args))
        report=collector.read_json(args.output/"run.json")
        self.assertEqual("COMPLETE",report["status"])
        self.assertEqual(10,len(report["diarization_evidence_cases"]))
        self.assertEqual(5,len(report["fixed_five_wer_port_gate"]["per_file_diagnostics"]))
        instrument=next(a for a in calls if a[:3]==("shell","am","instrument"))
        self.assertEqual("0",instrument[instrument.index("evalThreads")+1])
        self.assertEqual("auto_v1",instrument[instrument.index("evalCpuPlan")+1])
        self.assertEqual("3",state["stay"])

    def test_controlled_explicit_four_keeps_four_and_does_not_rewrite_as_auto(self):
        args,checked,process,calls,state=self.cpu_fake(4,1,requested=4)
        with mock.patch.object(collector,"preflight",return_value=checked),mock.patch.object(collector.subprocess,"run",side_effect=process),redirect_stdout(io.StringIO()):
            self.assertEqual(0,collector.run(args))
        instrument=next(a for a in calls if a[:3]==("shell","am","instrument"))
        self.assertEqual("4",instrument[instrument.index("evalThreads")+1])
        self.assertEqual("auto_v1",instrument[instrument.index("evalCpuPlan")+1])
        self.assertEqual("3",state["stay"])


if __name__ == "__main__":
    unittest.main()
