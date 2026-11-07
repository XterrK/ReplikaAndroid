"""Synthetic controls only. No ADB, NN, installation, source or device changes."""
from pathlib import Path
import contextlib
import copy
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path('/mnt/d/ReplikaAndroid/ReplikaAndroid')
SCRIPT = Path('/home/egor/replika-toolchain/evidence/step05-compact-smoke.py')
spec = importlib.util.spec_from_file_location('compact_smoke', SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        args = smoke.parser().parse_args(['--repo', str(ROOT), '--audio-root', '/home/egor/replika-toolchain/eval-audio'])
        args.model_root = ROOT/'model-pack'
        args.app_apk = ROOT/'app/build/outputs/apk/debug/app-debug.apk'
        args.test_apk = ROOT/'app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk'
        args.output = ROOT/'artifacts/test-results/step-05/compact-smoke-v1'
        cls.runner, cls.collector, cls.checked = smoke.preflight(args)
        cls.args = args

    def setUp(self):
        # Saved actual full-QA data is explicitly TRANSFORMED into a synthetic
        # compact/cpu control. It never establishes actual QAfalse behavior.
        source = ROOT/'artifacts/test-results/step-04/context600-c2-android-v3/dev-mono-s'
        self.d = self.runner.read_json(source/'diagnostics.json')
        self.n = self.runner.read_json(source/'case.json')
        self.h = self.runner.read_json(source/'hypothesis.json')
        self.n.update(collectEvidence=False, processId=12345, workManagerState='SUCCEEDED')
        for key in list(self.d):
            if key.startswith('diarizationEvidence'):
                del self.d[key]
        self.d.update(wordEvidenceRequested=False,wordEvidenceBytes=0,wordEvidenceTruncated=False)
        self.d['cpuPolicy'] = {'plan':'auto_v1','requestedThreads':2,'availableCores':2,'asrThreads':2,
            'diarizationThreads':2,'refinementThreads':2,'diarizationPinned':False,'refinementPinned':False}
        self.d['diarizationRefinement'].update(cpuPlan='auto_v1',embeddingThreads=2)
        for part in self.d['asrSlices']:
            for key in ('tokens','timestamps','words'):
                part.pop(key, None)
            part.update(wordEvidenceIncluded=False,wordEvidenceOmittedReason='not_requested')
        self.report = copy.deepcopy(self.d)
        self.report.update(status='COMPLETE', collectEvidence=False,newModelInference=True,
                           cases=[copy.deepcopy(self.n)],processId=12345,cpuPlan='auto_v1',requestedThreads=2)

    def validate(self, profile='compact-auto-two'):
        return smoke.validate_actual(self.runner,self.checked,self.report,self.n,self.d,self.h,profile)

    def legacy(self):
        for value in (self.d, self.report):
            value.update(threads=1,cpuPlan='v16',requestedThreads=1)
            value['cpuPolicy'].update(plan='v16',requestedThreads=1,asrThreads=1,
                diarizationPinned=True,refinementPinned=True)
        self.d['diarizationRefinement']['cpuPlan']='v16'

    def test_default_and_check_never_subprocess_mkdir_or_adb(self):
        for flag in ([], ['--check']):
            with (self.subTest(flag=flag),patch.object(subprocess,'run',side_effect=AssertionError('No subprocess')),
                patch.object(subprocess,'Popen',side_effect=AssertionError('No Popen')),
                patch.object(Path,'mkdir',side_effect=AssertionError('No mkdir')),
                contextlib.redirect_stdout(io.StringIO()) as output):
                self.assertEqual(smoke.main(flag+['--repo',str(ROOT),'--audio-root','/home/egor/replika-toolchain/eval-audio']),0)
                value=json.loads(output.getvalue());self.assertFalse(value['adb_invoked']);self.assertFalse(value['new_model_inference'])
        self.assertFalse(self.args.output.exists())

    def test_pure_auto_and_legacy_boundaries(self):
        counts,metrics=self.validate();self.assertTrue(counts['resources_balanced']);self.assertFalse(counts['full_token_vector_replay_performed'])
        self.assertIn('native_der_collar_0ms',metrics)
        self.legacy()
        counts,_=self.validate('legacy-c2-moderate-one')
        self.assertTrue(counts['narrow_legacy_stage_pin_smoke'])
        self.assertFalse(counts['strict_c2_acceptance_gate_applied'])

    def test_cpu_stage_pins_not_normalized_or_weakened(self):
        self.legacy()
        original=copy.deepcopy(self.d)
        for key,value in [('asrThreads',2),('diarizationThreads',1),('refinementThreads',1),
                          ('diarizationPinned',False),('refinementPinned',False),
                          ('availableCores',True),('availableCores',2**31),('requestedThreads',True)]:
            self.d=copy.deepcopy(original);self.d['cpuPolicy'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate('legacy-c2-moderate-one')
        self.d=copy.deepcopy(original);self.d['diarizationRefinement']['embeddingThreads']=1
        with self.assertRaises(ValueError):self.validate('legacy-c2-moderate-one')

    def test_native_copy_pid_and_real_completion(self):
        self.report['cases'][0]['workId']='00000000-0000-0000-0000-000000000001'
        with self.assertRaises(ValueError):self.validate()
        self.report['cases']=[copy.deepcopy(self.n)];self.report['processId']=54321
        with self.assertRaises(ValueError):self.validate()
        self.report['processId']=12345;self.n['workManagerState']='RUNNING';self.report['cases']=[copy.deepcopy(self.n)]
        with self.assertRaises(ValueError):self.validate()

    def test_compact_arrays_lifecycle_and_literal_text(self):
        original=copy.deepcopy(self.d)
        self.d['asrSlices'][0]['tokens']=[]
        with self.assertRaises(ValueError):self.validate()
        self.d=copy.deepcopy(original);self.d['diarizationRefinement']['refiner']['tree']=[]
        with self.assertRaises(ValueError):self.validate()
        self.d=copy.deepcopy(original);self.d['diarizationEmbeddingCounts']['releasedStreams']=0
        with self.assertRaises(ValueError):self.validate()
        self.d=copy.deepcopy(original);self.h['transcript'][0]['text']='changed literal ASR words'
        with self.assertRaises(ValueError):self.validate()

    def fake_adb(self, words, *, nonzero=False, restoration_failure=False):
        self.calls.append(words)
        payload=b'';code=0
        if words==['get-state']:payload=b'device\n'
        elif words[:3]==['shell','getprop','ro.kernel.qemu']:payload=b'1\n'
        elif words[:3]==['shell','pm','path']:
            suffix='test' if words[3].endswith('.test') else 'app'
            payload=('package:/data/app/'+suffix+'/base.apk\n').encode()
        elif words[:2]==['exec-out','sha256sum']:
            role='test' if '/test/' in words[2] else 'app';payload=(smoke.APKS[role]+'  '+words[2]).encode()
        elif words[:4]==['exec-out','run-as','ru.replika.offline','sha256sum']:
            key=words[4].removeprefix('files/models/')
            row=next(row for row in self.checked['models']['files'] if row['path']==key)
            payload=(row['sha256']+'  '+words[4]).encode()
        elif words[:3]==['shell','dumpsys','power']:payload=b'mWakefulness=Awake\n'
        elif words[:3]==['shell','dumpsys','activity']:payload=b'mResumedActivity: ru.replika.offline/ru.replika.MainActivity\n'
        elif words[:3]==['shell','settings','get']:payload=b'1\n'
        elif words[:3]==['shell','settings','put'] and restoration_failure:code=1
        elif words[:4]==['shell','run-as','ru.replika.offline','test']:code=1
        elif words[:3]==['shell','am','instrument']:
            self.report['run']=words[words.index('evalRun')+1]
            payload=b'FAILURES!!!\n' if nonzero else b'OK (1 test)\n'
            code=1 if nonzero else 0
        elif words[:4]==['exec-out','run-as','ru.replika.offline','cat']:
            name=Path(words[4]).name
            obj={'report.json':self.report,'dev-mono-s.case.json':self.n,
                'dev-mono-s.diagnostics.json':self.d,'dev-mono-s.hypothesis.json':self.h}[name]
            payload=json.dumps(obj).encode()
        return subprocess.CompletedProcess(['MOCK-ADB',*words],code,payload,b'MOCK ERROR' if code else b'')

    def execute_mock(self, profile='compact-auto-two',nonzero=False,restoration_failure=False):
        with tempfile.TemporaryDirectory(prefix='compact-control-',dir='/home/egor/replika-toolchain/evidence') as temporary:
            args=copy.copy(self.args);args.output=Path(temporary)/'MOCK-ONLY';args.execute=True;args.profile=profile
            self.calls=[]
            def subprocess_mock(argv,**kwargs):return self.fake_adb(argv[3:],nonzero=nonzero,restoration_failure=restoration_failure)
            with patch.object(smoke,'preflight',return_value=(self.runner,self.collector,self.checked)),patch.object(subprocess,'run',side_effect=subprocess_mock),contextlib.redirect_stderr(io.StringIO()):
                code=smoke.run(args)
            report=self.runner.read_json(args.output/'run.json')
            files={p.name for p in args.output.iterdir()}
            commands=list(self.calls)
            return code,report,files,commands

    def test_mock_end_to_end_both_profiles_only_audio_and_batch_staged(self):
        for profile in smoke.PROFILES:
            if profile!='compact-auto-two':self.legacy()
            code,report,files,commands=self.execute_mock(profile)
            self.assertEqual(code,0,report);self.assertEqual(report['status'],'COMPLETE')
            self.assertTrue(report['inference_completion_verified']);self.assertFalse(report['quality_acceptance'])
            pushes=[row for row in commands if row[0]=='push'];self.assertEqual(len(pushes),2)
            self.assertTrue(all(Path(row[1]).name in ('batch.json','dev-mono-s.wav') for row in pushes))
            self.assertFalse(any(any(verb in row for verb in ('install','force-stop','clear','uninstall')) for row in commands))
            self.assertEqual(report['screen_power']['restored_stay_on_while_plugged_in'],'1')

    def test_nonzero_instrumentation_pulls_partial_and_restores(self):
        code,report,files,commands=self.execute_mock(nonzero=True)
        self.assertEqual(code,1);self.assertEqual(report['status'],'FAILED')
        self.assertTrue({'instrumentation.log','instrumentation-report.json','dev-mono-s.case.json','dev-mono-s.diagnostics.json','dev-mono-s.hypothesis.json'}<=files)
        self.assertEqual(report['screen_power']['restored_stay_on_while_plugged_in'],'1')
        self.assertIsNone(report['new_model_inference']);self.assertFalse(report['inference_completion_verified'])

    def test_restore_failure_cannot_return_success(self):
        code,report,_,_=self.execute_mock(restoration_failure=True)
        self.assertEqual(code,1);self.assertEqual(report['status'],'FAILED');self.assertTrue(report['restoration_failed'])
        self.assertTrue(report['inference_completion_verified']);self.assertTrue(report['new_model_inference'])


if __name__=='__main__':unittest.main(verbosity=2)
