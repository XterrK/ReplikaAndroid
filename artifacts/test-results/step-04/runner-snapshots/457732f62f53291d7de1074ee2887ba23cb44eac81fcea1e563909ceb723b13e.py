import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tools.eval import score

ROOT = Path.cwd()
STEP = ROOT / 'artifacts/test-results/step-04'
raw, hashes, resolutions, rows = {}, {}, {}, []
equal = Counter()
totals = Counter()
checks = 0

def data(path):
    path = Path(path).resolve()
    key = str(path)
    if key not in raw:
        raw[key] = path.read_bytes()
        hashes[key] = hashlib.sha256(raw[key]).hexdigest()
    return raw[key]

def digest(path):
    data(path)
    return hashes[str(Path(path).resolve())]

def read(path):
    return json.loads(data(path))

def check(condition, label):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(label)

def code_pin(relative, expected):
    path = ROOT / relative
    if digest(path) != expected:
        path = STEP / 'runner-snapshots' / (expected + '.py')
    check(path.is_file() and digest(path) == expected, ('source version', relative, expected))
    resolutions[relative + '@' + expected] = str(path.relative_to(ROOT))

def record(folder, case, reference_sha):
    item = read(folder / 'case.json')
    evidence = {name: read(folder / name) for name in ('reference.json', 'hypothesis.json', 'metrics.json', 'diagnostics.json')}
    evidence_sha = {name: digest(folder / name) for name in evidence}
    check(item['evidence_sha256'] == evidence_sha and item['metrics'] == evidence['metrics.json'], ('evidence', case['id']))
    check(all(item[k] == case[k] for k in ('id', 'split', 'duration_ms', 'audio_sha256')), ('case input', case['id']))
    check(item['reference_sha256'] == reference_sha == evidence_sha['reference.json'], ('reference pin', case['id']))
    return item, evidence, {'case.json': digest(folder / 'case.json'), **evidence_sha}

def literal(document):
    return [word for row in sorted(document['transcript'], key=lambda r: (r['start_ms'], r['end_ms'])) for word in row['text'].split()]

def native(turns):
    return [{'speaker_id': 'native_' + str(t['speakerId']), 'start_ms': t['startMs'], 'end_ms': t['endMs'], 'text': ''} for t in turns]

