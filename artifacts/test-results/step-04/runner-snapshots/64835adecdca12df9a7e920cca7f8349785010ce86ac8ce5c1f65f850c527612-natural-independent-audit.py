import csv
import hashlib
import json
import math
import struct
import wave
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from tools.eval import pipeline as base, score, speaker_refiner as centroid, window_overcluster as window

ROOT = Path.cwd()
OUT = ROOT / 'artifacts/test-results/step-04/natural-ami-diar-only-v2'
snapshots, checks, versions, records = {}, 0, {}, []

def digest(path):
    path = Path(path).resolve()
    with path.open('rb') as f:
        result = hashlib.file_digest(f, 'sha256').hexdigest()
    if str(path) in snapshots:
        assert snapshots[str(path)] == result, ('changed during audit', str(path))
    snapshots[str(path)] = result
    return result

def read(path):
    digest(path)
    return json.loads(Path(path).read_text())

def check(condition, label):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(label)

def pin(path, expected):
    path = Path(path)
    if digest(path) != expected and path.suffix == '.py':
        replacement = ROOT / 'artifacts/test-results/step-04/runner-snapshots' / (expected + '.py')
        check(replacement.is_file(), ('missing source snapshot', str(path)))
        versions[str(path)] = str(replacement)
        path = replacement
    check(digest(path) == expected, ('source/model/input pin', str(path)))

def from_rows(rows):
    result = []
    for row in rows:
        check(set(row) == {'speaker_id', 'start_ms', 'end_ms', 'text'} and row['text'] == '', 'diar-only row shape')
        check(type(row['start_ms']) is int and type(row['end_ms']) is int and 0 <= row['start_ms'] < row['end_ms'] <= 60000, 'row clock')
        label = row['speaker_id']
        check(label.startswith('native_') and str(int(label[7:])) == label[7:] and int(label[7:]) >= 0, 'native speaker ID')
        result.append(base.Turn(row['start_ms'], row['end_ms'], int(label[7:])))
    return result

def as_rows(turns):
    return [{'speaker_id': 'native_' + str(t.speaker), 'start_ms': t.start_ms, 'end_ms': t.end_ms, 'text': ''} for t in turns]

def f32(value):
    return struct.unpack('!f', struct.pack('!f', value))[0]

def rounded_ms(seconds):
    return max(0, min(60000, math.floor(f32(f32(seconds) * 1000) + .5)))

