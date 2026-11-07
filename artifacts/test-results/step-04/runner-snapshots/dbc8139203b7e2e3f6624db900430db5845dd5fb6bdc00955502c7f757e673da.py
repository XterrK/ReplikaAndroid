import hashlib
import json
import math
import struct
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tools.eval import native_diar_policy as policy, pipeline as base, score
from tools.eval.run import aggregate

ROOT = Path.cwd()
STEP = ROOT / 'artifacts/test-results/step-04'
OUT = STEP / 'context600-c2-android-v3'
HOST = STEP / 'candidate-c2-full-original'
if (OUT / 'independent-audit.json').exists() or (OUT / 'independent-audit.md').exists():
    raise FileExistsError('Fresh staging required; never overwrite an existing audit')
hashes, resolutions, rows, native_records, comparison = {}, {}, [], [], []
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
    return policy.strict_json(Path(path).read_bytes())

def check(condition, label):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(label)

def code_pin(relative, expected):
    path = ROOT / relative
    if digest(path) != expected:
        path = STEP / 'runner-snapshots' / (expected + '.py')
    check(path.is_file() and digest(path) == expected, ('source version', relative))
    resolutions[relative + '@' + expected] = str(path.relative_to(ROOT))

def native_rows(turns):
    return [{'speaker_id': 'native_' + str(t.speaker), 'start_ms': t.start_ms, 'end_ms': t.end_ms, 'text': ''} for t in turns]

def word_rows(parts):
    return [dict(word) for part in parts for word in part['words']]

def vector_diff(native, host):
    key = lambda w: (w['start_ms'], w['end_ms'], w['speaker'])
    a, b = {key(w): w['embedding'] for w in native}, {key(w): w['embedding'] for w in host}
    common = sorted(set(a) & set(b))
    pairs = [(x, y) for clock in common for x, y in zip(a[clock], b[clock])]
    return {'native_windows': len(a), 'host_windows': len(b), 'layout_equal': set(a) == set(b),
        'common_windows': len(common), 'native_only_clocks': [list(k) for k in sorted(set(a)-set(b))],
        'host_only_clocks': [list(k) for k in sorted(set(b)-set(a))],
        'exact_common_windows': sum(a[k] == b[k] for k in common),
        'compared_values': len(pairs), 'different_values': sum(x != y for x, y in pairs),
        'maximum_absolute_difference': max((abs(x-y) for x, y in pairs), default=None)}

run = read(OUT / 'run.json')
host_run = read(HOST / 'run.json')
android = read(OUT / 'android-report.json')
manifest_path = ROOT / 'benchmark/eval/manifest.json'
manifest = read(manifest_path)
cases = {c['id']: c for c in manifest['files']}
fp = run['fingerprint']
check(run['status'] == 'COMPLETE' and run['gate_pass'] is True and run['new_model_inference'] is True and run['inference_requested'] is True and not run.get('failures'), 'terminal successful actual collection')
check(run['reference_text_or_counts_staged'] is False and run['expected_speakers'] == -1 and run['threads'] == 2 and run['emulator'] is True, 'automatic CPU2 emulator scope/no gold staged')
check(run['full_project_accepted'] is False and run['arm_phone_performance_accepted'] is False, 'limited acceptance scope')
dev_ids = [c['id'] for c in manifest['files'] if c['split'] == 'dev']
fixed_ids = ['dev-01-two-clean', 'dev-03-short', 'holdout-02-three-clean', 'holdout-04-overlap-expressive', 'dev-mono-s']
ids = dev_ids + [i for i in fixed_ids if i not in dev_ids]
check(len(dev_ids) == 8 and len(fixed_ids) == 5 and len(ids) == 10 and run['dev_ids'] == dev_ids and run['fixed_five_ids'] == fixed_ids, 'exact distinct dev8/fixed5 union10')
check(set(row['id'] for row in run['cases']) == set(ids) and len(run['cases']) == 10, 'complete native union')
check(android['status'] == 'COMPLETE' and android['run'] == run['run'] and android['newModelInference'] is True and len(android['cases']) == 10 and set(r['id'] for r in android['cases']) == set(ids), 'actual Android batch report')
check(android['supportedAbis'][0] == 'x86_64', 'actual x86 proxy ABI')
check(run['screen_power']['pre_inference_awake_resumed'] is True and run['screen_power']['original_stay_on_while_plugged_in'] == run['screen_power']['restored_stay_on_while_plugged_in'] == '1' and not run['screen_power']['restoration_errors'], 'screen condition/restoration')
check(digest(manifest_path) == fp['manifest_sha256'] and digest(HOST / 'run.json') == fp['host_run_sha256'] and host_run['fingerprint'] == fp['host_fingerprint'], 'host/manifest source fingerprints')
check(host_run['status'] == 'COMPLETE' and host_run['new_model_inference'] is True, 'fresh full host source')
check(read(HOST / 'config.json') == host_run['config'] and digest(HOST / 'config.json') == host_run['fingerprint']['config_sha256'], 'host configuration pin')
policy.validate_host_policy(host_run['config'], host_run['paired_asr_policy'])
policy.validate_native_diar_policy(host_run['config'], android, host_run['paired_asr_policy'])
policy.equal(run['requested_diar_policy'], policy.policy_for_diar_plan(), 'collector requested policy')
for relative, expected in fp['collector_code'].items():
    code_pin(relative, expected)
