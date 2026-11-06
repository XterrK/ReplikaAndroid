#!/usr/bin/env python3
"""Reproducible Linux CPU comparison. No phone/performance/real RU whisper claim.

Uses only held-out references for scoring; no reference words enter recognizers.
Synthetic attenuation preserves voiced-speech acoustics and is NOT whisper.
"""
import argparse, collections, hashlib, json, math, os, pathlib, re, struct, sys, time

def file_sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):h.update(chunk)
    return h.hexdigest()

def read_wav(path,np):
    b=path.read_bytes();assert b[:4]==b'RIFF' and b[8:12]==b'WAVE'
    pos=12;fmt=None;raw=None
    while pos+8<=len(b):
        tag,n=struct.unpack_from('<4sI',b,pos);data=b[pos+8:pos+8+n];pos+=8+n+(n&1)
        if tag==b'fmt ':fmt=struct.unpack_from('<HHIIHH',data)
        elif tag==b'data':raw=data
    kind,ch,sr,_,_,bits=fmt
    if kind==3 and bits==32:x=np.frombuffer(raw,dtype='<f4').astype(np.float32)
    elif kind==1 and bits==16:x=np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768
    elif kind==1 and bits==32:x=np.frombuffer(raw,dtype='<i4').astype(np.float32)/2147483648
    elif kind==1 and bits==24:
        q=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3).astype(np.int32);v=q[:,0]|q[:,1]<<8|q[:,2]<<16;x=((v^8388608)-8388608).astype(np.float32)/8388608
    else:raise ValueError((path,fmt))
    x=x.reshape(-1,ch).mean(axis=1)
    if sr!=16000:
        # Windowed sinc anti-alias, equivalent cutoff/tap count to app PcmLowPass.
        taps=np.arange(63)-31;cutoff=.45*16000/sr
        h=2*cutoff*np.sinc(2*cutoff*taps)*np.hamming(63);h/=h.sum()
        x=np.convolve(x,h,mode='same');positions=np.arange(math.ceil(len(x)*16000/sr))*sr/16000
        x=np.interp(positions,np.arange(len(x)),x).astype(np.float32)
    return x

