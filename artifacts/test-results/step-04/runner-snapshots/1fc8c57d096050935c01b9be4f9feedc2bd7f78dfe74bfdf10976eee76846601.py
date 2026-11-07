import hashlib
import json
import math
import struct
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tools.eval import diar_sweep, pipeline as base, score, speaker_refiner, window_overcluster

ROOT = Path.cwd()
STEP = ROOT / 'artifacts/test-results/step-04'
TARGET = STEP / 'final-native-parameter-audit.json'
if TARGET.exists() or (STEP / 'final-native-parameter-audit.md').exists():
    raise FileExistsError('Fresh staging required; audit outputs cannot be overwritten')
hashes, versions, records, profiles = {}, {}, [], []
checks = 0
totals = Counter()

def digest(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    if str(path) in hashes:
        assert hashes[str(path)] == value, ('changed during audit', str(path))
    hashes[str(path)] = value
    return value

def read(path):
    digest(path)
    return json.loads(Path(path).read_text())

def check(value, reason):
    global checks
    checks += 1
    if not value:
        raise AssertionError(reason)

def code_pin(relative, expected):
    path = ROOT / relative
    if digest(path) != expected:
        path = STEP / 'runner-snapshots' / (expected + '.py')
    check(path.is_file() and digest(path) == expected, ('source SHA', relative))
    versions[relative + '@' + expected] = str(path.relative_to(ROOT))

def evidence(folder, case, reference_sha):
    c = read(folder / 'case.json')
    items = {name: read(folder / name) for name in ('reference.json', 'hypothesis.json', 'diagnostics.json', 'metrics.json')}
    sha = {name: digest(folder / name) for name in items}
    check(c['evidence_sha256'] == sha and c['metrics'] == items['metrics.json'], ('case evidence', case['id']))
    check(all(c[k] == case[k] for k in ('id', 'split', 'audio_sha256', 'duration_ms')) and c['reference_sha256'] == reference_sha == sha['reference.json'], ('case input binding', case['id']))
    return c, items, sha

def turns(values, duration):
    result = []
    for row in values:
        check(set(row) == {'startMs', 'endMs', 'speakerId'} and all(type(row[k]) is int for k in row) and 0 <= row['startMs'] < row['endMs'] <= duration and row['speakerId'] >= 0, 'strict native turn schema/clock')
        result.append(base.Turn(row['startMs'], row['endMs'], row['speakerId']))
    return result

def rows(values):
    return [{'speaker_id': 'native_' + str(t.speaker), 'start_ms': t.start_ms, 'end_ms': t.end_ms, 'text': ''} for t in values]

def literal(document):
    return [t for row in sorted(document['transcript'], key=lambda x: (x['start_ms'], x['end_ms'])) for t in row['text'].split()]

protocol_path = ROOT / 'configs/eval/c2-final-native-parameters-v1.json'
protocol = read(protocol_path)
check(digest(protocol_path) == '43a81721b9341a0c713efcca9fa41915dda6b11eb7c8f5d898c9ea5338cfc0af', 'exact prespecified final protocol')
manifest_path = ROOT / protocol['manifest']
manifest = read(manifest_path)
cases = [c for c in manifest['files'] if c['split'] == 'dev']
ids = [c['id'] for c in cases]
check(len(cases) == len(set(ids)) == protocol['expected_cases'] == 8 and protocol['split'] == 'dev', 'complete dev8 only')
check(digest(manifest_path) == protocol['manifest_sha256'], 'manifest pin')
check(protocol['expected_speakers'] == -1 and protocol['threads'] == 2 and protocol['native_threshold'] == .3 and protocol['min_duration_on'] == .2, 'automatic global common policy')
baseline_root, d_root = ROOT / protocol['baseline_run'], ROOT / protocol['asr_run']
for name, expected in protocol['baseline_source_sha256'].items():
    check(digest(baseline_root / name) == expected, 'unchanged existing C2 baseline')
baseline_run, baseline_summary, d_run = read(baseline_root / 'run.json'), read(baseline_root / 'summary.json'), read(d_root / 'run.json')
check(baseline_run['status'] == d_run['status'] == 'COMPLETE' and baseline_run['new_model_inference'] is True and digest(d_root / 'run.json') == protocol['asr_run_sha256'], 'actual complete C2 and D sources')
baseline_dev = baseline_summary['by_split']['dev']
limit = protocol['selection']['maximum_native_der0']
check(baseline_dev['cases'] == 8 and baseline_dev['native_speaker_count_exact_cases'] == 7 and baseline_dev['native_der_collar_0ms']['rate'] == limit == .18298480576441103, 'prespecified baseline non-regrowth bound')
check(d_run['config']['pipeline'] == 'vad_words_v1' and d_run['config']['pre_roll_ms'] == 600 and d_run['config']['expected_speakers'] == -1, 'actual unchanged D context600 automatic policy')
check(digest(ROOT / 'configs/eval/diar-models.json') == protocol['catalog_sha256'] and digest(ROOT / 'app/src/main/assets/models-lock.json') == protocol['models_lock_sha256'], 'catalog and lock unchanged')
lock = read(ROOT / 'app/src/main/assets/models-lock.json')
check(len(lock['files']) == 7, 'all seven original models')
for spec in lock['files']:
    p = ROOT / 'model-pack' / spec['path']
    check(p.stat().st_size == spec['size'] and digest(p) == spec['sha256'], ('model pin', spec['path']))
for relative, expected in baseline_run['fingerprint']['code'].items():
    code_pin(relative, expected)
baseline_cases, d_cases = {}, {}
for case in cases:
    ref = manifest_path.parent / case['reference']
    ref_sha = digest(ref)
    check(digest(Path('/home/egor/replika-toolchain/eval-audio') / case['audio']) == case['audio_sha256'] and d_run['fingerprint']['references'][case['id']] == ref_sha, 'original canonical audio/reference pin')
    baseline_cases[case['id']] = evidence(baseline_root / case['id'], case, ref_sha)
    d_cases[case['id']] = evidence(d_root / case['id'], case, ref_sha)

expected_profiles = [p for p in protocol['profiles'] if p['inference']]
check([p['id'] for p in expected_profiles] == ['off-0p25', 'off-1p0', 'shift-0p25', 'shift-0p5'], 'exact bounded four alternatives')
for profile in expected_profiles:
    directory = STEP / ('final-native-' + profile['id'])
    run, summary = read(directory / 'run.json'), read(directory / 'summary.json')
    fp, sdk = run['fingerprint'], run['sdk_config']
    check(run['status'] == 'COMPLETE' and run['profile'] == profile == fp['profile'] and read(directory / 'protocol.json') == protocol, 'terminal profile/exact protocol copy')
    check(datetime.fromisoformat(protocol['frozen_at_utc']) < datetime.fromisoformat(run['started_at']), 'protocol before actual outputs')
    check(set(p.name for p in directory.iterdir() if p.is_dir()) == set(ids) and fp['selected_ids'] == ids, 'eight dev outputs only/no held-out cases')
    check(run['inference_requested'] is True and run['new_diarization_inference'] is True and run['new_embedding_inference'] is True and run['new_asr_inference'] is False and run['asr_replay'] is True, 'new SD/windows plus explicit cached ASR markers')
    check(fp['protocol_sha256'] == digest(protocol_path) and fp['manifest_sha256'] == digest(manifest_path) and fp['catalog_sha256'] == protocol['catalog_sha256'] and fp['models_lock_sha256'] == protocol['models_lock_sha256'] and fp['asr_run_sha256'] == protocol['asr_run_sha256'] and fp['baseline_source_sha256'] == protocol['baseline_source_sha256'], 'all scientific source fingerprints')
    for relative, expected in fp['code'].items():
        code_pin(relative, expected)
    check(fp['code']['tools/eval/probe_c2_native_parameters.py'] == '96c7a330483b2890f7ce9438a584e9191460568ce999296a0d9639c07b11f4d8', 'actual new runner source')
    for spec, actual in zip(lock['files'], fp['models']):
        check((actual['path'], actual['bytes'], actual['sha256'], actual['hashValidationCached']) == (spec['path'], spec['size'], spec['sha256'], False), 'actual per-process model validation pins')
    check(len(fp['models']) == 7 and fp['runtime']['version'] == '2.0.1' and fp['runtime']['onnxruntime'] == '1.28.2' and fp['runtime']['git'] == 'af2d8d81', 'pinned runtime metadata')
    extension = Path('/home/egor/replika-toolchain/host-venv/lib/python3.12/site-packages/sherpa_onnx/lib/_sherpa_onnx.cpython-312-x86_64-linux-gnu.so')
    check(digest(extension) == fp['runtime']['extension_sha256'], 'actual runtime binary SHA')
    check(sdk['num_clusters'] == -1 and sdk['threads'] == 2 and sdk['new_neural_inference'] is False, 'SDK metadata is configuration-only/automatic')
    for key, value in {'native_threshold': .3, 'window_shift': profile['window_shift'], 'min_duration_on': .2, 'min_duration_off': profile['min_duration_off']}.items():
        check(type(sdk['observed'][key]) in (float, int) and struct.pack('!f', sdk['observed'][key]).hex() == sdk['float32_bits'][key] == struct.pack('!f', value).hex(), ('actual SDK Float32 field', key))
    selected = []
    for case in cases:
        identifier, duration = case['id'], case['duration_ms']
        folder = directory / identifier
        item, e, e_sha = evidence(folder, case, digest(manifest_path.parent / case['reference']))
        diagnostic, metric = e['diagnostics.json'], e['metrics.json']
        d_case, d_e, d_sha = d_cases[identifier]
        b_case, b_e, b_sha = baseline_cases[identifier]
        source = fp['source_cases'][identifier]
        check(source == {'case_sha256': digest(d_root / identifier / 'case.json'), 'evidence_sha256': d_sha, 'baseline_case_sha256': digest(baseline_root / identifier / 'case.json'), 'baseline_evidence_sha256': b_sha}, 'strict actual-D/baseline per-case links')
        check(item['status'] == 'COMPLETE' and item['profile'] == profile['id'] and item['window_shift'] == profile['window_shift'] and item['min_duration_off'] == profile['min_duration_off'], 'single global profile per case')
        check(item['new_diarization_inference'] is True and item['new_embedding_inference'] is True and item['new_asr_inference'] is False and item['asr_replay'] is True and item['raw_asr_invariant'] is True, 'actual per-case neural/replay flags')
        check(diagnostic['newDiarizationInference'] is True and diagnostic['newEmbeddingInference'] is True and diagnostic['newAsrInference'] is False and diagnostic['asrReplay'] is True and diagnostic['originalPcm'] is True and diagnostic['sampleRate'] == 16000, 'original PCM and fresh NN stage contract')
        check(diagnostic['profile'] == profile and diagnostic['sdkConfig'] == sdk and diagnostic['modelFiles'] == fp['models'] and diagnostic['asrEvidenceSha256'] == d_sha and diagnostic['sourceDRunSha256'] == protocol['asr_run_sha256'], 'actual SDK/model/source diagnostic binding')
        raw_turns = turns(diagnostic['rawDiarizationTurns'], duration)
        native = turns(diagnostic['nativeDiarizationTurns'], duration)
        final = turns(diagnostic['diarizationTurns'], duration)
        check(base.stable_turns(raw_turns) == native, 'raw-to-stable speaker label mapping')
        windows = [speaker_refiner.EmbeddingWindow(**{**w, 'embedding': tuple(w['embedding'])}) for w in diagnostic['cleanEmbeddingWindows']]
        planned = speaker_refiner.clean_windows(native, duration)
        check([(w.start_ms, w.end_ms, w.speaker) for w in planned] == [(w.start_ms, w.end_ms, w.speaker) for w in windows], 'exact predicted clean-window coverage')
        for w in windows:
            check(w.clean is True and len(w.embedding) == 512 and all(math.isfinite(v) and struct.unpack('!f', struct.pack('!f', v))[0] == v for v in w.embedding) and math.hypot(*w.embedding) > 1e-12, 'actual finite promoted Float32 512-vector')
        counts = diagnostic['counts']
        check(counts['sdLoads'] == counts['sdProcessCalls'] == counts['extractorLoads'] == 1 and all(counts[k] is True for k in ('sdReleased', 'extractorReleased', 'nativeResourcesReleased')), 'fresh sequential model lifecycle')
        check(all(counts[k] == len(windows) for k in ('createdStreams', 'releasedStreams', 'computeAttempts', 'embeddingForwardCalls', 'plannedWindows', 'measuredWindows')) and counts['embeddingDimension'] == 512, 'actual window NN counts/releases')
        check(diagnostic['sdLoadMs'] > 0 and diagnostic['sdProcessMs'] > 0 and diagnostic['windowEmbeddingMs'] > 0, 'positive measured SD/embedding stage durations')
        replay = window_overcluster.overcluster(native, windows, duration, window_overcluster.WindowClusterConfig(**protocol['window_config']))
        check(replay.accepted is True and diagnostic['refinerAccepted'] is True and list(replay.turns) == final and replay.diagnostics == diagnostic['refiner'], 'exact selected C2 pure-window replay')
        chunks, actual_d_record, backend = diar_sweep.load_asr(d_root / identifier, case, item['reference_sha256'])
        check(actual_d_record == d_case and d_case['new_model_inference'] is True, 'actual original D NN source record')
        check(diar_sweep.project_asr(chunks, turns(d_e['diagnostics.json']['diarizationTurns'], duration), backend) == d_e['hypothesis.json'], 'original D words reconstruct original Jury')
        check(diar_sweep.project_asr(chunks, final, backend) == e['hypothesis.json'] and literal(e['hypothesis.json']) == literal(d_e['hypothesis.json']), 'actual D tokens/words replay and literal sequence invariant')
        fresh = score.score(e['reference.json'], e['hypothesis.json'], duration)
        for key, value in fresh.items():
            check(metric[key] == value, ('independent metric', identifier, key))
        for collar in (0, 250):
            check(score.der(e['reference.json']['transcript'], rows(final), duration, collar) == metric[f'native_der_collar_{collar}ms'], 'independent final native DER')
        count, truth = len({t.speaker for t in final}), metric['speakers']['reference']
        check((item['native_speaker_count'], item['reference_speaker_count'], item['native_speaker_count_error']) == (count, truth, abs(count-truth)), 'independent K/count error')
        check(metric['wer_raw'] == d_e['metrics.json']['wer_raw'], 'per-case raw WER unchanged')
        totals.update(sd_forward_calls=1, embedding_forward_calls=counts['embeddingForwardCalls'], released_streams=counts['releasedStreams'])
        selected.append(item)
        records.append({'profile': profile['id'], 'id': identifier, 'native_k': count, 'reference_k': truth, 'native_der0': metric['native_der_collar_0ms']['rate'], 'native_der250': metric['native_der_collar_250ms']['rate'], 'raw_errors': metric['wer_raw']['errors'], 'reference_words': metric['wer_raw']['reference_tokens'], 'real_windows': len(windows), 'evidence_sha256': e_sha, 'literal_word_replay': True, 'pure_c2_replay': True})
    aggregate = summary['aggregate']
    for field in ('wer_raw', 'wer_normalized', 'cpwer_raw', 'cpwer_normalized'):
        errors = sum(r['metrics'][field]['errors'] for r in selected)
        words = sum(r['metrics'][field]['reference_tokens'] for r in selected)
        check(aggregate[field] == {'errors': errors, 'reference_tokens': words, 'rate': errors/words}, ('independent profile edit aggregate', field))
    for field in ('native_der_collar_0ms', 'native_der_collar_250ms', 'der_collar_0ms', 'der_collar_250ms'):
        components = {key: sum(r['metrics'][field][key] for r in selected) for key in ('miss_ms', 'false_alarm_ms', 'confusion_ms', 'reference_speaker_ms')}
        components['rate'] = sum(components[k] for k in ('miss_ms', 'false_alarm_ms', 'confusion_ms')) / components['reference_speaker_ms']
        check(aggregate[field] == components, ('independent profile DER aggregate', field))
    exact = sum(r['native_speaker_count_error'] == 0 for r in selected)
    rate = aggregate['native_der_collar_0ms']['rate']
    conditions = {'complete_dev8': len(selected) == 8, 'raw_asr_invariant': all(r['raw_asr_invariant'] for r in selected) and aggregate['wer_raw']['errors'] == 71 and aggregate['wer_raw']['reference_tokens'] == 533, 'native_count_at_least7': exact >= 7, 'native_der_no_regrowth': rate <= limit}
    gate_pass = all(conditions.values())
    check(aggregate['cases'] == 8 and aggregate['speaker_count_exact_cases'] == exact and summary['conditions'] == conditions and summary['gate_pass'] == gate_pass and summary['strictly_better_der'] == (gate_pass and rate < limit) and summary['baseline_native_der0'] == limit, 'unchanged prespecified selection decision')
    check(aggregate['rtf'] is None and aggregate['rtf_diarization_stage'] is None, 'no partial/concurrent RTF claim')
    profiles.append({'id': profile['id'], 'window_shift': profile['window_shift'], 'min_duration_off': profile['min_duration_off'], 'exact_k_cases': exact, 'cases': 8, 'native_der0': rate, 'native_der250': aggregate['native_der_collar_250ms']['rate'], 'raw_errors': aggregate['wer_raw']['errors'], 'reference_words': aggregate['wer_raw']['reference_tokens'], 'gate_pass': gate_pass, 'strictly_better_der': summary['strictly_better_der'], 'sdk_config': sdk, 'run_sha256': digest(directory / 'run.json'), 'summary_sha256': digest(directory / 'summary.json')})

check(len(records) == totals['sd_forward_calls'] == 32 and totals['embedding_forward_calls'] == totals['released_streams'], 'all32 fresh SD/window cases accounted')
check(not any(p['gate_pass'] or p['strictly_better_der'] for p in profiles), 'all alternatives rejected; existing C2 retained')
for path, expected in hashes.copy().items():
    with Path(path).open('rb') as stream:
        check(hashlib.file_digest(stream, 'sha256').hexdigest() == expected, ('raw/source changed during audit', path))
source = Path(__file__).read_bytes()
source_sha = hashlib.sha256(source).hexdigest()
snapshot = STEP / 'runner-snapshots' / (source_sha + '.py')
if snapshot.exists():
    check(snapshot.read_bytes() == source, 'exact existing auditor snapshot')
else:
    with snapshot.open('xb') as stream: stream.write(source)
result = {'schema_version': 1, 'status': 'PASS', 'at': datetime.now(timezone.utc).isoformat(), 'checks': checks, 'scope': 'Independent saved-evidence integrity/replay/scoring audit of32 fresh final C2 native-parameter dev probes. PASS means valid rejection evidence, not acceptance of alternatives.', 'auditor_source_sha256': source_sha, 'auditor_source_snapshot': str(snapshot.relative_to(ROOT)), 'protocol_sha256': digest(protocol_path), 'source_sha256': hashes, 'source_version_resolutions': versions, 'totals': dict(totals), 'baseline': {'exact_k_cases': 7, 'cases': 8, 'native_der0': limit, 'window_shift': .1, 'min_duration_off': .5}, 'profiles': profiles, 'all_alternatives_rejected': True, 'selected_policy_unchanged': True, 'new_asr_inference': False, 'raw_D_replay_all32': True, 'holdout_reserve_or_ami_used_for_selection': False, 'new_global_C_gate': False, 'performance_claim': False, 'no_new_apk_or_revalidation_required_for_rejected_alternatives': True, 'reviewer_actions': {'neural_inference': False, 'source_model_main_edits': False, 'build': False, 'adb': False, 'git': False}, 'records': records}
with TARGET.open('x') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
lines = [f'Final C2 native-parameter probes: independent audit PASS, {checks} проверок, все32actualSD+windowNNdevcases. Все4альтернативы отвергнуты по заранее зафиксированному выбору; baselineC2неизменён.', '', '| Профиль | Shift | MinOff | Kexact | NativeDER0 | Selection |', '| --- | --- | --- | --- | --- | --- |', f'| baseline-existing | .1 | .5 | 7/8 | {limit*100:.6f}% | retain |']
for p in profiles:
    lines.append(f"| {p['id']} | {p['window_shift']} | {p['min_duration_off']} | {p['exact_k_cases']}/8 | {p['native_der0']*100:.6f}% | reject |")
lines += ['', f"Проверены source/model/input/reference/runtimeSHA, SDKFloat32bits всехminOn/minOff/shift/threshold,32freshSDcalls и{totals['embedding_forward_calls']}реальных512-dimensionalembeddingcalls сbalancedrelease; exactpureC2replay, actualcachedDword→Juryreplay, literal/rawWER71/533 во всех4полныхdev8профилях и независимый пересчётметрик/summary.", '', 'ГраницаSDKmetadata new_neural_inference=false относится только к чтениюconfig; actualcaseSD/windows NNотмечены отдельноtrue. ASRнеповторялся. Holdout/reserve/AMI не использовались длявыбора. Это финальнаяпроверкарекомендации minOff иselectedC2shift, а не новыйCgate/CPUтюнинг. RejectedvariantsнепереносятсявAPK; прежниеbaselinevalidationsсохраняются. Concurrenttimings не означаютускорение/fullpipelineRTF/ARM/телефоннуюприёмку. Raw/code/models/mainнеизменялись.']
with (STEP / 'final-native-parameter-audit.md').open('x') as stream:
    stream.write('\n'.join(lines) + '\n')
print(json.dumps({'status': 'PASS', 'checks': checks, 'totals': dict(totals), 'profiles': [{k: p[k] for k in ('id', 'exact_k_cases', 'native_der0', 'gate_pass')} for p in profiles], 'auditor_sha256': source_sha, 'audit_sha256': digest(TARGET)}, ensure_ascii=False))