check(set(fp['collector_code']) == {'tools/eval/pull_refined_android.py', 'tools/eval/native_diar_policy.py', 'tools/eval/native_policy.py', 'tools/eval/port_comparison.py'}, 'four semantic collector sources')
check(fp['collector_code']['tools/eval/pull_refined_android.py'] == '7cc15015f1fd328d61a5a4495700af907aba3104e03e8d6baa275efbe014737c' and fp['collector_code']['tools/eval/native_diar_policy.py'] == '82af9dd27356ac4b84f3793404b55d4515fbdd0ebcd19ab17758199273034609', 'frozen v5/v3 consumer sources')
for relative, expected in fp['host_fingerprint']['code'].items():
    code_pin(relative, expected)
lock_path = ROOT / 'app/src/main/assets/models-lock.json'
lock = read(lock_path)
pins = policy.validate_model_lock(lock)
check(digest(lock_path) == fp['model_lock_sha256'] and pins == run['native_model_sha256'] == host_run['fingerprint']['packaged_models'], 'seven actual remote model pins/host pack')
for spec in lock['files']:
    path = ROOT / 'model-pack' / spec['path']
    check(path.stat().st_size == spec['size'] and digest(path) == spec['sha256'], ('actual local model', spec['path']))
check(digest(ROOT / 'configs/eval/diar-models.json') == fp['host_fingerprint']['external_embedding']['catalog_sha256'], 'catalog pin')
build = read(STEP / 'build-c2-v2/summary.json')
check(build['status'] == 'PASS' and build['gradle_exit_code'] == 0 and build['build_flags'] == {'replikaAsrPlan': 'vad_words_context600', 'replikaDiarPlan': 'eres2net_window_v1'}, 'actual compiled candidate proof')
for relative, expected in build['sources_sha256'].items():
    check(digest(ROOT / relative) == expected, ('compiled Kotlin/source pin', relative))
for role, build_role in [('app', 'debug'), ('test', 'androidTest')]:
    spec = build['apks'][build_role]
    path = ROOT / spec['path']
    check(digest(path) == spec['sha256'] == fp['apk'][role]['sha256'] == run['installed_apks'][role]['sha256'] and path.stat().st_size == fp['apk'][role]['bytes'], ('actual installed/local compiled APK', role))
    if role == 'app':
        with zipfile.ZipFile(path) as archive:
            check(policy.validate_model_lock(policy.strict_json(archive.read('assets/models-lock.json'))) == pins, 'APK embedded lock')
