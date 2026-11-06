#!/usr/bin/env python3
"""Aggregate saved fixed-batch evidence. No inference, fitting or transcript edits."""
import collections,hashlib,json,pathlib,re

ROOT=pathlib.Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/test-evidence/v1.5'

def read(name):return json.loads((EVIDENCE/name).read_text())
def rows(name):return read(name)['asr']
def score(records,no_digits=False):
    if no_digits:records=[r for r in records if not re.search(r'\d',r['reference'])]
    errors=sum(r['wordErrors'] for r in records);words=sum(r['referenceWords'] for r in records)
    return {'files':len(records),'wordErrors':errors,'referenceWords':words,'wer':errors/words,'cer':sum(r['charErrors'] for r in records)/sum(r['referenceChars'] for r in records)}

def main():
    ordinary=rows('asr-host-ab.json')+rows('asr-host-holdout.json')
    ordinary=[r for r in ordinary if r['level']==1]
    base=rows('asr-host-v3-rnnt.json');ordinary+=[r for r in base if r['level']==1]
    groups=collections.defaultdict(list)
    for row in ordinary:groups[row['model']].append(row)
    result={'status':'Host experiments complete; Android acceptance is recorded separately','platform':'Linux WSL CPU, sherpa-onnx2.0.1, ASR2threads/VAD1thread; not phone performance','ordinary96':{m:score(r) for m,r in groups.items()},'ordinary96NoDigits':{m:score(r,True) for m,r in groups.items()},'selectedConfiguration':{'backend':'giga-v3','variant':'E2E RNNT INT8','decoding':'greedy_search','sampleRate':16000,'vadThreshold':.5,'vadMinSpeechSec':.25,'vadMinSilenceSec':.25,'vadMaxSpeechSec':20,'preRollMs':100,'postRollMs':0,'gainTriggerPeak':.01,'gainTargetPeak':.1,'gainMax':20,'gainSilenceFloor':1e-6,'originalPcmPreserved':True,'emptySlicesSkipAsrLoad':True},'limitations':['Fixed public convenience subset, not a broad Russian or whisper benchmark','Training overlap with public datasets cannot be ruled out','Literal digit formatting contributes heavily to all-reference WER improvement','Real Russian whisper and vivo microphone/thermal/battery performance are not confirmed','Automatic diarization is not declared fixed']}
    selectedQuiet=[r for r in rows('asr-host-quiet-safe.json')+rows('asr-host-holdout.json') if r['model']=='giga-v3' and r['level']==.01]
    result['quiet96WithGain']={'giga-v3-e2e':score(selectedQuiet),'giga-v3-base':score([r for r in base if r['level']==.01])}
    result['quiet96WithGainNoDigits']={'giga-v3-e2e':score(selectedQuiet,True),'giga-v3-base':score([r for r in base if r['level']==.01],True)}
    result['parakeet32']={str(level):score([r for r in rows('asr-host-parakeet.json') if r['level']==level]) for level in [1,.01]}
    result['pcm16Quiet32']={name:score(rows(file)) for name,file in [('e2eRaw','asr-host-e2e-pcm16-raw.json'),('e2eGain','asr-host-e2e-pcm16.json'),('baseGain','asr-host-v3-rnnt-pcm16.json')]}
    result['beam32']=score(rows('asr-host-beam.json'))
    controls=read('asr-host-negatives.json')['controls']+read('asr-host-negative-quiet-impulses.json')['controls']
    result['negativeControls']={'controls':len({r['id'] for r in controls}),'runs':len(controls),'directNonblank':sum(bool(r['directHypothesis'].strip()) for r in controls),'gatedNonblank':sum(any(t.strip() for t in r['gatedHypotheses']) for r in controls),'vadActivityOriginalIds':[r['id'] for r in controls if r['mode']=='original' and r['vadSpansSamples']],'vadActivityGainIds':[r['id'] for r in controls if r['mode']=='conservative_gain' and r['vadSpansSamples']]}
    vad=[]
    for file in ['asr-host-quiet-safe.json','asr-host-holdout.json']:
        vad += [r for r in read(file)['vad'] if r.get('language')=='ru' and r.get('level')==.01]
    result['quietVad96']={mode:{'files':len(group:=[r for r in vad if r['mode']==mode]),'filesWithNoDetectedSpeech':sum(r['detectedSec']==0 for r in group),'detectedSec':sum(r['detectedSec'] for r in group)} for mode in ['original','candidate_bounded_gain']}
    result['evidenceHashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(EVIDENCE.glob('*.json')) if p.name not in ['asr-final-summary.json'] and not p.name.startswith('android')}
    (EVIDENCE/'asr-final-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
