from pathlib import Path
import contextlib,copy,hashlib,io,json,sys,unittest,zipfile
from unittest.mock import patch
ROOT=Path('/mnt/d/ReplikaAndroid/ReplikaAndroid')
sys.path.insert(0,str(ROOT))
from tools import run_plan19_perf as runner
from tools import create_plan19_perf_corpus as corpus
OUT=Path(__file__).parent
class Checks(unittest.TestCase):
 def setUp(self):
  src=ROOT/'artifacts/test-results/step-04/context600-c2-android-v3/dev-01-two-clean'
  self.d=json.loads((src/'diagnostics.json').read_text());self.n=json.loads((src/'case.json').read_text());self.h=json.loads((src/'hypothesis.json').read_text())
  self.config=json.loads((ROOT/'configs/eval/c2-window-selected-full.json').read_text())
  self.case={'id':self.n['id'],'duration_ms':self.n['duration_ms'],'audio_sha256':self.n['audio_sha256']}
  self.n.update(collectEvidence=False,processId=12345,workManagerState='SUCCEEDED')
  self.d['diarizationRefinement'].update(cpuPlan='auto_v1',embeddingThreads=2)
  self.d['cpuPolicy']={'plan':'auto_v1','requestedThreads':2,'availableCores':2,'asrThreads':2,'diarizationThreads':2,'refinementThreads':2,'diarizationPinned':False,'refinementPinned':False}
  for key in list(self.d):
   if key.startswith('diarizationEvidence'):del self.d[key]
  self.d.update(wordEvidenceRequested=False,wordEvidenceBytes=0,wordEvidenceTruncated=False)
  for part in self.d['asrSlices']:
   for key in ('tokens','timestamps','words'):part.pop(key,None)
   part.update(wordEvidenceIncluded=False,wordEvidenceOmittedReason='not_requested')
 def check(self):return runner.validate_compact_case(self.case,self.n,self.d,self.h,self.config,2)
 def test_compact_saved_data_boundary(self):
  result=self.check();self.assertTrue(result['resources_balanced']);self.assertFalse(result['full_token_vector_replay_performed'])
 def test_explicit_qa_disabled_not_truncated(self):
  for field,value in [('wordEvidenceRequested',True),('wordEvidenceTruncated',True),('wordEvidenceBytes',1),('diarizationEvidenceRequested',True)]:
   d=copy.deepcopy(self.d);d[field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):runner.validate_compact_case(self.case,self.n,d,self.h,self.config,2)
 def test_no_hidden_arrays(self):
  for field in ('tokens','timestamps','words'):
   d=copy.deepcopy(self.d);d['asrSlices'][0][field]=[]
   with self.subTest(field=field),self.assertRaises(ValueError):runner.validate_compact_case(self.case,self.n,d,self.h,self.config,2)
 def test_real_lifecycle_counts_are_strict(self):
  for field,value in [('releasedStreams',0),('extractorLoads',True),('embeddingDimension',256)]:
   d=copy.deepcopy(self.d);d['diarizationEmbeddingCounts'][field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):runner.validate_compact_case(self.case,self.n,d,self.h,self.config,2)
 def test_clock_cpu_work_and_text_fail_closed(self):
  d=copy.deepcopy(self.d);d['asrSlices'][0]['frameStrideMs']=40.0
  with self.assertRaises(ValueError):runner.validate_compact_case(self.case,self.n,d,self.h,self.config,2)
  d=copy.deepcopy(self.d);d['cpuPolicy']['asrThreads']=4
  with self.assertRaises(ValueError):runner.validate_compact_case(self.case,self.n,d,self.h,self.config,2)
  n=copy.deepcopy(self.n);n['workManagerState']='RUNNING'
  with self.assertRaises(ValueError):runner.validate_compact_case(self.case,n,self.d,self.h,self.config,2)
  h=copy.deepcopy(self.h);h['transcript'][0]['text']='changed words'
  with self.assertRaises(ValueError):runner.validate_compact_case(self.case,self.n,self.d,h,self.config,2)
 def test_corpus_source_and_literal_repeated_reference(self):
  block,rows,facts,source,path=corpus.source_block(ROOT/'benchmark/eval',Path('/home/egor/replika-toolchain/eval-audio'))
  self.assertEqual(facts['exact_prefix_frames'],842543);self.assertEqual(len(rows),6);self.assertEqual(facts['submillisecond_author_clip_tail_retained_samples'],15)
  self.assertEqual(len(block),1920000);self.assertFalse(any(block[842543*2:]));self.assertEqual(corpus.sha(path),corpus.AUDIO_SHA256)
  manifest=json.loads((ROOT/'benchmark/eval-perf/manifest.json').read_text())
  for case in manifest['files']:
   ref=json.loads((ROOT/'benchmark/eval-perf'/case['reference']).read_text())['transcript']
   self.assertEqual(len(ref),6*case['repeat_blocks'])
   for i,row in enumerate(ref):
    original=rows[i%6];shift=(i//6)*60000
    self.assertEqual(row,{**original,'start_ms':original['start_ms']+shift,'end_ms':original['end_ms']+shift})
 def test_existing_corpus_never_overwritten(self):
  path=ROOT/'benchmark/eval-perf/manifest.json';before=runner.sha(path)
  with self.assertRaises(FileExistsError):corpus.prepare(ROOT/'benchmark/eval',Path('/home/egor/replika-toolchain/eval-audio'),Path('/home/egor/replika-toolchain/plan19-perf'),ROOT/'benchmark/eval-perf')
  self.assertEqual(before,runner.sha(path))
 def test_check_no_output_subprocess_or_adb(self):
  # Deliberately MOCK APKs for a local preflight test, never installed or inferred.
  app=OUT/'MOCK-app.apk';test=OUT/'MOCK-test.apk'
  with zipfile.ZipFile(app,'w') as z:z.writestr('assets/models-lock.json',(ROOT/'app/src/main/assets/models-lock.json').read_bytes())
  with zipfile.ZipFile(test,'w') as z:z.writestr('classes.dex',b'MOCK ONLY, not executable DEX: evalCollectEvidence')
  target=OUT/'MUST-REMAIN-ABSENT'
  args=runner.parser().parse_args(['--check','--serial','NEVER-CONTACTED','--audio-root','/home/egor/replika-toolchain/plan19-perf','--app-apk',str(app),'--test-apk',str(test),'--output',str(target)])
  stream=io.StringIO()
  with patch.object(runner.subprocess,'run',side_effect=AssertionError('No subprocess')),patch.object(runner.subprocess,'Popen',side_effect=AssertionError('No Popen')),patch.object(Path,'mkdir',side_effect=AssertionError('No mkdir')),contextlib.redirect_stdout(stream):
   self.assertEqual(runner.run(args),0)
  value=json.loads(stream.getvalue());self.assertEqual(value['status'],'PREFLIGHT_PASS');self.assertFalse(value['adb_invoked']);self.assertFalse(target.exists());self.assertEqual(value['workers'],12);self.assertEqual(value['total_audio_ms'],3360000)
 def test_adapter_cpu_algorithm_and_status_strict(self):
  for status in ('SUPPORTED','PARTIAL_TEMPORAL'):
   d=copy.deepcopy(self.d);d['diarizationRefinement']['status']=status
   runner.validate_compact_case(self.case,self.n,d,self.h,self.config,2)
  for key,value in [('cpuPlan','v16'),('embeddingThreads',4),('embeddingThreads',2.0),('algorithm','centroid-refiner-v1'),('status','UNSUPPORTED'),('status',None)]:
   d=copy.deepcopy(self.d);d['diarizationRefinement'][key]=value
   with self.subTest(key=key,value=value),self.assertRaises(ValueError):runner.validate_compact_case(self.case,self.n,d,self.h,self.config,2)
  for key in ('cpuPlan','embeddingThreads','algorithm','status'):
   d=copy.deepcopy(self.d);d['diarizationRefinement'].pop(key)
   with self.subTest(missing=key),self.assertRaises(ValueError):runner.validate_compact_case(self.case,self.n,d,self.h,self.config,2)
  d=copy.deepcopy(self.d);d['threads']=4
  d['cpuPolicy'].update(requestedThreads=4,asrThreads=4,diarizationThreads=4,refinementThreads=4)
  with self.assertRaises(ValueError):runner.validate_compact_case(self.case,self.n,d,self.h,self.config,4)
  d['diarizationRefinement']['embeddingThreads']=4
  runner.validate_compact_case(self.case,self.n,d,self.h,self.config,4)
 def test_full_native_report_case_copies_cannot_disagree(self):
  self.assertIsNone(runner.validate_case_copy(self.n,copy.deepcopy(self.n)))
  for key,value in [('processId',12346),('workId','00000000-0000-0000-0000-000000000001'),('recordingId','qa-evaluation-00000000-0000-0000-0000-000000000001'),('duration_ms',self.n['duration_ms']+1),('duration_ms',float(self.n['duration_ms'])),('processing_ms',self.n['processing_ms']+1),('audio_sha256','0'*64),('collectEvidence',True),('extra_unreported_field',1)]:
   different=copy.deepcopy(self.n);different[key]=value
   with self.subTest(key=key,value=value),self.assertRaises(ValueError):runner.validate_case_copy(different,self.n)
 def test_one_of_twelve_is_partial_and_never_forgets_verified_nn(self):
  report={'planned_workers':12,'batches':[{'cases':[]}],'new_model_inference':False,'inference_completion_verified':False}
  self.assertEqual(runner.update_verified_progress(report,requested=True),0)
  self.assertIsNone(report['new_model_inference']);self.assertFalse(report['inference_completion_verified'])
  report['batches'][0]['cases'].append({'verified_mock_case':True})
  self.assertEqual(runner.update_verified_progress(report),1)
  self.assertEqual(report['verified_workers'],1);self.assertEqual(report['completed_workers'],1)
  self.assertTrue(report['new_model_inference']);self.assertFalse(report['inference_completion_verified'])
  report['status']='FAILED'
  runner.update_verified_progress(report,requested=True)
  self.assertFalse(report['inference_completion_verified']);self.assertTrue(report['new_model_inference'])
  report['batches'].append({'cases':[]})
  runner.update_verified_progress(report,requested=True)
  self.assertTrue(report['new_model_inference']);self.assertFalse(report['inference_completion_verified'])
  report['batches'][1]['cases']=[{} for _ in range(11)]
  self.assertEqual(runner.update_verified_progress(report),12)
  self.assertEqual(report['verified_workers'],12);self.assertEqual(report['completed_workers'],12)
  self.assertTrue(report['new_model_inference']);self.assertTrue(report['inference_completion_verified'])
  report['batches'][1]['cases'].append({})
  with self.assertRaises(ValueError):runner.update_verified_progress(report)
if __name__=='__main__':unittest.main(verbosity=2)
