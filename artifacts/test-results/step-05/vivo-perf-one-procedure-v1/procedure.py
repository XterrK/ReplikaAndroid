#!/usr/bin/env python3
"""One physical auto0 1/3/10-minute group. Default --check invokes no ADB.
Root notifies the user before/after execution. Foreground instrumentation may
interrupt app UI. No phone settings, installation, model staging or data wipe.
Raw output is PRIVATE; export only reviewed sanitized tables afterward.
"""
import argparse, json, re, shutil, subprocess, sys, threading, time, uuid
from pathlib import Path, PurePosixPath
sys.dont_write_bytecode=True
REPO=Path('/mnt/d/ReplikaAndroid/ReplikaAndroid')
sys.path.insert(0,str(REPO))
from tools import run_plan19_perf as r
P=r.policy
APKS={'app':'ca18309f626d431d0bd7bb4c649a2a3ae77f3ef3b75f7f1bcb47c83bf449e15e','test':'ce4851c681962e8489bd9d8bc0edc0a229d245307b88fdfa9c19d0ef1f1df051'}
CPU={'plan':'auto_v1','requestedThreads':0,'availableCores':8,'asrThreads':4,'diarizationThreads':4,'refinementThreads':4,'diarizationPinned':False,'refinementPinned':False}
SCOPE='One physical ARM/API37/4KB auto0->4 sequential related-repeat group; uncontrolled caches/heat/charging and instrumentation overhead. Snapshot memory, not continuous peak. No causal CPU comparison or independent/natural-dialogue quality claim.'

def compact(case,n,d,h,config):
    transient,paired=r.execution_config(config,4)
    P.validate_native_diar_policy(transient,d,paired,cpu_plan='auto_v1',threads=4,requested_threads=0)
    P.equal(d.get('cpuPolicy'),CPU,'actual auto0 CPU')
    for key,value in {'id':case['id'],'status':'COMPLETE','audio_sha256':case['audio_sha256'],'newModelInference':True,'collectEvidence':False,'workManagerState':'SUCCEEDED'}.items():P.equal(n.get(key),value,'case.'+key)
    duration,processing=n.get('duration_ms'),n.get('processing_ms')
    if type(duration)is not int or abs(duration-case['duration_ms'])>1 or type(processing)is not int or processing<=0 or type(n.get('processId'))is not int or n['processId']<=0:raise ValueError('Actual clock/PID invalid')
    if str(uuid.UUID(n['workId']))!=n['workId'] or not n['recordingId'].startswith('qa-evaluation-') or str(uuid.UUID(n['recordingId'][14:]))!=n['recordingId'][14:]:raise ValueError('Actual own UUID invalid')
    for key,value in {'runtime':'sherpa-onnx 2.0.1','backend':P.base.SOURCE,'sampleRate':16000,'vadThreads':1,'maxAsrSegmentMs':20000,'wordEvidenceRequested':False,'wordEvidenceBytes':0,'wordEvidenceTruncated':False,'audioMs':duration,'totalMs':processing,'diarizationRefinementAccepted':True}.items():P.equal(d.get(key),value,key)
    if any(k.startswith('diarizationEvidence') for k in d):raise ValueError('Unexpected full sidecar payload')
    adapter=d.get('diarizationRefinement',{})
    for key,value in {'cpuPlan':'auto_v1','embeddingThreads':4,'algorithm':'window-overcluster-v1','nativeResourcesReleasedBeforeRefiner':True,'originalPcm':True,'embeddingInferenceCompleted':True,'computationalSupport':True,'retainedNativeModelCache':False,'config':P.WINDOW_CONFIG}.items():P.equal(adapter.get(key),value,'adapter.'+key)
    if adapter.get('status')not in ('SUPPORTED','PARTIAL_TEMPORAL'):raise ValueError('Unsupported refiner')
    P.equal(adapter,P.compact_refiner_diagnostic(adapter),'compact adapter')
    counts=d.get('diarizationEmbeddingCounts',{});count=counts.get('measuredWindows')
    if type(count)is not int or count<=0:raise ValueError('No real embedding inference')
    for key,value in {'extractorLoads':1,'embeddingDimension':512,**{k:count for k in ('plannedWindows','readWindows','createdStreams','releasedStreams','computeAttempts','embeddingForwardCalls')}}.items():P.equal(counts.get(key),value,'counts.'+key)
    parts=d.get('asrSlices');previous=0
    if not isinstance(parts,list)or not parts:raise ValueError('Missing actual ASR summaries')
    P.equal(d.get('wordProcessedChunks'),len(parts),'wordProcessedChunks')
    for part in parts:
        a,b=part.get('startMs'),part.get('endMs')
        if type(a)is not int or type(b)is not int or not previous<=a<b<=duration or b-a>20000:raise ValueError('Chunk clock invalid')
        previous=b
        if part.get('wordEvidenceIncluded')is not False or part.get('wordEvidenceOmittedReason')!='not_requested' or any(k in part for k in ('tokens','timestamps','words')):raise ValueError('QA arrays not disabled')
        P.equal(part.get('frameStrideMs'),40,'frameStrideMs')
        if type(part.get('text'))is not str or type(part.get('blank'))is not bool or part['blank']!=(not part['text'].strip()):raise ValueError('Invalid compact text/blank')
        if any(type(part.get(k))is not int or part[k]<0 for k in ('tokenCount','timestampCount','wordCount')):raise ValueError('Invalid compact counts')
    rows=r.scoring._document(h,duration)
    if ' '.join(row.text for row in rows).split()!=' '.join(part['text']for part in parts).split():raise ValueError('Actual ASR/Jury text differs')
    return {'asr_chunks':len(parts),'reported_tokens':sum(p['tokenCount']for p in parts),'reported_words':sum(p['wordCount']for p in parts),'measured_embedding_windows':count,'resources_balanced':True,'full_token_vector_replay_performed':False}