aio = ROOT / build['candidate_release_path']
check(digest(aio) == build['apks']['allInOne']['sha256'] == 'a83bfe95cf7db72ddb65177a33586fdc52074a92759aa721212cc335f6b2a496', 'AIO candidate bytes; not executed ARM evidence')
check(digest(ROOT / build['apks']['allInOne']['path']) == digest(aio), 'release copy exact')
fixed_root = ROOT / 'artifacts/test-results/step-03/context600-android'
check(digest(fixed_root / 'run.json') == fp['fixed_five_run_sha256'], 'historical fixed5 source run pin')
fixed_run = read(fixed_root / 'run.json')
check(fixed_run['status'] == 'COMPLETE' and {r['id'] for r in fixed_run['cases']} == set(fixed_ids), 'historical five identity')
baseline_root = STEP / 'fixed-v16-production-comparison'
baseline = read(baseline_root / 'summary.json')
check(digest(baseline_root / 'summary.json') == fp['fixed_dev_baseline_summary_sha256'] == '6cf29600a98830f2b9fd76d9728f4aadaca0233c5d9de437dbf76e347e13417d' and digest(baseline_root / 'run.json') == fp['fixed_dev_baseline_run_sha256'], 'fixed native dev baseline pins')
batch = read(OUT / 'batch.json')
check(set(batch) == {'schema_version', 'run', 'cases'} and batch['run'] == run['run'] and len(batch['cases']) == 10 and {r['id'] for r in batch['cases']} == set(ids), 'audio-only staged batch')
for row in batch['cases']:
    check(set(row) == {'id', 'audio', 'sha256'} and row['audio'] == 'audio/' + row['id'] + '.wav' and row['sha256'] == cases[row['id']]['audio_sha256'], 'no reference/K staged')
for name in ('commands.jsonl', 'instrumentation.log', 'power-before.txt', 'power-pre-inference.txt', 'activity-pre-inference.txt', 'power-after.txt'):
    digest(OUT / name)
