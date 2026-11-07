#!/usr/bin/env python3
"""Saved native CPU evidence only: hashes/replay/rescore and frozen new CPU gates. No NN/ADB."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True
PROTOCOL_SHA = '129f4fb4e147af26345c3a80e9d8bfe0d48d7a60c34def4627f4c672c0551ed0'
HELPER_SHA = '11fc1e516a2a0663ce950e755833b1cb9c9fd86b9c07ffba45a795239772b929'


def cpu_conditions(current, baseline, epsilon=1e-12):
    conditions = {'complete_dev8': current.get('cases') == baseline.get('cases') == 8}
    for key in ('wer_raw', 'wer_normalized', 'cpwer_raw'):
        value, prior = current[key], baseline[key]
        conditions[key + '_exact_denominator'] = type(value['reference_tokens']) is int and value['reference_tokens'] == prior['reference_tokens']
        conditions[key + '_errors_nonregression'] = type(value['errors']) is int and value['errors'] <= prior['errors']
    conditions['cpwer_raw_rate_nonregression'] = current['cpwer_raw']['rate'] <= baseline['cpwer_raw']['rate'] + epsilon
    conditions['native_der_exact_denominator'] = current['native_der_collar_0ms']['reference_speaker_ms'] == baseline['native_der_collar_0ms']['reference_speaker_ms']
    conditions['native_der0_nonregression'] = current['native_der_collar_0ms']['rate'] <= baseline['native_der_collar_0ms']['rate'] + epsilon
    conditions['native_count_exact_nonregression'] = type(current['native_speaker_count_exact_cases']) is int and current['native_speaker_count_exact_cases'] >= baseline['native_speaker_count_exact_cases']
    return conditions


def terminal_complete(value):
    return (value.get('status') in ('COMPLETE', 'PORT_PARITY_FAIL', 'C2_QUALITY_FAIL')
            and value.get('new_model_inference') is True and value.get('inference_requested') is True
            and not value.get('failures') and len(value.get('cases', [])) == 10)


def strict_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def receipt_matches(receipt, control, threads, requested, host_variant):
    if type(threads) is not int or type(requested) is not int or type(host_variant) is not str:
        return False
    if control == 'explicit-two':
        return (receipt.get('status') == 'READY_BEFORE_FIRST_NATIVE_CPU_NN'
                and threads == 2 and requested == 2 and host_variant == '2')
    if control == 'automatic-runtime-cores':
        return (receipt.get('status') == 'READY_BEFORE_FIRST_NATIVE_AUTOMATIC_CPU_NN'
                and threads == 1 and requested == 0 and host_variant == '1')
    return False


def helper_class():
    path = Path(__file__).with_name('step05-independent-cpu-audit.py')
    if hashlib.sha256(path.read_bytes()).hexdigest() != HELPER_SHA:
        raise ValueError('Frozen hash/provenance helper changed')
    spec = importlib.util.spec_from_file_location('frozen_step05_hash_audit', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    class Evidence(module.Audit):
        def read(self, path):
            self.sha(path)
            return strict_json(Path(path).read_bytes())
    return Evidence, path


def vector_difference(left, right):
    key = lambda w: (w['start_ms'], w['end_ms'], w['speaker'])
    a, b = {key(w): w['embedding'] for w in left}, {key(w): w['embedding'] for w in right}
    common = sorted(a.keys() & b.keys())
    differences = [abs(x-y) for clock in common for x,y in zip(a[clock],b[clock])]
    return {'native_windows':len(a),'host_windows':len(b),'layout_equal':a.keys()==b.keys(),
            'common_windows':len(common),'exact_common_windows':sum(a[k]==b[k] for k in common),
            'maximum_absolute_difference':max(differences,default=None)}


def audit(args, a, helper):
    repo, out = args.repo, args.run
    sys.path.insert(0, str(repo))
    from tools.eval import native_diar_policy as policy, score
    from tools.eval.run import aggregate
    from tools.eval.port_comparison import summarize

    protocol_path = repo/'artifacts/test-results/step-05/cpu-native-before-nn-protocol-v1.json'
    protocol = a.read(protocol_path)
    a.check(a.sha(protocol_path)==PROTOCOL_SHA,'immutable before-NN native CPU protocol')
    control = next(c for c in protocol['planned_native_controls'] if c['id']==args.control)
    threads, requested = control['expected_effective_threads'],control['requested_threads']
    cpu = {'cpu_plan':'auto_v1','threads':threads,'requested_threads':requested}
    run = a.read(out/'run.json')
    a.check(terminal_complete(run),'terminal complete supported full10 required; RUNNING is never audited as complete')
    host_spec = protocol['host_thread_variants'][str(threads)]
    host = repo/host_spec['run']; host_run = a.read(host/'run.json')
    android = a.read(out/'android-report.json'); fp=run['fingerprint']
    manifest_path=repo/protocol['case_manifest']; manifest=a.read(manifest_path); cases={c['id']:c for c in manifest['files']}
    ids,dev_ids,fixed_ids=protocol['union_ids'],protocol['dev_ids'],protocol['fixed_five_ids']
    a.check(len(ids)==len(set(ids))==10 and len(dev_ids)==8 and len(fixed_ids)==5 and ids==dev_ids+[i for i in fixed_ids if i not in dev_ids],'fixed exact dev8/five union10')
    a.check(run['dev_ids']==dev_ids and run['fixed_five_ids']==fixed_ids and len(run['cases'])==10 and {r['id'] for r in run['cases']}==set(ids),'collector complete coverage')
    a.check(android['status']=='COMPLETE' and android['newModelInference'] is True and android['run']==run['run'] and len(android['cases'])==10 and {r['id'] for r in android['cases']}==set(ids),'actual Android report exact full10')
    a.check(run['reference_text_or_counts_staged'] is False and run['expected_speakers']==-1 and run['emulator'] is True and run['requested_cpu_plan']=='auto_v1' and run['requested_threads']==requested and run['expected_effective_threads']==run['threads']==threads,'automatic requested/effective execution scope')
    a.check(run['full_project_accepted'] is False and run['arm_phone_performance_accepted'] is False and android['supportedAbis'][0]=='x86_64','limited actual x86 scope')
    a.check(a.sha(manifest_path)==protocol['manifest_sha256']==fp['manifest_sha256'] and a.sha(host/'run.json')==host_spec['run_sha256']==fp['host_run_sha256'] and host_run['fingerprint']==fp['host_fingerprint'],'manifest/paired-host pins')
    host_audit=a.read(repo/host_spec['independent_audit'])
    a.check(a.sha(repo/host_spec['independent_audit'])==host_spec['independent_audit_sha256'] and host_audit['quality_gate']=='PASS' and host_audit['cases']==13 and host_audit['run_sha256']==fp['host_run_sha256'],'before-native independent paired host quality proof')
    a.check(host_run['status']=='COMPLETE' and host_run['new_model_inference'] is True and a.read(host/'config.json')==host_run['config'] and a.sha(host/'config.json')==host_spec['config_sha256'],'actual fresh CPU host configuration')
    policy.validate_host_policy(host_run['config'],host_run['paired_asr_policy'],cpu_plan='auto_v1',threads=threads)
    policy.validate_native_diar_policy(host_run['config'],android,host_run['paired_asr_policy'],**cpu)
    receipt=a.read(args.receipt); preflight=receipt['preflight']
    a.check(receipt_matches(receipt,args.control,threads,requested,control['host_variant']) and receipt['native_protocol_sha256']==PROTOCOL_SHA and preflight['status']=='PREFLIGHT_PASS' and preflight['fingerprint']==fp and preflight['cases']==ids,'before-NN execution receipt binds exact host/APK/sources/selection')
    if args.control == 'automatic-runtime-cores':
        control_path = (repo / receipt['control_run']).resolve()
        a.check(control_path.is_relative_to(repo/'artifacts/test-results/step-05') and a.sha(control_path/'run.json')==receipt['control_run_sha256'],'automatic execution receipt binds preceding actual control2 run')
        prior_control = a.read(control_path/'independent-cpu-audit-v1.json')
        a.check(prior_control['status']=='PASS' and prior_control['native_cpu_acceptance']=='PASS' and prior_control['control']=='explicit-two' and prior_control['protocol_sha256']==PROTOCOL_SHA and prior_control['run_sha256']==receipt['control_run_sha256'] and prior_control['auditor_source_sha256']=='9dc7f6a5538ed1835aea26ce008892f2a8412c098244df16c16915511365fa62','automatic run follows independently accepted same-protocol explicit2 control')
    if args.preflight is not None:
        a.check(a.sha(args.preflight)==receipt['preflight_sha256'] and a.read(args.preflight)==preflight,'exact original preflight file bytes')
    commands=[strict_json(line) for line in (out/'commands.jsonl').read_text().splitlines() if line.strip()]
    a.sha(out/'commands.jsonl')
    inference=[c for c in commands if 'instrument' in c['argv'] and 'evalRun' in c['argv']]
    a.check(len(inference)==1,'one actual batch instrumentation command')
    argv=list(map(str,inference[0]['argv']))
    a.check(argv[argv.index('evalCpuPlan')+1]=='auto_v1' and argv[argv.index('evalThreads')+1]==str(requested) and argv[argv.index('evalExpectedSpeakers')+1]=='-1','actual staged CPU request and automatic K')
    a.check(datetime.fromisoformat(protocol['frozen_at'])<datetime.fromisoformat(receipt['at'])<datetime.fromisoformat(inference[0]['at']),'protocol and exact execution receipt before actual NN')
    for relative, expected in protocol['collector_code_sha256'].items():
        a.check(fp['collector_code'][relative]==expected,'predeclared collector pin')
    for relative,expected in fp['collector_code'].items():
        a.pin(relative,expected);a.check(a.sha(repo/relative)==expected,('actual collector semantics still frozen',relative))
    for relative,expected in host_run['fingerprint']['code'].items():a.pin(relative,expected)
    lock_path=repo/'app/src/main/assets/models-lock.json';lock=a.read(lock_path);pins=policy.validate_model_lock(lock)
    a.check(a.sha(lock_path)==protocol['model_lock_sha256']==fp['model_lock_sha256'] and pins==run['native_model_sha256']==host_run['fingerprint']['packaged_models'],'original seven actual remote/local/host model pins')
    for item in lock['files']:
        path=repo/'model-pack'/item['path'];a.check(path.stat().st_size==item['size'] and a.sha(path)==item['sha256'],('actual local model bytes',item['path']))
    a.check(a.sha(repo/'configs/eval/diar-models.json')==host_run['fingerprint']['external_embedding']['catalog_sha256'],'catalog unchanged')
    build=a.read(repo/'artifacts/test-results/step-05/build-auto-v2/summary.json');test_build=a.read(repo/'artifacts/test-results/step-05/build-test-v3/summary.json')
    a.check(build['status']==test_build['status']=='PASS' and build['gradle_exit_code']==test_build['gradle_exit_code']==0 and build['build_flags']=={'replikaAsrPlan':'vad_words_context600','replikaDiarPlan':'eres2net_window_v1','replikaCpuPlan':'auto_v1'},'actual compiled explicit candidate proof')
    changed_test='app/src/androidTest/java/ru/replika/CpuThermalPlan19Test.kt'
    for relative,expected in build['source_sha256'].items():
        a.check(a.sha(repo/relative)==(test_build['fixed_source_sha256'] if relative==changed_test else expected),('compiled source/test repair pin',relative))
    for role,spec in [('app',test_build['main_apks_unchanged']['debug']),('test',test_build['androidTest'])]:
        path=repo/spec['path'];a.check(path.stat().st_size==fp['apk'][role]['bytes'] and a.sha(path)==spec['sha256']==fp['apk'][role]['sha256']==run['installed_apks'][role]['sha256'],('actual installed/local compiled APK',role))
        if role=='app':
            with zipfile.ZipFile(path) as archive:a.check(policy.validate_model_lock(policy.strict_json(archive.read('assets/models-lock.json')))==pins,'actual installed APK model lock')
    aio=repo/build['preserved_release_path'];a.check(a.sha(aio)==build['apks']['allInOne']['sha256']==test_build['main_apks_unchanged']['allInOne']['sha256'],'preserved AIO unchanged; not executed ARM proof')
    batch=a.read(out/'batch.json');a.check(set(batch)=={'schema_version','run','cases'} and batch['run']==run['run'] and len(batch['cases'])==10 and {r['id'] for r in batch['cases']}==set(ids),'audio-only batch exact coverage')
    for row in batch['cases']:a.check(set(row)=={'id','audio','sha256'} and row['audio']=='audio/'+row['id']+'.wav' and row['sha256']==cases[row['id']]['audio_sha256'],'no gold text or K staged')
    for name in ('instrumentation.log','power-before.txt','power-pre-inference.txt','activity-pre-inference.txt','power-after.txt'):a.sha(out/name)
    log=(out/'instrumentation.log').read_text();a.check('OK (1 test)' in log and 'FAILURES!!!' not in log,'actual instrumentation completed')
    screen=run['screen_power'];a.check(screen['pre_inference_awake_resumed'] is True and screen['original_stay_on_while_plugged_in']==screen['restored_stay_on_while_plugged_in'] and not screen['restoration_errors'],'original screen-power state restored')
    baseline=repo/protocol['baseline']['run'];a.check(a.sha(baseline/'run.json')==protocol['baseline']['run_sha256'] and a.sha(baseline/'independent-audit.json')==protocol['baseline']['independent_audit_sha256'],'exact frozen actual native C2 baseline')
    baseline_specs={r['id']:r for r in protocol['baseline']['cases']}
    native_records=[];baseline_records=[];comparison=[];rows=[];totals=Counter();seen_work=set();seen_recording=set()
    def native_rows(turns):return [{'speaker_id':'native_'+str(t.speaker),'start_ms':t.start_ms,'end_ms':t.end_ms,'text':''} for t in turns]
    for cid in ids:
        spec=cases[cid];folder=out/cid;old_folder=baseline/cid;duration=spec['duration_ms']
        native_case=a.read(folder/'case.json');scored=a.read(folder/'scored-case.json');diag=a.read(folder/'diagnostics.json');hyp=a.read(folder/'hypothesis.json');metric=a.read(folder/'metrics.json')
        reference_path=manifest_path.parent/spec['reference'];reference=a.read(reference_path);audio=Path('/home/egor/replika-toolchain/eval-audio')/spec['audio']
        a.check(a.sha(reference_path)==a.sha(folder/'reference.json')==host_run['fingerprint']['references'][cid] and a.sha(audio)==spec['audio_sha256']==host_run['fingerprint']['audio'][cid],'canonical independent reference/audio hashes')
        for name,expected in baseline_specs[cid]['baseline_evidence_sha256'].items():a.check(a.sha(old_folder/name)==expected,('frozen native baseline per-case evidence',cid,name))
        policy.equal(native_case,next(r for r in android['cases'] if r['id']==cid),'native case/report copy')
        policy.validate_native_diar_policy(host_run['config'],diag,host_run['paired_asr_policy'],**cpu)
        a.check(diag['cpuPolicy']==android['cpuPolicy'],'per-case CPU selection equals actual batch Runtime CPU policy')
        sidecar=folder/'diarization-evidence.json';a.sha(sidecar);raw=sidecar.read_bytes()
        replay=policy.validate_diarization_evidence(diag,native_case,raw,case_id=cid,audio_sha256=spec['audio_sha256'],duration_ms=duration,**cpu)
        wrapper=policy.strict_json(raw)
        a.check(native_case['workId'] not in seen_work and native_case['recordingId'] not in seen_recording,'unique actual UUID identities')
        seen_work.add(native_case['workId']);seen_recording.add(native_case['recordingId'])
        reconstructed,word_proof=policy.reconstruct_jury(diag,duration);policy.equal(reconstructed,hyp,'actual tokens→words→speakers→Jury replay')
        a.check(native_case['segments']==len(hyp['transcript']),'actual exported segment count')
        fresh=score.score(reference,hyp,duration,native_case['processing_ms'])
        for key,value in fresh.items():a.check(value==metric[key],('independent native metric',cid,key))
        turns=policy.turns_from_json(diag['diarizationTurns'],duration)
        for collar in (0,250):a.check(score.der(reference['transcript'],native_rows(turns),duration,collar)==metric[f'native_der_collar_{collar}ms'],('independent native DER',cid,collar))
        count=len({t.speaker for t in turns});a.check(metric['native_speaker_count']==count and metric['native_speaker_count_error']==abs(count-fresh['speakers']['reference']),'native K from actual turns')
        evidence={name:a.sha(folder/name) for name in ('reference.json','hypothesis.json','diagnostics.json','metrics.json')}
        a.check(scored['status']=='COMPLETE' and scored['new_model_inference'] is True and scored['id']==cid and scored['metrics']==metric and scored['evidence_sha256']==evidence and scored['reference_sha256']==a.sha(reference_path) and scored['audio_sha256']==a.sha(audio),'scored evidence hashes/copies')
        host_folder=host/cid;host_case=a.read(host_folder/'case.json');host_diag=a.read(host_folder/'diagnostics.json');host_metric=a.read(host_folder/'metrics.json');host_hyp=a.read(host_folder/'hypothesis.json')
        a.check(a.sha(host_folder/'case.json')==fp['selected_case_sha256'][cid] and host_case['metrics']==host_metric and host_case['evidence_sha256']=={name:a.sha(host_folder/name) for name in evidence},'paired host per-case evidence hashes')
        host_fresh=score.score(reference,host_hyp,duration,host_case['processing_ms'])
        for key in ('wer_raw','wer_normalized','cpwer_raw'):a.check(host_fresh[key]==host_metric[key],('paired host rescore',cid,key))
        old_hyp=a.read(old_folder/'hypothesis.json');old_diag=a.read(old_folder/'diagnostics.json');old_case=a.read(old_folder/'case.json');old_metric=a.read(old_folder/'metrics.json')
        old_fresh=score.score(reference,old_hyp,duration,old_case['processing_ms'])
        for key,value in old_fresh.items():a.check(value==old_metric[key],('frozen native baseline rescore',cid,key))
        old_turns=policy.turns_from_json(old_diag['diarizationTurns'],duration)
        for collar in (0,250):a.check(score.der(reference['transcript'],native_rows(old_turns),duration,collar)==old_metric[f'native_der_collar_{collar}ms'],('frozen native baseline DER',cid,collar))
        old_count=len({t.speaker for t in old_turns});a.check(old_metric['native_speaker_count']==old_count and old_metric['native_speaker_count_error']==abs(old_count-old_fresh['speakers']['reference']),'frozen baseline actual K')
        changed_chunks=[]
        for index,(left,right) in enumerate(zip(diag['asrSlices'],host_diag['asrSlices'])):
            fields=[k for k in ('startMs','endMs','text','tokens','timestamps') if left[k]!=right[k]]
            if fields:changed_chunks.append({'index':index,'fields':fields,'native':{k:left[k] for k in fields},'host':{k:right[k] for k in fields}})
        difference={'raw_turns_equal':diag['rawDiarizationTurns']==host_diag['rawDiarizationTurns'],'stable_turns_equal':diag['nativeDiarizationTurns']==host_diag['nativeDiarizationTurns'],'refined_turns_equal':diag['diarizationTurns']==host_diag['diarizationTurns'],'vectors':vector_difference(wrapper['windows'],host_diag['cleanEmbeddingWindows']),'jury_content_equal':hyp==host_hyp,'native_chunks':len(diag['asrSlices']),'host_chunks':len(host_diag['asrSlices']),'changed_chunks':changed_chunks}
        counts=diag['diarizationEmbeddingCounts'];totals.update(sidecars=1,measured_windows=counts['measuredWindows'],released_streams=counts['releasedStreams'],embedding_forward_calls=counts['embeddingForwardCalls'],asr_chunks=len(diag['asrSlices']),tokens=sum(len(p['tokens']) for p in diag['asrSlices']),words=sum(len(p['words']) for p in diag['asrSlices']))
        comparison.append({'id':cid,'split':spec['split'],'reference_words':metric['wer_raw']['reference_tokens'],'native_errors':metric['wer_raw']['errors'],'host_errors':host_metric['wer_raw']['errors']})
        native_records.append({'id':cid,'split':spec['split'],'duration_ms':duration,'processing_ms':native_case['processing_ms'],'metrics':metric})
        baseline_records.append({'id':cid,'split':spec['split'],'duration_ms':duration,'processing_ms':old_case['processing_ms'],'metrics':old_metric})
        rows.append({'id':cid,'split':spec['split'],'cpu_policy':diag['cpuPolicy'],'raw_wer':metric['wer_raw'],'normalized_wer':metric['wer_normalized'],'cpwer_raw':metric['cpwer_raw'],'native_der0':metric['native_der_collar_0ms'],'native_der250':metric['native_der_collar_250ms'],'native_k':count,'reference_k':fresh['speakers']['reference'],'raw_error_delta_vs_native_c2':metric['wer_raw']['errors']-old_metric['wer_raw']['errors'],'der0_delta_pp_vs_native_c2':100*(metric['native_der_collar_0ms']['rate']-old_metric['native_der_collar_0ms']['rate']),'counts':counts,'sidecar_replay':replay,'word_replay':word_proof,'evidence_sha256':{**evidence,'case.json':a.sha(folder/'case.json'),'scored-case.json':a.sha(folder/'scored-case.json'),'diarization-evidence.json':a.sha(sidecar)},'host_differences':difference})
    a.check(run['cases']==comparison,'actual paired error table exact')
    dev=aggregate([r for r in native_records if r['id'] in dev_ids]);old_dev=aggregate([r for r in baseline_records if r['id'] in dev_ids]);declared=protocol['baseline']['native_dev']
    a.check(dev==run['dev_native_quality'],'all independently recomputed dev aggregate fields')
    a.check((old_dev['wer_raw']['errors'],old_dev['wer_raw']['reference_tokens'],old_dev['wer_normalized']['errors'],old_dev['wer_normalized']['reference_tokens'],old_dev['cpwer_raw']['errors'],old_dev['native_speaker_count_exact_cases'],old_dev['native_der_collar_0ms']['rate'])==(70,533,16,532,145,7,.18298480576441103),'recomputed exact predeclared C2-native baseline')
    a.check(old_dev['native_der_collar_0ms']['rate']==declared['native_der0'] and {k:old_dev['native_der_collar_0ms'][k] for k in declared['native_der0_components']}==declared['native_der0_components'],'frozen actual DER denominator/components')
    conditions=cpu_conditions(dev,old_dev,protocol['native_cpu_quality_gate']['numeric_epsilon'])
    fixed_rows=[next(r for r in comparison if r['id']==cid) for cid in fixed_ids]
    port=summarize(fixed_rows,threshold_pp=.5)
    a.check(port==run['fixed_five_wer_port_gate'] and port['reference_words']==442 and port['host_errors']==44,'independent fixed-five weighted port and all per-file outliers')
    fixed_root=repo/'artifacts/test-results/step-04/fixed-v16-production-comparison'
    fixed_baseline=a.read(fixed_root/'summary.json')
    a.check(a.sha(fixed_root/'summary.json')==fp['fixed_dev_baseline_summary_sha256']=='6cf29600a98830f2b9fd76d9728f4aadaca0233c5d9de437dbf76e347e13417d' and a.sha(fixed_root/'run.json')==fp['fixed_dev_baseline_run_sha256'],'unchanged historical fixed-V1.6 comparison pins')
    legacy_gate=run['dev_quality_gate'];legacy_count=dev['native_speaker_count_exact_cases']>=7;legacy_der=dev['native_der_collar_0ms']['rate']<=fixed_baseline['native_der_collar_0ms']['rate']+.02
    a.check(legacy_gate['native_der0']==dev['native_der_collar_0ms']['rate'] and legacy_gate['native_count_exact']==dev['native_speaker_count_exact_cases'] and legacy_gate['count_pass']==legacy_count and legacy_gate['native_der0_pass']==legacy_der and legacy_gate['gate_pass']==(legacy_count and legacy_der) and run['wer_port_parity_pass']==port['gate_pass'] and run['gate_pass']==(port['gate_pass'] and legacy_count and legacy_der),'legacy collector gates independently consistent; distinct from new CPU gate')
    a.check(len(rows)==len(seen_work)==len(seen_recording)==10 and totals['measured_windows']==totals['released_streams']==totals['embedding_forward_calls'],'complete identities and released actual resources')
    a.sha(helper);a.verify_unchanged()
    accepted=all(conditions.values()) and port['gate_pass']
    return {'status':'PASS','integrity_status':'PASS','native_cpu_acceptance':'PASS' if accepted else 'FAIL','control':args.control,'cpu_plan':'auto_v1','requested_threads':requested,'effective_threads':threads,'run':str(out.relative_to(repo)),'run_sha256':a.sha(out/'run.json'),'protocol_sha256':PROTOCOL_SHA,'cases':10,'checks':a.checks,'new_cpu_nonregression_gate':{'gate_pass':all(conditions.values()),'conditions':conditions,'actual':dev,'baseline':old_dev},'fixed_five_port_gate':port,'collector_legacy_gate_pass':run['gate_pass'],'source_sha256':a.hashes,'source_version_resolutions':a.resolutions,'totals':dict(totals),'rows':rows,'screen_restored':True,'helper_sha256':HELPER_SHA}


def self_test():
    import copy
    v={'cases':8,'wer_raw':{'errors':70,'reference_tokens':533},'wer_normalized':{'errors':16,'reference_tokens':532},'cpwer_raw':{'errors':145,'reference_tokens':533,'rate':145/533},'native_der_collar_0ms':{'rate':.18298480576441103,'reference_speaker_ms':255360.},'native_speaker_count_exact_cases':7}
    count=0
    assert all(cpu_conditions(v,v).values());count+=1
    for key in ('wer_raw','wer_normalized','cpwer_raw'):
        changed=copy.deepcopy(v);changed[key]['errors']+=1;assert not all(cpu_conditions(changed,v).values());count+=1
        changed=copy.deepcopy(v);changed[key]['reference_tokens']+=1;assert not all(cpu_conditions(changed,v).values());count+=1
    changed=copy.deepcopy(v);changed['native_der_collar_0ms']['rate']+=1e-9;assert not all(cpu_conditions(changed,v).values());count+=1
    changed=copy.deepcopy(v);changed['native_speaker_count_exact_cases']=6;assert not all(cpu_conditions(changed,v).values());count+=1
    changed=copy.deepcopy(v);changed['cases']=7;assert not all(cpu_conditions(changed,v).values());count+=1
    for status,expected in [('RUNNING',False),('COMPLETE',True),('C2_QUALITY_FAIL',True),('FAILED',False)]:
        assert terminal_complete({'status':status,'new_model_inference':True,'inference_requested':True,'cases':[{}]*10}) is expected;count+=1
    for raw in ('{"x":1,"x":2}','{"x":NaN}'):
        try:strict_json(raw)
        except ValueError:count+=1
        else:raise AssertionError('Invalid JSON accepted')
    for status, control, threads, requested, host, expected in (
        ('READY_BEFORE_FIRST_NATIVE_CPU_NN','explicit-two',2,2,'2',True),
        ('READY_BEFORE_FIRST_NATIVE_AUTOMATIC_CPU_NN','automatic-runtime-cores',1,0,'1',True),
        ('READY_BEFORE_FIRST_NATIVE_CPU_NN','automatic-runtime-cores',1,0,'1',False),
        ('READY_BEFORE_FIRST_NATIVE_AUTOMATIC_CPU_NN','explicit-two',2,2,'2',False),
        ('READY_BEFORE_NATIVE_CPU_NN','automatic-runtime-cores',1,0,'1',False),
        ('UNKNOWN','automatic-runtime-cores',1,0,'1',False),
        ('READY_BEFORE_FIRST_NATIVE_AUTOMATIC_CPU_NN','automatic-runtime-cores',2,0,'1',False),
        ('READY_BEFORE_FIRST_NATIVE_AUTOMATIC_CPU_NN','automatic-runtime-cores',1,1,'1',False),
        ('READY_BEFORE_FIRST_NATIVE_AUTOMATIC_CPU_NN','automatic-runtime-cores',True,0,'1',False),
        ('READY_BEFORE_FIRST_NATIVE_AUTOMATIC_CPU_NN','automatic-runtime-cores',1,False,'1',False),
        ('READY_BEFORE_FIRST_NATIVE_AUTOMATIC_CPU_NN','automatic-runtime-cores',1,0,'2',False)):
        assert receipt_matches({'status':status},control,threads,requested,host) is expected;count+=1
    print(json.dumps({'self_test':'PASS','checks':count,'neural_inference':False,'scope':'Synthetic acceptance/coverage/JSON guards only'}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--run',type=Path);p.add_argument('--control',choices=('explicit-two','automatic-runtime-cores'));p.add_argument('--receipt',type=Path);p.add_argument('--preflight',type=Path);p.add_argument('--output',type=Path);p.add_argument('--self-test',action='store_true');args=p.parse_args()
    if args.self_test:self_test();return
    if any(v is None for v in (args.run,args.control,args.receipt,args.output)):p.error('--run/--control/--receipt/--output required')
    args.repo,args.run,args.receipt,args.output=(v.resolve() for v in (args.repo,args.run,args.receipt,args.output));md=args.output.with_suffix('.md')
    if args.output.exists() or md.exists():raise ValueError('Fresh output only; no overwrite')
    Evidence,helper=helper_class();a=Evidence(args.repo)
    try:result=audit(args,a,helper)
    except BaseException as error:result={'status':'FAIL','integrity_status':'FAIL','native_cpu_acceptance':'NOT_EVALUATED','checks':a.checks,'error':{'type':type(error).__name__,'message':str(error)},'source_sha256':a.hashes,'source_version_resolutions':a.resolutions}
    script=Path(__file__).read_bytes();h=hashlib.sha256(script).hexdigest();snapshot=args.repo/'artifacts/test-results/step-05/runner-snapshots'/(h+'-native-cpu-independent-audit.py');snapshot.parent.mkdir(parents=True,exist_ok=True)
    if snapshot.exists():
        if snapshot.read_bytes()!=script:raise ValueError('Immutable snapshot collision')
    else:
        with snapshot.open('xb') as f:f.write(script)
    result.update(schema_version=1,at=datetime.now(timezone.utc).isoformat(),auditor_source_sha256=h,auditor_source_snapshot=str(snapshot.relative_to(args.repo)),neural_inference_by_auditor=False,scope='Actual x86_64 native CPU regression only; exact frozen new CPU nonregression and historical fixed-five port gates separate. No NN/ADB/build/source mutation by auditor. No ARM/phone speed, natural-dialogue, independent word gold or full-project acceptance.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    lines=[f"Независимый native CPU аудит: {result['status']}; CPU-приёмка: {result['native_cpu_acceptance']}.",f"Проверок: {result['checks']}; новый NN/ADB/сборки аудитор не запускал.",'']
    if result['status']=='PASS':
        d=result['new_cpu_nonregression_gate']['actual'];port=result['fixed_five_port_gate'];lines += [f"Dev8: raw {d['wer_raw']['errors']}/533, normalized {d['wer_normalized']['errors']}/532, cpWER {d['cpwer_raw']['errors']}/533, точное K {d['native_speaker_count_exact_cases']}/8, native DER0 {d['native_der_collar_0ms']['rate']*100:.8f}%.",f"Фиксированная пятёрка отдельно: native {port['native_errors']}/442 против host {port['host_errors']}/442; port gate {port['gate_pass']}. Все пофайловые выбросы сохранены.",'Полные реальные векторы и интервалы C2, actual tokens→words→Jury JSON воспроизведены; метрики и исходная C2-native база пересчитаны по независимым эталонам. Старый collector gate не заменяет новый CPU nonregression.']
    else:lines.append(str(result['error']))
    lines += ['',f"JSON: [{args.output.name}]({args.output.name}); SHA аудитора `{h}`.",'Это ранее просмотренный монтажный прокси, а не естественные диалоги/независимые времена слов. Время не является причинным доказательством скорости и не переносится с x86 на ARM/телефон.']
    with md.open('x') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps({k:result.get(k) for k in ('status','integrity_status','native_cpu_acceptance','control','cases','checks','error','auditor_source_sha256')},ensure_ascii=False))
    if result['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
