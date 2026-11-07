"""Pure post-run integrity/count aggregation; no neural, audio or device APIs."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0,str(REPO))
from tools.eval.run import evidence_hashes


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol,freeze = load(HERE/'protocol.json'),load(HERE/'execution-freeze.json')
    assert sha(HERE/'protocol.json') == freeze['protocol_sha256']
    assert sha(HERE/'run_study.py') == freeze['procedure_sha256']
    assert datetime.fromisoformat(protocol['frozen_utc']) < datetime.fromisoformat(freeze['frozen_utc'])
    for key in ('source_sha256','source_code_sha256'):
        for relative,expected in protocol[key].items():
            assert sha(REPO/relative)==expected,relative
    summaries = load(HERE/'summaries.json')
    assert summaries['status']=='COMPLETE' and len(summaries['profiles'])==21
    assert load(HERE/'failures.json')==[]
    selection=load(HERE/'selection.json')
    assert selection['selected_tau'] is None and selection['passing_profiles']==0 and selection['promoted'] is False
    assert selection['new_neural_inference'] is False and selection['performance_claim'] is False
    inputs=load(REPO/protocol['manifest'])['files']
    dev={c['id']:c for c in inputs if c['split']=='dev'}
    checks=0
    for summary in summaries['profiles']:
        tau=summary['tau'];folder=HERE/'outputs'/('tau-'+format(tau,'.2f').replace('.','p'))
        assert sorted(p.name for p in folder.iterdir())==sorted(protocol['selected_ids'])
        records=[]
        for identifier in protocol['selected_ids']:
            case=folder/identifier;r=load(case/'case.json');d=load(case/'diagnostics.json')
            h=load(case/'hypothesis.json');m=load(case/'metrics.json')
            source=REPO/protocol['source_asr_run']/identifier
            source_h=load(source/'hypothesis.json');source_m=load(source/'metrics.json')
            assert r['evidence_sha256']==evidence_hashes(case)
            assert r['metrics']==m and r['refiner_accepted'] is True and d['refinerAccepted'] is True
            assert r['config']=={**protocol['base_window_config'],'tau':tau}
            assert r['audio_sha256']==dev[identifier]['audio_sha256']
            assert sha(case/'reference.json')==sha(REPO/Path(protocol['manifest']).parent/dev[identifier]['reference'])
            assert [w for row in h['transcript'] for w in row['text'].split()]==[w for row in source_h['transcript'] for w in row['text'].split()]
            for name in ('wer_raw','wer_normalized'):
                assert m[name]==source_m[name],(identifier,tau,name)
            assert all(r[name] is False for name in ('new_diarization_inference','new_embedding_inference','new_asr_inference'))
            if tau==.36:
                old=REPO/protocol['source_diar_run']/identifier
                assert h==load(old/'hypothesis.json')
                assert d['diarizationTurns']==load(old/'diagnostics.json')['diarizationTurns']
                old_m=load(old/'metrics.json')
                for name in ('wer_raw','wer_normalized','cpwer_raw','native_der_collar_0ms','native_der_collar_250ms'):
                    assert m[name]==old_m[name],(identifier,name)
            records.append(r);checks+=1
        assert len(records)==8
        exact=sum(r['native_speaker_count_error']==0 for r in records)
        assert exact==summary['speaker_count_exact_cases']
        assert sum(r['metrics']['wer_raw']['errors'] for r in records)==71
        assert sum(r['metrics']['wer_normalized']['errors'] for r in records)==16
        assert sum(r['metrics']['wer_raw']['reference_tokens'] for r in records)==533
        assert sum(r['metrics']['wer_normalized']['reference_tokens'] for r in records)==532
        native=[r['metrics']['native_der_collar_0ms'] for r in records]
        der=sum(v[k] for v in native for k in ('miss_ms','false_alarm_ms','confusion_ms'))/sum(v['reference_speaker_ms'] for v in native)
        assert der==summary['native_der_collar_0ms']['rate']
        cp=sum(r['metrics']['cpwer_raw']['errors'] for r in records)
        assert cp==summary['cpwer_raw']['errors']
        joint=exact>=7 and der<=.18298480576441103+1e-12 and cp<=146
        assert joint==summary['gate']['pass'] and joint is False
        assert summary['rtf'] is None and summary['new_diarization_inference'] is False
    result={'status':'PASS','actual_cached_vector_cases':8,'audited_case_outputs':checks,
        'global_thresholds':21,'tau036_matches_original_saved_source_exactly':True,
        'literal_D_words_raw_and_normalized_metrics_invariant':True,'source_hashes_unchanged':True,
        'protocol_frozen_before_execution':True,'strict_joint_gate_passing_profiles':0,
        'new_neural_inference':False,'performance_claim':False,'holdout_reserve_natural_used':False,
        'auditor_sha256':sha(Path(__file__))}
    with (HERE/'integrity-audit.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()
