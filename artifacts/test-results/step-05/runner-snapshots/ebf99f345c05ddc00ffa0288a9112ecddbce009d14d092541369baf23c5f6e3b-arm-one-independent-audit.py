#!/usr/bin/env python3
"""Saved-only first physical ARM smoke audit; no ADB, model/runtime construction or full10 gate."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import wave
import zipfile

sys.dont_write_bytecode = True
PROTOCOL_SHA = '0455e562054dfa454c2df9ab563430d5b184c26a3f1f8c0098cc06e0a190a15f'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(); repo = args.repo.resolve(); private = args.run_dir.resolve(); out = args.output_dir.resolve()
    if out.exists(): raise ValueError('Fresh output only; previous evidence must not be overwritten')
    sys.path.insert(0, str(repo))
    from tools.eval import native_diar_policy as policy, native_policy, pull_refined_android as collector
    hashes = {}; sources = {}; checks = []
    def check(ok, label):
        checks.append(label)
        if not ok: raise AssertionError(label)
    def sha(path, label=None):
        path = Path(path).resolve(); digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if path in hashes: check(hashes[path] == digest, 'unchanged reread: ' + (label or path.name))
        hashes[path] = digest
        public_label = label or (str(path.relative_to(repo)) if path.is_relative_to(repo) else 'private-allowlisted/' + path.name)
        sources[public_label] = digest
        return digest
    def read(path, label=None):
        sha(path, label); return policy.strict_json(Path(path).read_bytes())
    def equal(a, b, label):
        policy.equal(a, b, label); check(True, label)
    protocol_path = repo/'artifacts/test-results/step-05/vivo-arm-one-protocol-v1.json'
    protocol = read(protocol_path); check(sha(protocol_path) == PROTOCOL_SHA, 'exact before-NN protocol')
    for relative, expected in protocol['source_sha256'].items(): check(sha(repo/relative) == expected, 'protocol source pin: ' + relative)
    receipt = read(repo/'artifacts/test-results/step-05/vivo-arm-one-execution-receipt-v1.json')
    preflight_path = repo/protocol['preflight_path']; preflight = read(preflight_path)
    check(sha(preflight_path) == protocol['preflight_sha256'] == receipt['preflight_sha256'], 'exact before-NN preflight')
    check(receipt['status'] == 'READY_BEFORE_FIRST_ARM_NN' and receipt['protocol_sha256'] == PROTOCOL_SHA, 'actual known ARM execution receipt')
    check(datetime.fromisoformat(preflight['created_utc']) < datetime.fromisoformat(protocol['frozen_utc']) < datetime.fromisoformat(receipt['created_utc']), 'preflight and protocol before execution receipt')
    check(receipt['reference_or_gold_speaker_count_staged'] is False and receipt['only_staged'] == ['audio/dev-mono-s.wav', 'batch.json'], 'no reference or true K staged')
    equal(read(private/'execution-receipt.json'), receipt, 'private/public execution receipt exact copy')
    check(preflight['status'] == 'ARM_APKS_AND_SEVEN_REMOTE_MODELS_MATCH_BEFORE_NN' and preflight['new_inference_started'] is False, 'preflight precedes NN')
    check(preflight['api'] == 37 and preflight['abi'] == 'arm64-v8a' and preflight['page_size'] == 4096 and preflight['online_cpus'] == '0-7', 'actual physical ARM/API37/4KiB/eight cores')
    check(preflight['network_settings_mutated'] is False and preflight['app_data_cleared'] is False, 'phone network and prior app data preserved by execution policy')
    lock = read(repo/'app/src/main/assets/models-lock.json'); pins = policy.validate_model_lock(lock)
    equal(preflight['models_sha256'], pins, 'all seven actual remote model hashes')
    build = read(repo/'artifacts/test-results/step-05/build-auto-v2/summary.json')
    test_build = read(repo/'artifacts/test-results/step-05/build-test-v3/summary.json')
    check(build['status'] == test_build['status'] == 'PASS', 'actual app and matching test build receipts')
    app = repo/build['preserved_release_path']; test = repo/test_build['androidTest']['path']
    check(sha(app) == preflight['installed_apks']['ru.replika.offline'] == build['apks']['allInOne']['sha256'], 'installed physical app equals preserved candidate')
    check(sha(test) == preflight['installed_apks']['ru.replika.offline.test'] == test_build['androidTest']['sha256'], 'installed matching test APK exact hash')
    with zipfile.ZipFile(app) as bundle: equal(policy.validate_model_lock(policy.strict_json(bundle.read('assets/models-lock.json'))), pins, 'executed APK model lock exact')
    worker = protocol['worker']; cid = worker['exact_case_id']; duration = worker['duration_ms']; kw = dict(cpu_plan='auto_v1', threads=4, requested_threads=0)
    check(cid == 'dev-mono-s' and duration == 6333, 'one exact known duplicate, not new quality cohort')
    audio = Path('/home/egor/replika-toolchain/eval-audio')/worker['host_audio_relative']
    check(sha(audio, 'canonical-author-audio/'+worker['host_audio_relative']) == worker['audio_sha256'], 'canonical source audio exact hash')
    with wave.open(str(audio), 'rb') as wav:
        check((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1,2,16000) and (wav.getnframes()*1000+8000)//16000 == duration, 'actual canonical PCM16 mono16k clock')
    report = read(private/'report.json'); case = read(private/(cid+'.case.json')); diag = read(private/(cid+'.diagnostics.json')); hyp = read(private/(cid+'.hypothesis.json'))
    check(report['status'] == 'COMPLETE' and report['newModelInference'] is True and report['collectEvidence'] is True and len(report['cases']) == 1, 'one actual complete full-QA Worker')
    equal(report['cases'][0], case, 'complete case/report copy')
    check(type(report['processId']) is int and report['processId'] > 0 and case['processId'] == report['processId'], 'positive actual same process')
    check(report['api'] == 37 and report['supportedAbis'] == ['arm64-v8a'] and diag['android'] == 37, 'runtime ARM/API37 report matches preflight')
    check(report['run'] == receipt['run'] == worker['instrumentation_arguments']['evalRun'], 'fresh run identity matches frozen invocation')
    batch = read(private/'batch.json')
    equal(batch, {'schema_version':1, 'run':report['run'], 'cases':[{'id':cid,'audio':'audio/'+cid+'.wav','sha256':worker['audio_sha256']}]}, 'strict staged input allowlist without gold')
    log_path = private/'instrumentation.log'; sha(log_path); log = log_path.read_text()
    check(re.search(r'OK \(1 test\)', log) is not None and 'FAILURES!!!' not in log and 'Process crashed' not in log and 'INSTRUMENTATION_CODE: -1' in log, 'actual one-test instrumentation success')
    host = repo/worker['paired_full_host_run']; host_run = read(host/'run.json')
    check(sha(host/'run.json') == protocol['host_run_sha256'] and host_run['status'] == 'COMPLETE' and host_run['new_model_inference'] is True, 'frozen paired complete host4 run')
    policy.validate_host_policy(host_run['config'], host_run['paired_asr_policy'], cpu_plan='auto_v1', threads=4); check(True,'paired host4 strict global policy')
    for payload in [report, diag]: policy.validate_native_diar_policy(host_run['config'], payload, host_run['paired_asr_policy'], **kw)
    check(True,'actual report and diagnostic strict CPU/native/ASR policies')
    equal(diag['cpuPolicy'], worker['required_actual_cpu_policy'], 'actual request0/cores8/ASR4/SD4/refiner4/no pins')
    equal(report['cpuPolicy'], diag['cpuPolicy'], 'report/Worker CPU policy copy')
    sidecar_path = private/(cid+'.diarization-evidence.json'); sidecar = sidecar_path.read_bytes(); sha(sidecar_path)
    vector = policy.validate_diarization_evidence(diag,case,sidecar,case_id=cid,audio_sha256=worker['audio_sha256'],duration_ms=duration,**kw); check(True,'actual512-vectors, lifecycles and C2 exact replay')
    words = native_policy.validate_word_evidence(diag); jury, word_replay = policy.reconstruct_jury(diag,duration)
    equal(jury,hyp,'real tokens/times→words/speaker→Jury exact replay')
    check(case['segments'] == len(hyp['transcript']), 'actual segment count')
    reference_path = repo/worker['independent_reference_host_only']; reference = read(reference_path)
    check(sha(reference_path) == worker['reference_sha256'], 'independent author reference hash')
    metrics = collector.score_case(reference,hyp,diag,duration,case['processing_ms'])
    hf = host/cid; hc = read(hf/'case.json'); hd = read(hf/'diagnostics.json'); hh = read(hf/'hypothesis.json'); hm = read(hf/'metrics.json')
    equal(hc['evidence_sha256'],{name:sha(hf/name) for name in ('reference.json','hypothesis.json','diagnostics.json','metrics.json')},'host4 per-case evidence hashes')
    equal(hc['metrics'],hm,'host4 embedded metrics copy'); check(sha(hf/'reference.json') == worker['reference_sha256'],'host4 independent reference exact bytes')
    fresh_host = collector.score_case(reference,hh,hd,duration,hc['processing_ms'])
    metric_keys = ['wer_raw','wer_normalized','cpwer_raw','native_der_collar_0ms','native_der_collar_250ms','native_speaker_count','native_speaker_count_error']
    for key in metric_keys: equal(fresh_host[key],hm[key],'independent host4 rescore: '+key)
    # Publish only known author dev outputs. Do not read/copy commands-private, DB, serial or dumpsys.
    allowed = ['report.json','batch.json','instrumentation.log',cid+'.case.json',cid+'.diagnostics.json',cid+'.hypothesis.json',cid+'.diarization-evidence.json']
    public_bytes = {name:(private/name).read_bytes() for name in allowed}
    for name, raw in public_bytes.items():
        check(not re.search(rb'(?i)"(?:serial|imei|android_id|phone_number)"\s*:',raw) and b'dumpsys' not in raw and b'commands-private' not in raw,'allowlisted public output privacy: '+name)
    for path, expected in list(hashes.items()):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected: raise ValueError('Source changed during saved-only audit: '+path.name)
    check(True,'all saved inputs unchanged during audit')
    own = Path(__file__).read_bytes(); own_sha = hashlib.sha256(own).hexdigest(); snapshot = repo/'artifacts/test-results/step-05/runner-snapshots'/(own_sha+'-arm-one-independent-audit.py')
    snapshot.parent.mkdir(parents=True,exist_ok=True)
    if snapshot.exists(): check(snapshot.read_bytes() == own,'immutable auditor snapshot')
    else:
        with snapshot.open('xb') as f:f.write(own)
    out.mkdir(parents=True,exist_ok=False)
    for name, raw in public_bytes.items():
        with (out/name).open('xb') as f:f.write(raw)
    with (out/'reference.json').open('xb') as f:f.write(reference_path.read_bytes())
    for name, obj in [('metrics.json',metrics),('host4-rescored-metrics.json',fresh_host)]:
        with (out/name).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    result = {'schema_version':1,'status':'PASS_ONE_PHYSICAL_ARM_COMPATIBILITY_SMOKE','at':datetime.now(timezone.utc).isoformat(),'checks':len(checks),'check_labels':checks,'source_sha256':sources,'public_output_sha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in public_bytes.items()},'auditor_sha256':own_sha,'auditor_snapshot':str(snapshot.relative_to(repo)),'protocol_sha256':PROTOCOL_SHA,'case_id':cid,'cases':1,'device':{'physical':True,'label':'vivo_X300','api':37,'abi':'arm64-v8a','page_size_bytes':4096},'actual_cpu_policy':diag['cpuPolicy'],'processing_ms':case['processing_ms'],'audio_ms':duration,'descriptive_short_rtf':case['processing_ms']/duration,'vector_replay':vector,'word_evidence':words,'word_replay':word_replay,'native_metrics':{k:metrics[k] for k in metric_keys},'host4_metrics':{k:fresh_host[k] for k in metric_keys},'host4_comparison':{'jury_content_equal':hyp==hh,'same_metric_values':{k:metrics[k]==fresh_host[k] for k in metric_keys}},'new_neural_inference_by_auditor':False,'full10_gate_applied':False,'speed_accepted':False,'full_ARM_acceptance':False,'whole_project_accepted':False,'scope':'One repeated known6333ms author sample on actual physical ARM/API37/4KiB, with real automatic CPU4 and full QA replay. No new blind cohort, long-recording/thermal/battery/speed acceptance, native PCM hash or word-gold claim. FullQA has no compact WorkInfo SUCCEEDED field. Original raw private commands/serial/dumpsys/DB never copied.'}
    with (out/'independent-audit.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    lines=[f"# Первый короткий прогон на физическом ARM: PASS ({len(checks)} проверок)",'Один повтор известного dev-mono-s: API37/arm64-v8a, страница4096, cores8/request0→ASR4/SD4/refiner4. APK/семь моделей/протокол до NN и фактические артефакты связаны хешами.',f"Реальные {vector['measured_windows']}×512 вектора, освобождение ресурсов и C2 replay совпали. {words['tokenCount']} токена/времени и {words['wordCount']} слов точно воспроизвели Jury JSON.",f"Независимый score: raw{metrics['wer_raw']['errors']}/{metrics['wer_raw']['reference_tokens']}, normalized{metrics['wer_normalized']['errors']}/{metrics['wer_normalized']['reference_tokens']}, cpWER{metrics['cpwer_raw']['errors']}/{metrics['cpwer_raw']['reference_tokens']}; native DER0 {metrics['native_der_collar_0ms']['rate']:.12%}, K={metrics['native_speaker_count']}. Host4 пересчитан отдельно; буквальное совпадение Jury: {hyp==hh}.",f"Worker {case['processing_ms']} мс на {duration} мс аудио, описательный короткий RTF={case['processing_ms']/duration:.6f}. Это один smoke, не приёмка скорости, длинных файлов, батареи, нагрева или полного ARM/quality-корпуса.",'Сохранены только отчёты известного авторского dev-файла и эталон. Команды/серийный номер/dumpsys/DB остались вне публичных артефактов. Аудитор не выполнял NN/ADB/сборки/Git.']
    with (out/'independent-audit.md').open('x') as f:f.write('\n\n'.join(lines)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'output':str(out),'auditor_sha256':own_sha,'audit_sha256':hashlib.sha256((out/'independent-audit.json').read_bytes()).hexdigest(),'jury_equal_host4':hyp==hh,'metric_equal_host4':result['host4_comparison']['same_metric_values']},ensure_ascii=False))


if __name__ == '__main__': main()