check('OK (1 test)' in (OUT / 'instrumentation.log').read_text() and 'FAILURES!!!' not in (OUT / 'instrumentation.log').read_text(), 'actual instrumentation completion')
seen_work, seen_recording = set(), set()
for identifier in ids:
    case = cases[identifier]
    folder, host_folder = OUT / identifier, HOST / identifier
    native_case = read(folder / 'case.json')
    scored = read(folder / 'scored-case.json')
    diagnostic = read(folder / 'diagnostics.json')
    hypothesis = read(folder / 'hypothesis.json')
    metrics = read(folder / 'metrics.json')
    reference = read(folder / 'reference.json')
    source_reference = ROOT / 'benchmark/eval' / case['reference']
    audio = Path('/home/egor/replika-toolchain/eval-audio') / case['audio']
    check(digest(audio) == case['audio_sha256'] == fp['host_fingerprint']['audio'][identifier] and digest(source_reference) == digest(folder / 'reference.json') == fp['host_fingerprint']['references'][identifier], 'actual input/reference pairing')
    policy.equal(native_case, next(r for r in android['cases'] if r['id'] == identifier), 'native report/case copy')
    policy.validate_native_diar_policy(host_run['config'], diagnostic, host_run['paired_asr_policy'])
    sidecar_path = folder / 'diarization-evidence.json'
    digest(sidecar_path)
    sidecar_raw = sidecar_path.read_bytes()
    replay = policy.validate_diarization_evidence(diagnostic, native_case, sidecar_raw, case_id=identifier, audio_sha256=case['audio_sha256'], duration_ms=case['duration_ms'])
    wrapper = policy.strict_json(sidecar_raw)
    check(native_case['workId'] not in seen_work and native_case['recordingId'] not in seen_recording, 'unique actual work/record UUID')
    seen_work.add(native_case['workId']); seen_recording.add(native_case['recordingId'])
    reconstructed, word_proof = policy.reconstruct_jury(diagnostic, case['duration_ms'])
    policy.equal(reconstructed, hypothesis, 'independent actual token/word/Jury replay')
    check(native_case['segments'] == len(hypothesis['transcript']), 'actual segment count')
    fresh = score.score(reference, hypothesis, case['duration_ms'], native_case['processing_ms'])
    for key, value in fresh.items():
        check(metrics[key] == value, (identifier, 'independent metric', key))
    turns = policy.turns_from_json(diagnostic['diarizationTurns'], case['duration_ms'])
    for collar in (0, 250):
        check(score.der(reference['transcript'], native_rows(turns), case['duration_ms'], collar) == metrics[f'native_der_collar_{collar}ms'], 'independent native DER')
    native_k = len({t.speaker for t in turns})
    check(metrics['native_speaker_count'] == native_k and metrics['native_speaker_count_error'] == abs(native_k-metrics['speakers']['reference']), 'independent native K')
    evidence = {name: digest(folder / name) for name in ('reference.json', 'hypothesis.json', 'diagnostics.json', 'metrics.json')}
    check(scored['status'] == 'COMPLETE' and scored['new_model_inference'] is True and scored['id'] == identifier and scored['metrics'] == metrics and scored['evidence_sha256'] == evidence and scored['reference_sha256'] == digest(source_reference) and scored['audio_sha256'] == digest(audio), 'scored-case evidence pins')
    host_case, host_diagnostic = read(host_folder / 'case.json'), read(host_folder / 'diagnostics.json')
    host_hypothesis, host_metrics = read(host_folder / 'hypothesis.json'), read(host_folder / 'metrics.json')
    check(digest(host_folder / 'case.json') == fp['selected_case_sha256'][identifier] and host_case['metrics'] == host_metrics and host_case['evidence_sha256'] == {name: digest(host_folder / name) for name in ('reference.json', 'hypothesis.json', 'diagnostics.json', 'metrics.json')}, 'actual host case evidence SHA')
    check(host_case['new_model_inference'] is True and host_case['asr_replay'] is False, 'host comparison fresh inference')
    host_words, native_words = word_rows(host_diagnostic['asrSlices']), word_rows(diagnostic['asrSlices'])
    host_words = [{k: v for k, v in w.items() if k != 'chunkIndex'} for w in host_words]
    changed_word_fields = Counter()
    word_differences = []
    for index, (left, right) in enumerate(zip(native_words, host_words)):
        differences = [k for k in set(left) | set(right) if left.get(k) != right.get(k)]
        if differences:
            changed_word_fields.update(differences)
            word_differences.append({'word_index': index, 'fields': sorted(differences), 'native': left, 'host': right})
    chunk_differences = []
    for index, (left, right) in enumerate(zip(diagnostic['asrSlices'], host_diagnostic['asrSlices'])):
        changed = [k for k in ('startMs', 'endMs', 'text', 'tokens', 'timestamps') if left[k] != right[k]]
        if changed:
            item = {'chunk_index': index, 'fields': changed}
            if 'text' in changed: item.update(native_text=left['text'], host_text=right['text'])
            if 'tokens' in changed: item.update(native_tokens=left['tokens'], host_tokens=right['tokens'])
            if 'timestamps' in changed: item['different_timestamp_positions'] = sum(a != b for a, b in zip(left['timestamps'], right['timestamps']))
            chunk_differences.append(item)
    diff = {'raw_turns_equal': diagnostic['rawDiarizationTurns'] == host_diagnostic['rawDiarizationTurns'],
        'stable_turns_equal': diagnostic['nativeDiarizationTurns'] == host_diagnostic['nativeDiarizationTurns'],
        'refined_turns_equal': diagnostic['diarizationTurns'] == host_diagnostic['diarizationTurns'],
        'vectors': vector_diff(wrapper['windows'], host_diagnostic['cleanEmbeddingWindows']),
        'native_chunks': len(diagnostic['asrSlices']), 'host_chunks': len(host_diagnostic['asrSlices']),
        'chunk_differences': chunk_differences, 'native_words': len(native_words), 'host_words': len(host_words),
        'changed_word_fields': dict(changed_word_fields), 'word_differences': word_differences,
        'jury_content_equal': hypothesis == host_hypothesis,
        'native_raw_errors': metrics['wer_raw']['errors'], 'host_raw_errors': host_metrics['wer_raw']['errors'],
        'native_normalized_errors': metrics['wer_normalized']['errors'], 'host_normalized_errors': host_metrics['wer_normalized']['errors']}
    counts = diagnostic['diarizationEmbeddingCounts']
    token_count = sum(len(p['tokens']) for p in diagnostic['asrSlices'])
    totals.update(sidecars=1, work_ids=1, extractor_loads=counts['extractorLoads'], measured_windows=counts['measuredWindows'], released_streams=counts['releasedStreams'], embedding_forward_calls=counts['embeddingForwardCalls'], asr_chunks=len(diagnostic['asrSlices']), tokens=token_count, word_proxies=len(native_words))
    row = {'id': identifier, 'split': case['split'], 'reference_words': metrics['wer_raw']['reference_tokens'], 'native_errors': metrics['wer_raw']['errors'], 'host_errors': host_metrics['wer_raw']['errors']}
    comparison.append(row)
    native_records.append({'id': identifier, 'split': case['split'], 'duration_ms': case['duration_ms'], 'processing_ms': native_case['processing_ms'], 'metrics': metrics})
    rows.append({'id': identifier, 'work_id': native_case['workId'], 'recording_id': native_case['recordingId'], 'native_k': native_k, 'reference_k': metrics['speakers']['reference'], 'raw_wer': metrics['wer_raw'], 'normalized_wer': metrics['wer_normalized'], 'cpwer_raw': metrics['cpwer_raw'], 'native_der0': metrics['native_der_collar_0ms'], 'native_der250': metrics['native_der_collar_250ms'], 'counts': counts, 'sidecar_proof': replay, 'word_proof': word_proof, 'evidence_sha256': evidence, 'host_differences': diff})