def preflight(a):
    if a.output.resolve().is_relative_to(REPO)or a.output.exists():raise ValueError('Fresh PRIVATE output outside repository required')
    if r.sha(REPO/'tools/run_plan19_perf.py')!='a910dd990505175d031312e1dc0ed8848cb5caabcc64434dde19d367c2a4747c':raise ValueError('Frozen helper changed')
    checked=r.preflight(a) # Original four-group protocol validates only immutable controlled source inputs here; run() is NEVER called.
    if any(checked['fingerprint']['apk'][role]['sha256']!=value for role,value in APKS.items()):raise ValueError('Frozen ARM/app or test APK differs')
    if a.serial.startswith('emulator-'):raise ValueError('Explicit physical serial required')
    checked['fingerprint']['local_files'].update({str(Path(__file__).resolve()):r.sha(__file__),str(a.physical_protocol.resolve()):r.sha(a.physical_protocol),str(Path(a.adb).resolve()):r.sha(a.adb)})
    protocol=r.read_json(a.physical_protocol)
    if protocol['case_order']!=list(r.CASE_IDS)or protocol['cpu_policy']!=CPU or protocol['collectEvidence']is not False:raise ValueError('One-group physical protocol differs')
    for relative,expected in protocol['source_sha256'].items():
        if r.sha(REPO/relative)!=expected:raise ValueError('Frozen physical procedure source differs: '+relative)
    if a.instrument_timeout_seconds!=7200 or a.sample_seconds!=10:raise ValueError('Frozen host timeout/snapshot interval differs')
    return checked

