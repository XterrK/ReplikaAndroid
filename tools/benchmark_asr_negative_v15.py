#!/usr/bin/env python3
"""Synthetic negative controls, including direct ASR and the actual VAD gate.

No WER is computed for non-speech. Direct recognizer output and gated product
output are reported separately so a VAD rejection cannot hide a hallucination.
"""
import argparse,json,pathlib,sys,time
from benchmark_asr_v15 import candidate_gain,vad_spans

def main():
    p=argparse.ArgumentParser();p.add_argument('--python-path');p.add_argument('--model',type=pathlib.Path,required=True);p.add_argument('--vad',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--only',help='Comma-separated fixed control ids');a=p.parse_args()
    if a.python_path:sys.path.insert(0,a.python_path)
    import numpy as np,sherpa_onnx as sherpa
    rng=np.random.default_rng(104);n=16000*15;t=np.arange(n)/16000
    white=rng.normal(0,1,n);freq=np.fft.rfftfreq(n);pink=np.fft.irfft(np.fft.rfft(white)/np.sqrt(np.maximum(freq,1/n)),n);pink=(pink/np.max(np.abs(pink))*.004).astype(np.float32)
    impulses=np.zeros(n,dtype=np.float32)
    for start in range(0,n,8000):impulses[start:start+800]=(.004*np.exp(-np.arange(800)/90)*rng.normal(0,1,800)).astype(np.float32)
    controls=[('silence',np.zeros(n)),('near_silence',rng.normal(0,1e-8,n)),('white_noise_-60dBFS',white*.001),('white_noise_-40dBFS',white*.01),('pink_noise_peak_004',pink),('hum_80Hz_peak_003',.003*np.sin(2*np.pi*80*t)),('hum_50Hz_harmonics',.001*(np.sin(2*np.pi*50*t)+np.sin(2*np.pi*100*t)+np.sin(2*np.pi*150*t))),('repeating_short_impulses',impulses),('quiet_repeating_short_impulses',impulses*.1),('synthetic_stationary_chord',.001*(np.sin(2*np.pi*220*t)+np.sin(2*np.pi*277*t)+np.sin(2*np.pi*330*t))),('fan_hum_and_noise',.001*np.sin(2*np.pi*120*t)+white*.0003)]
    if a.only:controls=[c for c in controls if c[0] in a.only.split(',')]
    r=sherpa.OfflineRecognizer.from_transducer(encoder=str(a.model/'encoder.int8.onnx'),decoder=str(a.model/'decoder.onnx'),joiner=str(a.model/'joiner.onnx'),tokens=str(a.model/'tokens.txt'),num_threads=2,model_type='nemo_transducer')
    out={'platform':'Linux host CPU; not phone','runtime':sherpa.__version__,'model':'GigaAM v3 E2E RNNT INT8','seed':104,'gainPolicy':{'triggerPeak':.01,'targetPeak':.1,'maxGain':20,'silenceFloorPeak':1e-6},'controls':[]};a.out.parent.mkdir(parents=True,exist_ok=True)
    def recognize(x):
        s=r.create_stream();s.accept_waveform(16000,x);r.decode_stream(s);return s.result.text
    for label,x in controls:
        x=x.astype(np.float32)
        for mode,g in [('original',1.),('conservative_gain',candidate_gain(np,x,.01))]:
            start=time.perf_counter();direct=recognize(x*g);spans=vad_spans(sherpa,np,a.vad,x,g);texts=[]
            for begin,end in spans:
                # Match app single-speaker VAD context (100 ms pre-roll, no post-roll).
                begin=max(0,(begin//16-100)*16);end=min(len(x),(end//16)*16)
                for pos in range(begin,end,320000):texts.append(recognize(x[pos:min(end,pos+320000)]*g))
            row={'id':label,'mode':mode,'seconds':15,'peak':float(np.max(np.abs(x))),'gain':g,'directHypothesis':direct,'vadSpansSamples':spans,'gatedHypotheses':texts,'elapsedSec':time.perf_counter()-start}
            out['controls'].append(row);a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(label,mode,'direct=',repr(direct),'spans=',len(spans),'gated=',repr(texts),flush=True)

if __name__=='__main__':main()