check(comparison == run['cases'], 'per-case paired error table')
fixed_rows = [next(r for r in comparison if r['id'] == identifier) for identifier in fixed_ids]
words = sum(r['reference_words'] for r in fixed_rows)
host_errors = sum(r['host_errors'] for r in fixed_rows)
native_errors = sum(r['native_errors'] for r in fixed_rows)
delta_pp = 100 * (native_errors-host_errors) / words
check((words, host_errors, native_errors) == (442, 44, 43) and abs(delta_pp) <= .5 and run['fixed_five_wer_port_gate']['wer_delta_percentage_points'] == delta_pp and run['fixed_five_wer_port_gate']['gate_pass'] is True, 'independent weighted historical fixed5 port gate')
check(run['fixed_five_wer_port_gate']['per_file_diagnostics'] == [{**r, 'wer_delta_percentage_points': 100*(r['native_errors']-r['host_errors'])/r['reference_words'], 'per_file_within_threshold': abs(100*(r['native_errors']-r['host_errors'])/r['reference_words']) <= .5} for r in fixed_rows], 'per-file outliers preserved')
dev = aggregate([r for r in native_records if r['id'] in dev_ids])
check(dev == run['dev_native_quality'], 'independent dev8 aggregate')
limit = baseline['native_der_collar_0ms']['rate'] + .02
dev_pass = dev['cases'] == 8 and dev['native_speaker_count_exact_cases'] >= 7 and dev['native_der_collar_0ms']['rate'] <= limit
check(dev_pass and run['dev_quality_gate']['gate_pass'] is True and run['dev_quality_gate']['native_der0'] == dev['native_der_collar_0ms']['rate'] and run['gate_pass'] is True and run['wer_port_parity_pass'] is True, 'unchanged separate dev gate')
check(dev['wer_raw']['errors'] == 70 and dev['wer_raw']['reference_tokens'] == 533 and dev['wer_normalized']['errors'] == 16 and dev['wer_normalized']['reference_tokens'] == 532 and dev['native_speaker_count_exact_cases'] == 7 and dev['native_der_collar_0ms']['rate'] == run['dev_host_quality']['native_der_collar_0ms']['rate'], 'actual dev metrics and exact aggregate DER comparison only')
check(len(seen_work) == len(seen_recording) == 10 and len(rows) == 10 and totals['measured_windows'] == totals['released_streams'] == totals['embedding_forward_calls'], 'complete fresh identities/resources')
for path, expected in hashes.copy().items():
    with Path(path).open('rb') as stream:
        check(hashlib.file_digest(stream, 'sha256').hexdigest() == expected, ('raw/source changed', path))
script = Path(__file__).read_bytes()
script_sha = hashlib.sha256(script).hexdigest()
snapshot = STEP / 'runner-snapshots' / (script_sha + '.py')
if snapshot.exists():
    check(snapshot.read_bytes() == script, 'existing exact auditor source snapshot')
else:
    with snapshot.open('xb') as stream: stream.write(script)