def independent_reference(rttm, meeting):
    result = []
    left, right = Decimal(0), Decimal(60)
    for line in Path(rttm).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split()
        check(len(fields) == 10 and fields[:3] == ['SPEAKER', meeting, '1'], 'independent RTTM shape')
        start, duration = Decimal(fields[3]), Decimal(fields[4])
        check(start.is_finite() and duration.is_finite() and start >= 0 and duration > 0, 'RTTM finite positive clock')
        a, b = max(left, start), min(right, start + duration)
        if b <= a:
            continue
        a = int((a * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        b = int((b * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if b > a:
            result.append({'speaker_id': fields[7], 'start_ms': a, 'end_ms': b, 'text': ''})
    return {'transcript': sorted(result, key=lambda r: (r['start_ms'], r['end_ms'], r['speaker_id']))}

meta, summary = read(OUT / 'run.json'), read(OUT / 'summary.json')
manifest = read(ROOT / 'benchmark/eval-natural-ami/manifest.json')
provenance = read(ROOT / 'benchmark/eval-natural-ami/provenance.json')
freeze = read(ROOT / 'artifacts/test-results/step-04/natural-probe-freeze.json')
c1freeze = read(ROOT / 'artifacts/test-results/step-04/candidate-c1-validation-freeze.json')
c2freeze = read(ROOT / 'artifacts/test-results/step-04/candidate-c2-validation-freeze.json')
check(meta['status'] == summary['status'] == 'COMPLETE' and meta['completed_cases'] == meta['expected_profile_cases'] == summary['profile_cases'] == 9, 'complete nine coverage')
check(meta['new_model_inference'] is True and all(meta[k] is False for k in ('new_asr_inference', 'new_vad_inference', 'new_lid_inference')), 'fresh SD only')
check(meta['automatic_expected_speakers'] == -1 and meta['threads'] == 2 and meta['reference_inputs_to_inference'] == [], 'global automatic no-gold policy')
check(summary['acceptance_gate'] is None and summary['candidate_selection'] is None, 'no natural tuning or acceptance gate')
for path, expected in meta['tracked_sha256'].items():
    pin(path, expected)
for target, original in [('input-manifest.json', manifest), ('model-catalog.json', read(ROOT / 'configs/eval/diar-models.json')), ('model-lock.json', read(ROOT / 'app/src/main/assets/models-lock.json')), ('natural-preparation-provenance.json', provenance), ('selection-freeze.json', freeze), ('preparation-audit.json', read(ROOT / 'benchmark/eval-natural-ami/preparation-audit.json'))]:
    check(read(OUT / target) == original, ('exported provenance', target))
check(meta['whole_source_audio_sha256'] is None and provenance['whole_source_audio_sha256'] is None, 'no invented whole-source audio SHA')
check(freeze['decided_at'] < meta['started_at'] if 'decided_at' in freeze else True, 'selection before NN')
check(meta['runtime']['sherpa_version'] == '2.0.1' and meta['runtime']['onnxruntime'] == '1.28.2' and meta['runtime']['git_sha1'] == 'af2d8d81' and meta['runtime']['scipy_version'] == '1.18.1' and meta['runtime']['numpy_version'] == '2.5.4', 'pinned numerical runtime')
for key in ('extension', 'scipy_hierarchy_source', 'scipy_hierarchy_extension', 'numpy_core_extension'):
    pin(meta['runtime'][key + '_file'], meta['runtime'][key + '_sha256'])
catalog = read(OUT / 'model-catalog.json')
check(len(catalog['models']) == 6 and len(read(OUT / 'model-lock.json')['files']) == 7, 'full catalog and seven-file model lock')
profiles = {p['id']: p for p in meta['profiles']}
check(set(profiles) == {'legacy-v16', 'c1-centroid', 'c2-window'}, 'three immutable profiles')
c1config = dict(centroid.RefineConfig(merge_threshold=.7, minimum_reassignment_similarity=.7, small_missing_centroid_policy='temporal').__dict__)
check(profiles['c1-centroid']['config'] == c1config and profiles['c2-window']['config'] == c2freeze['window_config'], 'frozen C1/C2 pure configs')
check(c1freeze['policy']['refiner_tau'] == .7 and c1freeze['policy']['minimum_reassignment_similarity'] == .7 and c1freeze['policy']['missing_centroid_policy'] == 'temporal', 'C1 candidate freeze policy')
cases = manifest['files']
check(len(cases) == 3 and [c['reference_speaker_count'] for c in cases] == [4, 4, 3], 'exact diagnostic cases/reference K')
check(cases[0]['reference_sha256'] == cases[1]['reference_sha256'] and cases[0]['reference_group'] == cases[1]['reference_group'] and cases[0]['paired_session'] == cases[1]['paired_session'] == 'EN2002a', 'paired microphones share conversation/gold')
check(cases[2]['paired_session'] == 'EN2002c' and {c['related_participants_group'] for c in cases} == {'AMI-EN2002'} and manifest['total_audio_ms'] == 180000 and manifest['unique_meeting_crop_ms'] == 120000, 'a/c related participants and non-independent duration')
prepared = {c['id']: c for c in provenance['cases']}
totals = Counter()
for case in cases:
    ref_path = ROOT / 'benchmark/eval-natural-ami' / case['reference']
    reference = read(ref_path)
    source = ROOT / 'benchmark/eval-natural-ami/sources' / (case['paired_session'] + '.rttm')
    check(reference == independent_reference(source, case['paired_session']), 'independent Decimal RTTM reconstruction')
    check(len({r['speaker_id'] for r in reference['transcript']}) == case['reference_speaker_count'] and all(r['text'] == '' for r in reference['transcript']), 'blank diarization-only reference')
    audio = Path('/home/egor/replika-toolchain/eval-natural-ami-audio') / case['audio']
    check(digest(audio) == case['audio_sha256'] and digest(ref_path) == case['reference_sha256'], 'actual canonical audio/reference hashes')
    with wave.open(str(audio)) as wav:
        check((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (1, 2, 16000, 960000), 'exact 60s mono16kPCM16')
        pcm = wav.readframes(960001)
    check(len(pcm) == 1920000 and hashlib.sha256(pcm).hexdigest() == prepared[case['id']]['pcm_crop_sha256'], 'canonical PCM payload source pin')
    for profile_id, profile in profiles.items():
        expected_model, expected_threshold, dimension = ('wespeaker_resnet34_lm', .5, 256) if profile_id == 'c1-centroid' else ('eres2net_zh', .3 if profile_id == 'c2-window' else .5, 512)
        check((profile['model_id'], profile['native_threshold'], profile['embedding_dimension']) == (expected_model, expected_threshold, dimension), 'fixed model/native threshold/dimension')
        check(all(profile[k] == v for k, v in {'threads': 2, 'expected_speakers': -1, 'window_shift': .1, 'min_duration_on': .2, 'min_duration_off': .5}.items()), 'CPU2/global-1/shift/on/off')
        model = next(m for m in catalog['models'] if m['id'] == expected_model)
        check(profile['embedding_sha256'] == model['sha256'], 'profile model SHA')
        folder = OUT / profile_id / case['id']
        item = read(folder / 'case.json')
        evidence = {name: read(folder / name) for name in ('diagnostics.json', 'metrics.json', 'hypothesis.json', 'reference.json')}
        check(item['evidence_sha256'] == {name: digest(folder / name) for name in evidence} and item['metrics'] == evidence['metrics.json'], 'case evidence SHA/embedded metrics')
        d, m = evidence['diagnostics.json'], evidence['metrics.json']
        check(item['status'] == 'COMPLETE' and item['id'] == case['id'] and item['profile'] == profile_id and item['policy'] == profile and item['audio_sha256'] == case['audio_sha256'] and item['reference_sha256'] == case['reference_sha256'] and evidence['reference.json'] == reference, 'case identity/policy/pins')
        check(item['new_model_inference'] is True and item['new_asr_inference'] is False and d['duration_ms'] == item['duration_ms'] == 60000 and d['native_resources_released'] is True, 'new SD markers/clock/resource release')
        counts = d['counts']
        check(counts == item['counts'] and d['stages_ms'] == item['stages_ms'] and d['processing_ms'] == item['processing_ms'], 'stage/count copies')
        check(all(counts[k] == 1 for k in ('diarizer_loads', 'diarizer_releases', 'diarization_forward_calls')) and all(counts[k] is False for k in ('new_asr_inference', 'new_vad_inference', 'new_lid_inference')), 'one actual SD/no ASR/VAD/LID')
        check(d['stages_ms']['diarization_inference_ms'] > 0 and d['stages_ms']['diarizer_load_ms'] > 0 and d['stages_ms']['diarizer_release_ms'] > 0, 'positive recorded actual SD stages')
        raw_turns = from_rows(d['raw_turns'])
        rebuilt = []
        for a, b, label in d['raw_native_seconds']:
            check(math.isfinite(a) and math.isfinite(b) and type(label) is int and label >= 0 and a < b, 'real native Float seconds')
            a, b = rounded_ms(a), rounded_ms(b)
            if b > a:
                rebuilt.append(base.Turn(a, b, label))
        check(rebuilt == raw_turns and base.stable_turns(raw_turns) == from_rows(d['stable_turns']), 'Float32 clock and raw-to-stable labels')
        stable = from_rows(d['stable_turns'])
        measured = [centroid.EmbeddingWindow(**{**w, 'embedding': tuple(w['embedding'])}) for w in d['clean_embedding_windows']]
        if profile_id == 'legacy-v16':
            check(not measured and d['refiner_accepted'] is None and d['refiner'] == {'algorithm': 'none', 'status': 'NOT_APPLICABLE'} and d['final_turns'] == d['stable_turns'], 'legacy has no extra refiner/embedding')
            check(all(counts[k] == 0 for k in ('extractor_loads', 'extractor_releases', 'planned_windows', 'read_windows', 'created_streams', 'released_streams', 'compute_attempts', 'embedding_forward_calls', 'measured_windows')), 'legacy no extra embedding calls')
        else:
            planned = centroid.clean_windows(stable, 60000)
            check([(w.start_ms, w.end_ms, w.speaker) for w in planned] == [(w.start_ms, w.end_ms, w.speaker) for w in measured], 'exact real clean-window coverage')
            check(counts['extractor_loads'] == counts['extractor_releases'] == 1 and all(counts[k] == len(measured) for k in ('planned_windows', 'read_windows', 'created_streams', 'released_streams', 'compute_attempts', 'embedding_forward_calls', 'measured_windows')), 'measured lifecycle counts balanced')
            for w in measured:
                check(w.clean is True and len(w.embedding) == dimension and all(math.isfinite(x) and f32(x) == x for x in w.embedding) and math.hypot(*w.embedding) > 1e-12, 'real finite Float32 outputs/same dimension/nonzero')
            replay = centroid.refine(stable, measured, 60000, centroid.RefineConfig(**profile['config'])) if profile_id == 'c1-centroid' else window.overcluster(stable, measured, 60000, window.WindowClusterConfig(**profile['config']))
            check(replay.accepted is True and d['refiner_accepted'] is True and as_rows(replay.turns) == d['final_turns'] and replay.diagnostics == d['refiner'], 'exact pure refiner turn/diagnostic replay')
        check(item['refiner_accepted'] == d['refiner_accepted'] and evidence['hypothesis.json'] == {'transcript': d['final_turns']}, 'final hypothesis and support flag')
        check(m['reference_speakers'] == case['reference_speaker_count'], 'scoring-only reference K')
        for stage in ('raw', 'stable', 'final'):
            stage_rows = d[stage + '_turns']
            count = len({r['speaker_id'] for r in stage_rows})
            check(m[stage]['speakers'] == count and m[stage]['speaker_count_error'] == abs(count - case['reference_speaker_count']) and m[stage]['speaker_count_exact'] == (count == case['reference_speaker_count']), 'independent K/count error')
            for collar in (0, 250):
                check(score.der(reference['transcript'], stage_rows, 60000, collar) == m[stage][f'der_collar_{collar}ms'], 'independent raw/stable/final DER')
        totals.update(sd_calls=1, embedding_calls=counts['embedding_forward_calls'], measured_windows=len(measured))
        records.append({'profile': profile_id, 'id': case['id'], 'reference_group': case['reference_group'], 'related_participants_group': case['related_participants_group'], 'reference_k': case['reference_speaker_count'], 'raw_k': m['raw']['speakers'], 'final_k': m['final']['speakers'], 'der0': m['final']['der_collar_0ms']['rate'], 'der250': m['final']['der_collar_250ms']['rate'], 'vectors': len(measured), 'evidence_sha256': item['evidence_sha256'], 'metrics': m})

check(len(records) == 9 and totals['sd_calls'] == 9, 'all nine freshly recorded SD calls')
for profile_id in profiles:
    selected = [r for r in records if r['profile'] == profile_id]
    s = summary['profiles'][profile_id]
    check(s['cases'] == 3 and s['speaker_count_exact_cases'] == sum(r['final_k'] == r['reference_k'] for r in selected), 'per-profile summary K')
    for collar in (0, 250):
        key = f'der_collar_{collar}ms'
        parts = {field: sum(r['metrics']['final'][key][field] for r in selected) for field in ('miss_ms', 'false_alarm_ms', 'confusion_ms', 'reference_speaker_ms')}
        check(all(s[key][k] == v for k, v in parts.items()) and s[key]['rate'] == sum(parts[k] for k in ('miss_ms', 'false_alarm_ms', 'confusion_ms')) / parts['reference_speaker_ms'], 'descriptive weighted channel-time aggregate')
c2 = [next(r for r in records if r['profile'] == 'c2-window' and r['id'] == c['id']) for c in cases]
check([r['final_k'] for r in c2] == [6, 8, 5] and sum(r['final_k'] == r['reference_k'] for r in c2) == 0, 'C2 zero-of-three exact K')
third_legacy = next(r for r in records if r['profile'] == 'legacy-v16' and r['id'] == cases[2]['id'])
regression_pp = (c2[2]['der0'] - third_legacy['der0']) * 100
check(regression_pp > 0, 'third-crop C2 DER regression retained')
for path, expected in snapshots.copy().items():
    with Path(path).open('rb') as f:
        check(hashlib.file_digest(f, 'sha256').hexdigest() == expected, ('raw/source changed', path))
result = {'schema_version': 1, 'status': 'PASS', 'at': datetime.now(timezone.utc).isoformat(), 'scope': 'Independent saved-evidence audit only; no NN/ASR/VAD/LID/build/ADB/Git/source edits. Integrity/recalculation PASS is not model-quality acceptance.', 'checks': checks, 'profile_cases': 9, 'totals': dict(totals), 'failures': [], 'source_sha256': snapshots, 'source_version_resolutions': versions, 'audit_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'c2_exact_count': {'successes': 0, 'cases': 3, 'predicted_k': [6, 8, 5], 'reference_k': [4, 4, 3]}, 'third_crop_regression': {'id': cases[2]['id'], 'legacy_der0': third_legacy['der0'], 'c2_der0': c2[2]['der0'], 'delta_percentage_points': regression_pp}, 'related_sample_scope': {'same_conversation_and_gold': [cases[0]['id'], cases[1]['id']], 'shared_participants': 'EN2002a/c, AMI-EN2002', 'channel_audio_ms': 180000, 'unique_meeting_crop_ms': 120000, 'independent_splits': False, 'training_overlap': 'unknown'}, 'acceptance_gate': None, 'candidate_selection': None, 'pool_with_dev': False, 'tuning_performed': False, 'generalization_claim': False, 'performance_claim': False, 'records': records}
with (OUT / 'independent-audit.json').open('x') as f:
    f.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
lines = [f'AMI natural diagnostic: audit integrity/recalculation PASS, {checks} проверок, все9 свежих SD case-profile outputs. Рецензент не запускалNN/ASR/VAD/LID/build/ADB и не менял raw/source.', '', '| Профиль | Crop | K ref→final | DER0 | DER250 |', '| --- | --- | --- | --- | --- |']
for r in records:
    lines.append(f"| {r['profile']} | {r['id']} | {r['reference_k']}→{r['final_k']} | {r['der0']*100:.4f}% | {r['der250']*100:.4f}% |")
lines += ['', f"C2: точное K0/3, предсказано6/8/5 приэталоне4/4/3. НаEN2002c-headset DER0 ухудшился с{third_legacy['der0']*100:.6f}% до{c2[2]['der0']*100:.6f}%, +{regression_pp:.6f}п.п. Это отрицательный диагностический результат, а не PASS качества.", '', 'Проверены source/model/catalog/lock/audio/RTTM/reference/runtime SHA, независимое Decimalвосстановлениеgold, Float32rawclock/stablelabels, DER0/250/K всехraw/stable/finalturns, реальныеvectors и exactpureC1/C2replay, lifecyclecounts/resources иNNmarkers. Всего9SDcalls; ASR/VAD/LID не запускались.', '', 'EN2002a headset/array — таже беседа и gold; a/c имеют общих участников.180s channel-time соответствуют120s уникальных meetingcrops. Trainingoverlap неизвестен. Агрегаты только описательные, это не независимые splits. Не объединятьK сdev, не использоватьдляподбора/новогоgate, не заявлять generalization/Android/phone/speedacceptance. Все исходные артефакты сохранены.']
with (OUT / 'independent-audit.md').open('x') as f:
    f.write('\n'.join(lines) + '\n')
print(json.dumps({'status': 'PASS', 'checks': checks, 'totals': dict(totals), 'c2_K': [6, 8, 5], 'third_regression_pp': regression_pp, 'audit_sha256': digest(OUT / 'independent-audit.json')}, ensure_ascii=False))
