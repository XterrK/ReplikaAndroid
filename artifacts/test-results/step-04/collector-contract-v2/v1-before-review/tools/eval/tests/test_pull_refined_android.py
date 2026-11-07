"""Collector boundary/gate/power tests using fakes; no ADB/NN or Android changes."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import wave
import uuid

from tools.eval import pull_refined_android as c
from tools.eval.pipeline_refined import PAIRED_ASR_POLICY
from tools.eval.tests.test_native_diar_policy import evidence_fixture, bind, word_fixture, host, native_policy


class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def args(self, *extra):
        return c.parser().parse_args(["--serial", "nonexistent-do-not-adb", "--audio-root", str(self.root / "audio"),
            "--host-run", str(self.root / "host"), "--output", str(self.root / "fresh"), *extra])

    def test_negative_preflight_precedes_any_adb_subprocess_or_output_creation(self):
        for extra in (("--diar-plan", "v16"), ("--asr-plan", "v16"), ("--threads", "1"),
                      ("--expected-speakers", "2"), ("--package", "unsafe;command")):
            args=self.args(*extra)
            with mock.patch.object(c.subprocess,"run") as process, self.assertRaises(ValueError):
                c.run(args)
            process.assert_not_called();self.assertFalse(args.output.exists())

    def test_existing_outputs_never_overwritten(self):
        args=self.args();args.output.mkdir();(args.output/"proof").write_text("preserve")
        with mock.patch.object(c.subprocess,"run") as process,self.assertRaisesRegex(ValueError,"fresh"):
            c.run(args)
        process.assert_not_called();self.assertEqual("preserve",(args.output/"proof").read_text())

    def test_check_only_makes_no_output_or_device_calls(self):
        args=self.args("--check")
        checked={"cases":[{"id":"a"}],"fixed_five_ids":["a"],"fingerprint":{"test":True}}
        with mock.patch.object(c,"preflight",return_value=checked),mock.patch.object(c.subprocess,"run") as process,redirect_stdout(io.StringIO()) as out:
            self.assertEqual(0,c.run(args))
        self.assertEqual("PREFLIGHT_PASS",json.loads(out.getvalue())["status"])
        process.assert_not_called();self.assertFalse(args.output.exists())

    def test_weighted_historical_five_cannot_be_masked_by_dev_extras(self):
        fixed=["a","b","c","d","e"];dev=["a","b","c","f","g","h","i","j"]
        rows=[{"id":i,"reference_words":100,"host_errors":10,"native_errors":10} for i in fixed]
        rows[0]["native_errors"]=13  # 3/500 = +.6pp => FAIL fixedfive.
        rows.extend({"id":i,"reference_words":10000,"host_errors":1000,"native_errors":0} for i in dev if i not in fixed)
        result=c.paired_summary(rows,dev,fixed)
        self.assertFalse(result["gate_pass"])
        self.assertAlmostEqual(.6,result["fixed_five_wer_port_gate"]["wer_delta_percentage_points"])
        self.assertEqual(10,result["union_cases"])
        rows[0]["native_errors"]=12 # +.4pp => PASS although that one file is +2pp.
        result=c.paired_summary(rows,dev,fixed)
        self.assertTrue(result["gate_pass"])
        self.assertFalse(result["fixed_five_wer_port_gate"]["per_file_diagnostics"][0]["per_file_within_threshold"])

    def test_missing_duplicate_extra_cases_do_not_shrink_gate(self):
        fixed=["a","b","c","d","e"];dev=["a","b","c","f","g","h","i","j"]
        rows=[{"id":i,"reference_words":1,"host_errors":0,"native_errors":0} for i in set(fixed+dev)]
        for invalid in (rows[:-1],rows+[rows[0]],rows+[{**rows[0],"id":"extra"}]):
            with self.assertRaises(ValueError):c.paired_summary(invalid,dev,fixed)

    def test_dev_quality_gate_distinct_count_der_and_undefined_denominator(self):
        baseline={"cases":8,"native_der_collar_0ms":{"rate":.2688518170426065,"reference_speaker_ms":255360.}}
        summary={"cases":8,"native_speaker_count_exact_cases":7,
                 "native_der_collar_0ms":{"rate":.2888518170426065,"reference_speaker_ms":255360.}}
        result=c.dev_quality(summary,baseline)
        self.assertTrue(result["gate_pass"])
        self.assertEqual(2,result["der_allowance_percentage_points"])
        summary["native_speaker_count_exact_cases"]=6
        self.assertFalse(c.dev_quality(summary,baseline)["count_pass"])
        summary["native_speaker_count_exact_cases"]=7
        summary["native_der_collar_0ms"]["rate"]+=1e-10
        self.assertFalse(c.dev_quality(summary,baseline)["native_der0_pass"])
        summary["native_der_collar_0ms"].update(rate=None,reference_speaker_ms=0)
        self.assertFalse(c.dev_quality(summary,baseline)["gate_pass"])

    def test_canonical_wav_shape_and_floor_duration(self):
        path=self.root/"canonical.wav"
        with wave.open(str(path),"wb") as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000)
            stream.writeframes(b"\0\0"*16015)
        self.assertEqual(16015,c.canonical_audio(path,1000))
        with self.assertRaises(ValueError):c.canonical_audio(path,1001)
        with wave.open(str(path),"wb") as stream:
            stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(16000);stream.writeframes(b"\0"*64000)
        with self.assertRaisesRegex(ValueError,"canonical"):c.canonical_audio(path,1000)

    def screen_adb(self, *, sleeping=False, fail_wake=False):
        calls=[];current={"setting":"3"}
        def adb(*args,**kwargs):
            calls.append(args)
            if args==("shell","dumpsys","power"):
                data=b"mWakefulness=Asleep\n" if sleeping else b"mWakefulness=Awake\n"
            elif args==("shell","dumpsys","activity","activities"):
                data=b"mResumedActivity: ActivityRecord{ ru.replika.offline/.MainActivity }\n"
            elif args[:4]==("shell","settings","get","global"):
                data=current["setting"].encode()+b"\n"
            elif args[:4]==("shell","settings","put","global"):
                current["setting"]=args[-1];data=b""
            elif args==("shell","svc","power","stayon","true"):
                current["setting"]="7";data=b""
            elif fail_wake and args==("shell","input","keyevent","KEYCODE_WAKEUP"):
                raise RuntimeError("fake wake failure")
            else:data=b""
            return subprocess.CompletedProcess(args,0,data,b"")
        return adb,calls,current

    def test_emulator_power_prepare_and_finally_restore_original(self):
        adb,calls,current=self.screen_adb();state={}
        c.screen_prepare(adb,"ru.replika.offline",self.root,state,emulator=True)
        self.assertEqual("7",current["setting"]);self.assertTrue(state["pre_inference_awake_resumed"])
        self.assertTrue(c.screen_restore(adb,self.root,state));self.assertEqual("3",current["setting"])
        self.assertTrue((self.root/"power-before.txt").exists());self.assertTrue((self.root/"power-after.txt").exists())
        self.assertIn(("shell","wm","dismiss-keyguard"),calls)

    def test_partial_wake_failure_retains_original_for_finally(self):
        adb,calls,current=self.screen_adb(fail_wake=True);state={}
        with self.assertRaisesRegex(RuntimeError,"wake"):
            c.screen_prepare(adb,"ru.replika.offline",self.root,state,emulator=True)
        self.assertEqual("3",state["original_stay_on_while_plugged_in"])
        self.assertTrue(c.screen_restore(adb,self.root,state))

    def test_sleeping_and_unresumed_cannot_enter_inference_and_phone_not_mutated(self):
        adb,calls,current=self.screen_adb(sleeping=True);state={}
        with self.assertRaisesRegex(ValueError,"Awake"):
            c.screen_prepare(adb,"ru.replika.offline",self.root,state,emulator=False)
        self.assertFalse(any(a[1:3] in (("input","keyevent"),("svc","power")) for a in calls))
        adb,calls,current=self.screen_adb();state={}
        def no_resume(*args,**kwargs):
            if args==("shell","dumpsys","activity","activities"):
                return subprocess.CompletedProcess(args,0,b"mResumedActivity: other.app",b"")
            return adb(*args,**kwargs)
        with self.assertRaisesRegex(ValueError,"RESUMED"):
            c.screen_prepare(no_resume,"ru.replika.offline",self.root,state,emulator=False)

    def full_fake(self, *, restore_fails=False, corrupt_one=False):
        """A synthetic ten-case completed batch exercises the real collector path."""
        args=self.args();args.host_run.mkdir();(args.host_run/"run.json").write_text("{}")
        audio=self.root/"input.wav";audio.write_bytes(b"synthetic audio fixture, never decoded")
        audio_sha=c.digest(audio)
        reference=self.root/"independent-reference.json"
        reference.write_text(json.dumps({"transcript":[{"speaker_id":"speaker_1","start_ms":0,"end_ms":3000,"text":"Привет, мир!"}]}))
        dev=["dev-01-two-clean","dev-03-short","dev-mono-s","dev-two","dev-three","dev-four","dev-five","dev-six"]
        fixed=list(c.FIXED_FIVE);ids=dev+[i for i in fixed if i not in dev]
        payloads={};native_cases=[];records={};cases=[];inputs={}
        for i,identifier in enumerate(ids):
            d,n,w=evidence_fixture();d.update(word_fixture())
            n.update(id=identifier,audio_sha256=audio_sha,segments=1,
                workId=str(uuid.uuid5(uuid.NAMESPACE_DNS,"work"+identifier)),
                recordingId="qa-evaluation-"+str(uuid.uuid5(uuid.NAMESPACE_DNS,"record"+identifier)))
            w.update(work_id=n["workId"],recording_id=n["recordingId"])
            w["metadata"]["inputAudioSha256"]=audio_sha
            raw=bind(d,n,w)
            hyp,_=c.policy.reconstruct_jury(d,3000)
            metric=c.score_case(json.loads(reference.read_text()),hyp,d,3000,120)
            if corrupt_one and i==0:
                d["wordEvidenceTruncated"]=True
            payloads[identifier]={"case":json.dumps(n).encode(),"hypothesis":json.dumps(hyp).encode(),
                "diagnostics":json.dumps(d).encode(),"diarization-evidence":raw}
            native_cases.append(n)
            case={"id":identifier,"duration_ms":3000,"audio_sha256":audio_sha,"split":"dev" if identifier in dev else "holdout","kind":"synthetic-fixture"}
            cases.append(case);inputs[identifier]={"audio":audio,"reference":reference,"reference_sha256":c.digest(reference)}
            records[identifier]={**case,"processing_ms":120,"metrics":metric}
        checked={"cases":cases,"dev_ids":dev,"fixed_five_ids":fixed,"models":{"files":[]},
            "host_records":records,"inputs":inputs,"host":{"config":host(),"paired_asr_policy":dict(PAIRED_ASR_POLICY)},
            "fixed_dev_baseline":{"cases":8,"native_der_collar_0ms":{"rate":.2688518170426065,"reference_speaker_ms":24000.}},
            "fingerprint":{"host_run_sha256":c.digest(args.host_run/"run.json"),"apk":{"app":{"sha256":"a"*64},"test":{"sha256":"a"*64}}}}
        calls=[];state={"stay":"3","run":None}
        def subprocess_fake(command,**kwargs):
            a=tuple(map(str,command[3:]));calls.append(a)
            code=0;raw=b""
            if a==("get-state",):raw=b"device\n"
            elif a==("shell","getprop","ro.kernel.qemu"):raw=b"1\n"
            elif a[:3]==("shell","pm","path"):raw=b"package:/data/app/fake/base.apk\n"
            elif a[:2]==("exec-out","sha256sum"):raw=("a"*64+"  fake\n").encode()
            elif a[:4]==("shell","settings","get","global"):
                raw=(state["stay"]+"\n").encode()
            elif a[:4]==("shell","settings","put","global"):
                if restore_fails:raise RuntimeError("fake original setting restore failure")
                state["stay"]=a[-1]
            elif a==("shell","svc","power","stayon","true"):state["stay"]="7"
            elif a==("shell","dumpsys","power"):raw=b"mWakefulness=Awake\n"
            elif a==("shell","dumpsys","activity","activities"):raw=b"mResumedActivity: ru.replika.offline/.MainActivity\n"
            elif a[:4]==("shell","am","instrument","-w"):
                state["run"]=a[a.index("evalRun")+1];raw=b"OK (1 test)\n"
            elif a[:4]==("shell","run-as",args.package,"test"):code=1
            elif a[:4]==("exec-out","run-as",args.package,"cat"):
                name=Path(a[-1]).name
                if name=="report.json":
                    raw=json.dumps({**native_policy(),"status":"COMPLETE","run":state["run"],"newModelInference":True,"cases":native_cases}).encode()
                else:
                    identifier,suffix=name[:-5].split(".",1);raw=payloads[identifier][suffix]
            return subprocess.CompletedProcess(command,code,raw,b"")
        return args,checked,subprocess_fake,calls,state

    def test_full_synthetic_collector_checks_replay_scores_fixed5_dev_and_restores(self):
        args,checked,process,calls,state=self.full_fake()
        with mock.patch.object(c,"preflight",return_value=checked),mock.patch.object(c.subprocess,"run",side_effect=process),redirect_stdout(io.StringIO()):
            self.assertEqual(0,c.run(args))
        report=c.read_json(args.output/"run.json")
        self.assertEqual("COMPLETE",report["status"]);self.assertTrue(report["dev_quality_gate"]["gate_pass"])
        self.assertEqual(5,len(report["fixed_five_wer_port_gate"]["per_file_diagnostics"]))
        self.assertEqual("3",state["stay"]);self.assertEqual(10,len(report["diarization_evidence_cases"]))
        self.assertTrue((args.output/"results.csv").exists())
        instrument=next(a for a in calls if a[:3]==("shell","am","instrument"))
        self.assertEqual(c.policy.PLAN,instrument[instrument.index("evalDiarPlan")+1])
        pushed=[a[1] for a in calls if a[0]=="push"]
        self.assertFalse(any("reference" in x for x in pushed))

    def test_finally_restore_failure_is_nonzero_and_does_not_leave_complete(self):
        args,checked,process,calls,state=self.full_fake(restore_fails=True)
        with mock.patch.object(c,"preflight",return_value=checked),mock.patch.object(c.subprocess,"run",side_effect=process),redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,"restore"):
            c.run(args)
        report=c.read_json(args.output/"run.json")
        self.assertEqual("FAILED",report["status"])
        self.assertEqual("COMPLETE",report["prior_status_before_restoration_failure"])

    def test_one_bad_case_kept_with_other_nine_outputs_and_cannot_pass(self):
        args,checked,process,calls,state=self.full_fake(corrupt_one=True)
        with mock.patch.object(c,"preflight",return_value=checked),mock.patch.object(c.subprocess,"run",side_effect=process),self.assertRaisesRegex(ValueError,"validation failed"):
            c.run(args)
        report=c.read_json(args.output/"run.json")
        self.assertEqual("FAILED",report["status"]);self.assertEqual(9,len(report["cases"]))
        self.assertTrue((args.output/checked["cases"][0]["id"]/"validation-failure.json").exists())
        self.assertEqual("3",state["stay"])


if __name__=="__main__":
    unittest.main()