result = {'schema_version': 1, 'status': 'PASS', 'at': datetime.now(timezone.utc).isoformat(), 'checks': checks, 'cases': 10,
    'scope': 'Independent actual native10 integrity/replay/scoring audit; fixed5 port and dev8 quality gates remain separate. No new NN/ADB/build/Git/source edits by auditor.',
    'auditor_source_sha256': script_sha, 'auditor_source_snapshot': str(snapshot.relative_to(ROOT)), 'source_sha256': hashes, 'source_version_resolutions': resolutions,
    'totals': dict(totals), 'fixed_five_gate': {'cases': 5, 'reference_words': words, 'host_errors': host_errors, 'native_errors': native_errors, 'delta_percentage_points': delta_pp, 'maximum_absolute_delta_pp': .5, 'gate_pass': True, 'per_file_outliers_preserved': run['fixed_five_wer_port_gate']['per_file_diagnostics']},
    'dev_gate': {'cases': 8, 'native_k_exact': dev['native_speaker_count_exact_cases'], 'native_der0': dev['native_der_collar_0ms']['rate'], 'fixed_v16_der0': baseline['native_der_collar_0ms']['rate'], 'maximum_der0': limit, 'raw_wer': dev['wer_raw'], 'normalized_wer': dev['wer_normalized'], 'cpwer_raw': dev['cpwer_raw'], 'gate_pass': dev_pass},
    'both_gates_pass': True, 'screen_restored': True, 'native_vector_replay_cases': 10, 'token_word_jury_replay_cases': 10, 'all_core_metrics_rescored_cases': 10,
    'cross_runtime_scope': 'Host/native raw turns, actual embedding floats, timestamps and word rows are compared per case below; equal aggregate DER does not assert exact numerical NN parity or establish its cause.',
    'limitations': ['Actual x86_64 Android emulator only; wall timing uncontrolled and not algorithm-causal, ARM/phone or thermal/battery acceptance.', 'Authored montage utterance-interval DER proxy; no independent word gold.', 'Natural AMI diagnostic remains separate, with negative count/generalization findings; no pooling or tuning.', 'Gate success is not complete project acceptance; ordinary V1.6 fallback remains separately available.'], 'rows': rows}
with (OUT / 'independent-audit.json').open('x') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
lines = [f'C2 actual Android native10: independent audit PASS, {checks} проверок. Все10 sidecars и реальные512-мерныеvectors прошли C2replay; actualtokens→words→JuryJSON реконструированы, все основные метрики пересчитаны. Аудитор не запускалNN/ADB/build и не менял raw/source.', '', f'Historicalfixed5 rawWER: native{native_errors}/{words} противhost{host_errors}/{words}, Δ={delta_pp:.6f}п.п.; corpusgate absΔ<=0.5п.п. PASS. Perfileoutliers сохранены, остальныеdevфайлы не расширяютпулWER.', '', f"Отдельныйdev8: точноеK{dev['native_speaker_count_exact_cases']}/8, nativeDER0={dev['native_der_collar_0ms']['rate']*100:.6f}%, rawWER70/533, normalizedWER16/532. Count>=7 иDER<=fixedV1.6+2п.п. PASS.", '', f"Проверены actualinstalledAPKhashes, all7remote/localmodelpins, build/source/config/catalog/input/reference/sidecarSHA, UUID/lifecyclecounts/releases и отсутствиеfallback/truncation. Всего{totals['measured_windows']} реальныхwindows, {totals['asr_chunks']} ASRchunks, {totals['tokens']} tokens и{totals['word_proxies']} wordproxies. Screenstay-on restored1.", '', '| Файл | Rawerrors native/host | Rawturns equal | Exact common windows | Timestamp chunks differing |', '| --- | --- | --- | --- | --- |']
for row in rows:
    d = row['host_differences'];v = d['vectors']
    lines.append(f"| {row['id']} | {d['native_raw_errors']}/{d['host_raw_errors']} | {d['raw_turns_equal']} | {v['exact_common_windows']}/{v['common_windows']} | {sum('timestamps' in x['fields'] for x in d['chunk_differences'])} |")
lines += ['', 'Полные vector/text/token/timestamp/word различия пофайлам, доказательства иSHA — independent-audit.json. Не утверждается точное численное совпадениеNNмеждуhost/native; одинаковыйaggregateDER не доказывает его. x86timing uncontrolled, неcausal/ARM/телефонная/thermalприёмка. DER — montageproxy; AMInegative diagnostic остаётсяотдельным, безpooling/tuning/generalizationclaim. Это не полнаяприёмкапроекта.']
with (OUT / 'independent-audit.md').open('x') as stream:
    stream.write('\n'.join(lines) + '\n')
print(json.dumps({'status': 'PASS', 'checks': checks, 'totals': dict(totals), 'fixed5': [native_errors, host_errors, words, delta_pp], 'dev8': [dev['native_speaker_count_exact_cases'], dev['native_der_collar_0ms']['rate']], 'auditor_source_sha256': script_sha, 'audit_sha256': digest(OUT / 'independent-audit.json')}, ensure_ascii=False))
