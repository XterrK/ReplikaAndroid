#!/usr/bin/env python3
"""Saved-only performance evidence integrity/rescore; no NN, decoder, ADB, build or speed acceptance."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import sys
import wave

sys.dont_write_bytecode=True
PROTOCOL_SHA='aef12832afdd97eef5e301e1515402535e01fbbbe7ce0414bdefda0b3419196a'
DRIVER_SHA='a910dd990505175d031312e1dc0ed8848cb5caabcc64434dde19d367c2a4747c'
HELPER_SHA='11fc1e516a2a0663ce950e755833b1cb9c9fd86b9c07ffba45a795239772b929'
ORDER=[2,4,4,2];IDS=['perf-01m','perf-03m','perf-10m'];DURATIONS=[60000,180000,600000]

def strict_json(raw):
    def pairs(rows):
        out={}
        for k,v in rows:
            if k in out:raise ValueError('Duplicate JSON key: '+k)
            out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))

def complete(value):
    return (value.get('status')=='COMPLETE' and value.get('inference_requested') is True
            and value.get('new_model_inference') is True and value.get('inference_completion_verified') is True
            and all(type(value.get(k)) is int and value[k]==12 for k in ('planned_workers','completed_workers','verified_workers'))
            and len(value.get('batches',[]))==4
            and all(b.get('status')=='COMPLETE' and [r.get('id') for r in b.get('cases',[])]==IDS for b in value['batches']))

def summary(rows):
    audio=sum(r['duration_ms'] for r in rows);processing=sum(r['processing_ms'] for r in rows)
    out={'cases':len(rows),'audio_ms':audio,'processing_ms':processing,'rtf':processing/audio if audio else None}
    for key in ('wer_raw','wer_normalized','cpwer_raw'):
        errors=sum(r['metrics'][key]['errors'] for r in rows);words=sum(r['metrics'][key]['reference_tokens'] for r in rows)
        out[key]={'errors':errors,'reference_tokens':words,'rate':errors/words if words else None}
    return out

def sample_summary(samples):
    return {'scope':'Observed periodic batch snapshots only, not continuous peak; startup samples excluded until instrumentation report exists',
            'samples':len(samples),'errors':sum('error' in r for r in samples),
            'observed_pids':sorted({r['pids'] for r in samples if r.get('pids')}),
            'maximum_observed_rss_kb':max((r['rss_kb'] for r in samples if r.get('rss_kb') is not None),default=None),
            'maximum_observed_pss_kb':max((r['pss_kb'] for r in samples if r.get('pss_kb') is not None),default=None)}

def clock_steps(samples):
    result=[]
    for index,(before,after) in enumerate(zip(samples,samples[1:]),1):
        wall=(datetime.fromisoformat(after['at'])-datetime.fromisoformat(before['at'])).total_seconds()
        monotonic=after['monotonic_seconds']-before['monotonic_seconds']
        if abs(wall-monotonic)>1:
            result.append({'index':index,'before_at':before['at'],'after_at':after['at'],
                'before_batch':before.get('_batch'),'after_batch':after.get('_batch'),
                'wall_delta_seconds':wall,'monotonic_delta_seconds':monotonic,
                'wall_minus_monotonic_delta_seconds':wall-monotonic})
    return result


def load_helper():
    path=Path(__file__).with_name('step05-independent-cpu-audit.py')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=HELPER_SHA:raise ValueError('Hash helper changed')
    spec=importlib.util.spec_from_file_location('frozen_perf_hash_helper',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    class Evidence(m.Audit):
        def read(self,p):self.sha(p);return strict_json(Path(p).read_bytes())
    return Evidence,path

def audit(args,a,helper):
    repo,out=args.repo,args.run;sys.path.insert(0,str(repo))
    from tools.eval import native_diar_policy as policy,score
    from tools import run_plan19_perf as driver
    a.check(a.sha(repo/'tools/run_plan19_perf.py')==DRIVER_SHA,'frozen reviewed driver')
    run=a.read(out/'run.json');a.check(complete(run),'terminal all12 required; no partial completion claims')
    manifest_path=repo/'benchmark/eval-perf/manifest.json';manifest=a.read(manifest_path);cases=manifest['files']
    protocol_path=manifest_path.parent/'protocol.json';protocol=a.read(protocol_path)
    receipt=a.read(repo/'artifacts/test-results/step-05/perf-execution-receipt-v1.json')
    preflight_path=repo/'artifacts/test-results/step-05/perf-preflight-v2.json';preflight=a.read(preflight_path)
    a.check(a.sha(protocol_path)==PROTOCOL_SHA==receipt['protocol_sha256'] and run['protocol']==protocol,'original before-NN protocol unchanged')
    a.check(receipt['status']=='READY_BEFORE_PERFORMANCE_NN' and receipt['runner_sha256']==DRIVER_SHA and a.sha(preflight_path)==receipt['preflight_sha256'],'exact execution receipt/preflight pins')
    fp=run['fingerprint'];a.check(preflight['fingerprint']==fp and run['order']==protocol['threads_order']==receipt['order']==ORDER,'actual ordered preflight fingerprint')
    a.check([c['id'] for c in cases]==IDS and [c['duration_ms'] for c in cases]==DURATIONS and run['planned_audio_ms']==3360000 and run['planned_workers']==12,'fixed three related inputs/four repetitions')
    a.check(run['reference_text_or_counts_staged'] is False and run['collectEvidence'] is False and protocol['expected_speakers']==-1 and protocol['cpu_plan']=='auto_v1','automatic speakers/no gold/compact QA scope')
    a.check(run['device']['abi']=='x86_64' and run['device']['sdk']=='35','actual API35/x86 execution scope')
    commands=[strict_json(s) for s in (out/'commands.jsonl').read_text().splitlines() if s.strip()];a.sha(out/'commands.jsonl')
    instruments=[r for r in commands if 'instrument' in r['argv'] and 'evalRun' in r['argv']]
    a.check(len(instruments)==4 and datetime.fromisoformat(protocol['frozen_utc'])<datetime.fromisoformat(receipt['at'])<datetime.fromisoformat(instruments[0]['at']),'protocol/receipt before exactly four NN batches')
    for record,threads in zip(instruments,ORDER):
        argv=list(map(str,record['argv']))
        for name,value in {'evalThreads':str(threads),'evalExpectedSpeakers':'-1','evalCpuPlan':'auto_v1','evalAsrPlan':policy.ASR_PLAN,'evalDiarPlan':policy.PLAN,'evalCollectEvidence':'false'}.items():a.check(argv[argv.index(name)+1]==value,('actual instrumentation policy',name))
    for relative,expected in fp['code'].items():
        a.check(a.sha(out/'source-snapshots'/relative)==expected,('immutable executing source snapshot',relative))
        a.check(a.sha(repo/relative)==expected,('current frozen source/config',relative))
    for absolute,expected in fp['local_files'].items():a.check(a.sha(Path(absolute))==expected,('original local input/APK/model pin',absolute))
    lock= a.read(repo/'app/src/main/assets/models-lock.json');pins=policy.validate_model_lock(lock)
    a.check(run['native_model_sha256_before']==run['native_model_sha256_after']==pins,'all seven actual Android models before/after')
    for role in ('app','test'):a.check(run['installed_apks'][role]['sha256']==fp['apk'][role]['sha256'],'actual installed APK equals local preflight pin')
    provenance=a.read(manifest_path.parent/'provenance.json');a.check(a.sha(manifest_path.parent/'provenance.json')==manifest['source_provenance_sha256'] and provenance['new_model_inference'] is False and provenance['status']=='COMPLETE','unrecognised corpus preparation provenance')
    source=provenance['source'];author=a.read(manifest_path.parent/'sources/source-reference.json')['transcript'][:6]
    a.check(source['kept_utterance_indices']==list(range(6)) and source['exact_prefix_frames']==842543 and source['silence_padding_frames']==117457,'complete author utterance boundary policy')
    input_records={}
    for c in cases:
        reference_path=manifest_path.parent/c['reference'];reference=a.read(reference_path)
        a.check(a.sha(reference_path)==c['reference_sha256'] and c['kind']=='related_controlled_repeat' and c['split']=='performance_proxy','independent authored reference and related scope')
        expected={'transcript':[{**r,'start_ms':r['start_ms']+block*60000,'end_ms':r['end_ms']+block*60000} for block in range(c['repeat_blocks']) for r in author]}
        policy.equal(reference,expected,'whole literal author reference repeat')
        matches=[Path(p) for p,h in fp['local_files'].items() if h==c['audio_sha256']]
        a.check(len(matches)==1,'exact original canonical performance WAV pin');audio=matches[0]
        with wave.open(str(audio),'rb') as wav:
            a.check((wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())==(1,2,16000,c['frames']),'canonical 16k PCM16 clock')
            first=wav.readframes(960000)
            a.check(hashlib.sha256(first).hexdigest()==source['block_pcm16_sha256'] and hashlib.sha256(first[:842543*2]).hexdigest()==source['prefix_pcm16_sha256'] and not any(first[842543*2:]),'original complete utterance prefix plus exact silence')
            for _ in range(c['repeat_blocks']-1):a.check(wav.readframes(960000)==first,'unchanged repeated source block')
        input_records[c['id']]={'spec':c,'reference':reference,'reference_path':reference_path}
    for smoke in receipt['smokes']:
        path=repo/smoke['path'];v=a.read(path);a.check(a.sha(path)==smoke['sha256'] and v['status']=='COMPLETE' and v['contract_smoke_pass'] is True,'before-performance actual compact contracts')
    config=a.read(repo/'configs/eval/c2-window-selected-full.json');seen_work=set();seen_recording=set();all_rows=[];batch_reports=[];totals=Counter()
    all_clock_samples=[]
    for index,(batch,threads) in enumerate(zip(run['batches'],ORDER),1):
        directory=out/f'batch-{index:02d}-threads{threads}';native_report=a.read(directory/'instrumentation-report.json')
        a.check(batch['batch']==index and batch['threads']==threads and batch['status']=='COMPLETE' and batch['instrumentation_exit_code']==0,'completed ordered batch')
        transient,paired=driver.execution_config(config,threads);policy.validate_native_diar_policy(transient,native_report,paired,cpu_plan='auto_v1',threads=threads)
        a.check(native_report['run']==batch['run'] and native_report['status']=='COMPLETE' and native_report['collectEvidence'] is False and native_report['newModelInference'] is True and [r['id'] for r in native_report['cases']]==IDS,'actual ordered compact batch report')
        pid=native_report['processId'];a.check(type(pid) is int and pid>0 and batch['single_instrumented_process_id']==pid and all(c['processId']==pid for c in native_report['cases']),'same instrumented process for all three files')
        staged=a.read(directory/'batch.json');a.check(set(staged)=={'schema_version','run','cases'} and staged['run']==batch['run'] and [r['id'] for r in staged['cases']]==IDS,'staged exact order')
        for row,c in zip(staged['cases'],cases):a.check(set(row)=={'id','audio','sha256'} and row['audio']=='audio/'+c['id']+'.wav' and row['sha256']==c['audio_sha256'],'audio/ID/SHA only on device')
        log=(directory/'instrumentation.log').read_bytes();a.sha(directory/'instrumentation.log');a.sha(directory/'instrumentation.stderr')
        a.check(re.search(rb'OK \(1 tests?\)',log) is not None and re.search(rb'FAILURES!!!|INSTRUMENTATION_FAILED|Process crashed',log) is None,'actual JUnit completed')
        records=[]
        for stored,c in zip(batch['cases'],cases):
            cid=c['id'];native=a.read(directory/f'{cid}.case.json');diag=a.read(directory/f'{cid}.diagnostics.json');hyp=a.read(directory/f'{cid}.hypothesis.json');metric=a.read(directory/f'{cid}.metrics.json')
            policy.equal(native,next(r for r in native_report['cases'] if r['id']==cid),'native case/report exact copy')
            counts=driver.validate_compact_case(c,native,diag,hyp,config,threads)
            a.check(counts==stored['compact_evidence'] and counts['full_token_vector_replay_performed'] is False,'compact-only support scope')
            a.check(native['workId'] not in seen_work and native['recordingId'] not in seen_recording,'fresh unique Worker/recording UUID');seen_work.add(native['workId']);seen_recording.add(native['recordingId'])
            reference=input_records[cid]['reference'];a.check(a.sha(directory/f'{cid}.reference.json')==c['reference_sha256'],'separate exact reference bytes')
            fresh=score.score(reference,hyp,native['duration_ms'],native['processing_ms'])
            for key,value in fresh.items():a.check(value==metric[key],('independent score',index,cid,key))
            turns=policy.turns_from_json(diag['diarizationTurns'],native['duration_ms']);native_rows=[{'speaker_id':str(t.speaker),'start_ms':t.start_ms,'end_ms':t.end_ms,'text':''} for t in turns]
            for collar in (0,250):a.check(score.der(reference['transcript'],native_rows,native['duration_ms'],collar)==metric[f'native_der_collar_{collar}ms'],('independent native DER',index,cid,collar))
            a.check(len({t.speaker for t in turns})==metric['native_speaker_count'],'actual native speaker count')
            hashes={suffix:a.sha(directory/f'{cid}.{suffix}.json') for suffix in ('reference','hypothesis','diagnostics','case','metrics')}
            a.check(stored['id']==cid and stored['duration_ms']==native['duration_ms'] and stored['processing_ms']==native['processing_ms'] and stored['metrics']==metric and stored['evidence_sha256']==hashes and stored['new_model_inference'] is True,'batch record/evidence exact copies')
            a.check(stored['work_id']==native['workId'] and stored['recording_id']==native['recordingId'] and stored['process_id']==native['processId']==pid,'per-case real process/identity copies')
            stages,telemetry=diag['stagesMs'],diag['telemetry'];a.check(stored['stages_ms']==stages==telemetry['stagesMs'] and stored['telemetry']==telemetry,'stage timing/telemetry copies')
            a.check(all(type(v) is int and v>=0 for v in stages.values()) and type(telemetry['observedMaxPssKb']) is int and telemetry['observedMaxPssKb']>0,'nonnegative actual stage clocks and observed memory')
            a.check(math.isclose(metric['rtf'],native['processing_ms']/native['duration_ms'],rel_tol=0,abs_tol=1e-12),'Worker RTF recomputed')
            totals.update(workers=1,audio_ms=native['duration_ms'],processing_ms=native['processing_ms'],embedding_windows=counts['measured_embedding_windows'],asr_chunks=counts['asr_chunks'],reported_tokens=counts['reported_tokens'],reported_words=counts['reported_words'])
            records.append(stored);all_rows.append({'batch':index,'threads':threads,'id':cid,'work_id':native['workId'],'recording_id':native['recordingId'],'process_id':pid,'duration_ms':native['duration_ms'],'processing_ms':native['processing_ms'],'rtf':metric['rtf'],'raw_wer':metric['wer_raw'],'normalized_wer':metric['wer_normalized'],'cpwer_raw':metric['cpwer_raw'],'native_der0':metric['native_der_collar_0ms'],'native_der250':metric['native_der_collar_250ms'],'native_speakers':metric['native_speaker_count'],'stages_ms':stages,'telemetry':telemetry,'compact_evidence':counts,'evidence_sha256':hashes})
        a.check(summary(records)==batch['summary'],'independently weighted batch summary')
        samples=[strict_json(s) for s in (directory/'samples.jsonl').read_text().splitlines() if s.strip()];a.sha(directory/'samples.jsonl')
        a.check(sample_summary(samples)==batch['sampled_resources'],'periodic sampled resource summary exact')
        all_clock_samples.extend([{**sample,'_batch':index} for sample in samples])
        matching_pid=0;other_pid=0
        for sample_index,s in enumerate(samples):
            a.check(type(s['monotonic_seconds']) in (int,float) and math.isfinite(s['monotonic_seconds']),'finite sample monotonic clock')
            if sample_index:a.check(s['monotonic_seconds']>=samples[sample_index-1]['monotonic_seconds'],'ordered periodic resource snapshots')
            if s.get('pids')==str(pid):matching_pid+=1
            elif s.get('pids'):other_pid+=1
            for field,suffix,pattern in [('rss_kb','proc',rb'^VmRSS:\s+(\d+)\s+kB'),('pss_kb','meminfo',rb'TOTAL PSS:\s*(\d+)')]:
                path=directory/f'sample-{sample_index:05d}-{suffix}.txt'
                if path.exists():
                    a.sha(path);match=re.search(pattern,path.read_bytes(),re.M);value=int(match[1]) if match else None
                    if field in s:a.check(s[field]==value,('raw resource snapshot parsing',index,sample_index,field))
            thermal=directory/f'sample-{sample_index:05d}-thermal.txt'
            if thermal.exists():a.sha(thermal)
        stage_log=directory/'stage-pss-logcat.txt';a.sha(stage_log);a.sha(directory/'stage-pss-logcat.stderr')
        events=[]
        for line in stage_log.read_text(errors='replace').splitlines():
            start=line.find('{')
            if start<0:continue
            try:event=strict_json(line[start:])
            except (ValueError,TypeError):continue
            if isinstance(event,dict) and 'run' in event:events.append(event)
        batch_reports.append({'batch':index,'threads':threads,'pid':pid,'summary':summary(records),'sampled_resources':sample_summary(samples),'samples_with_instrumented_pid':matching_pid,'samples_with_other_pid':other_pid,'captured_stage_events':len(events),'stage_event_scope':'Raw logs may include previous runs and finish after the diagnostic snapshot; UUIDs/values retained, not a continuous memory peak.'})
    a.check(len(seen_work)==len(seen_recording)==totals['workers']==12 and totals['audio_ms']==run['completed_audio_ms'],'all12 unique Workers and completed actual audio sum')
    expected_pairs=[]
    for first,second in ((0,1),(3,2)):
        two,four=run['batches'][first],run['batches'][second]
        expected_pairs.append({'threads2_batch':first+1,'threads4_batch':second+1,'threads4_over_threads2_processing_ratio':four['summary']['processing_ms']/two['summary']['processing_ms'],'scope':'Paired descriptive ratio with order retained; uncontrolled conditions, no causal speed claim','per_case':[{'id':r['id'],'threads4_over_threads2_ratio':s['processing_ms']/r['processing_ms'],'raw_errors_threads2':r['metrics']['wer_raw']['errors'],'raw_errors_threads4':s['metrics']['wer_raw']['errors']} for r,s in zip(two['cases'],four['cases'])]})
    a.check(run['paired_comparisons']==expected_pairs,'both predeclared directional timing comparisons recomputed')
    reader=csv.DictReader(io.StringIO((out/'results.csv').read_text()));csv_rows=list(reader);a.sha(out/'results.csv')
    a.check(len(csv_rows)==12 and [(int(r['batch']),int(r['threads']),r['case']) for r in csv_rows]==[(r['batch'],r['threads'],r['id']) for r in all_rows],'CSV complete ordered coverage')
    for row,actual in zip(csv_rows,all_rows):a.check(int(row['processing_ms'])==actual['processing_ms'] and int(row['audio_ms'])==actual['duration_ms'] and float(row['rtf'])==actual['rtf'],'CSV actual times/RTF')
    screen=run['screen_power'];a.check(screen['restored_exactly'] is True and screen['original']==screen['restored'],'original screen-power setting restored')
    a.sha(helper);a.verify_unchanged()
    return {'status':'PASS','performance_evidence_integrity':'PASS','checks':a.checks,'workers':12,'input_files':3,'order':ORDER,'planned_audio_ms':3360000,'actual_totals':dict(totals),'protocol_sha256':PROTOCOL_SHA,'run_sha256':a.sha(out/'run.json'),'batch_reports':batch_reports,'paired_descriptive_comparisons':expected_pairs,'rows':all_rows,'source_sha256':a.hashes,'source_version_resolutions':a.resolutions,'screen_restored':True,'host_wall_clock_discontinuities':clock_steps(all_clock_samples),'timing_clock_scope':'RTF uses recorded Worker elapsed SystemClock timings; ISO wall-clock differences are not treated as processing durations. Wall/monotonic steps are retained without inferring a cause.'}

def self_test():
    import copy
    value={'status':'COMPLETE','inference_requested':True,'new_model_inference':True,'inference_completion_verified':True,'planned_workers':12,'completed_workers':12,'verified_workers':12,'batches':[{'status':'COMPLETE','cases':[{'id':i} for i in IDS]} for _ in ORDER]};count=0
    assert complete(value);count+=1
    for key,changed in [('status','RUNNING'),('verified_workers',11),('completed_workers',True),('inference_completion_verified',False)]:
        other=copy.deepcopy(value);other[key]=changed;assert not complete(other);count+=1
    other=copy.deepcopy(value);other['batches'][2]['cases'].pop();assert not complete(other);count+=1
    other=copy.deepcopy(value);other['batches'][2]['cases'].reverse();assert not complete(other);count+=1
    assert sample_summary([{'pids':'4','rss_kb':10,'pss_kb':7},{'state':'waiting_for_instrumentation_report'},{'error':'unavailable'}])['errors']==1;count+=1
    assert sample_summary([])['maximum_observed_pss_kb'] is None;count+=1
    rows=[{'duration_ms':60000,'processing_ms':30000,'metrics':{k:{'errors':10,'reference_tokens':100} for k in ('wer_raw','wer_normalized','cpwer_raw')}},
          {'duration_ms':180000,'processing_ms':180000,'metrics':{k:{'errors':10,'reference_tokens':300} for k in ('wer_raw','wer_normalized','cpwer_raw')}}]
    assert summary(rows)['rtf']==.875 and summary(rows)['wer_raw']['rate']==.05;count+=1
    for raw in ('{"x":NaN}','{"x":1,"x":2}'):
        try:strict_json(raw)
        except ValueError:count+=1
        else:raise AssertionError('Bad JSON accepted')
    samples=[{'at':'2026-11-07T00:00:00+00:00','monotonic_seconds':0},{'at':'2026-11-07T00:00:10+00:00','monotonic_seconds':10}]
    assert clock_steps(samples)==[];count+=1
    samples.append({'at':'2026-11-07T02:00:20+00:00','monotonic_seconds':20})
    assert len(clock_steps(samples))==1 and clock_steps(samples)[0]['wall_minus_monotonic_delta_seconds']==7200;count+=1
    print(json.dumps({'self_test':'PASS','checks':count,'neural_inference':False,'scope':'Synthetic coverage/JSON/resource guards only; no incomplete actual run audited'}))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--run',type=Path);p.add_argument('--output',type=Path);p.add_argument('--self-test',action='store_true');args=p.parse_args()
    if args.self_test:self_test();return
    if args.run is None or args.output is None:p.error('--run and --output required')
    args.repo,args.run,args.output=(v.resolve() for v in (args.repo,args.run,args.output));md=args.output.with_suffix('.md')
    if args.output.exists() or md.exists():raise ValueError('Fresh output only; no overwrite')
    Evidence,helper=load_helper();a=Evidence(args.repo)
    try:result=audit(args,a,helper)
    except BaseException as error:result={'status':'FAIL','performance_evidence_integrity':'FAIL','checks':a.checks,'error':{'type':type(error).__name__,'message':str(error)},'source_sha256':a.hashes}
    script=Path(__file__).read_bytes();h=hashlib.sha256(script).hexdigest();snapshot=args.repo/'artifacts/test-results/step-05/runner-snapshots'/(h+'-perf-independent-audit.py');snapshot.parent.mkdir(parents=True,exist_ok=True)
    if snapshot.exists():
        if snapshot.read_bytes()!=script:raise ValueError('Immutable snapshot collision')
    else:
        with snapshot.open('xb') as f:f.write(script)
    result.update(schema_version=1,at=datetime.now(timezone.utc).isoformat(),auditor_source_sha256=h,auditor_source_snapshot=str(snapshot.relative_to(args.repo)),neural_inference_by_auditor=False,full_token_vector_replay=False,speed_causal_accepted=False,arm_phone_accepted=False,whole_step5_accepted=False,scope='Saved actual x86 performance receipts only. Three related inputs repeated four times; metrics are author-utterance proxies, not independent/natural-dialogue or word-boundary gold. QAfalse omits full arrays. Observed RTF/resource snapshots and descriptive order pairs are not causal speed/ARM/phone or continuous memory peaks.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    lines=[f"Независимый performance-аудит: {result['status']}, {result['checks']} проверок.",'Аудитор не запускал NN/decoder/ADB/Gradle. Полные token/vector массивы не собирались и не воспроизводились.','']
    if result['status']=='PASS':
        lines+=['| Пакет | Потоки | Файлов | Audio ms | Worker ms | Наблюдаемый RTF |','| --- | ---: | ---: | ---: | ---: | ---: |']
        for b in result['batch_reports']:
            s=b['summary'];lines.append(f"| {b['batch']} | {b['threads']} | {s['cases']} | {s['audio_ms']} | {s['processing_ms']} | {s['rtf']:.6f} |")
    else:lines.append(str(result['error']))
    lines += ['',f"JSON: [{args.output.name}]({args.output.name}); source SHA `{h}`.",'Это четыре повтора трёх связанных записей с измеренным порядком 2/4/4/2. Кеши/температура/overhead не контролируются полностью; причинное ускорение, ARM/телефон, непрерывный пик RAM и полная приёмка проекта не заявляются.']
    with md.open('x') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps({k:result.get(k) for k in ('status','performance_evidence_integrity','workers','checks','error','auditor_source_sha256')},ensure_ascii=False))
    if result['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
