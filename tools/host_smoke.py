#!/usr/bin/env python3
"""Real model compatibility check on Linux. This is NOT an Android test."""
import pathlib,time,json,wave,numpy as np,sherpa_onnx,resource
ROOT=pathlib.Path(__file__).resolve().parents[1];MODELS=ROOT/'model-pack'
def wav(path):
 with wave.open(str(path)) as w:
  assert w.getframerate()==16000 and w.getnchannels()==1 and w.getsampwidth()==2
  return np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32)/32768
start=time.perf_counter()
r=sherpa_onnx.OfflineRecognizer.from_transducer(encoder=str(MODELS/'giga-v2/encoder.int8.onnx'),decoder=str(MODELS/'giga-v2/decoder.onnx'),joiner=str(MODELS/'giga-v2/joiner.onnx'),tokens=str(MODELS/'giga-v2/tokens.txt'),num_threads=2,model_type='nemo_transducer')
audio=wav('/mnt/f/ReplikaToolchain/russian-example.wav');stream=r.create_stream();stream.accept_waveform(16000,audio);r.decode_stream(stream);print('ASR:',stream.result.text,flush=True)
asr=time.perf_counter()-start;asrText=stream.result.text;del r,stream
c=sherpa_onnx.OfflineSpeakerDiarizationConfig(segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(MODELS/'diar/segmentation.onnx')),num_threads=2),embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(MODELS/'diar/embedding.onnx'),num_threads=2),clustering=sherpa_onnx.FastClusteringConfig(num_clusters=4))
start=time.perf_counter();sd=sherpa_onnx.OfflineSpeakerDiarization(c);multi=wav('/mnt/f/ReplikaToolchain/four-speakers-zh.wav');turns=sd.process(multi).sort_by_start_time();diar=time.perf_counter()-start
out={'platform':'Linux WSL x86_64; NOT Android','asrSource':'official GigaAM v2 archive test_wavs/example.wav','asrText':asrText,'asrSecondsIncludingLoad':asr,'asrAudioSeconds':len(audio)/16000,'diarSecondsIncludingLoad':diar,'diarAudioSeconds':len(multi)/16000,'diarSpeakers':len(set(s.speaker for s in turns)),'turns':[{'startMs':round(s.start*1000),'endMs':round(s.end*1000),'speakerId':s.speaker} for s in turns],'peakRssKb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'WER':'N/A','CER':'N/A','DER':'N/A'}
print(json.dumps(out,ensure_ascii=False,indent=2),flush=True);(ROOT/'docs/host-smoke.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
