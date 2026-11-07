#!/usr/bin/env python3
"""Read-only CPU quality audit: hashes, saved-vector/token replay, independent score. No NN."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True


def cpu_policy(diag, threads, asr, window):
    expected = {'plan': 'auto_v1', 'asrThreads': threads, 'diarizationThreads': threads,
                'refinementThreads': threads, 'vadThreads': 1}
    cpu = diag.get('cpuExecutionPolicy', {})
    if any(type(cpu.get(k)) is not type(v) or cpu.get(k) != v for k, v in expected.items()):
        return False
    config = diag.get('config', {})
    fixed = {'provider': 'cpu', 'threads': threads, 'vadThreads': 1, 'nativeNumClusters': -1,
             'nativeThreshold': .3, 'segmentationWindowShiftRatio': .1,
             'diarMinDurationOnSec': .2, 'diarMinDurationOffSec': .5,
             'cleanWindowMs': 1500, 'cleanWindowStepMs': 750, 'cleanMinimumIslandMs': 1000,
             'refiner': window, 'asr': asr}
    if config != fixed or diag.get('pairedAsrPolicy') != asr:
        return False
    if diag.get('selectedNativePolicy') != {'model_id': 'eres2net_zh', 'threshold': .3,
            'window_shift': .1, 'threads': threads, 'num_clusters': -1}:
        return False
    native = diag.get('nativeConfigString', '')
    return (re.findall(r'\bnum_threads=(\d+)', native) == [str(threads), str(threads)]
            and native.count('provider="cpu"') == 2
            and all(value in native for value in ('window_shift_ratio=0.1', 'num_clusters=-1',
                'threshold=0.3', 'min_duration_on=0.2', 'min_duration_off=0.5')))


def quality_conditions(actual, baseline):
    conditions = {}
    for name in ('wer_raw', 'wer_normalized', 'cpwer_raw'):
        conditions[name + '_denominator_unchanged'] = actual[name]['reference_tokens'] == baseline[name]['reference_tokens']
        conditions[name + '_errors_not_greater'] = actual[name]['errors'] <= baseline[name]['errors']
    conditions['native_der0_not_greater'] = actual['native_der_collar_0ms']['rate'] <= baseline['native_der_collar_0ms']['rate'] + 1e-12
    conditions['native_count_exact_not_fewer'] = actual['native_speaker_count_exact_cases'] >= baseline['native_speaker_count_exact_cases']
    return conditions


class Audit:
    def __init__(self, repo):
        self.repo, self.hashes, self.resolutions, self.checks = repo, {}, {}, 0

    def check(self, condition, label):
        self.checks += 1
        if not condition:
            raise AssertionError(str(label))

    def sha(self, path):
        path = Path(path).resolve()
        if str(path) not in self.hashes:
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            self.hashes[str(path)] = h.hexdigest()
        return self.hashes[str(path)]

    def read(self, path):
        self.sha(path)
        return json.loads(Path(path).read_bytes(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

    def pin(self, relative, expected):
        candidates = [self.repo / relative]
        for step in ('step-04', 'step-05'):
            candidates.extend((self.repo / 'artifacts/test-results' / step / 'runner-snapshots').glob(expected + '*.py'))
        matches = [p for p in candidates if p.is_file() and self.sha(p) == expected]
        self.check(bool(matches), ('preserved source pin', relative, expected))
        self.resolutions[relative + '@' + expected] = str(matches[0].relative_to(self.repo))

    def case(self, folder, spec, reference_sha):
        record = self.read(folder / 'case.json')
        evidence = {name: self.read(folder / name) for name in ('reference.json', 'hypothesis.json', 'diagnostics.json', 'metrics.json')}
        self.check(record['evidence_sha256'] == {name: self.sha(folder / name) for name in evidence}, ('case evidence hashes', spec['id']))
        self.check(record['metrics'] == evidence['metrics.json'], ('embedded metrics', spec['id']))
        self.check(all(record[k] == spec[k] for k in ('id', 'split', 'duration_ms', 'audio_sha256')), ('case input identity', spec['id']))
        self.check(record['reference_sha256'] == reference_sha == self.sha(folder / 'reference.json'), ('independent reference bytes', spec['id']))
        self.check(type(record['processing_ms']) in (int, float) and math.isfinite(record['processing_ms']) and record['processing_ms'] > 0, ('positive processing clock', spec['id']))
        return record, evidence

    def verify_unchanged(self):
        for name, expected in list(self.hashes.items()):
            h = hashlib.sha256()
            with Path(name).open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            self.check(h.hexdigest() == expected, ('input unchanged throughout audit', name))


def audit(args, a):
    sys.path.insert(0, str(args.repo))
    from tools.eval import pipeline as base, pipeline_refined as full, score
    from tools.eval.speaker_refiner import EmbeddingWindow, clean_windows
    from tools.eval.vad_words import words_from_tokens, assign_words, group_words, plan_vad_chunks
    from tools.eval.window_overcluster import overcluster, WindowClusterConfig
    from tools.eval.run import aggregate
    import numpy as np

    repo, run = args.repo, args.run
    protocol_path = repo / 'configs/eval/cpu-auto-v1-protocol.json'
    protocol = a.read(protocol_path)
    manifest_path = repo / protocol['case_manifest']
    manifest = a.read(manifest_path)
    cases = manifest['files']
    baseline = repo / protocol['baseline_run']
    meta, old_meta = a.read(run / 'run.json'), a.read(baseline / 'run.json')
    fp, old_fp = meta['fingerprint'], old_meta['fingerprint']
    config = a.read(repo / f'configs/eval/cpu-auto-v1-threads{args.threads}.json')
    old_config = a.read(repo / 'configs/eval/c2-window-selected-full.json')
    selected = [c['id'] for c in cases]
    a.check(len(cases) == len(set(selected)) == 13 and Counter(c['split'] for c in cases) == {'dev': 8, 'holdout': 5}, 'fixed full13/cohorts')
    a.check(args.threads in protocol['threads_to_measure'] and protocol['cpu_plan'] == 'auto_v1', 'frozen thread protocol')
    a.check(meta['status'] == old_meta['status'] == 'COMPLETE', 'both runs terminal COMPLETE')
    a.check(meta['inference_requested'] is True and meta['new_model_inference'] is True, 'actual full new inference markers')
    a.check(datetime.fromisoformat(protocol['frozen_at']) < datetime.fromisoformat(meta['started_at']), 'protocol before inference')
    a.check(fp['selected_ids'] == old_fp['selected_ids'] == selected and a.read(run / 'manifest.json') == manifest == a.read(baseline / 'manifest.json'), 'exact order and coverage')
    a.check({p.name for p in run.iterdir() if p.is_dir()} == set(selected), 'no omitted or extra case directories')
    a.check(fp['manifest_sha256'] == old_fp['manifest_sha256'] == a.sha(manifest_path), 'canonical manifest SHA')
    a.check(meta['config'] == config == a.read(run / 'config.json') and fp['config_sha256'] == a.sha(repo / f'configs/eval/cpu-auto-v1-threads{args.threads}.json'), 'explicit CPU configuration SHA')
    a.check(old_meta['config'] == old_config == a.read(baseline / 'config.json') and old_fp['config_sha256'] == a.sha(repo / 'configs/eval/c2-window-selected-full.json'), 'frozen C2 baseline configuration SHA')
    a.check(config['cpu_plan'] == 'auto_v1' and type(config['threads']) is int and config['threads'] == args.threads, 'explicit global threads and opt-in')
    options = {k: v for k, v in config.items() if k not in ('id', 'notes', 'cpu_plan', 'threads')}
    a.check(options == {k: v for k, v in old_config.items() if k not in ('id', 'notes', 'threads')}, 'CPU is sole inference configuration change')
    a.check(a.sha(protocol_path) in config['notes'], 'configuration binds pre-inference protocol SHA')
    freeze_path = repo / 'artifacts/test-results/step-04/candidate-c2-validation-freeze.json'
    freeze = a.read(freeze_path)
    a.check(config['candidate_freeze_sha256'] == a.sha(freeze_path) and config['window_config'] == freeze['window_config'], 'frozen candidate and window settings')
    a.check(all(config[k] == v for k, v in {'pipeline': 'window_words_v1', 'expected_speakers': -1, 'model_id': 'eres2net_zh', 'window_shift': .1, 'native_threshold': .3}.items()), 'no known-K or per-file inference parameters')
    asr = {**old_meta['paired_asr_policy'], 'threads': args.threads}
    a.check(meta['paired_asr_policy'] == asr, 'only paired ASR thread count changes')
    a.check(fp['model_lock_sha256'] == old_fp['model_lock_sha256'] == a.sha(repo / 'app/src/main/assets/models-lock.json'), 'original model-lock SHA')
    lock = a.read(repo / 'app/src/main/assets/models-lock.json')
    a.check(len(lock['files']) == 7 and fp['packaged_models'] == old_fp['packaged_models'] == {m['path']: m['sha256'] for m in lock['files']}, 'same seven model bytes')
    for item in lock['files']:
        path = repo / 'model-pack' / item['path']
        a.check(path.stat().st_size == item['size'] and a.sha(path) == item['sha256'], ('actual model bytes', item['path']))
    a.check(fp['external_embedding'] == old_fp['external_embedding'] and fp['external_embedding']['catalog_sha256'] == a.sha(repo / 'configs/eval/diar-models.json'), 'unchanged actual embedding/catalog pins')
    a.check(fp['runtime'] == old_fp['runtime'] and fp['runtime']['version'] == importlib.metadata.version('sherpa-onnx') == '2.0.1', 'identical sherpa/runtime build metadata')
    runtime_files = list(Path(sys.prefix).glob('lib/python*/site-packages/sherpa_onnx/lib/_sherpa_onnx*.so'))
    a.check(len(runtime_files) == 1 and a.sha(runtime_files[0]) == fp['runtime']['extension_sha256'], 'actual installed native extension SHA')
    for relative, expected in fp['code'].items():
        a.pin(relative, expected)
        a.check(a.sha(repo / relative) == expected, ('CPU inference code still frozen', relative))
    for relative, expected in old_fp['code'].items():
        a.pin(relative, expected)
        if relative not in ('tools/eval/pipeline_refined.py', 'tools/eval/run_refined.py'):
            a.check(expected == fp['code'][relative], ('unchanged pure/ASR/decoder/scorer dependency', relative))
    tree = ast.parse((repo / 'tools/eval/pipeline_refined.py').read_text())
    process = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'process')
    a.check(not any('reference' in item.arg or 'gold' in item.arg or 'case_id' in item.arg for item in process.args.args + process.args.kwonlyargs), 'inference API contains no reference/case-specific argument')
    calls = [node for node in ast.walk(process) if isinstance(node, ast.Call)]
    sd = [node for node in calls if ast.unparse(node.func) == 'diar_sweep.make_config']
    extra = [node for node in calls if ast.unparse(node.func) == 'diar_sweep.extract_windows']
    asr_calls = [node for node in calls if ast.unparse(node.func) == 'sherpa.OfflineRecognizer.from_transducer']
    a.check(len(sd) == len(extra) == len(asr_calls) == 1 and ast.unparse(sd[0].args[2]) == '-1' and ast.unparse(sd[0].args[5]) == 'threads' and ast.unparse(extra[0].args[3]) == 'threads' and next(ast.unparse(k.value) for k in asr_calls[0].keywords if k.arg == 'num_threads') == 'threads', 'frozen actual SDK calls bind automatic K and all three stage threads')
    records, old_records, rows, totals = [], [], [], Counter()
    for spec in cases:
        cid, duration = spec['id'], spec['duration_ms']
        audio = args.audio_root / spec['audio']
        reference_path = manifest_path.parent / spec['reference']
        reference_sha, audio_sha = a.sha(reference_path), a.sha(audio)
        a.check(reference_sha == fp['references'][cid] == old_fp['references'][cid] and audio_sha == spec['audio_sha256'] == fp['audio'][cid] == old_fp['audio'][cid], ('actual canonical input hashes', cid))
        record, e = a.case(run / cid, spec, reference_sha)
        old_record, old_e = a.case(baseline / cid, spec, reference_sha)
        d, metric = e['diagnostics.json'], e['metrics.json']
        old_d, old_metric = old_e['diagnostics.json'], old_e['metrics.json']
        a.check(cpu_policy(d, args.threads, asr, config['window_config']), ('per-stage CPU/SD SDK policy', cid))
        a.check(all(record.get(k) is True for k in ('new_model_inference', 'new_diarization_inference', 'new_embedding_inference', 'new_asr_inference')) and record.get('asr_replay') is False, ('case fresh-inference markers', cid))
        a.check(all(d.get(k) is True for k in ('newDiarizationInference', 'newEmbeddingInference', 'newAsrInference', 'refinerAccepted', 'wordAssignmentSupported')) and all(d.get(k) is False for k in ('asrReplay', 'nativeModelCacheRetained', 'turnsUsedForAsrSlicing', 'refinerFallbackToNative')) and d['fallbackChunks'] == 0, ('supported fresh inference without replay/cache', cid))
        a.check(d['expectedSpeakers'] == -1 and d['clusteringMode'] == 'automatic' and d['pipelineVariant'] == 'window_words_v1' and d['refinementStrategy'] == 'window_v1', ('automatic global pipeline', cid))
        a.check(d['audioSha256'] == audio_sha and d['audioMs'] == duration and d['sampleRate'] == 16000, ('diagnostic source clock', cid))
        a.check({m['path']: m['sha256'] for m in d['modelFiles']} == fp['packaged_models'] and d['modelBytes'] == d['validatedModelBytes'] == sum(m['size'] for m in lock['files']), ('per-case seven model pins', cid))
        a.check(d['externalEmbedding']['sha256'] == fp['external_embedding']['sha256'] and d['externalEmbedding']['catalogSha256'] == fp['external_embedding']['catalog_sha256'] and d['externalEmbedding']['embeddingDimension'] == 512, ('per-case measured embedder pin', cid))
        a.check(d['runtimeBuild'] == old_d['runtimeBuild'] and d['runtimeBuild']['extensionSha256'] == fp['runtime']['extension_sha256'], ('per-case runtime pin', cid))
        a.check(all(fp['code'][path] == expected for path, expected in d['sourceFiles'].items()), ('per-case source SHA', cid))
        a.check(d['windowConfig'] == config['window_config'] == d['refiner']['config'] and d['refiner']['algorithm'] == 'window-overcluster-v1' and d['refiner']['status'] in ('SUPPORTED', 'PARTIAL_TEMPORAL'), ('frozen supported C2 refiner', cid))
        def turns(items):
            a.check(all(type(t['speakerId']) is int and t['speakerId'] >= 0 and type(t['startMs']) is int and type(t['endMs']) is int and 0 <= t['startMs'] < t['endMs'] <= duration for t in items), ('strict native turn clocks/labels', cid))
            return [base.Turn(t['startMs'], t['endMs'], t['speakerId']) for t in items]
        raw, stable = turns(d['rawDiarizationTurns']), turns(d['nativeDiarizationTurns'])
        a.check(base._turn_json(base.stable_turns(raw)) == d['nativeDiarizationTurns'], ('raw-to-stable replay', cid))
        measured = d['cleanEmbeddingWindows']
        expected_windows = clean_windows(stable, duration)
        a.check([(w.start_ms, w.end_ms, w.speaker) for w in expected_windows] == [(w['start_ms'], w['end_ms'], w['speaker']) for w in measured], ('clean windows from native activity only', cid))
        for w in measured:
            a.check(w['clean'] is True and len(w['embedding']) == 512 and all(type(x) in (int, float) and math.isfinite(x) for x in w['embedding']) and any(w['embedding']), ('finite measured nonzero 512-vector', cid))
        observations = [EmbeddingWindow(w['start_ms'], w['end_ms'], w['speaker'], tuple(w['embedding']), w['clean']) for w in measured]
        # This API receives only predicted native activity, actual vectors and one global config.
        refined = overcluster(stable, observations, duration, WindowClusterConfig(**config['window_config']))
        a.check(refined.accepted is True and refined.diagnostics == d['refiner'] and base._turn_json(refined.turns) == d['diarizationTurns'] == d['refinedDiarizationTurns'], ('actual-window complete C2 replay', cid))
        a.check(d['tokenTimestampPolicy']['verified'] is True and d['tokenTimestampPolicy']['frame_stride_ms'] == 40, ('actual token emission stride', cid))
        samples = base._read_canonical_wav(audio, np)
        a.check(len(samples) * 1000 // 16000 == duration, ('canonical decoded duration', cid))
        bounded = base.context_spans([base.Span(s['startMs'], s['endMs']) for s in d['vadSpans']], duration, 600, 0)
        a.check(base._span_json(bounded) == d['asrSpeechSpans'] and base._span_json(plan_vad_chunks(bounded, samples, 20000, True)) == d['asrChunks'], ('original-PCM VAD energy chunk replay', cid))
        segments, words = [], []
        a.check(len(d['asrChunks']) == len(d['asrSlices']) == d['asrForwardCalls'] and len(measured) == d['embeddingForwardCalls'], ('quantitative neural-call markers', cid))
        for index, (chunk, item) in enumerate(zip(d['asrChunks'], d['asrSlices'])):
            a.check(all(chunk[k] == item[k] for k in ('startMs', 'endMs')) and len(item['tokens']) == len(item['timestamps']), ('actual chunk token bounds/count', cid, index))
            parsed = words_from_tokens(item['text'], item['tokens'], item['timestamps'], item['startMs'], item['endMs'], 40)
            a.check(parsed.supported is True and item['wordAssignmentSupported'] is True and parsed.reason == item['wordAssignmentReason'], ('word timestamp support/reason', cid, index))
            assigned = assign_words(parsed.words, list(refined.turns))
            values = [{'startMs': w.start_ms, 'endMs': w.end_ms, 'text': w.text, 'speakerId': w.speaker, 'warnings': list(w.reasons), 'chunkIndex': index} for w in assigned]
            a.check(values == item['words'], ('actual token-to-word speaker replay', cid, index))
            words.extend(values)
            segments.extend(group_words(assigned, base.SOURCE, 'none'))
        a.check(words == d['words'] and segments == d['segments'], ('per-chunk word grouping exact', cid))
        hypothesis = {'transcript': base.jury_projection(segments)}
        a.check(hypothesis == e['hypothesis.json'], ('strict Jury projection replay', cid))
        a.check(set(hypothesis) == {'transcript'} and all(set(row) == {'speaker_id', 'start_ms', 'end_ms', 'text'} for row in hypothesis['transcript']), ('strict Jury schema', cid))
        # Gold is used only for scoring after the saved-data replay above.
        reference = a.read(reference_path)
        a.check(reference == e['reference.json'], ('separate canonical reference', cid))
        fresh = score.score(reference, hypothesis, duration, record['processing_ms'])
        for key, value in fresh.items():
            a.check(value == metric[key], ('independent scorer field', cid, key))
        old_fresh = score.score(reference, old_e['hypothesis.json'], duration, old_record['processing_ms'])
        for key, value in old_fresh.items():
            a.check(value == old_metric[key], ('independent baseline scorer field', cid, key))
        native = lambda rows: [{'speaker_id': 'native_' + str(t['speakerId']), 'start_ms': t['startMs'], 'end_ms': t['endMs'], 'text': ''} for t in rows]
        for collar in (0, 250):
            a.check(score.der(reference['transcript'], native(d['diarizationTurns']), duration, collar) == metric[f'native_der_collar_{collar}ms'], ('independent refined native DER', cid, collar))
            a.check(score.der(reference['transcript'], native(d['nativeDiarizationTurns']), duration, collar) == metric[f'unrefined_native_der_collar_{collar}ms'], ('independent initial native DER', cid, collar))
            a.check(score.der(reference['transcript'], native(old_d['diarizationTurns']), duration, collar) == old_metric[f'native_der_collar_{collar}ms'], ('independent baseline refined native DER', cid, collar))
        count = len({t['speakerId'] for t in d['diarizationTurns']})
        a.check(type(metric['native_speaker_count']) is int and metric['native_speaker_count'] == count and metric['native_speaker_count_error'] == abs(count - fresh['speakers']['reference']), ('speaker counts from real intervals', cid))
        old_count = len({t['speakerId'] for t in old_d['diarizationTurns']})
        a.check(type(old_metric['native_speaker_count']) is int and old_metric['native_speaker_count'] == old_count and old_metric['native_speaker_count_error'] == abs(old_count - old_fresh['speakers']['reference']), ('baseline speaker counts from real intervals', cid))
        a.check(all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in d['stagesMs'].values()) and all(d['stagesMs'][key] > 0 for key in ('diarizationInferenceMs', 'cleanEmbeddingStageMs', 'asrInferenceMs')), ('positive finite neural timings', cid))
        equivalence = {key: d[key] == old_d[key] for key in ('rawDiarizationTurns', 'nativeDiarizationTurns', 'refinedDiarizationTurns', 'cleanEmbeddingWindows', 'refiner', 'words')}
        equivalence['jury_bytes'] = a.sha(run / cid / 'hypothesis.json') == a.sha(baseline / cid / 'hypothesis.json')
        equivalence['asr_tokens_timestamps'] = len(d['asrSlices']) == len(old_d['asrSlices']) and all(all(x[k] == y[k] for k in ('startMs', 'endMs', 'text', 'tokens', 'timestamps', 'words')) for x, y in zip(d['asrSlices'], old_d['asrSlices']))
        equivalence['core_metrics'] = all(value == old_metric[key] for key, value in metric.items() if key not in ('inputs', 'rtf')) and {k:v for k,v in metric['inputs'].items() if k!='processing_ms'} == {k:v for k,v in old_metric['inputs'].items() if k!='processing_ms'}
        if args.threads == 2:
            a.check(all(equivalence.values()), ('mandatory control2 exact preservation', cid))
        totals.update(clean_vectors=len(measured), asr_chunks=len(d['asrSlices']), tokens=sum(len(x['tokens']) for x in d['asrSlices']), words=len(words), sd_calls=1)
        rows.append({'id': cid, 'split': spec['split'], 'raw_errors': metric['wer_raw']['errors'], 'reference_tokens': metric['wer_raw']['reference_tokens'], 'native_k': count, 'reference_k': fresh['speakers']['reference'], 'native_der0': metric['native_der_collar_0ms']['rate'], 'baseline_native_der0': old_metric['native_der_collar_0ms']['rate'], 'raw_error_delta': metric['wer_raw']['errors']-old_metric['wer_raw']['errors'], 'native_der0_delta_pp': (metric['native_der_collar_0ms']['rate']-old_metric['native_der_collar_0ms']['rate'])*100, 'baseline_equivalence': equivalence, 'evidence_sha256': {name: a.sha(run/cid/name) for name in ('case.json','reference.json','hypothesis.json','diagnostics.json','metrics.json')}})
        records.append(record); old_records.append(old_record)
    summary = a.read(run / 'summary.json')
    a.check(summary['status'] == 'COMPLETE' and summary['expected_cases'] == 13 and summary['all'] == aggregate(records), 'recomputed complete corpus summary')
    cohorts = {}
    for split, size in protocol['cohorts'].items():
        actual = aggregate([r for r in records if r['split'] == split])
        prior = aggregate([r for r in old_records if r['split'] == split])
        a.check(actual['cases'] == prior['cases'] == size and summary['by_split'][split] == actual, ('independent cohort summary', split))
        declared = protocol['baseline'][split]
        a.check(all(declared[k] == v for k, v in {'raw_errors': prior['wer_raw']['errors'], 'raw_reference_words': prior['wer_raw']['reference_tokens'], 'normalized_errors': prior['wer_normalized']['errors'], 'cpwer_raw_errors': prior['cpwer_raw']['errors'], 'count_exact': prior['native_speaker_count_exact_cases'], 'native_der0': prior['native_der_collar_0ms']['rate']}.items()), ('protocol baseline independently pinned', split))
        conditions = quality_conditions(actual, prior)
        cohorts[split] = {'status': 'PASS' if all(conditions.values()) else 'FAIL', 'conditions': conditions, 'actual': actual, 'baseline': prior}
    a.verify_unchanged()
    return {'status': 'PASS', 'integrity_status': 'PASS', 'quality_gate': 'PASS' if all(c['status'] == 'PASS' for c in cohorts.values()) else 'FAIL', 'cases': 13, 'threads': args.threads, 'cpu_plan': 'auto_v1', 'run': str(run.relative_to(repo)), 'run_sha256': a.sha(run/'run.json'), 'baseline_run': str(baseline.relative_to(repo)), 'protocol_sha256': a.sha(protocol_path), 'checks': a.checks, 'cohorts': cohorts, 'totals': dict(totals), 'rows': rows, 'source_sha256': a.hashes, 'source_version_resolutions': a.resolutions}


def self_test():
    template = {'wer_raw': {'errors': 2, 'reference_tokens': 10}, 'wer_normalized': {'errors': 1, 'reference_tokens': 9}, 'cpwer_raw': {'errors': 3, 'reference_tokens': 10}, 'native_der_collar_0ms': {'rate': .2}, 'native_speaker_count_exact_cases': 7}
    import copy
    checks = 0
    assert all(quality_conditions(template, template).values()); checks += 1
    for field in ('wer_raw', 'wer_normalized', 'cpwer_raw'):
        changed = copy.deepcopy(template); changed[field]['errors'] += 1
        assert not all(quality_conditions(changed, template).values()); checks += 1
        changed = copy.deepcopy(template); changed[field]['reference_tokens'] += 1
        assert not all(quality_conditions(changed, template).values()); checks += 1
    changed = copy.deepcopy(template); changed['native_der_collar_0ms']['rate'] += 1e-9
    assert not all(quality_conditions(changed, template).values()); checks += 1
    changed = copy.deepcopy(template); changed['native_speaker_count_exact_cases'] -= 1
    assert not all(quality_conditions(changed, template).values()); checks += 1
    assert not cpu_policy({}, 2, {}, {}); checks += 1
    print(json.dumps({'self_test': 'PASS', 'checks': checks, 'neural_inference': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--run', type=Path)
    parser.add_argument('--threads', type=int, choices=(1, 2, 4))
    parser.add_argument('--audio-root', type=Path, default=Path('/home/egor/replika-toolchain/eval-audio'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.run is None or args.threads is None or args.output is None:
        parser.error('--run, --threads and --output are required')
    args.repo, args.run, args.output = args.repo.resolve(), args.run.resolve(), args.output.resolve()
    md = args.output.with_suffix('.md')
    if args.output.exists() or md.exists():
        raise ValueError('Fresh audit output required; no overwrite')
    a = Audit(args.repo)
    try:
        result = audit(args, a)
    except BaseException as error:
        result = {'status': 'FAIL', 'integrity_status': 'FAIL', 'quality_gate': 'NOT_EVALUATED', 'checks': a.checks, 'error': {'type': type(error).__name__, 'message': str(error)}, 'source_sha256': a.hashes, 'source_version_resolutions': a.resolutions}
    script = Path(__file__).read_bytes(); script_sha = hashlib.sha256(script).hexdigest()
    snapshot = args.repo / 'artifacts/test-results/step-05/runner-snapshots' / (script_sha + '-independent-cpu-audit.py')
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.exists():
        if snapshot.read_bytes() != script:
            raise ValueError('Immutable script snapshot collision')
    else:
        with snapshot.open('xb') as stream: stream.write(script)
    result.update(schema_version=1, at=datetime.now(timezone.utc).isoformat(), audit_script_sha256=script_sha, audit_script_snapshot=str(snapshot.relative_to(args.repo)), neural_inference_by_auditor=False, scope='Saved full host CPU execution regression, each already-seen cohort separately. References only score after real-window/token replay. No Android/ARM/phone, general-dialogue, timing-gold or causal speed acceptance.', limitations=['NN provenance is established from frozen executing source, runtime/model/input hashes, actual saved vectors/tokens, positive timings and forward markers; auditor never creates a model.', 'Native SDK config string verifies both SD submodel num_threads. Extra embedding/ASR thread policy is bound by frozen call source and stage diagnostics, not a scheduler utilization trace.', 'Montage interval proxies and previously seen regression cohorts; no independent word-boundary or natural-dialogue gold.', 'Sequential timing order/caches uncontrolled; no causal speed result.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream: stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    lines = [f"Независимый CPU-аудит: {result['status']}; качество: {result['quality_gate']}.", '', f"Проверок: {result['checks']}. Нового NN-инференса аудитор не запускал."]
    if result['status'] == 'PASS':
        lines += ['', '| Группа | Верное K | Native DER0 | Raw WER | Гейт |', '| --- | ---: | ---: | ---: | --- |']
        for split, cohort in result['cohorts'].items():
            v=cohort['actual']; lines.append(f"| {split} | {v['native_speaker_count_exact_cases']}/{v['cases']} | {v['native_der_collar_0ms']['rate']*100:.6f}% | {v['wer_raw']['errors']}/{v['wer_raw']['reference_tokens']} | {cohort['status']} |")
        lines += ['', 'Повторно проверены хеши всех источников и каждого case/evidence, реальные CPU/SD SDK параметры, исходные/стабильные интервалы, чистые окна и все векторы. C2 целиком воспроизведён из actual embeddings; слова/говорящие/группы/Jury JSON — из фактических токенов и timestamps; WER/cpWER/DER0/250/K пересчитаны по отдельным каноническим эталонам. Контроль2 обязан совпасть с C2 по каждому файлу, а качество 1/4 оценивается раздельно по двум группам, без усреднения регресса.', '', f"Полный JSON: [{args.output.name}]({args.output.name}). SHA скрипта: `{script_sha}`."]
    else:
        lines += ['', str(result['error'])]
    lines += ['', 'Это регрессионная проверка уже просмотренного монтажного корпуса. Общая приёмка естественного диалога, независимых времён слов, Android/ARM/телефона и скорости не заявляется. Времена сохранены, но порядок/кеши не контролируются.']
    with md.open('x', encoding='utf-8') as stream: stream.write('\n'.join(lines)+'\n')
    print(json.dumps({k: result.get(k) for k in ('status','integrity_status','quality_gate','threads','cases','checks','error','audit_script_sha256')}, ensure_ascii=False))
    if result['status'] != 'PASS': raise SystemExit(1)


if __name__ == '__main__':
    main()
