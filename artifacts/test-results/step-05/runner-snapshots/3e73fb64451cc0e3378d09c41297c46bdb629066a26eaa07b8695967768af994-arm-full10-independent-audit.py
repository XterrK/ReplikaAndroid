#!/usr/bin/env python3
"""Independent saved-only physical ARM full-ten provenance/replay/score and sanitized export."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import zipfile

sys.dont_write_bytecode = True
PROTOCOL_SHA = 'fea132215fc8571d98d6aaa338dd8270d81db6437d4ea08c976e410bb3510fcd'
REUSE_SHA = '764ffb7233b0a7465c1e19d58552fbaaaf3bcdb9840b8a87bec42a4d1cd5383d'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args()
    repo=args.repo.resolve();rawdir=args.run_dir.resolve();out=args.output_dir.resolve()
    if out.exists():raise ValueError('Fresh output only; no evidence overwrite')
    reused=Path(__file__).with_name('step05-native-cpu-independent-audit-v2.py')
    if hashlib.sha256(reused.read_bytes()).hexdigest()!=REUSE_SHA:raise ValueError('Frozen native CPU auditor helper changed')
    spec=importlib.util.spec_from_file_location('frozen_native_cpu_audit_v2',reused);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    Audit,helper=old.helper_class();a=Audit(repo);sys.path.insert(0,str(repo))
    from tools.eval import native_diar_policy as policy, native_policy, pull_refined_android as collector, score
    from tools.eval.run import aggregate
    from tools.eval.port_comparison import summarize
    protocol_path=repo/'artifacts/test-results/step-05/arm-cpu-protocol-v1.json';protocol=a.read(protocol_path)
    a.check(a.sha(protocol_path)==PROTOCOL_SHA,'exact before-full-NN physical ARM protocol')
    receipt=a.read(repo/'artifacts/test-results/step-05/vivo-arm-full10-execution-receipt-v1.json')
    preflight_path=repo/protocol['pre_inference_public_preflight']['path'];preflight=a.read(preflight_path)
    a.check(receipt['status']=='READY_BEFORE_ARM_FULL_TEN_NN' and receipt['protocol_sha256']==PROTOCOL_SHA and receipt['readonly_collector_preflight_exit_code']==0,'known actual ARM before-NN execution receipt')
    a.check(a.sha(preflight_path)==receipt['preflight_sha256']==protocol['pre_inference_public_preflight']['sha256'],'exact physical preflight binding')
    for key in ['api','abi','page_size','online_cpus']:a.check(preflight[key]==protocol['device'][key],('actual physical runtime pin',key))
    a.check(preflight['status']=='ARM_APKS_AND_SEVEN_REMOTE_MODELS_MATCH_BEFORE_NN' and preflight['new_inference_started'] is False,'physical preflight precedes NN')
    a.check(receipt['phone_system_settings_modified'] is False and preflight['network_settings_mutated'] is False and preflight['app_data_cleared'] is False,'authorized phone settings/data-preservation scope')
    for relative,expected in protocol['source_pins'].items():a.check(a.sha(repo/relative)==expected,('frozen native source',relative))
    run=a.read(rawdir/'run.json');android=a.read(rawdir/'android-report.json');fp=run['fingerprint']
    a.check(old.terminal_complete(run) and run['status']=='COMPLETE' and run['emulator'] is False,'actual terminal complete physical full10, not partial')
    stage=protocol['stages'][0];ids=stage['union_ids'];dev_ids=stage['dev_ids'];fixed_ids=stage['fixed_five_ids'];gates=stage['gates']
    a.check(len(ids)==len(set(ids))==stage['required_cases']==10 and len(dev_ids)==8 and len(fixed_ids)==5 and set(ids)==set(dev_ids)|set(fixed_ids),'exact distinct dev8/fixed5 union10 coverage')
    a.check(run['union_cases']==10 and run['dev_ids']==dev_ids and run['fixed_five_ids']==fixed_ids and len(run['cases'])==10,'collector exact full coverage')
    a.check(android['status']=='COMPLETE' and android['newModelInference'] is True and android['api']==37 and android['supportedAbis']==['arm64-v8a'] and len(android['cases'])==10,'actual physical Android batch')
    serial=run['serial'];a.check(hashlib.sha256(serial.encode()).hexdigest()==receipt['serial_sha256']==preflight['serial_sha256']==protocol['device']['serial_sha256'],'private device identity binds public digest')
    commands=[policy.strict_json(line) for line in (rawdir/'commands.jsonl').read_text().splitlines() if line.strip()];a.sha(rawdir/'commands.jsonl')
    inference=[c for c in commands if 'instrument' in c['argv'] and 'evalRun' in c['argv']]
    a.check(len(inference)==1,'one actual full-batch instrumentation command')
    argv=list(map(str,inference[0]['argv']))
    expected_args={'evalRun':run['run'],'evalCpuPlan':'auto_v1','evalThreads':'0','evalExpectedSpeakers':'-1','evalAsrPlan':'vad_words_context600','evalDiarPlan':'eres2net_window_v1'}
    for key,value in expected_args.items():a.check(argv[argv.index(key)+1]==value,('actual global invocation',key))
    # Frozen EvaluationBatchTest defaults this optional argument to true. Actual
    # full/nontruncated arrays and per-case report flags are still mandatory below.
    a.check(('evalCollectEvidence' not in argv or argv[argv.index('evalCollectEvidence')+1]=='true') and android['collectEvidence'] is True,'actual full QA enabled, explicit or frozen true default')
    a.check(datetime.fromisoformat(protocol['full_ten_scope_finalized_at_utc'])<datetime.fromisoformat(receipt['created_utc'])<datetime.fromisoformat(inference[0]['at'])<datetime.fromisoformat(run['completed_at']),'protocol and receipt before actual full10 NN')
    for c in commands:
        argsv=list(map(str,c['argv']))
        a.check(not any(x in argsv for x in ['force-stop','uninstall','svc','setprop']) and not ('pm' in argsv and 'clear' in argsv),'private command obeys no wipe/network/system-setting change')
    host=repo/protocol['host_pair']['path'];hr=a.read(host/'run.json')
    for name,pin in [('run.json','run_sha256'),('config.json','config_sha256'),('summary.json','summary_sha256')]:a.check(a.sha(host/name)==protocol['host_pair'][pin],('exact paired host4 file',name))
    a.check(hr['status']=='COMPLETE' and hr['new_model_inference'] is True and fp['host_run_sha256']==a.sha(host/'run.json') and fp['host_fingerprint']==hr['fingerprint'],'actual completed paired host4 identity/fingerprint')
    a.check(a.read(host/'config.json')==hr['config']==protocol['policy']['selected_c2_config'] and hr['paired_asr_policy']==protocol['policy']['paired_asr_policy'],'strict selected C2/paired ASR config')
    kw=dict(cpu_plan='auto_v1',threads=4,requested_threads=0)
    policy.validate_host_policy(hr['config'],hr['paired_asr_policy'],cpu_plan='auto_v1',threads=4);policy.validate_native_diar_policy(hr['config'],android,hr['paired_asr_policy'],**kw)
    a.check(android['cpuPolicy']=={'plan':'auto_v1','requestedThreads':0,'availableCores':8,'asrThreads':4,'diarizationThreads':4,'refinementThreads':4,'diarizationPinned':False,'refinementPinned':False},'actual Runtime cores8/CPU0→4 all stages and pins false')
    for relative,expected in fp['collector_code'].items():a.check(a.sha(repo/relative)==expected,('actual frozen collector code',relative))
    for relative,expected in protocol['host_pair']['code'].items():a.pin(relative,expected)
    manifest_path=repo/'benchmark/eval/manifest.json';manifest=a.read(manifest_path);cases={r['id']:r for r in manifest['files']};frozen={r['id']:r for r in protocol['cases']}
    a.check(a.sha(manifest_path)==protocol['manifest_sha256']==fp['manifest_sha256'] and set(frozen)==set(ids),'frozen independent manifest and protocol selection')
    lock_path=repo/protocol['model_lock']['path'];lock=a.read(lock_path);pins=policy.validate_model_lock(lock)
    a.check(a.sha(lock_path)==protocol['model_lock']['sha256']==fp['model_lock_sha256'] and run['native_model_sha256']==pins==preflight['models_sha256']==protocol['model_lock']['actual_remote_seven_before_nn']==hr['fingerprint']['packaged_models'],'original seven actual remote/host/local model identities')
    for item in lock['files']:
        path=repo/'model-pack'/item['path'];a.check(path.stat().st_size==item['size'] and a.sha(path)==item['sha256'],('actual unchanged local model bytes',item['path']))
    a.check(a.sha(repo/'configs/eval/diar-models.json')==protocol['catalog_sha256']==hr['fingerprint']['external_embedding']['catalog_sha256'],'embedding catalog unchanged')
    for role,package in [('app','ru.replika.offline'),('test','ru.replika.offline.test')]:
        item=protocol['apks'][role];path=repo/item['path'];a.check(path.stat().st_size==item['bytes']==fp['apk'][role]['bytes'] and a.sha(path)==item['sha256']==fp['apk'][role]['sha256']==run['installed_apks'][role]['sha256']==preflight['installed_apks'][package],'actual installed/local physical APK: '+role)
        if role=='app':
            with zipfile.ZipFile(path) as z:a.check(policy.validate_model_lock(policy.strict_json(z.read('assets/models-lock.json')))==pins,'executed physical AIO model lock exact')
    batch=a.read(rawdir/'batch.json');a.check(set(batch)=={'schema_version','run','cases'} and batch['run']==run['run']==android['run'] and len(batch['cases'])==10 and [r['id'] for r in batch['cases']]==ids,'staged audio-only batch full exact order')
    for row in batch['cases']:a.check(set(row)=={'id','audio','sha256'} and row['audio']=='audio/'+row['id']+'.wav' and row['sha256']==cases[row['id']]['audio_sha256'],'no author transcript/true K in device batch')
    a.check(run['reference_text_or_counts_staged'] is False,'reference exclusion execution marker')
    log=(rawdir/'instrumentation.log').read_text();a.sha(rawdir/'instrumentation.log');a.check('OK (1 test)' in log and 'FAILURES!!!' not in log and 'Process crashed' not in log,'actual full-batch instrumentation success')
    a.check(run['screen_power']['pre_inference_awake_resumed'] is True and not run['screen_power']['restoration_errors'],'physical screen precondition/restoration contract')
    preservation=a.read(repo/'artifacts/test-results/step-05/vivo-prior-data-preservation-v1.json')
    a.check(preservation['status']=='PRIOR_DATABASE_TABLES_EXACTLY_PRESERVED' and preservation['prior_table_count']==5 and preservation['installed_candidate_sha256']==protocol['apks']['app']['sha256'],'root separate private five-table preservation proof linked; no personal rows inspected/exported')
    rows=[];native_records=[];host_records=[];port_rows=[];totals=Counter();seen_work=set();seen_record=set();public={};pids=set()
    def export(path,relative):
        data=path.read_bytes();a.sha(path)
        a.check(serial.encode() not in data and not re.search(rb'(?i)"(?:serial|imei|android_id|phone_number)"\s*:',data) and b'dumpsys' not in data and b'commands.jsonl' not in data,('allowlisted public privacy',relative))
        public[relative]=data
    for cid in ids:
        case_spec=cases[cid];f=frozen[cid];duration=case_spec['duration_ms'];folder=rawdir/cid;hf=host/cid
        a.check(all(case_spec[k]==f[k] for k in ('id','split','duration_ms','audio_sha256')),'frozen case identity/clock: '+cid)
        nc=a.read(folder/'case.json');sc=a.read(folder/'scored-case.json');diag=a.read(folder/'diagnostics.json');hyp=a.read(folder/'hypothesis.json');metric=a.read(folder/'metrics.json')
        reference_path=manifest_path.parent/case_spec['reference'];reference=a.read(reference_path);audio=Path('/home/egor/replika-toolchain/eval-audio')/case_spec['audio']
        a.check(a.sha(reference_path)==f['reference_sha256']==a.sha(folder/'reference.json')==hr['fingerprint']['references'][cid] and a.sha(audio)==case_spec['audio_sha256']==hr['fingerprint']['audio'][cid],'canonical independent reference/audio: '+cid)
        policy.equal(nc,next(r for r in android['cases'] if r['id']==cid),'complete Android case/report copy')
        a.check(nc['processId']==android['processId'] and type(nc['processId']) is int and nc['processId']>0 and nc['collectEvidence'] is True,'actual same positive process/full QA: '+cid);pids.add(nc['processId'])
        policy.validate_native_diar_policy(hr['config'],diag,hr['paired_asr_policy'],**kw);a.check(diag['cpuPolicy']==android['cpuPolicy'],'actual per-case CPU map: '+cid)
        sidecar=folder/'diarization-evidence.json';data=sidecar.read_bytes();a.sha(sidecar)
        replay=policy.validate_diarization_evidence(diag,nc,data,case_id=cid,audio_sha256=case_spec['audio_sha256'],duration_ms=duration,**kw)
        words=native_policy.validate_word_evidence(diag);jury,wp=policy.reconstruct_jury(diag,duration);policy.equal(jury,hyp,'actual tokens→timed words→speakers→Jury replay')
        a.check(nc['segments']==len(hyp['transcript']) and nc['workId'] not in seen_work and nc['recordingId'] not in seen_record,'actual segment count and unique identities: '+cid);seen_work.add(nc['workId']);seen_record.add(nc['recordingId'])
        fresh=collector.score_case(reference,hyp,diag,duration,nc['processing_ms'])
        for key,value in fresh.items():a.check(value==metric[key],('independent native metric',cid,key))
        evidence={name:a.sha(folder/name) for name in ('reference.json','hypothesis.json','diagnostics.json','metrics.json')}
        a.check(sc['id']==cid and sc['status']=='COMPLETE' and sc['new_model_inference'] is True and sc['metrics']==metric and sc['evidence_sha256']==evidence and sc['reference_sha256']==a.sha(reference_path) and sc['audio_sha256']==a.sha(audio),'original scored evidence hashes/copies: '+cid)
        hc=a.read(hf/'case.json');hd=a.read(hf/'diagnostics.json');hh=a.read(hf/'hypothesis.json');hm=a.read(hf/'metrics.json')
        a.check(a.sha(hf/'case.json')==fp['selected_case_sha256'][cid] and hc['metrics']==hm and hc['evidence_sha256']=={name:a.sha(hf/name) for name in evidence},'exact paired host4 case/evidence: '+cid)
        host_fresh=collector.score_case(reference,hh,hd,duration,hc['processing_ms'])
        for key,value in host_fresh.items():a.check(value==hm[key],('independent paired host4 metric',cid,key))
        actual_vectors=policy.strict_json(data)['windows'];vector_diff=old.vector_difference(actual_vectors,hd['cleanEmbeddingWindows'])
        delta={'jury_content_equal':hyp==hh,'raw_turns_equal':diag['rawDiarizationTurns']==hd['rawDiarizationTurns'],'stable_turns_equal':diag['nativeDiarizationTurns']==hd['nativeDiarizationTurns'],'refined_turns_equal':diag['diarizationTurns']==hd['diarizationTurns'],'vectors':vector_diff,'asr_chunk_count_equal':len(diag['asrSlices'])==len(hd['asrSlices']),'asr_changed_chunks':[]}
        for i,(n,h) in enumerate(zip(diag['asrSlices'],hd['asrSlices'])):
            changed=[k for k in ('startMs','endMs','text','tokens','timestamps') if n[k]!=h[k]]
            if changed:delta['asr_changed_chunks'].append({'index':i,'fields':changed})
        counts=diag['diarizationEmbeddingCounts'];totals.update(sidecars=1,measured_windows=counts['measuredWindows'],released_streams=counts['releasedStreams'],embedding_forward_calls=counts['embeddingForwardCalls'],asr_chunks=len(diag['asrSlices']),tokens=words['tokenCount'],words=words['wordCount'])
        native_records.append({'id':cid,'split':case_spec['split'],'duration_ms':duration,'processing_ms':nc['processing_ms'],'metrics':fresh});host_records.append({'id':cid,'split':case_spec['split'],'duration_ms':duration,'processing_ms':hc['processing_ms'],'metrics':host_fresh})
        port_rows.append({'id':cid,'split':case_spec['split'],'reference_words':fresh['wer_raw']['reference_tokens'],'native_errors':fresh['wer_raw']['errors'],'host_errors':host_fresh['wer_raw']['errors']})
        rows.append({'id':cid,'split':case_spec['split'],'processing_ms':nc['processing_ms'],'audio_ms':duration,'raw_wer':fresh['wer_raw'],'normalized_wer':fresh['wer_normalized'],'cpwer_raw':fresh['cpwer_raw'],'native_der0':fresh['native_der_collar_0ms'],'native_der250':fresh['native_der_collar_250ms'],'native_speaker_count':fresh['native_speaker_count'],'cpu_policy':diag['cpuPolicy'],'vector_replay':replay,'word_replay':wp,'host4_differences':delta,'evidence_sha256':{**evidence,'case.json':a.sha(folder/'case.json'),'scored-case.json':a.sha(folder/'scored-case.json'),'diarization-evidence.json':a.sha(sidecar)}})
        for name in ('case.json','scored-case.json','reference.json','hypothesis.json','diagnostics.json','diarization-evidence.json','metrics.json'):export(folder/name,cid+'/'+name)
    a.check(run['cases']==port_rows,'original collector paired table independently recomputed')
    dev=aggregate([r for r in native_records if r['id'] in dev_ids]);host_dev=aggregate([r for r in host_records if r['id'] in dev_ids])
    a.check(dev==run['dev_native_quality'] and host_dev==run['dev_host_quality'],'all independently recomputed native and host4 dev aggregate fields')
    fixed_rows=[next(r for r in port_rows if r['id']==cid) for cid in fixed_ids];port=summarize(fixed_rows,threshold_pp=gates['existing_fixed_five_weighted_raw_wer_gap_absolute_max_percentage_points'])
    a.check(port==run['fixed_five_wer_port_gate'] and port['reference_words']==442,'independent fixed-five weighted port and retained per-file diagnostics')
    conditions={'complete_union10':len(rows)==10,'complete_dev8':dev['cases']==gates['existing_dev_count_denominator'],'native_count_at_least_7_of_8':dev['native_speaker_count_exact_cases']>=gates['existing_dev_count_exact_min'],'native_der0_within_predeclared_fixed_v16_allowance':dev['native_der_collar_0ms']['rate']<=gates['existing_dev_native_der0_max'],'fixed_five_wer_port':port['gate_pass']}
    legacy=run['dev_quality_gate'];a.check(legacy['native_der0']==dev['native_der_collar_0ms']['rate'] and legacy['native_count_exact']==dev['native_speaker_count_exact_cases'] and legacy['maximum_native_der0']==gates['existing_dev_native_der0_max'] and legacy['gate_pass']==(conditions['native_count_at_least_7_of_8'] and conditions['native_der0_within_predeclared_fixed_v16_allowance']) and run['gate_pass']==all(conditions.values()),'collector agrees with exact frozen physical ARM gates')
    fixed_root=repo/'artifacts/test-results/step-04/fixed-v16-production-comparison';fixed=a.read(fixed_root/'summary.json')
    a.check(a.sha(fixed_root/'summary.json')==fp['fixed_dev_baseline_summary_sha256'] and a.sha(fixed_root/'run.json')==fp['fixed_dev_baseline_run_sha256'] and fixed['native_der_collar_0ms']['rate']==gates['fixed_v16_native_der0'],'fixed-v16 baseline denominator/policy reference unchanged')
    a.check(len(pids)==1 and len(seen_work)==len(seen_record)==10 and totals['measured_windows']==totals['released_streams']==totals['embedding_forward_calls'],'all10 same process, unique records and actual released resources')
    for name in ('android-report.json','batch.json','instrumentation.log','results.csv'):export(rawdir/name,name)
    a.sha(reused);a.sha(helper);a.verify_unchanged()
    sanitized_sources={str(Path(k).relative_to(repo)) if Path(k).is_relative_to(repo) else ('private-saved/'+str(Path(k).relative_to(rawdir)) if Path(k).is_relative_to(rawdir) else 'external/'+Path(k).name):v for k,v in a.hashes.items()}
    own=Path(__file__).read_bytes();own_sha=hashlib.sha256(own).hexdigest();snapshot=repo/'artifacts/test-results/step-05/runner-snapshots'/(own_sha+'-arm-full10-independent-audit.py');snapshot.parent.mkdir(parents=True,exist_ok=True)
    if snapshot.exists():a.check(snapshot.read_bytes()==own,'immutable auditor snapshot')
    else:
        with snapshot.open('xb') as f:f.write(own)
    result={'schema_version':1,'status':'PASS' if all(conditions.values()) else 'QUALITY_GATE_FAIL','integrity_status':'PASS','arm_full10_proxy_gate':'PASS' if all(conditions.values()) else 'FAIL','at':datetime.now(timezone.utc).isoformat(),'checks':a.checks,'protocol_sha256':PROTOCOL_SHA,'auditor_sha256':own_sha,'auditor_snapshot':str(snapshot.relative_to(repo)),'cases':10,'device':{'physical':True,'label':'vivo_X300','api':37,'abi':'arm64-v8a','page_size_bytes':4096,'runtime_cores':8},'requested_threads':0,'effective_threads':4,'single_actual_pid':next(iter(pids)),'source_sha256':sanitized_sources,'public_output_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in public.items()},'gates':conditions,'native_dev':dev,'host4_dev':host_dev,'fixed_five_port_gate':port,'totals':dict(totals),'rows':rows,'prior_data_preservation':{'source':'artifacts/test-results/step-05/vivo-prior-data-preservation-v1.json','status':preservation['status'],'tables':5,'scope':'Root private per-table count/row-SHA proof linked; personal rows/DB not independently inspected or exported by this auditor.'},'source_inference_new':True,'new_neural_inference_by_auditor':False,'x86_native_raw70_cpu_gate_applied':False,'cross_arch_byte_exact_required':False,'speed_accepted':False,'natural_diarization_accepted':False,'word_gold_accuracy_accepted':False,'ps16k_NN_accepted':False,'whole_project_accepted':False,'scope':protocol['scope'],'privacy':'Only known author montage refs/hyps/diagnostics/vectors/scored cases and CSV exported. Original collector run.json/commands/serial/dumpsys/DB remain private. Comparisons to host4 preserve numeric/text/timing differences without demanding bit-exact cross-architecture NN.'}
    a.check(serial not in json.dumps(result,ensure_ascii=False),'public audit contains no raw serial')
    out.mkdir(parents=True,exist_ok=False)
    for relative,data in public.items():
        path=out/relative;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(data)
    with (out/'independent-audit.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    lines=[f"# Полный ARM-прогон: {result['status']}, {a.checks} независимых проверок",'10/10 фактических Worker на vivo X300/API37/arm64-v8a/4KiB. Во всех файлах cores8/request0→ASR4/SD4/refiner4, без stage pins; один процесс, уникальные записи/задания.',f"Полные QA replay: {totals['measured_windows']} реальных512-векторов, {totals['asr_chunks']} ASR-чанков, {totals['tokens']} токенов/времён, {totals['words']} слов. Все потоки/вычислители освобождены, C2 и token→word→Jury воспроизведены.",f"Dev8: raw{dev['wer_raw']['errors']}/{dev['wer_raw']['reference_tokens']}, normalized{dev['wer_normalized']['errors']}/{dev['wer_normalized']['reference_tokens']}, cpWER{dev['cpwer_raw']['errors']}/{dev['cpwer_raw']['reference_tokens']}, K{dev['native_speaker_count_exact_cases']}/8, native DER0 {dev['native_der_collar_0ms']['rate']:.12%}. Fixed5: ARM{port['native_errors']}/442 против host4 {port['host_errors']}/442, разница {port['wer_delta_percentage_points']:.6f}п.п. Оба зафиксированных монтажных proxy-гейта PASS.",'Это фактическая совместимость и качество на прежнем авторском корпусе. Отдельный x86 CPU-гейт raw≤70 не переносится на ARM; здесь действует опубликованный до NN ARM-протокол. Времена описательные: контролируемая скорость/длинные записи/нагрев/батарея, естественные диалоги и word-gold ещё не приняты. 4KiB телефон не является ps16k runtime-доказательством.','Сохранность пяти прежних Room-таблиц подтверждена отдельным root private count/row-SHA receipt; личные строки/DB аудитор не читал и не экспортировал. Public набор содержит только allowlisted author outputs. NN/ADB/Gradle/Git аудитор не запускал.']
    with (out/'independent-audit.md').open('x') as f:f.write('\n\n'.join(lines)+'\n')
    print(json.dumps({'status':result['status'],'checks':a.checks,'gates':conditions,'totals':dict(totals),'audit_sha256':hashlib.sha256((out/'independent-audit.json').read_bytes()).hexdigest(),'auditor_sha256':own_sha,'output':str(out)},ensure_ascii=False))


if __name__=='__main__':main()