def words(s):return re.findall(r'[\w]+',s.lower().replace('ё','е'),re.UNICODE)
def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        prev=row;row=[i]
        for j,y in enumerate(b,1):row.append(min(row[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
    return row[-1]

def vad_spans(sherpa,np,model,x,gain=1):
    c=sherpa.VadModelConfig();c.silero_vad.model=str(model);c.silero_vad.threshold=.5;c.silero_vad.min_silence_duration=.25;c.silero_vad.min_speech_duration=.25;c.silero_vad.max_speech_duration=20;c.sample_rate=16000;c.num_threads=1
    detector=sherpa.VoiceActivityDetector(c,buffer_size_in_seconds=60);spans=[]
    def drain():
        while not detector.empty():
            s=detector.front;spans.append([s.start,s.start+len(s.samples)]);detector.pop()
    for pos in range(0,len(x),512):
        block=np.zeros(512,dtype=np.float32);n=min(512,len(x)-pos);block[:n]=x[pos:pos+n]*gain;detector.accept_waveform(block);drain()
    detector.flush();drain();return spans

def candidate_gain(np,x,trigger=.01):
    # Deliberately opt-in candidate, evaluated before any product adoption.
    peak=float(np.max(np.abs(x))) if len(x) else 0
    if peak<=1e-6 or peak>=trigger:return 1.
    return min(20.,.1/peak)

def main():
    p=argparse.ArgumentParser();p.add_argument('--python-path');p.add_argument('--fixtures',type=pathlib.Path,required=True);p.add_argument('--v2',type=pathlib.Path,required=True);p.add_argument('--v3',type=pathlib.Path,required=True);p.add_argument('--parakeet',type=pathlib.Path);p.add_argument('--models',default='giga-v2,giga-v3');p.add_argument('--gain-mode',choices=['original','candidate_bounded_gain'],default='original');p.add_argument('--skip-vad',action='store_true');p.add_argument('--vad',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--threads',type=int,default=2);p.add_argument('--levels',default='1,0.01');p.add_argument('--methods',default='greedy_search')
    p.add_argument('--gain-trigger',type=float,default=.01)
    p.add_argument('--v3-tag',default='giga-v3',help='Explicit tag for another GigaAM v3 RNNT variant in --v3')
    p.add_argument('--pcm16',action='store_true',help='Quantize the level-adjusted signal to signed PCM16 before recognition/gain; still not real whisper')
    # Keep all experiment parameters explicit in saved evidence.
    a=p.parse_args()
    if a.python_path:sys.path.insert(0,a.python_path)
    import numpy as np,sherpa_onnx as sherpa
    fixture_manifest=json.loads((a.fixtures/'fixtures.json').read_text());fixtures=fixture_manifest['fixtures'];audio={}
    for f in fixtures:
        path=a.fixtures/f['path']
        if file_sha256(path)!=f['sha256']:raise ValueError(f"Fixture integrity mismatch: {f['id']}")
        audio[f['id']]=read_wav(path,np)
    levels=[float(v) for v in a.levels.split(',')];out={'platform':'Linux host CPU; not Android or vivo; uncontrolled caches/temperature','runtime':sherpa.__version__,'threads':a.threads,'selection':'first 32 FLEURS test archive entries fixed before inference; EARS publisher English whisper sample','limitations':['small convenience subset, not representative benchmark','FLEURS may overlap model training; no claim of independent training data','digits vs spoken number text not inverse-normalized; shown literally in WER','no real Russian whispered audio available without access approval','real English whisper is VAD-only, no Russian-ASR WER'],'asr':[],'vad':[],'models':{}}
    out['gainPolicy']={'triggerPeak':a.gain_trigger,'targetPeak':.1,'maxGain':20,'silenceFloorPeak':1e-6}
    out['inputQuantization']='signed PCM16 after attenuation' if a.pcm16 else 'original float signal after attenuation'
    out['selection']=fixture_manifest['selection'];out['scriptSha256']=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    def save():a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    candidates=[('giga-v2',a.v2),(a.v3_tag,a.v3)]+([('parakeet-v3',a.parakeet)] if a.parakeet else [])
    for model_id,path in candidates:
        if model_id not in a.models.split(','):continue
        decoder='decoder.onnx' if (path/'decoder.onnx').exists() else 'decoder.int8.onnx';joiner='joiner.onnx' if (path/'joiner.onnx').exists() else 'joiner.int8.onnx'
        out['models'][model_id]={n:{'bytes':(path/n).stat().st_size,'sha256':file_sha256(path/n)} for n in ['encoder.int8.onnx',decoder,joiner,'tokens.txt']}
        for method in a.methods.split(','):
            t=time.perf_counter();r=sherpa.OfflineRecognizer.from_transducer(encoder=str(path/'encoder.int8.onnx'),decoder=str(path/decoder),joiner=str(path/joiner),tokens=str(path/'tokens.txt'),num_threads=a.threads,model_type='nemo_transducer',decoding_method=method,max_active_paths=4)
            load=time.perf_counter()-t
            for level in levels:
                for f in fixtures:
                    if f['language']!='ru':continue
                    x=audio[f['id']]*level
                    if a.pcm16:x=np.clip(np.round(x*32768),-32768,32767).astype(np.float32)/32768
                    gain=candidate_gain(np,x,a.gain_trigger) if a.gain_mode=='candidate_bounded_gain' else 1.;s=r.create_stream();s.accept_waveform(16000,x*gain);t=time.perf_counter();r.decode_stream(s);elapsed=time.perf_counter()-t;hyp=s.result.text
                    ref=words(f['reference']);h=words(hyp);record={'id':f['id'],'model':model_id,'method':method,'level':level,'audioSec':len(x)/16000,'inferenceSec':elapsed,'loadSec':load,'reference':f['reference'],'hypothesis':hyp,'wordErrors':distance(ref,h),'referenceWords':len(ref),'charErrors':distance(list(' '.join(ref)),list(' '.join(h))),'referenceChars':len(' '.join(ref))}
                    record.update(gainMode=a.gain_mode,gain=gain);out['asr'].append(record);print(model_id,method,level,f['id'],record['wordErrors'],len(ref),flush=True);save()
            del r
    rng=np.random.default_rng(104)
    for f in ([] if a.skip_vad else fixtures):
        for level in levels:
            x=audio[f['id']]*level;gain=candidate_gain(np,x,a.gain_trigger)
            if a.pcm16:x=np.clip(np.round(x*32768),-32768,32767).astype(np.float32)/32768;gain=candidate_gain(np,x,a.gain_trigger)
            for mode,g in [('original',1.),('candidate_bounded_gain',gain)]:
                spans=vad_spans(sherpa,np,a.vad,x,g);out['vad'].append({'id':f['id'],'language':f['language'],'speech':f['speech'],'level':level,'mode':mode,'gain':g,'audioSec':len(x)/16000,'spansSamples':spans,'detectedSec':sum(e-s for s,e in spans)/16000});save()
    for label,x in [('silence',np.zeros(16000*15,dtype=np.float32)),('white_noise_-60dBFS',rng.normal(0,.001,16000*15).astype(np.float32)),('white_noise_-40dBFS',rng.normal(0,.01,16000*15).astype(np.float32)),('hum_80Hz_-50dBFS',(.003*np.sin(np.arange(16000*15)*2*np.pi*80/16000)).astype(np.float32))]:
        for mode,g in [('original',1.),('candidate_bounded_gain',candidate_gain(np,x,a.gain_trigger))]:
            spans=vad_spans(sherpa,np,a.vad,x,g);out['vad'].append({'id':label,'speech':'synthetic negative control','mode':mode,'gain':g,'audioSec':15,'spansSamples':spans,'detectedSec':sum(e-s for s,e in spans)/16000});save()
    groups=collections.defaultdict(list)
    for r in out['asr']:groups[(r['model'],r['method'],r['level'])].append(r)
    out['summary']=[{'model':k[0],'method':k[1],'level':k[2],'files':len(v),'wordErrors':sum(r['wordErrors'] for r in v),'referenceWords':sum(r['referenceWords'] for r in v),'wer':sum(r['wordErrors'] for r in v)/sum(r['referenceWords'] for r in v),'cer':sum(r['charErrors'] for r in v)/sum(r['referenceChars'] for r in v),'audioSec':sum(r['audioSec'] for r in v),'inferenceSec':sum(r['inferenceSec'] for r in v)} for k,v in groups.items()];save();print(json.dumps(out['summary'],ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
