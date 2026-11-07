#!/usr/bin/env python3
"""Independent saved-only audit of the failed 12-Worker experiment's completed five cases."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import csv,hashlib,io,json,math,re,sys,wave
sys.dont_write_bytecode=True
REPO=Path('/mnt/d/ReplikaAndroid/ReplikaAndroid')
OUT=REPO/'artifacts/test-results/step-05/perf-2-4-4-2-v1'
OUTPUT=OUT/'independent-partial-audit.json'
DRIVER='a910dd990505175d031312e1dc0ed8848cb5caabcc64434dde19d367c2a4747c'
PROTOCOL='aef12832afdd97eef5e301e1515402535e01fbbbe7ce0414bdefda0b3419196a'
IDS=['perf-01m','perf-03m','perf-10m']
class Audit:
 def __init__(self):self.hashes={};self.checks=0
 def check(self,value,label):
  self.checks+=1
  if not value:raise AssertionError(str(label))
 def sha(self,path):
  path=Path(path).resolve();name=str(path)
  if name not in self.hashes:
   with path.open('rb') as f:self.hashes[name]=hashlib.file_digest(f,'sha256').hexdigest()
  return self.hashes[name]
 def read(self,path):self.sha(path);return strict(Path(path).read_bytes())
 def unchanged(self):
  for name,expected in list(self.hashes.items()):
   with Path(name).open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
   self.check(actual==expected,('immutable throughout audit',name))
def strict(raw):
 def pairs(items):
  d={}
  for k,v in items:
   if k in d:raise ValueError('duplicate key: '+k)
   d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def weighted(rows):
 audio=sum(r['duration_ms'] for r in rows);processing=sum(r['processing_ms'] for r in rows)
 out={'cases':len(rows),'audio_ms':audio,'processing_ms':processing,'observed_rtf':processing/audio if audio else None}
 for metric in ['wer_raw','wer_normalized','cpwer_raw']:
  errors=sum(r['metrics'][metric]['errors'] for r in rows);words=sum(r['metrics'][metric]['reference_tokens'] for r in rows)
  out[metric]={'errors':errors,'reference_tokens':words,'rate':errors/words if words else None}
 return out

def audit(a):
 run=a.read(OUT/'run.json');fp=run['fingerprint']
 a.check(run['status']=='FAILED' and run['inference_requested'] is True and run['new_model_inference'] is True,'failed actual experiment retained')
 a.check(run['verified_workers']==run['completed_workers']==3 and run['planned_workers']==12 and run['inference_completion_verified'] is False,'driver verified3/12, not all12')
 a.check([(b['batch'],b['threads'],b['status'],len(b['cases'])) for b in run['batches']]==[(1,2,'COMPLETE',3),(2,4,'RUNNING',0)],'native second batch failure occurred before driver postprocessing')
 a.check(run['collectEvidence'] is False and run['reference_text_or_counts_staged'] is False and run['order']==[2,4,4,2],'compact QA and frozen design scope')
 manifest=a.read(REPO/'benchmark/eval-perf/manifest.json');specs={c['id']:c for c in manifest['files']}
 protocol=a.read(REPO/'benchmark/eval-perf/protocol.json');a.check(a.sha(REPO/'benchmark/eval-perf/protocol.json')==PROTOCOL and run['protocol']==protocol,'pre-NN fixed protocol')
 receipt=a.read(REPO/'artifacts/test-results/step-05/perf-execution-receipt-v1.json');preflight=a.read(REPO/'artifacts/test-results/step-05/perf-preflight-v2.json')
 a.check(receipt['runner_sha256']==DRIVER and receipt['protocol_sha256']==PROTOCOL and receipt['preflight_sha256']==a.sha(REPO/'artifacts/test-results/step-05/perf-preflight-v2.json'),'before-NN receipt/preflight source pins')
 a.check(preflight['fingerprint']==fp,'actual execution local preflight equality')
 a.check(a.sha(REPO/'tools/run_plan19_perf.py')==DRIVER,'exact frozen reviewed driver')
 aliases=[]
 for relative,expected in fp['code'].items():
  a.check(a.sha(OUT/'source-snapshots'/relative)==expected,('executing source snapshot',relative))
  match=a.sha(REPO/relative)==expected;aliases.append({'path':relative,'current_matches':match})
  a.check(match,('current frozen replay helper/source pin',relative))
 for absolute,expected in fp['local_files'].items():a.check(a.sha(Path(absolute))==expected,('local source/audio/ref/APK/model fingerprint',absolute))
 sys.path.insert(0,str(REPO))
 from tools import run_plan19_perf as driver
 from tools.eval import native_diar_policy as policy,score
 from tools.create_plan19_perf_corpus import source_block,AUDIO_SHA256
 lock=a.read(REPO/'app/src/main/assets/models-lock.json');pins=policy.validate_model_lock(lock)
 a.check(run['native_model_sha256_before']==pins,'all7 actual Android models before inference')
 for role in ['app','test']:a.check(run['installed_apks'][role]['sha256']==fp['apk'][role]['sha256'],'installed/local APK identity')
 source_root=Path('/home/egor/replika-toolchain/eval-audio');block,author,facts,source,original=source_block(REPO/'benchmark/eval',source_root)
 a.check(a.sha(original)==AUDIO_SHA256 and facts['exact_prefix_frames']==842543 and facts['silence_padding_frames']==117457,'unmodified original and six whole clips, including15sample tail')
 a.check(len(author)==6,'same six authored utterances, not independent samples')
 for spec in specs.values():
  reference_path=REPO/'benchmark/eval-perf'/spec['reference'];ref=a.read(reference_path)
  a.check(a.sha(reference_path)==spec['reference_sha256'],'independent author reference SHA')
  expected={'transcript':[{**row,'start_ms':row['start_ms']+i*60000,'end_ms':row['end_ms']+i*60000} for i in range(spec['repeat_blocks']) for row in author]}
  policy.equal(ref,expected,'exact repeated literal author gold')
  audio=Path('/home/egor/replika-toolchain/plan19-perf')/spec['audio'];a.check(a.sha(audio)==spec['audio_sha256'],'original corpus WAV SHA')
  with wave.open(str(audio),'rb') as wav:
   a.check((wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())==(1,2,16000,spec['frames']),'canonical source clock')
   for _ in range(spec['repeat_blocks']):a.check(wav.readframes(960000)==block,'exact byte repeated PCM')
 commands=[strict(line) for line in (OUT/'commands.jsonl').read_text().splitlines() if line];a.sha(OUT/'commands.jsonl')
 instruments=[item for item in commands if 'instrument' in item['argv'] and 'evalRun' in item['argv']]
 a.check(len(instruments)==2,'only first two of four planned instrumentation batches started')
 for item,threads in zip(instruments,[2,4]):
  argv=list(map(str,item['argv']))
  for key,value in {'evalThreads':str(threads),'evalExpectedSpeakers':'-1','evalCpuPlan':'auto_v1','evalAsrPlan':'vad_words_context600','evalDiarPlan':'eres2net_window_v1','evalCollectEvidence':'false'}.items():a.check(argv[argv.index(key)+1]==value,('global instrumentation policy',threads,key))
 a.check(datetime.fromisoformat(protocol['frozen_utc'])<datetime.fromisoformat(receipt['at'])<datetime.fromisoformat(instruments[0]['at']),'protocol and receipt frozen before first NN')
 seen_work=set();seen_recordings=set();rows=[];batches=[];non_json=[];totals=Counter();clock_steps=[]
 config=a.read(REPO/'configs/eval/c2-window-selected-full.json')
 for number,threads,expected_ids in [(1,2,IDS),(2,4,IDS[:2])]:
  folder=OUT/f'batch-{number:02d}-threads{threads}';report=a.read(folder/'instrumentation-report.json');stored=run['batches'][number-1]
  a.check(report['status']==('COMPLETE' if number==1 else 'FAILED') and report['collectEvidence'] is False and report['newModelInference'] is True,'actual native batch terminal scope')
  transient,paired=driver.execution_config(config,threads);policy.validate_native_diar_policy(transient,report,paired,cpu_plan='auto_v1',threads=threads)
  a.check([r['id'] for r in report['cases']]==expected_ids and report['run']==stored['run'],'native completed case coverage/order')
  pid=report['processId'];a.check(type(pid) is int and pid>0 and all(r['processId']==pid for r in report['cases']),'same instrumented process within each observed triplet/prefix')
  staged=a.read(folder/'batch.json');a.check(set(staged)=={'schema_version','run','cases'} and staged['run']==report['run'] and [r['id'] for r in staged['cases']]==IDS,'all3 only audio/id/SHA staged in fixed order')
  for entry,cid in zip(staged['cases'],IDS):a.check(set(entry)=={'id','audio','sha256'} and entry['audio']=='audio/'+cid+'.wav' and entry['sha256']==specs[cid]['audio_sha256'],'no gold text or K on device')
  log=(folder/'instrumentation.log').read_text();a.sha(folder/'instrumentation.log');a.sha(folder/'instrumentation.stderr')
  if number==1:a.check(re.search(r'OK \(1 tests?\)',log) is not None and 'FAILURES!!!' not in log,'batch1 actual JUnit success')
  else:a.check('FAILURES!!!' in log and 'TimeoutCancellationException' in log and '1200000 ms' in log and report['cancellationRequested'] is True,'batch2 per-case1200s timeout and own cancellation request, not success')
  batch_rows=[]
  for item in report['cases']:
   cid=item['id'];spec=specs[cid];native=a.read(folder/f'{cid}.case.json');diag=a.read(folder/f'{cid}.diagnostics.json');hyp=a.read(folder/f'{cid}.hypothesis.json')
   policy.equal(native,item,'native full report/case copy')
   counts=driver.validate_compact_case(spec,native,diag,hyp,config,threads)
   a.check(native['workId'] not in seen_work and native['recordingId'] not in seen_recordings,'fresh actual succeeded WorkInfo UUIDs');seen_work.add(native['workId']);seen_recordings.add(native['recordingId'])
   ref_path=REPO/'benchmark/eval-perf'/spec['reference'];ref=a.read(ref_path)
   fresh=score.score(ref,hyp,native['duration_ms'],processing_ms=native['processing_ms'])
   turns=policy.turns_from_json(diag['diarizationTurns'],native['duration_ms'])
   turn_rows=[{'speaker_id':str(t.speaker),'start_ms':t.start_ms,'end_ms':t.end_ms,'text':''} for t in turns]
   for collar in [0,250]:fresh[f'native_der_collar_{collar}ms']=score.der(ref['transcript'],turn_rows,native['duration_ms'],collar_ms=collar)
   fresh['native_speaker_count']=len({t.speaker for t in turns})
   if number==1:
    saved_metric=a.read(folder/f'{cid}.metrics.json');saved=next(r for r in stored['cases'] if r['id']==cid)
    policy.equal(fresh,saved_metric,'fresh full independent scores vs saved metrics')
    a.check(saved['metrics']==saved_metric and saved['compact_evidence']==counts and saved['duration_ms']==native['duration_ms'] and saved['processing_ms']==native['processing_ms'],'driver verified case copies')
    hashes={suffix:a.sha(folder/f'{cid}.{suffix}.json') for suffix in ['reference','hypothesis','diagnostics','case','metrics']}
    a.check(hashes==saved['evidence_sha256'] and a.sha(folder/f'{cid}.reference.json')==spec['reference_sha256'],'driver evidence/reference SHA')
   else:
    a.check(not (folder/f'{cid}.metrics.json').exists() and not (folder/f'{cid}.reference.json').exists(),'new audit rescores completed native-only prefix without altering raw source')
    hashes={suffix:a.sha(folder/f'{cid}.{suffix}.json') for suffix in ['hypothesis','diagnostics','case']};hashes['host_reference']=a.sha(ref_path)
   stages,telemetry=diag['stagesMs'],diag['telemetry']
   a.check(stages==telemetry['stagesMs'] and all(type(v) is int and v>=0 for v in stages.values()),'actual nonnegative stage clocks')
   a.check(type(telemetry['observedMaxPssKb']) is int and telemetry['observedMaxPssKb']>0 and 'not continuous' in telemetry['memoryScope'],'stage observed PSS, not continuous peak')
   a.check(type(telemetry['thermalStatus']) is int and type(telemetry.get('thermalStatusAvailable')) is bool,'actual thermal availability distinguishes unknown')
   a.check(math.isclose(fresh['rtf'],native['processing_ms']/native['duration_ms'],rel_tol=0,abs_tol=1e-12),'actual Worker elapsed RTF')
   result={'batch':number,'threads':threads,'id':cid,'duration_ms':native['duration_ms'],'processing_ms':native['processing_ms'],'metrics':fresh,'compact_evidence':counts,'work_id':native['workId'],'recording_id':native['recordingId'],'process_id':pid,'work_manager_state':native['workManagerState'],'stages_ms':stages,'telemetry':telemetry,'evidence_sha256':hashes,'driver_verified':number==1,'independently_verified':True}
   rows.append(result);batch_rows.append(result);totals.update(workers=1,audio_ms=native['duration_ms'],processing_ms=native['processing_ms'],embedding_windows=counts['measured_embedding_windows'],asr_chunks=counts['asr_chunks'],reported_tokens=counts['reported_tokens'],reported_words=counts['reported_words'])
   print(json.dumps({'audited_saved_case':cid,'batch':number,'threads':threads,'raw_errors':fresh['wer_raw']['errors'],'words':fresh['wer_raw']['reference_tokens']}),flush=True)
  if number==2:
   for suffix in ['case','diagnostics','hypothesis']:
    path=folder/f'perf-10m.{suffix}.json';raw=path.read_bytes();a.sha(path)
    try:strict(raw)
    except (ValueError,UnicodeDecodeError):pass
    else:raise AssertionError('Failed10m missing output must not be scored as JSON')
    a.check(raw.startswith(b'cat: ') and b'No such file or directory' in raw,'preserved failed pull cat error, not fake JSON')
    non_json.append({'path':str(path.relative_to(REPO)),'sha256':a.sha(path),'bytes':len(raw),'classification':'CAT_NO_SUCH_FILE_NOT_JSON','preview':raw.decode('utf-8','replace').strip()})
  samples=[strict(line) for line in (folder/'samples.jsonl').read_text().splitlines() if line];a.sha(folder/'samples.jsonl')
  sample_pids=set();max_rss=[];max_pss=[]
  for index,sample in enumerate(samples):
   a.check(type(sample['monotonic_seconds']) in (int,float) and math.isfinite(sample['monotonic_seconds']),'finite sample clock')
   if index:
    before=samples[index-1];a.check(sample['monotonic_seconds']>=before['monotonic_seconds'],'nondecreasing sampled monotonic clock')
    wall=(datetime.fromisoformat(sample['at'])-datetime.fromisoformat(before['at'])).total_seconds();mono=sample['monotonic_seconds']-before['monotonic_seconds']
    if abs(wall-mono)>1:clock_steps.append({'batch':number,'index':index,'wall_minus_monotonic_seconds':wall-mono,'before_at':before['at'],'after_at':sample['at']})
   if sample.get('pids'):sample_pids.add(sample['pids'])
   for field,suffix,pattern,values in [('rss_kb','proc',rb'^VmRSS:\s+(\d+)\s+kB',max_rss),('pss_kb','meminfo',rb'TOTAL PSS:\s*(\d+)',max_pss)]:
    path=folder/f'sample-{index:05d}-{suffix}.txt'
    if path.exists():
     a.sha(path);match=re.search(pattern,path.read_bytes(),re.M);value=int(match[1]) if match else None
     if field in sample:a.check(sample[field]==value,('independent raw resource parse',number,index,field))
    if sample.get(field) is not None:values.append(sample[field])
   thermal=folder/f'sample-{index:05d}-thermal.txt'
   if thermal.exists():a.sha(thermal)
  stage_log=folder/'stage-pss-logcat.txt';a.sha(stage_log);a.sha(folder/'stage-pss-logcat.stderr');events=[]
  for line in stage_log.read_text(errors='replace').splitlines():
   start=line.find('{')
   if start<0:continue
   try:event=strict(line[start:])
   except (ValueError,UnicodeDecodeError):continue
   if isinstance(event,dict):events.append(event)
  linked={r['telemetry']['run']:sum(e.get('run')==r['telemetry']['run'] for e in events) for r in batch_rows}
  a.check(all(value>0 for value in linked.values()),'stage events linked by actual telemetry run UUID')
  batches.append({'batch':number,'threads':threads,'native_status':report['status'],'native_completed_cases':len(batch_rows),'driver_verified_cases':len(stored['cases']),'instrumented_process_id':pid,'summary':weighted(batch_rows),'resource_snapshots':{'samples':len(samples),'errors':sum('error' in s for s in samples),'observed_pids':sorted(sample_pids),'maximum_observed_rss_kb':max(max_rss,default=None),'maximum_observed_pss_kb':max(max_pss,default=None),'scope':'periodic batch observations including incomplete work; not per-case or continuous peak'},'stage_log_events_by_completed_run':linked,'failed_record_id':report.get('failedRecordId')})
 a.check(len(rows)==len(seen_work)==len(seen_recordings)==5 and sum(r['driver_verified'] for r in rows)==3,'five succeeded native Workers, only three recorded as verified by failed driver')
 csv_path=OUT/'results.csv';a.sha(csv_path);csv_rows=list(csv.DictReader(io.StringIO(csv_path.read_text())))
 a.check(len(csv_rows)==3 and [r['case'] for r in csv_rows]==IDS and all(r['batch']=='1' for r in csv_rows),'original CSV retains exactly three driver verified rows')
 for item,row in zip(csv_rows,rows[:3]):a.check(int(item['processing_ms'])==row['processing_ms'] and int(item['raw_errors'])==row['metrics']['wer_raw']['errors'],'original CSV agrees with rescore')
 a.check(run['screen_power']['restored_exactly'] is True and run['screen_power']['original']==run['screen_power']['restored'],'original stay-on setting restored')
 paired=[]
 for cid in IDS[:2]:
  two=next(r for r in rows if r['threads']==2 and r['id']==cid);four=next(r for r in rows if r['threads']==4 and r['id']==cid)
  paired.append({'id':cid,'threads2_processing_ms':two['processing_ms'],'threads4_processing_ms':four['processing_ms'],'observed_threads4_over_threads2_ratio':four['processing_ms']/two['processing_ms'],'raw_errors_threads2':two['metrics']['wer_raw']['errors'],'raw_errors_threads4':four['metrics']['wer_raw']['errors'],'scope':'Only first directional short-file observations; full/reverse pairs and 4-thread10m missing, no causal speed conclusion'})
 a.unchanged()
 return {'status':'PASS_PARTIAL_EVIDENCE','experiment_status':'FAILED','data_integrity_for_completed_five':'PASS','checks':a.checks,'native_completed_workers':5,'driver_verified_workers':3,'planned_workers':12,'inference_completion_verified':False,'full_design_completed':False,'not_started_batches':[3,4],'failed_case':{'batch':2,'threads':4,'id':'perf-10m','timeout_ms':1200000,'result':'NO_COMPLETED_OUTPUTS','worker_final_state_not_claimed':True,'partial_cancellation_requested':True},'post_run_native_model_hashes_available':('native_model_sha256_after' in run),'actual_totals_of_completed_five':dict(totals),'batches':batches,'rows':rows,'preserved_non_json_failed_pull_artifacts':non_json,'incomplete_descriptive_comparisons':paired,'current_source_aliases':aliases,'source_sha256':a.hashes,'host_wall_clock_steps':clock_steps,'timing_scope':'Worker elapsed/SystemClock times, not host ISO deltas; snapshots include interrupted case activity','full_token_vector_replay':False,'neural_inference_by_auditor':False,'speed_causal_accepted':False,'arm_phone_accepted':False,'whole_step5_accepted':False,'scope':'Five saved completed outputs only. Twelve-worker 2/4/4/2 experiment failed at batch2 4-thread10m timeout. Related repeated author utterance corpus, not independent/natural dialogue or word-time gold. No missing case is zero-scored; no whole12 PASS or speed/ARM acceptance.'}

def main():
 if OUTPUT.exists() or OUTPUT.with_suffix('.md').exists():raise FileExistsError('Fresh audit outputs only')
 a=Audit();result=audit(a);source=Path(__file__).read_bytes();digest=hashlib.sha256(source).hexdigest();snap=REPO/'artifacts/test-results/step-05/runner-snapshots'/(digest+'-perf-partial-audit.py')
 if snap.exists():
  if snap.read_bytes()!=source:raise ValueError('Source snapshot collision')
 else:
  with snap.open('xb') as f:f.write(source)
 result.update(schema_version=1,at=datetime.now(timezone.utc).isoformat(),auditor_source_sha256=digest,auditor_source_snapshot=str(snap.relative_to(REPO)))
 with OUTPUT.open('x',encoding='utf-8') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
 lines=['Частичный независимый аудит: PASS_PARTIAL_EVIDENCE; исходный эксперимент FAILED.',f"Проверено 5 завершённых native Workers; драйвер успел подтвердить 3 из 12. Проверок: {result['checks']}.",'','| Batch | Потоки | Кейс | Worker ms | RTF наблюдаемый | Raw WER | Norm WER | Native DER0 | K |','| --- | ---: | --- | ---: | ---: | --- | --- | ---: | ---: |']
 for row in result['rows']:
  m=row['metrics'];lines.append(f"| {row['batch']} | {row['threads']} | {row['id']} | {row['processing_ms']} | {m['rtf']:.6f} | {m['wer_raw']['errors']}/{m['wer_raw']['reference_tokens']} | {m['wer_normalized']['errors']}/{m['wer_normalized']['reference_tokens']} | {m['native_der_collar_0ms']['rate']:.6f} | {m['native_speaker_count']} |")
 lines+=['','Batch2/threads4/10min превысил per-case timeout 1200000 ms. Три сохранённых файла с расширением JSON содержат cat: No such file, не являются гипотезами/диагностикой и не оценивались. Окончательное состояние этого Worker этим аудитом не установлено.','Batch3/4 не стартовали; полный и обратный A/B не завершены. Нет вывода об ускорении, ARM/телефоне или непрерывном пике RAM. QAfalse: полные токены/векторы не собирались и не воспроизводились. После прерванного эксперимента нет финального remote model hash sweep; исходные model pins/валидация завершённых Workers сохранены.','Исходные JSON/CSV/logs не изменены. Дополнительные метрики двух native-only результатов находятся только в новом audit JSON.']
 with OUTPUT.with_suffix('.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
 print(json.dumps({'status':result['status'],'checks':result['checks'],'native_completed_workers':5,'driver_verified_workers':3,'totals':result['actual_totals_of_completed_five'],'audit_source_sha256':digest}),flush=True)
if __name__=='__main__':main()