def run(a):
    checked=preflight(a)
    if not a.execute:
        print(json.dumps({'status':'PREFLIGHT_PASS','adb_invoked':False,'new_neural_inference':False,'workers':3,'case_order':list(r.CASE_IDS),'cpu_policy':CPU,'apk_sha256':APKS,'script_sha256':r.sha(__file__),'physical_protocol_sha256':r.sha(a.physical_protocol)}));return 0
    if not a.allow_physical:raise ValueError('Explicit --allow-physical required')
    a.output.mkdir(parents=True)
    meta={'status':'STAGING','scope':SCOPE,'fingerprint':checked['fingerprint'],'serial':a.serial,'reference_text_or_counts_staged':False,'phone_settings_changed':False,'planned_workers':3,'verified_workers':0,'inference_requested':False,'new_model_inference':False,'inference_completion_verified':False,'batches':[{'batch':1,'threads':4,'requested_threads':0,'cases':[]}],'errors':[]}
    r.write_json(a.output/'run.json',meta);shutil.copyfile(__file__,a.output/'procedure.py');shutil.copyfile(a.physical_protocol,a.output/'protocol.json')
    session='armperf_'+uuid.uuid4().hex;remote='files/evaluation/'+session;stop=threading.Event();sampler=None;logger=None;lock=threading.Lock()
    def argv(*words):
        command=[a.adb,'-s',a.serial,*map(str,words)]
        with lock,(a.output/'commands.jsonl').open('a')as log:log.write(json.dumps({'at':r.now(),'argv':command})+'\n')
        return command
    def adb(*words,check=True,timeout=120):
        value=subprocess.run(argv(*words),capture_output=True,timeout=timeout)
        if check and value.returncode:raise RuntimeError(value.stderr.decode('utf-8','replace'))
        return value
    def models():
        observed={}
        for row in checked['models']['files']:
            value=adb('exec-out','run-as',a.package,'sha256sum','files/models/'+row['path']).stdout.decode().split()[0]
            if value!=row['sha256']:raise ValueError('Actual model hash differs: '+row['path'])
            observed[row['path']]=value
        return observed
    def pull():
        for name in ['report.json',*[c+'.'+s+'.json'for c in r.CASE_IDS for s in ('case','hypothesis','diagnostics')]]:
            try:
                value=adb('exec-out','run-as',a.package,'cat',remote+'/output/'+name,check=False)
                if value.returncode==0:(a.output/name).write_bytes(value.stdout)
                else:meta['errors'].append({'pull':name,'returncode':value.returncode})
            except Exception as error:meta['errors'].append({'pull':name,'error':repr(error)})
    def sample():
        index=0
        while not stop.is_set():
            row={'at':r.now(),'scope':'10-second own-process snapshot, not continuous peak'}
            try:
                value=adb('exec-out','run-as',a.package,'cat',remote+'/output/report.json',check=False,timeout=10)
                doc=P.strict_json(value.stdout)if value.returncode==0 else {};pid=doc.get('processId')
                if type(pid)is int and pid>0 and adb('shell','pidof',a.package,check=False,timeout=10).stdout.decode().strip()==str(pid):
                    row['process_id']=pid;raw=adb('exec-out','run-as',a.package,'cat',f'/proc/{pid}/status',check=False,timeout=10).stdout
                    (a.output/f'sample-{index:05d}-proc.txt').write_bytes(raw);match=re.search(rb'^VmRSS:\s+(\d+)\s+kB',raw,re.M);row['rss_kb']=int(match[1])if match else None
                    (a.output/f'sample-{index:05d}-meminfo.txt').write_bytes(adb('shell','dumpsys','meminfo',a.package,check=False,timeout=10).stdout)
                    (a.output/f'sample-{index:05d}-thermal.txt').write_bytes(adb('shell','dumpsys','thermalservice',check=False,timeout=10).stdout)
            except Exception as error:row['error']=repr(error)
            with(a.output/'samples.jsonl').open('a')as log:log.write(json.dumps(row)+'\n')
            index+=1;stop.wait(10)
    try:
        r.check_unchanged(checked)
        if adb('get-state').stdout.strip()!=b'device' or adb('shell','getprop','ro.kernel.qemu').stdout.strip()==b'1':raise ValueError('Ready physical phone required')
        for prop,expected in [('ro.build.version.sdk','37'),('ro.product.cpu.abi','arm64-v8a')]:
            if adb('shell','getprop',prop).stdout.decode().strip()!=expected:raise ValueError('Physical API/ABI differs')
        if adb('shell','getconf','PAGE_SIZE').stdout.strip()!=b'4096':raise ValueError('Expected 4KB phone')
        meta['installed_apks']={}
        for role,package in [('app',a.package),('test',a.package+'.test')]:
            paths=adb('shell','pm','path',package).stdout.decode().splitlines()
            if len(paths)!=1 or not re.fullmatch(r'package:/data/app/[A-Za-z0-9_~./=+-]+\.apk',paths[0])or '..'in PurePosixPath(paths[0][8:]).parts:raise ValueError('Invalid installed base APK path')
            actual=adb('exec-out','sha256sum',paths[0][8:]).stdout.decode().split()[0]
            if actual!=APKS[role]:raise ValueError('Installed/local APK differs')
            meta['installed_apks'][role]={'sha256':actual,'path':paths[0][8:]}
        meta['model_sha256_before']=models()
        power=adb('shell','dumpsys','power').stdout;activity=adb('shell','dumpsys','activity','activities').stdout
        (a.output/'power-before.txt').write_bytes(power);(a.output/'activity-before.txt').write_bytes(activity)
        if not re.search(rb'mWakefulness=Awake\b',power)or not any(a.package.encode()in line and(b'mResumedActivity'in line or b'topResumedActivity'in line)for line in activity.splitlines()):raise ValueError('Phone must already be Awake with Replika RESUMED; no settings changed')
        if adb('shell','run-as',a.package,'test','-e',remote,check=False).returncode==0:raise ValueError('Remote run exists')
        batch={'schema_version':1,'run':session,'cases':[{'id':c['id'],'audio':'audio/'+c['id']+'.wav','sha256':c['audio_sha256']}for c in checked['cases']]};r.write_json(a.output/'batch.json',batch)
        for local,suffix in [(checked['inputs'][c['id']]['audio'],'audio/'+c['id']+'.wav')for c in checked['cases']]+[(a.output/'batch.json','batch.json')]:
            temporary='/data/local/tmp/'+session+'-'+PurePosixPath(suffix).name
            adb('push',local,temporary);adb('shell','run-as',a.package,'mkdir','-p',str(PurePosixPath(remote+'/'+suffix).parent));adb('shell','run-as',a.package,'cp',temporary,remote+'/'+suffix);adb('shell','rm',temporary)
        r.check_unchanged(checked);meta.update(status='RUNNING',inference_requested=True,new_model_inference=None,remote_run=session);r.write_json(a.output/'run.json',meta)
        sampler=threading.Thread(target=sample,daemon=True);sampler.start()
        with(a.output/'stage-pss-logcat.txt').open('wb')as log,(a.output/'stage-pss-logcat.stderr').open('wb')as err:
            logger=subprocess.Popen(argv('logcat','-v','epoch','-T','1','-s','ReplikaPerf:I','*:S'),stdout=log,stderr=err)
            try:
                value=adb('shell','am','instrument','-w','-r','-e','evalRun',session,'-e','evalThreads','0','-e','evalExpectedSpeakers','-1','-e','evalCpuPlan','auto_v1','-e','evalAsrPlan',P.ASR_PLAN,'-e','evalDiarPlan',P.PLAN,'-e','evalCollectEvidence','false','-e','class',r.BRIDGE,a.package+'.test/androidx.test.runner.AndroidJUnitRunner',check=False,timeout=a.instrument_timeout_seconds)
                meta['instrumentation_exit_code']=value.returncode;(a.output/'instrumentation.log').write_bytes(value.stdout);(a.output/'instrumentation.stderr').write_bytes(value.stderr)
            except subprocess.TimeoutExpired as error:
                (a.output/'instrumentation.log').write_bytes(error.stdout or b'');(a.output/'instrumentation.stderr').write_bytes(error.stderr or b'');meta['errors'].append({'instrumentation_timeout':True})
            finally:
                stop.set();sampler.join(40);logger.terminate()
                try:logger.wait(10)
                except subprocess.TimeoutExpired:logger.kill();logger.wait()
                pull()
        doc=r.read_json(a.output/'report.json');transient,paired=r.execution_config(checked['config'],4)
        P.validate_native_diar_policy(transient,doc,paired,cpu_plan='auto_v1',threads=4,requested_threads=0);P.equal(doc['cpuPolicy'],CPU,'report CPU')
        ids=[c.get('id')for c in doc['cases']]
        if doc.get('run')!=session or ids!=list(r.CASE_IDS)[:len(ids)]or len(ids)>3 or type(doc.get('processId'))is not int:raise ValueError('Batch identity/order/PID differs')
        seen=set()
        for case in checked['cases'][:len(ids)]:
            identity=case['id'];n,d,h=[r.read_json(a.output/(identity+'.'+s+'.json'))for s in ('case','diagnostics','hypothesis')]
            r.validate_case_copy(n,doc['cases'][len(meta['batches'][0]['cases'])]);counts=compact(case,n,d,h,checked['config'])
            if n['processId']!=doc['processId']or n['workId']in seen or n['recordingId']in seen:raise ValueError('Shared PID/fresh own UUID differs')
            seen.update([n['workId'],n['recordingId']]);reference=checked['inputs'][identity]['reference'];metrics=r.score_case(r.read_json(reference),h,d,n['duration_ms'],n['processing_ms'])
            shutil.copyfile(reference,a.output/(identity+'.reference.json'));r.write_json(a.output/(identity+'.metrics.json'),metrics)
            meta['batches'][0]['cases'].append({'id':identity,'duration_ms':n['duration_ms'],'processing_ms':n['processing_ms'],'metrics':metrics,'compact_evidence':counts,'stages_ms':d.get('stagesMs'),'telemetry':d.get('telemetry'),'work_id':n['workId'],'recording_id':n['recordingId'],'process_id':n['processId']})
            meta.update(verified_workers=len(meta['batches'][0]['cases']),new_model_inference=True);r.write_json(a.output/'run.json',meta)
        raw=(a.output/'instrumentation.log').read_bytes()
        if len(ids)!=3 or doc.get('status')!='COMPLETE'or doc.get('collectEvidence')is not False or doc.get('newModelInference')is not True or meta.get('instrumentation_exit_code')!=0 or not re.search(rb'OK \(1 tests?\)',raw)or re.search(rb'FAILURES!!!|INSTRUMENTATION_FAILED|Process crashed',raw):raise ValueError('Group incomplete/failed; partial verified evidence preserved')
        meta.update(status='COMPLETE',inference_completion_verified=True);meta['summary']=r.batch_summary(meta['batches'][0]['cases'])
    except BaseException as error:meta.update(status='FAILED',error=repr(error))
    finally:
        stop.set()
        if meta['inference_requested']:
            try:meta['model_sha256_after']=models()
            except Exception as error:meta.update(status='FAILED',post_model_hash_error=repr(error))
        try:r.check_unchanged(checked)
        except Exception as error:meta.update(status='FAILED',source_changed_error=repr(error))
        meta['completed_workers']=meta['verified_workers'];meta['inference_may_still_be_running']=meta['inference_requested']and not meta['inference_completion_verified']
        r.write_csv(a.output/'results.csv',meta['batches']);r.write_json(a.output/'run.json',meta)
    print(json.dumps({'status':meta['status'],'verified_workers':meta['verified_workers'],'private_raw_output':True}));return 0 if meta['status']=='COMPLETE'else 1

def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group();g.add_argument('--check',action='store_true');g.add_argument('--execute',action='store_true')
    p.add_argument('--allow-physical',action='store_true');p.add_argument('--serial',required=True);p.add_argument('--adb',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--package',default='ru.replika.offline');p.add_argument('--audio-root',type=Path,default=Path('/home/egor/replika-toolchain/plan19-perf'));p.add_argument('--model-root',type=Path,default=REPO/'model-pack')
    p.add_argument('--manifest',type=Path,default=REPO/'benchmark/eval-perf/manifest.json');p.add_argument('--protocol',type=Path,default=REPO/'benchmark/eval-perf/protocol.json');p.add_argument('--physical-protocol',type=Path,required=True)
    p.add_argument('--app-apk',type=Path,default=REPO/'release/REPLIKA-Hack-Step05-AutoCPU-AllInOne-arm64.apk');p.add_argument('--test-apk',type=Path,default=REPO/'app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk');p.set_defaults(sample_seconds=10,instrument_timeout_seconds=7200)
    return run(p.parse_args())
if __name__=='__main__':raise SystemExit(main())
