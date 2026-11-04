"""Reproducible pinned-weight host sensitivity probe; NOT Android or independent corpus validation."""
import sys,time,json,wave
from pathlib import Path
sys.path.insert(0,'/mnt/f/ReplikaToolchain/python')
import sherpa_onnx as s,numpy as np
project=Path(__file__).resolve().parents[1]
root=str(project/'model-pack')+'/'
def read(p):
 with wave.open(p) as w:return np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32)/32768
ru=read('/mnt/f/ReplikaToolchain/russian-example.wav');zh=read('/mnt/f/ReplikaToolchain/four-speakers-zh.wav')
rows=[]
for name,audio in [('ru',ru),('ru-repeat-4min',np.tile(np.concatenate([ru,np.zeros(8000,np.float32)]),21)),('zh',zh)]:
 for threshold in [.5,.7,.85]:
  c=s.OfflineSpeakerDiarizationConfig(segmentation=s.OfflineSpeakerSegmentationModelConfig(pyannote=s.OfflineSpeakerSegmentationPyannoteModelConfig(model=root+'diar/segmentation.onnx'),num_threads=2),embedding=s.SpeakerEmbeddingExtractorConfig(model=root+'diar/embedding.onnx',num_threads=2),clustering=s.FastClusteringConfig(num_clusters=-1,threshold=threshold))
  t=time.perf_counter();sd=s.OfflineSpeakerDiarization(c);load=time.perf_counter()-t;t=time.perf_counter();turns=sd.process(audio).sort_by_start_time();elapsed=time.perf_counter()-t
  row=dict(name=name,threshold=threshold,audioMs=len(audio)/16,loadMs=load*1000,inferenceMs=elapsed*1000,speakers=len(set(t.speaker for t in turns)),turnCount=len(turns));rows.append(row);print(row,flush=True);del sd
  open(project/'docs/test-evidence/v1.3/host-diarization-probe.json','w').write(json.dumps({'platform':'Linux WSL x86_64; NOT Android; repeated audio is controlled, not independent','runs':rows},indent=2))
