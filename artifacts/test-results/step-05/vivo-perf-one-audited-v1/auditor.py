#!/usr/bin/env python3
"""Saved-only terminal ARM group audit; no ADB, subprocess, model loading or raw export."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict
import csv, hashlib, io, json, math, re, shutil, sys, uuid, wave
sys.dont_write_bytecode=True
REPO=Path('/mnt/d/ReplikaAndroid/ReplikaAndroid')
RAW=Path('/home/egor/replika-toolchain/evidence/step05-vivo-perf-one-PRIVATE-v1')
OUT=REPO/'artifacts/test-results/step-05/vivo-perf-one-audited-v1'
sys.path.insert(0,str(REPO))
from tools import run_plan19_perf as driver
from tools.eval import native_diar_policy as P, score
IDS=['perf-01m','perf-03m','perf-10m']
CPU={'plan':'auto_v1','requestedThreads':0,'availableCores':8,'asrThreads':4,'diarizationThreads':4,'refinementThreads':4,'diarizationPinned':False,'refinementPinned':False}
HASHES={}; CHECKS=0
def check(value,label):
 global CHECKS
 CHECKS+=1
 if not value:raise AssertionError(label)
def sha(path):
 path=Path(path).resolve()
 if path not in HASHES:
  with path.open('rb') as f:HASHES[path]=hashlib.file_digest(f,'sha256').hexdigest()
 return HASHES[path]
def read(path):sha(path);return P.strict_json(Path(path).read_bytes())
def equal(actual,expected,label):P.equal(actual,expected,label);check(True,label)
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
 check(not OUT.exists(),'fresh public export only')
 run=read(RAW/'run.json')
 check(run['status']=='COMPLETE' and run['inference_completion_verified'] is True and run['new_model_inference'] is True,'terminal complete actual3; never audit live as final')
 check(run['planned_workers']==run['verified_workers']==run['completed_workers']==3 and run['inference_may_still_be_running'] is False,'three verified Workers only')
 for path in RAW.iterdir():
  if path.is_file():sha(path)
 protocol=read(RAW/'protocol.json');receipt=read(REPO/'artifacts/test-results/step-05/vivo-perf-one-execution-receipt-v1.json');fp=run['fingerprint']
 oldpath=REPO/'artifacts/test-results/step-05/perf-2-4-4-2-v1/run.json';old=read(oldpath);oldaudit=read(oldpath.parent/'independent-partial-audit.json')
 check(old['status']=='FAILED' and old['inference_completion_verified'] is False and sha(oldpath)==oldaudit['source_sha256'][str(oldpath)],'previous FAILED x86 result stays exactly preserved')
 equal(protocol['cpu_policy'],CPU,'frozen requested0 actual4 policy');check(protocol['case_order']==IDS and protocol['collectEvidence'] is False,'frozen complete related-repeat triplet')
 check(sha(RAW/'protocol.json')==receipt['protocol_sha256'] and sha(RAW/'procedure.py')==receipt['procedure_sha256'],'actual frozen executing procedure and protocol')
 equal(protocol,read(REPO/'artifacts/test-results/step-05/vivo-perf-one-procedure-v1/protocol.json'),'immutable public/private protocol')
 for path,expected in fp['code'].items():check(sha(REPO/path)==expected,('execution source pin',path))
 for path,expected in fp['local_files'].items():check(sha(path)==expected,('local APK/model/audio/reference pin',Path(path).name))
 for path,expected in protocol['source_sha256'].items():check(sha(REPO/path)==expected,('explicit procedure source pin',path))
 lock=read(REPO/'app/src/main/assets/models-lock.json');pins=P.validate_model_lock(lock)
 equal(run['model_sha256_before'],pins,'seven actual models before');equal(run['model_sha256_after'],pins,'seven actual models after')
 postpath=REPO/'artifacts/test-results/step-05/vivo-prior-data-preservation-after-long3-v1.json';post=read(postpath)
 for role,expected in protocol['apk_sha256'].items():check(run['installed_apks'][role]['sha256']==fp['apk'][role]['sha256']==expected==post['installed_apks_after_long3']['ru.replika.offline'+('.test' if role=='test' else '')],('actual installed/local APK before and root after receipt',role))
 commands=[P.strict_json(x) for x in (RAW/'commands.jsonl').read_text().splitlines() if x]
 instruments=[x for x in commands if 'instrument' in x['argv'] and 'evalRun' in x['argv']];check(len(instruments)==1,'one instrumentation group, not prior12 design')
 argv=instruments[0]['argv']
 for k,v in {'evalThreads':'0','evalExpectedSpeakers':'-1','evalCpuPlan':'auto_v1','evalAsrPlan':P.ASR_PLAN,'evalDiarPlan':P.PLAN,'evalCollectEvidence':'false'}.items():check(argv[argv.index(k)+1]==v,('actual instrumentation option',k))
 check(datetime.fromisoformat(protocol['frozen_utc'])<datetime.fromisoformat(receipt['created_utc'])<datetime.fromisoformat(instruments[0]['at']),'protocol+receipt before actual group NN')
 check(all(x['argv'][:3]==[argv[0],'-s',run['serial']] for x in commands),'explicit private serial for every command')
 check(not any(any(v in x['argv'] for v in ('install','force-stop','settings','stayon','airplane-mode','svc')) for x in commands),'no explicit install/system-setting/network/force-stop commands')
 check(run['phone_settings_changed'] is False and run['reference_text_or_counts_staged'] is False,'phone data/network contract')
 report=read(RAW/'report.json');equal(report['cpuPolicy'],CPU,'actual native report CPU')
 check(report['status']=='COMPLETE' and report['collectEvidence'] is False and report['newModelInference'] is True and [x['id'] for x in report['cases']]==IDS,'complete3 native report')
 check(report['run']==run['remote_run'] and type(report['processId']) is int and report['processId']>0 and report['api']==37 and 'arm64-v8a' in report['supportedAbis'],'actual ARM/API37/process identity')
 batch=read(RAW/'batch.json');check(set(batch)=={'schema_version','run','cases'} and batch['run']==report['run'] and [x['id'] for x in batch['cases']]==IDS,'exact audio-only staged batch')
 manifest=read(REPO/'benchmark/eval-perf/manifest.json');specs={x['id']:x for x in manifest['files']};config=read(REPO/'configs/eval/c2-window-selected-full.json');transient,paired=driver.execution_config(config,4)
 P.validate_native_diar_policy(transient,report,paired,cpu_plan='auto_v1',threads=4,requested_threads=0)
 log=(RAW/'instrumentation.log').read_text();check(run['instrumentation_exit_code']==0 and re.search(r'OK \(1 tests?\)',log) and not re.search(r'FAILURES!!!|INSTRUMENTATION_FAILED|Process crashed',log),'actual JUnit completion')
 rows=[];totals=Counter();work=set();recordings=set();export={}
 for index,cid in enumerate(IDS):
  spec=specs[cid];n=read(RAW/f'{cid}.case.json');d=read(RAW/f'{cid}.diagnostics.json');h=read(RAW/f'{cid}.hypothesis.json');ref=read(RAW/f'{cid}.reference.json');saved=run['batches'][0]['cases'][index]
  equal(n,report['cases'][index],'full case/report copy');equal(d['cpuPolicy'],CPU,'actual case CPU0->4');P.validate_native_diar_policy(transient,d,paired,cpu_plan='auto_v1',threads=4,requested_threads=0)
  check(n['id']==cid and n['status']=='COMPLETE' and n['workManagerState']=='SUCCEEDED' and n['newModelInference'] is True and n['collectEvidence'] is False and n['processId']==report['processId'],'actual succeeded own Worker')
  check(str(uuid.UUID(n['workId']))==n['workId'] and n['workId'] not in work and n['recordingId'].startswith('qa-evaluation-') and str(uuid.UUID(n['recordingId'][14:]))==n['recordingId'][14:] and n['recordingId'] not in recordings,'fresh canonical own UUIDs');work.add(n['workId']);recordings.add(n['recordingId'])
  duration,ms=n['duration_ms'],n['processing_ms'];check(type(duration)is int and abs(duration-spec['duration_ms'])<=1 and type(ms)is int and ms>0 and d['audioMs']==duration and d['totalMs']==ms,'actual sample/elapsed clock')
  equal(batch['cases'][index],{'id':cid,'audio':'audio/'+cid+'.wav','sha256':spec['audio_sha256']},'no gold/counts staged')
  check(n['audio_sha256']==spec['audio_sha256'] and sha(RAW/f'{cid}.reference.json')==spec['reference_sha256'],'actual input+independent gold pins')
  audio=Path('/home/egor/replika-toolchain/plan19-perf')/spec['audio'];check(sha(audio)==spec['audio_sha256'],'source WAV SHA')
  with wave.open(str(audio),'rb') as wav:
   check((wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())==(1,2,16000,spec['frames']),'canonical repeated source clock');block=wav.readframes(960000)
   for _ in range(spec['repeat_blocks']-1):check(wav.readframes(960000)==block,'exact related60s repeat bytes')
  adapter=d['diarizationRefinement'];check(d['diarizationRefinementAccepted'] is True and adapter['status'] in ('SUPPORTED','PARTIAL_TEMPORAL'),'supported actual C2 computation')
  for k,v in {'cpuPlan':'auto_v1','embeddingThreads':4,'algorithm':'window-overcluster-v1','nativeResourcesReleasedBeforeRefiner':True,'originalPcm':True,'embeddingInferenceCompleted':True,'computationalSupport':True,'retainedNativeModelCache':False,'config':P.WINDOW_CONFIG}.items():equal(adapter.get(k),v,'adapter.'+k)
  equal(adapter,P.compact_refiner_diagnostic(adapter),'no retained full vectors in compact adapter');counts=d['diarizationEmbeddingCounts'];count=counts['measuredWindows'];check(type(count)is int and count>0,'actual clean embedding inference')
  for k,v in {'extractorLoads':1,'embeddingDimension':512,**{k:count for k in ('plannedWindows','readWindows','createdStreams','releasedStreams','computeAttempts','embeddingForwardCalls')}}.items():equal(counts.get(k),v,'balanced window resources.'+k)
  check(d['wordEvidenceRequested'] is False and d['wordEvidenceBytes']==0 and d['wordEvidenceTruncated'] is False and not any(k.startswith('diarizationEvidence') for k in d),'QA=false no full sidecars')
  parts=d['asrSlices'];previous=0;check(parts and d['wordProcessedChunks']==len(parts),'actual ASR chunks')
  for part in parts:
   a,b=part['startMs'],part['endMs'];check(type(a)is int and type(b)is int and previous<=a<b<=duration and b-a<=20000,'nonoverlap actual chunk clock');previous=b
   check(part['wordEvidenceIncluded'] is False and part['wordEvidenceOmittedReason']=='not_requested' and part['frameStrideMs']==40 and not any(k in part for k in ('tokens','timestamps','words')),'real compact summaries, no fabricated full replay')
   check(type(part['text'])is str and type(part['blank'])is bool and part['blank']==(not part['text'].strip()) and all(type(part[k])is int and part[k]>=0 for k in ('tokenCount','timestampCount','wordCount')),'actual compact text/counts')
  check(' '.join(x.text for x in score._document(h,duration)).split()==' '.join(x['text'] for x in parts).split(),'actual ASR/Jury lexical sequence preserved')
  metrics=score.score(ref,h,duration,processing_ms=ms);turns=P.turns_from_json(d['diarizationTurns'],duration);turnrows=[{'speaker_id':str(t.speaker),'start_ms':t.start_ms,'end_ms':t.end_ms,'text':''} for t in turns]
  for collar in (0,250):metrics[f'native_der_collar_{collar}ms']=score.der(ref['transcript'],turnrows,duration,collar_ms=collar)
  metrics['native_speaker_count']=len({t.speaker for t in turns});equal(metrics,read(RAW/f'{cid}.metrics.json'),'fresh independent full scores');equal(metrics,saved['metrics'],'driver saved metrics')
  compact={'asr_chunks':len(parts),'reported_tokens':sum(x['tokenCount'] for x in parts),'reported_words':sum(x['wordCount'] for x in parts),'measured_embedding_windows':count,'resources_balanced':True,'full_token_vector_replay_performed':False};equal(compact,saved['compact_evidence'],'independent compact resource totals')
  telemetry=d['telemetry'];equal(d['stagesMs'],telemetry['stagesMs'],'stage clock copies');check(all(type(v)is int and v>=0 for v in d['stagesMs'].values()) and type(telemetry['observedMaxPssKb'])is int and telemetry['observedMaxPssKb']>0 and 'not continuous' in telemetry['memoryScope'],'actual stage snapshot semantics')
  check(type(telemetry['thermalStatus'])is int and type(telemetry['thermalStatusAvailable'])is bool and type(telemetry['thermalListenerRegistered'])is bool,'actual thermal availability, no unknown=>safe substitution')
  rows.append({'id':cid,'duration_ms':duration,'processing_ms':ms,'observed_rtf':ms/duration,'metrics':metrics,'compact_evidence':compact,'cpu_policy':CPU,'work_id':n['workId'],'recording_id':n['recordingId'],'process_id':n['processId'],'work_manager_state':n['workManagerState'],'stages_ms':d['stagesMs'],'telemetry':telemetry})
  totals.update(workers=1,audio_ms=duration,processing_ms=ms,embedding_windows=count,asr_chunks=len(parts),reported_tokens=compact['reported_tokens'],reported_words=compact['reported_words']);allow=['runtime','backend','sampleRate','audioMs','totalMs','threads','vadThreads','cpuPlan','cpuPolicy','asrPlan','asrPolicy','diarizationPlanRequested','diarizationPlan','diarizationPolicy','nativeDiarizationTurns','stableDiarizationTurns','diarizationTurns','refinedDiarizationTurns','diarizationRefinement','diarizationRefinementAccepted','diarizationEmbeddingCounts','asrSlices','wordProcessedChunks','wordFallbackChunks','wordEvidenceRequested','wordEvidenceBytes','wordEvidenceTruncated','maxAsrSegmentMs','stagesMs','telemetry'];export[cid]={'hypothesis.json':h,'reference.json':ref,'metrics.json':metrics,'diagnostics.json':{k:d[k] for k in allow if k in d}}
 equal(driver.batch_summary(rows),run['summary'],'independent weighted group summary')
 samples=[P.strict_json(x) for x in (RAW/'samples.jsonl').read_text().splitlines() if x];rss=[];pss=[];temps=defaultdict(list);own=0
 for i,s in enumerate(samples):
  if 'process_id' not in s:continue
  check(s['process_id']==report['processId'],'only actual instrumented PID sampled');own+=1;proc=(RAW/f'sample-{i:05d}-proc.txt').read_bytes();match=re.search(rb'^Pid:\s+(\d+)',proc,re.M);check(match and int(match[1])==report['processId'],'raw /proc PID binding')
  match=re.search(rb'^VmRSS:\s+(\d+)\s+kB',proc,re.M);value=int(match[1]) if match else None;equal(s.get('rss_kb'),value,'independent raw RSS parse')
  if value is not None:rss.append(value)
  mem=(RAW/f'sample-{i:05d}-meminfo.txt').read_text();match=re.search(r'MEMINFO in pid (\d+) \[ru\.replika\.offline\]',mem);check(match and int(match[1])==report['processId'],'raw meminfo own PID/package binding');match=re.search(r'TOTAL PSS:\s*(\d+)',mem)
  if match:pss.append(int(match[1]))
  thermal=(RAW/f'sample-{i:05d}-thermal.txt').read_text()
  for value,kind in re.findall(r'Temperature\{mValue=([-+0-9.eE]+), mType=(-?\d+)',thermal):
   value=float(value)
   if math.isfinite(value):temps[int(kind)].append(value)
 events=[];ignored=0;runs={r['telemetry']['run']:r for r in rows}
 for line in (RAW/'stage-pss-logcat.txt').read_text(errors='replace').splitlines():
  match=re.match(r'^\s*[0-9.]+\s+(\d+)\s+\d+\s+[A-Z]\s+ReplikaPerf\s*:\s*(\{.*\})\s*$',line)
  if not match:continue
  event=P.strict_json(match[2])
  if event.get('run') not in runs:ignored+=1;continue
  check(int(match[1])==report['processId'],'stage log own PID+telemetry UUID binding');events.append(event)
 for row in rows:
  selected=[x for x in events if x.get('run')==row['telemetry']['run']];cfg=[x for x in selected if x['stage']=='config'];observed=[x['pssKb'] for x in selected if 'pssKb' in x]
  if selected:check(len(cfg)==1,'one stage policy event');equal(cfg[0]['cpuPolicy'],CPU,'stage log exact actual auto CPU');check(observed and max(observed)>=row['telemetry']['observedMaxPssKb'],'stage observed PSS consistent with own-run raw log')
  row['stage_log']={'matched_events':len(selected),'maximum_observed_pss_kb':max(observed,default=None),'scope':'Stage logcat empty: no independent log reconstruction; actual diagnostics telemetry remains available' if not selected else 'Own-PID/telemetry-UUID matched events'}
 csvrows=list(csv.DictReader(io.StringIO((RAW/'results.csv').read_text())));check([x['case'] for x in csvrows]==IDS,'complete actual3 CSV')
 for cr,row in zip(csvrows,rows):check(int(cr['processing_ms'])==row['processing_ms'] and int(cr['raw_errors'])==row['metrics']['wer_raw']['errors'],'actual CSV/scoring copies')
 for path,expected in list(HASHES.items()):
  with path.open('rb') as f:check(hashlib.file_digest(f,'sha256').hexdigest()==expected,('immutable throughout audit',path.name))
 result={'schema_version':1,'status':'PASS_SAVED_COMPLETE_THREE','created_utc':datetime.now(timezone.utc).isoformat(),'checks':CHECKS,'actual_complete_workers':3,'actual_cpu_policy':CPU,'device':protocol['device'],'summary':driver.batch_summary(rows),'actual_totals':dict(totals),'rows':rows,'resource_snapshots':{'samples':len(samples),'own_pid_samples':own,'sample_errors':sum('error' in x for x in samples),'maximum_observed_rss_kb':max(rss,default=None),'maximum_observed_pss_kb':max(pss,default=None),'thermal_numeric_ranges_by_type':{str(k):{'min':min(v),'max':max(v),'entries':len(v)} for k,v in temps.items()},'stage_events':len(events),'ignored_other_telemetry_runs':ignored,'scope':'10-second own-PID RSS/PSS snapshots and stage-boundary PSS; not continuous peaks. Thermal numbers are provider dumpsys cached/current entries by numeric type, may repeat; not core-temperature attribution.'},'source_pins':{'protocol_sha256':sha(RAW/'protocol.json'),'procedure_sha256':sha(RAW/'procedure.py'),'execution_receipt_sha256':sha(REPO/'artifacts/test-results/step-05/vivo-perf-one-execution-receipt-v1.json'),'code':fp['code'],'installed_apk_sha256':{k:v['sha256'] for k,v in run['installed_apks'].items()},'model_sha256_before':run['model_sha256_before'],'model_sha256_after':run['model_sha256_after'],'private_raw_file_sha256':{p.name:v for p,v in HASHES.items() if p.parent==RAW}},'phone_settings_changed':False,'full_token_vector_replay':False,'neural_inference_by_auditor':False,'prior_failed_x86_experiment_unchanged':True,'causal_speed_comparison_accepted':False,'natural_or_independent_quality_accepted':False,'whole_step5_accepted':False,'scope':'One completed physical ARM/API37/4KiB automatic0->4 sequential related-repeat 1/3/10-minute group. Worker elapsed times are descriptive under uncontrolled caches, heat, charging, instrumentation/sampling. Not the failed x86 12-Worker comparison, not natural dialogue or independent word-time gold; no full QA token/vector replay or phone-data preservation claim by this auditor.'}
 result['installed_apk_hash_scope']='Actual installed app/test SHA before group and root separate sanitized post-group receipt both match local pinned APKs; all seven actual model SHA are checked by driver both before and after. No additional ADB by auditor.'
 result['root_post_group_preservation_receipt']={'path':str(postpath.relative_to(REPO)),'sha256':sha(postpath),'status':post['status'],'all_prior_table_rows_exact':post['all_prior_table_rows_exact'],'prior_table_count':post['prior_table_count'],'app_process_absent':post['app_process_absent'],'scope':'Root receipt verified/pinned; private user database not read by this auditor.'}
 result['stage_logcat']={'bytes':(RAW/'stage-pss-logcat.txt').stat().st_size,'parsed_own_run_events':len(events),'scope':'Logger enabled but saved file empty; reason not established. Stage timing/PSS/thermal fields are actual diagnostic snapshots; no independent stage-log proof claimed.'}
 result['stage_timing_scope']='Timers are nested: diarizationMs includes native SD sub-stages; asrMs includes nested work/cooling and must not be added to its sub-stages or global thermalWaitMs. Worker total/RTF includes actual cooling; no additive decomposition or causal cross-platform/CPU speed claim.'
 result['prior_failed_x86_run_sha256']=sha(oldpath)
 result['auditor_sha256']=sha(__file__);encoded=json.dumps(result,ensure_ascii=False);check(run['serial'] not in encoded,'no private serial in public derived report')
 OUT.mkdir(parents=True)
 for cid,files in export.items():
  folder=OUT/cid;folder.mkdir()
  for name,value in files.items():write(folder/name,value)
 write(OUT/'independent-audit.json',result);shutil.copyfile(__file__,OUT/'auditor.py')
 text=['# ARM: сохранённый замер 1/3/10 минут','',f'Независимый saved-only аудит: {CHECKS} проверок PASS. Три настоящих Worker SUCCEEDED, один PID, CPU automatic0→4. Полные токены/векторы не собирались и не воспроизводились.','','| Файл | Аудио, мс | Worker, мс | RTF | Raw WER | Stage PSS, KiB |','| --- | ---: | ---: | ---: | --- | ---: |']
 for row in rows:text.append(f"| {row['id']} | {row['duration_ms']} | {row['processing_ms']} | {row['observed_rtf']:.6f} | {row['metrics']['wer_raw']['errors']}/{row['metrics']['wer_raw']['reference_tokens']} | {row['telemetry']['observedMaxPssKb']} |")
 text+=['',f"10мин: native SD {rows[2]['stages_ms']['diarizationInferenceMs']}мс; refiner {rows[2]['stages_ms']['diarizationRefinementMs']}мс; ASR inference {rows[2]['stages_ms']['asrInferenceMs']}мс; фактическое ожидание охлаждения {rows[2]['stages_ms']['thermalWaitMs']}мс включено в полный Worker. Таймеры вложенные: asrMs и thermalWaitMs нельзя складывать с подстадиями как независимые слагаемые.",'','Stage-logcat пуст; причина не установлена. PSS/thermal стадий взяты из actual diagnostic telemetry, не восстановлены из отсутствующего журнала. RSS/PSS/thermal — отдельные снимки, не непрерывные пики. Корпус — связанные повторы знакомых авторских реплик. Это описательные результаты одного ARM-прогона; причинное сравнение потоков/платформ, естественный диалог и весь пункт 5 не приняты. Старый FAILED x86-прогон не изменён. Serial, сырые команды, dumpsys, /proc и сенсоры остаются приватными. Сохранность прежних пользовательских таблиц и APK после группы подтверждена отдельным pinned root receipt; приватную БД аудитор не читал.']
 (OUT/'independent-audit.md').write_text('\n'.join(text)+'\n');print(json.dumps({'status':result['status'],'checks':CHECKS,'output':str(OUT.relative_to(REPO))}))
if __name__=='__main__':main()