freeze = read(STEP / 'candidate-c2-validation-freeze.json')
source_freeze = read(STEP / 'c2-full-host-source-freeze.json')
configuration = read(ROOT / 'configs/eval/c2-window-selected-full.json')
window_config = freeze['window_config']
check(window_config == source_freeze['config']['window_config'] == configuration['window_config'], 'frozen window config')
check(configuration['candidate_freeze_sha256'] == digest(STEP / 'candidate-c2-validation-freeze.json'), 'candidate freeze SHA')
check(all(configuration[k] == value for k, value in {'pipeline': 'window_words_v1', 'model_id': 'eres2net_zh', 'native_threshold': .3, 'window_shift': .1, 'threads': 2, 'expected_speakers': -1}.items()), 'global automatic full policy')
runtime_files = list(Path(sys.prefix).glob('lib/python*/site-packages/sherpa_onnx/lib/_sherpa_onnx*.so'))
check(len(runtime_files) == 1, 'one actual native extension')
runtime_sha = digest(runtime_files[0])
cached_code = {'runner': 'window_overcluster_sweep.py', 'refiner': 'window_overcluster.py', 'source_loader': 'refine_sweep.py', 'asr_replay_helpers': 'refiner_ablation.py', 'scorer': 'score.py'}
sd_code = {'runner': 'diar_sweep.py', 'baseline_helpers': 'pipeline.py', 'decoder_helpers': 'decoder_parity.py', 'word_helpers': 'vad_words.py', 'scorer': 'score.py', 'refiner_helpers': 'speaker_refiner.py'}
d_code = {'pipeline_code_sha256': 'pipeline_words.py', 'baseline_helpers_sha256': 'pipeline.py', 'decoder_code_sha256': 'decoder_parity.py', 'scorer_code_sha256': 'score.py', 'runner_code_sha256': 'run.py', 'word_planner_code_sha256': 'vad_words.py'}
cohorts = [('original', 'benchmark/eval/manifest.json', 'eval-audio', 'context600-selected-host', 13), ('reserve', 'benchmark/eval-reserve/manifest.json', 'eval-reserve-audio', 'reserve-context600-host', 10)]
full_runs = {}
for cohort, manifest_name, audio_name, d_name, expected in cohorts:
    manifest = ROOT / manifest_name
    corpus = read(manifest)
    full = STEP / ('candidate-c2-full-' + cohort)
    meta = read(full / 'run.json')
    fp = meta['fingerprint']
    d_root = ROOT / 'artifacts/test-results/step-03' / d_name
    d_meta = read(d_root / 'run.json')
    check(meta['status'] == 'COMPLETE' and meta['new_model_inference'] is True and meta['inference_requested'] is True, 'completed new full NN')
    check(len(corpus['files']) == expected and set(fp['selected_ids']) == {c['id'] for c in corpus['files']}, 'complete cohort')
    check(fp['manifest_sha256'] == digest(manifest) and read(full / 'manifest.json') == corpus, 'full manifest SHA/export')
    check(meta['config'] == configuration == read(full / 'config.json') and fp['config_sha256'] == digest(ROOT / 'configs/eval/c2-window-selected-full.json'), 'full config SHA/export')
    check(freeze['at'] < meta['started_at'] and source_freeze['at'] < meta['started_at'], 'freeze before inference')
    check(fp['model_lock_sha256'] == digest(ROOT / 'app/src/main/assets/models-lock.json') == d_meta['fingerprint']['model_lock_sha256'], 'same actual legacy model lock')
    check(d_meta['status'] == 'COMPLETE' and all(d_meta['config'][k] == value for k, value in {'pipeline': 'vad_words_v1', 'pre_roll_ms': 600, 'expected_speakers': -1}.items()), 'D automatic context600 source')
    for path, expected_sha in fp['code'].items():
        code_pin(path, expected_sha)
    for key, name in d_code.items():
        code_pin('tools/eval/' + name, d_meta['fingerprint'][key])
    for path, expected_sha in fp['packaged_models'].items():
        check(digest(ROOT / 'model-pack' / path) == expected_sha, ('actual model SHA', path))
    check(fp['runtime']['version'] == '2.0.1' and fp['runtime']['onnxruntime'] == '1.28.2' and fp['runtime']['extension_sha256'] == runtime_sha, 'actual runtime build pin')
    check(fp['external_embedding']['sha256'] == freeze['model']['sha256'] == fp['packaged_models']['diar/embedding.onnx'] and fp['external_embedding']['dimension'] == 512, 'C2 legacy ERes embedding bytes')
    check(fp['external_embedding']['catalog_sha256'] == digest(ROOT / 'configs/eval/diar-models.json'), 'catalog SHA')
    for case in corpus['files']:
        cid = case['id']
        dev = case['split'] == 'dev'
        label = 'reserve' if cohort == 'reserve' else case['split']
        cache = STEP / ('candidate-c2-reserve-refined' if cohort == 'reserve' else 'window-eres2net-030-average-small-fine-v1' if dev else 'candidate-c2-holdout-refined')
        sd = STEP / ('candidate-c2-reserve-diar' if cohort == 'reserve' else 'auto-eres2net-zh' if dev else 'candidate-c2-holdout-diar')
        cached_meta, cached_fp, sd_meta = read(cache / 'run.json'), read(cache / 'source-fingerprint.json'), read(sd / 'run.json')
        check(cached_meta['status'] == sd_meta['status'] == 'COMPLETE' and not cached_meta['failures'] and not cached_meta['pending_cases'], 'complete research sources')
        canonical = hashlib.sha256(json.dumps(cached_fp, sort_keys=True, allow_nan=False).encode()).hexdigest()
        check(canonical == cached_meta['source_fingerprint_sha256'] and cached_fp['config'] == cached_meta['config'], 'canonical cached source fingerprint')
        check(cached_fp['manifest'] == digest(manifest) and cached_fp['diar_run'] == digest(sd / 'run.json') and cached_fp['asr_run'] == digest(d_root / 'run.json'), 'cached run source links')
        check(cached_fp['model_id'] == 'eres2net_zh' and cached_fp['embedding_dimension'] == 512 and cached_meta['config']['profile'] == 'auto-0p30' and cached_meta['config']['method'] == 'average' and cached_meta['config']['refiner_config']['reassign_small'] is True, 'one global research policy')
        if not dev:
            check(cached_meta['config']['thresholds'] == [.36] and cached_meta['config']['expected_cases'] == (10 if cohort == 'reserve' else 5), 'prespecified full validation profile')
            check(cached_meta['config']['window_protocol_sha256'] == digest(ROOT / 'configs/eval/c2-window-selected-validation.json'), 'selected validation protocol SHA')
        for key, name in cached_code.items():
            code_pin('tools/eval/' + name, cached_fp[key])
        nfp = sd_meta['fingerprint']
        check(nfp['asr_run'] == digest(d_root / 'run.json') and nfp['manifest'] == digest(manifest) and nfp['embedding'] == fp['packaged_models']['diar/embedding.onnx'] and nfp['segmentation'] == fp['packaged_models']['diar/segmentation.onnx'] and nfp['catalog'] == fp['external_embedding']['catalog_sha256'], 'SD source/model policy links')
        for key, name in sd_code.items():
            code_pin('tools/eval/' + name, nfp[key])
        reference_sha = digest(manifest.parent / case['reference'])
        audio_sha = digest(Path('/home/egor/replika-toolchain') / audio_name / case['audio'])
        check(reference_sha == fp['references'][cid] and audio_sha == fp['audio'][cid] == case['audio_sha256'], 'actual independent input SHA')
        full_case, full_e, full_sha = record(full / cid, case, reference_sha)
        cached_case, cache_e, cache_sha = record(cache / 'tau-0p36' / cid, case, reference_sha)
        sd_case, sd_e, sd_sha = record(sd / 'auto-0p30' / cid, case, reference_sha)
        d_case, d_e, d_sha = record(d_root / cid, case, reference_sha)
        links = {'diar': sd_sha, 'asr': d_sha, 'reference': reference_sha, 'original_audio': audio_sha}
        check(links == cached_fp['cases'][cid] == cached_case['source_evidence_sha256'] == cache_e['diagnostics.json']['sourceEvidence'], 'per-case strict source links')
        diagnostic, cached_d, sd_d, d_d = (e['diagnostics.json'] for e in (full_e, cache_e, sd_e, d_e))
        metric, old = full_e['metrics.json'], cache_e['metrics.json']
        check(sd_d['asrEvidenceSha256'] == {k: v for k, v in d_sha.items() if k != 'case.json'}, 'SD ASR replay link')
        check(sd_case['mode'] == 'auto' and sd_case['model_id'] == 'eres2net_zh' and all(sd_d[k] == value for k, value in {'numClustersPassed': -1, 'threshold': .3, 'windowShiftRatio': .1, 'threads': 2}.items()), 'automatic native research config')
        check(diagnostic['pipelineVariant'] == 'window_words_v1' and diagnostic['refinementStrategy'] == 'window_v1' and diagnostic['expectedSpeakers'] == -1 and diagnostic['windowConfig'] == window_config == diagnostic['config']['refiner'] == cached_d['refiner']['config'], 'actual frozen full global strategy')
        check(all(diagnostic['config'][k] == value for k, value in {'nativeNumClusters': -1, 'nativeThreshold': .3, 'segmentationWindowShiftRatio': .1, 'threads': 2}.items()), 'actual full automatic native config')
        check(full_case['new_model_inference'] is True and all(full_case[k] is True for k in ('new_asr_inference', 'new_diarization_inference', 'new_embedding_inference')) and full_case['asr_replay'] is False, 'case actual NN markers')
        check(all(diagnostic[k] is True for k in ('newDiarizationInference', 'newAsrInference', 'newEmbeddingInference')) and diagnostic['asrReplay'] is False and diagnostic['nativeModelCacheRetained'] is False, 'diagnostic actual NN markers')
        check(diagnostic['wordAssignmentSupported'] is True and diagnostic['fallbackChunks'] == 0 and diagnostic['refinerAccepted'] is True and diagnostic['turnsUsedForAsrSlicing'] is False, 'complete supported VAD-only ASR')
        check({x['path']: x['sha256'] for x in diagnostic['modelFiles']} == fp['packaged_models'] and diagnostic['externalEmbedding']['sha256'] == fp['external_embedding']['sha256'] and diagnostic['externalEmbedding']['catalogSha256'] == fp['external_embedding']['catalog_sha256'] and digest(Path(diagnostic['externalEmbedding']['path'])) == fp['external_embedding']['sha256'], 'per-case actual model pins')
        check(diagnostic['validatedModelBytes'] == diagnostic['modelBytes'], 'same seven weights only')
        check(diagnostic['runtimeBuild']['extensionSha256'] == runtime_sha and diagnostic['runtimeBuild']['git'] == fp['runtime']['git'] and diagnostic['runtimeBuild']['onnxruntime'] == fp['runtime']['onnxruntime'], 'per-case actual runtime pins')
        for path, expected_sha in diagnostic['sourceFiles'].items():
            check(fp['code'][path] == expected_sha, 'per-case/full source pins')
        check(diagnostic['audioSha256'] == audio_sha and diagnostic['audioMs'] == case['duration_ms'], 'decoded source pin')
        comparisons = {
            'jury_json': full_e['hypothesis.json'] == cache_e['hypothesis.json'],
            'jury_bytes_sha': full_sha['hypothesis.json'] == cache_sha['hypothesis.json'],
            'literal_tokens': literal(full_e['hypothesis.json']) == literal(cache_e['hypothesis.json']) == literal(d_e['hypothesis.json']),
            'raw_native_turns': diagnostic['rawDiarizationTurns'] == sd_d['rawDiarizationTurns'],
            'stable_native_turns': diagnostic['nativeDiarizationTurns'] == sd_d['diarizationTurns'],
            'refined_turns': diagnostic['diarizationTurns'] == diagnostic['refinedDiarizationTurns'] == cached_d['diarizationTurns'],
            'actual_clean_vectors': diagnostic['cleanEmbeddingWindows'] == sd_d['cleanEmbeddingWindows'],
            'refiner_diagnostics': diagnostic['refiner'] == cached_d['refiner'],
            'asr_slices': len(diagnostic['asrSlices']) == len(d_d['asrSlices']) and all(all(a[k] == b[k] for k in ('startMs', 'endMs', 'text', 'tokens', 'timestamps')) for a, b in zip(diagnostic['asrSlices'], d_d['asrSlices'])),
        }
        for field in ('originalPcmPeak', 'recognitionInputGain', 'vadDetectorGain', 'vadPrimarySpanCount', 'vadRescueAttempted', 'vadRescueApplied', 'vadRescueRms', 'vadRescueRmsSamples', 'vadRescueSpanCount', 'vadSpans', 'asrChunks'):
            comparisons['vad_gain.' + field] = diagnostic[field] == d_d[field]
        for key, value in old.items():
            if key == 'rtf':
                continue
            if key == 'inputs':
                comparisons['metric.inputs_except_processing_ms'] = {k: v for k, v in metric[key].items() if k != 'processing_ms'} == {k: v for k, v in value.items() if k != 'processing_ms'}
            else:
                comparisons['metric.' + key] = metric[key] == value
        fresh = score.score(full_e['reference.json'], full_e['hypothesis.json'], case['duration_ms'])
        for key, value in fresh.items():
            if key not in ('inputs', 'rtf'):
                check(metric[key] == value, (cid, 'independent score', key))
        for collar in (0, 250):
            check(score.der(full_e['reference.json']['transcript'], native(diagnostic['diarizationTurns']), case['duration_ms'], collar) == metric[f'native_der_collar_{collar}ms'], 'independent final DER')
            check(metric[f'unrefined_native_der_collar_{collar}ms'] == sd_e['metrics.json'][f'native_der_collar_{collar}ms'], 'unrefined native DER')
        check(diagnostic['asrForwardCalls'] == len(diagnostic['asrSlices']) == len(diagnostic['asrChunks']) and diagnostic['embeddingForwardCalls'] == len(diagnostic['cleanEmbeddingWindows']), 'quantitative forward markers')
        check(all(diagnostic['stagesMs'][k] > 0 for k in ('diarizationInferenceMs', 'cleanEmbeddingStageMs', 'asrInferenceMs')), 'positive recorded neural-stage durations')
        for key, matched in comparisons.items():
            check(matched, (cid, key))
            equal[key] += int(matched)
        counts = {'asr_slices': len(diagnostic['asrSlices']), 'tokens': sum(len(x['tokens']) for x in diagnostic['asrSlices']), 'word_proxies': len(diagnostic['words']), 'clean_vectors': len(diagnostic['cleanEmbeddingWindows']), 'diarization_forwards': 1}
        totals.update(counts)
        rows.append({'id': cid, 'cohort': label, 'split': case['split'], 'full_run': str(full.relative_to(ROOT)), 'cached_refined_run': str(cache.relative_to(ROOT)), 'native_run': str(sd.relative_to(ROOT)), 'new_model_inference': True, 'asr_replay': False, 'counts': counts, 'all_equivalent': True, 'equivalence': comparisons, 'raw_errors': metric['wer_raw']['errors'], 'reference_words': metric['wer_raw']['reference_tokens'], 'native_k': metric['native_speaker_count'], 'reference_k': metric['speakers']['reference'], 'native_der_components': {k: metric['native_der_collar_0ms'][k] for k in ('miss_ms', 'false_alarm_ms', 'confusion_ms', 'reference_speaker_ms')}, 'full_evidence_sha256': full_sha, 'cached_evidence_sha256': cache_sha})
    full_runs[cohort] = {'run_sha256': digest(full / 'run.json'), 'config_sha256': fp['config_sha256'], 'started_at': meta['started_at'], 'completed_at': meta['completed_at'], 'cases': expected, 'new_model_inference': True}

