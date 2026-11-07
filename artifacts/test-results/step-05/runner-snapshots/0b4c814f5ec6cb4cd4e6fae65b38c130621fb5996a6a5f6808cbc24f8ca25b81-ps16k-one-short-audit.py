#!/usr/bin/env python3
"""One saved ps16k compatibility smoke; pure validators only, never the full10 CLI/NN/ADB."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import zipfile

sys.dont_write_bytecode=True
PROTOCOL_SHA='7c155d33c8ccc889587f0471952d937f6558a96765a0129db29f1255513afd9d'
HELPER_SHA='11fc1e516a2a0663ce950e755833b1cb9c9fd86b9c07ffba45a795239772b929'

def helper_class():
    path=Path(__file__).with_name('step05-independent-cpu-audit.py')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=HELPER_SHA:raise ValueError('Frozen hash helper changed')
    spec=importlib.util.spec_from_file_location('ps16k_hash_helper',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.Audit,path

def one_file(directory,names):
    found=[directory/name for name in names if (directory/name).is_file()]
    if len(found)!=1:raise ValueError('Expected exactly one explicitly named evidence file: '+str(names))
    return found[0]

def audit(args,a,helper):
    repo,folder=args.repo,args.run_dir;sys.path.insert(0,str(repo))
    from tools.eval import native_diar_policy as policy,native_policy
    from tools.eval import pull_refined_android as collector
    # Strict JSON for every actual input, including rejected duplicate/NaN keys.
    def read(path):a.sha(path);return policy.strict_json(Path(path).read_bytes())
    protocol_path=repo/'artifacts/test-results/step-05/ps16k-protocol-v1/protocol.json';protocol=read(protocol_path)
    a.check(a.sha(protocol_path)==PROTOCOL_SHA,'immutable one-short protocol')
    for relative,expected in protocol['source_sha256'].items():
        a.check(a.sha(repo/relative)==expected,('frozen protocol source/input pin',relative))
    worker=protocol['worker'];cid=worker['exact_case_id'];duration=worker['duration_ms'];cpu={'cpu_plan':'auto_v1','threads':1,'requested_threads':0}
    a.check(cid=='dev-mono-s' and duration==6333,'exact one short duplicate, not a cohort subset acceptance')
    runtime=read(args.runtime_proof);observed=runtime['observed']
    for key,expected in [('sys.boot_completed','1'),('ro.build.version.sdk','35'),('ro.product.cpu.abi','x86_64'),('PAGE_SIZE','16384')]:
        a.check(observed[key]['returncode']==0 and observed[key]['stdout'].strip()==expected,('actual runtime observation',key))
    setup=read(repo/'artifacts/test-results/step-05/ps16k-environment-v1/runtime-setup.json')
    writes=[r for r in setup if r['args'][:2]==['shell','setprop']]
    backcompat_disabled=bool(writes) and all(r['returncode']==0 for r in writes)
    bindings=read(args.installed_bindings);a.check(bindings['status']=='APK_INSTALLED_HASHES_MATCH' and bindings['build_v2_exit_code']==0,'actual built/installed isolated APK bindings')
    a.check(len(bindings['apks'])==2,'exact app and matching test APK bindings')
    for item,package in zip(bindings['apks'],['ru.replika.offline.aioqa','ru.replika.offline.aioqa.test']):
        path=repo/item['path'];a.check(path.stat().st_size==item['bytes'] and a.sha(path)==item['sha256']==item['installed_sha256'] and ("name='"+package+"'") in item['package'],'installed/local package and APK exact pin')
        a.check('SHA-256 digest: f40399356577bcd0a5c220818ba13e9686768a02830a7f6e3af81d5a487947ab' in item['signer'],'preserved app/test signing certificate')
    lock=read(repo/'app/src/main/assets/models-lock.json');pins=policy.validate_model_lock(lock)
    static=read(repo/'artifacts/test-results/step-05/ps16k-environment-v1/aioqa-static.json')
    a.check(static['staticVerification']=='PASS' and not static['errors'] and static['actualAbis']==['x86_64'] and static['sha256']==bindings['apks'][0]['sha256'],'static ps16k APK alignment and seven-weight proof')
    with zipfile.ZipFile(repo/bindings['apks'][0]['path']) as z:a.check(policy.validate_model_lock(policy.strict_json(z.read('assets/models-lock.json')))==pins,'actual executed bundled APK model lock')
    cold=read(repo/'artifacts/test-results/step-05/ps16k-cold-provision-v1/summary.json')
    for key in ('cleanOfflinePreparation','coldRestartNoExtraction','forcedInterruptionAndResume'):
        a.check(cold[key]=='PASS',('existing actual cold-provision prerequisite',key))
    prepared=read(args.prepared_models)
    a.check(prepared['package']=='ru.replika.offline.aioqa' and prepared['api']==35 and 'x86_64' in prepared['abis'] and prepared['processIs64Bit'] is True and prepared['repeatReadinessPreservedModificationTimes'] is True,'actual non-skipped prepared-file proof')
    a.check([(m['path'],m['bytes'],m['sha256']) for m in prepared['models']]==list(policy.MODEL_PINS),'seven freshly prepared actual model hashes')
    host=repo/worker['paired_full_host_run'];host_run=read(host/'run.json')
    policy.validate_host_policy(host_run['config'],host_run['paired_asr_policy'],cpu_plan='auto_v1',threads=1)
    a.check(host_run['status']=='COMPLETE' and host_run['new_model_inference'] is True,'completed paired full host1 source')
    report=read(one_file(folder,['report.json','instrumentation-report.json','android-report.json']))
    native=read(folder/f'{cid}.case.json');diag=read(folder/f'{cid}.diagnostics.json');hyp=read(folder/f'{cid}.hypothesis.json')
    a.check(report['status']=='COMPLETE' and report['newModelInference'] is True and len(report['cases'])==1 and report['cases'][0]['id']==cid and report.get('collectEvidence') is True,'actual exactly-one full-QA report')
    policy.equal(native,report['cases'][0],'full case/report object copy')
    a.check(type(report.get('processId')) is int and report['processId']>0 and native.get('processId')==report['processId'],'positive same actual process PID')
    # Full-QA deliberately has no compact-only WorkInfo SUCCEEDED requirement.
    policy.validate_native_diar_policy(host_run['config'],report,host_run['paired_asr_policy'],**cpu)
    policy.validate_native_diar_policy(host_run['config'],diag,host_run['paired_asr_policy'],**cpu)
    policy.equal(diag['cpuPolicy'],worker['required_actual_cpu_policy'],'actual cores2/request0/ASR1/SD1/refiner1')
    policy.equal(report['cpuPolicy'],diag['cpuPolicy'],'batch/Worker CPU resolution copy')
    batch=read(folder/'batch.json')
    a.check(set(batch)=={'schema_version','run','cases'} and batch['run']==report['run'] and batch['cases']==[{'id':cid,'audio':'audio/'+cid+'.wav','sha256':worker['audio_sha256']}],'only audio/hash/ID staged, no reference or true K')
    raw=(folder/f'{cid}.diarization-evidence.json').read_bytes();a.sha(folder/f'{cid}.diarization-evidence.json')
    vector_proof=policy.validate_diarization_evidence(diag,native,raw,case_id=cid,audio_sha256=worker['audio_sha256'],duration_ms=duration,**cpu)
    word_proof=native_policy.validate_word_evidence(diag);reconstructed,replay_words=policy.reconstruct_jury(diag,duration)
    policy.equal(hyp,reconstructed,'literal actual timed words/speakers/Jury projection')
    a.check(native['segments']==len(hyp['transcript']),'native exported segment count')
    log=one_file(folder,['instrumentation.log','worker-instrumentation.log']);a.sha(log);text=log.read_text(errors='replace')
    a.check(re.search(r'OK \(1 tests?\)',text) is not None and 'FAILURES!!!' not in text and 'INSTRUMENTATION_FAILED' not in text,'actual JUnit success, not a skipped/provisioning proof')
    reference_path=repo/worker['independent_reference_host_only'];reference=read(reference_path)
    a.check(a.sha(reference_path)==worker['reference_sha256'],'independent canonical author reference')
    metrics=collector.score_case(reference,hyp,diag,duration,native['processing_ms'])
    host_folder=host/cid;host_case=read(host_folder/'case.json');host_diag=read(host_folder/'diagnostics.json');host_hyp=read(host_folder/'hypothesis.json');host_metric=read(host_folder/'metrics.json')
    a.check(host_case['evidence_sha256']=={name:a.sha(host_folder/name) for name in ['reference.json','hypothesis.json','diagnostics.json','metrics.json']} and host_case['metrics']==host_metric and a.sha(host_folder/'reference.json')==worker['reference_sha256'],'paired host per-case evidence hashes/copies')
    fresh_host=collector.score_case(reference,host_hyp,host_diag,duration,host_case['processing_ms'])
    for key in ['wer_raw','wer_normalized','cpwer_raw','native_der_collar_0ms','native_der_collar_250ms']:a.check(fresh_host[key]==host_metric[key],('independent paired host rescore',key))
    for name in ['reference.json',f'{cid}.reference.json']:
        if (folder/name).exists():a.check(a.sha(folder/name)==worker['reference_sha256'],'preserved reference exact bytes')
    for name in ['metrics.json',f'{cid}.metrics.json']:
        if (folder/name).exists():policy.equal(read(folder/name),metrics,'root/scorer metric copy')
    # Bind the separate root execution receipt only after its actual saved shape is known.
    receipt=read(args.execution_receipt)
    a.check(receipt['protocol_sha256']==PROTOCOL_SHA and receipt['serial']=='emulator-5558' and receipt['package']=='ru.replika.offline.aioqa','root exact protocol/device/package execution binding')
    a.check(receipt['reference_text_or_counts_staged'] is False and receipt['inference_requested'] is True and receipt['new_model_inference'] is True,'root new actual NN/no gold markers')
    a.check(receipt['native_model_sha256_before']==pins,'actual provisioned remote models before NN')
    a.sha(helper);a.verify_unchanged()
    return {'status':'PASS_ONE_SHORT_COMPATIBILITY_SMOKE','checks':a.checks,'cases':1,'case_id':cid,'protocol_sha256':PROTOCOL_SHA,'runtime_page_size_bytes':16384,'runtime_api':35,'runtime_abi':'x86_64','actual_cpu_policy':diag['cpuPolicy'],'backcompat_disabled_proven':backcompat_disabled,'previous_system_failure_observed':bindings.get('first_instrumentation_result')=='FAILED_PROCESS_CRASHED','vector_replay':vector_proof,'word_evidence':word_proof,'word_replay':replay_words,'native_metrics':metrics,'host1_metrics':fresh_host,'host1_jury_content_equal':hyp==host_hyp,'source_sha256':a.hashes,'work_manager_state_scope':protocol['worker']['work_state_scope']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--execution-receipt',type=Path,required=True);p.add_argument('--prepared-models',type=Path,required=True);p.add_argument('--runtime-proof',type=Path);p.add_argument('--installed-bindings',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.repo=args.repo.resolve();args.run_dir=args.run_dir.resolve();args.output=args.output.resolve()
    args.runtime_proof=args.runtime_proof or args.repo/'artifacts/test-results/step-05/ps16k-environment-v1/runtime-before-setup.json'
    args.installed_bindings=args.installed_bindings or args.repo/'artifacts/test-results/step-05/ps16k-environment-v1/installed-build-bindings.json'
    md=args.output.with_suffix('.md')
    if args.output.exists() or md.exists():raise ValueError('Fresh audit path only; no overwrite')
    Audit,helper=helper_class();a=Audit(args.repo)
    try:result=audit(args,a,helper)
    except BaseException as error:result={'status':'FAIL','checks':a.checks,'error':{'type':type(error).__name__,'message':str(error)},'source_sha256':a.hashes}
    raw=Path(__file__).read_bytes();h=hashlib.sha256(raw).hexdigest();snapshot=args.repo/'artifacts/test-results/step-05/runner-snapshots'/(h+'-ps16k-one-short-audit.py');snapshot.parent.mkdir(parents=True,exist_ok=True)
    if snapshot.exists():
        if snapshot.read_bytes()!=raw:raise ValueError('Immutable snapshot collision')
    else:
        with snapshot.open('xb') as f:f.write(raw)
    result.update(schema_version=1,at=datetime.now(timezone.utc).isoformat(),auditor_source_sha256=h,auditor_source_snapshot=str(snapshot.relative_to(args.repo)),neural_inference_by_auditor=False,full10_quality_gate_applied=False,arm_phone_accepted=False,speed_accepted=False,whole_project_accepted=False,scope='One duplicate 6333ms API35/x86_64/16KiB actual Worker compatibility proof only. Existing strict pure APIs replay vectors/tokens and independently score author reference. No full10 CLI/subset gate or new metric threshold. Compatibility-off not established when property writes failed; prior system-server failures remain separate from app/NN attribution.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    lines=[f"Один короткий ps16k smoke: {result['status']}; проверок {result['checks']}.",'Нового NN/ADB/сборок аудитор не запускал. Это функциональная x86_64/16KiB проверка, без полного quality-гейта, ARM или скорости.']
    if result['status'].startswith('PASS'):lines += ['Существующие validators подтвердили actual cores2/request0/ASR1/SD1/refiner1, реальные512-векторы/C2/resource release, token→word→Jury exact replay и независимый reference/host1 rescore.','Compatibility-off не объявляется при denied setprop; предыдущий system-server crash сохраняется отдельным фактом.']
    else:lines.append(str(result['error']))
    with md.open('x') as f:f.write('\n\n'.join(lines)+'\n')
    print(json.dumps({k:result.get(k) for k in ['status','checks','cases','error','auditor_source_sha256']},ensure_ascii=False))
    if not result['status'].startswith('PASS'):raise SystemExit(1)

if __name__=='__main__':main()