check(len(rows) == 23, 'full23 coverage')
summary = {}
for label in ('dev', 'holdout', 'reserve'):
    selected = [row for row in rows if row['cohort'] == label]
    parts = {k: sum(row['native_der_components'][k] for row in selected) for k in ('miss_ms', 'false_alarm_ms', 'confusion_ms', 'reference_speaker_ms')}
    summary[label] = {'cases': len(selected), 'native_count_exact_cases': sum(row['native_k'] == row['reference_k'] for row in selected), 'native_der0': sum(parts[k] for k in ('miss_ms', 'false_alarm_ms', 'confusion_ms')) / parts['reference_speaker_ms'], 'raw_errors': sum(row['raw_errors'] for row in selected), 'reference_words': sum(row['reference_words'] for row in selected)}
for path, expected_sha in hashes.copy().items():
    check(hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected_sha, ('source changed during audit', path))
result = {'schema_version': 1, 'status': 'PASS', 'at': datetime.now(timezone.utc).isoformat(), 'scope': 'Read-only per-case equivalence of completed NEW full C2 host inference vs selected frozen research projections and actual saved D ASR. No Android/ARM/phone/release/speed acceptance.', 'cases': 23, 'checks': checks, 'failures': [], 'all_cases_exact': True, 'neural_inference_by_auditor': False, 'full_runs': full_runs, 'cohort_metrics': summary, 'equality_counts': dict(equal), 'actual_full_evidence_totals': dict(totals), 'nn_evidence_scope': 'Every case records fresh SD/clean embeddings/GigaAM, no ASR replay or retained cache, positive neural stage timings and forward counts; frozen source implements actual neural calls. Auditor runs no NN.', 'metric_scope': 'All common core metrics including raw/normalized WER, cpWER, punctuation, native/projected DER and segment timing proxy match per case. Only performance wall/stage/processing/RTF timings excluded. Standard metrics and final native DER independently rescored for all23; no aggregate cancellation.', 'history_scope': 'Historic source pins resolve to preserved snapshots where current versions differ, including dev runner6dd80 vs generic validation runner4c321. No old evidence rewritten.', 'limitations': ['Authored montage clip-interval proxy; no independent word gold or blind/natural-dialogue acceptance.', 'Reserve native count remains correct only5/10.', 'Host equivalence does not establish Android parity or phone performance.'], 'audit_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'source_version_resolutions': resolutions, 'source_sha256': hashes, 'rows': rows}
output = STEP / 'full-c2-equivalence-audit.json'
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
lines = ['Полный C2 host: аудит эквивалентности PASS, все23 файла, ' + str(checks) + ' проверок. Аудитор не запускал NN.', '', 'Все23 JuryJSON совпали побайтно. Новые ASR chunks/text/tokens/timestamps совпали с Dcontext600; raw/stable/refined turns, реальные clean-window vectors и refiner diagnostics — с выбранными C2 research projections. Все основные метрики, включая segment timing proxy, совпали по каждому файлу и пересчитаны независимо. Агрегаты не скрывают различий между файлами.', '', '| Набор | Верный K | NativeDER0 | RawWER |', '| --- | --- | --- | --- |']
for label, values in summary.items():
    lines.append(f"| {label} | {values['native_count_exact_cases']}/{values['cases']} | {values['native_der0']*100:.6f}% | {values['raw_errors']}/{values['reference_words']} |")
lines += ['', f"Новые полные прогоны: {totals['asr_slices']} ASR forwards, {totals['tokens']} tokens, {totals['word_proxies']} word proxies, {totals['clean_vectors']} реальных clean vectors. Проверены NN markers, counts, положительные stage timings, отсутствие replay/cache и все code/config/catalog/model-lock/model/reference/audio SHA с историческими source snapshots. Подробности — full-c2-equivalence-audit.json.", '', 'Исключено только время выполнения wall/stage/processing/RTF; скорость не заявляется. Это host-эквивалентность, а не Android/ARM/телефонная приёмка. Наборы — montage-прокси, word gold отсутствует, blind/natural-dialogue обобщение не установлено. Reserve K остаётся5/10.']
(STEP / 'full-c2-equivalence-audit.md').write_text('\n'.join(lines) + '\n')
print(json.dumps({'status': 'PASS', 'cases': 23, 'checks': checks, 'totals': dict(totals), 'cohorts': summary, 'audit_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}, ensure_ascii=False))
