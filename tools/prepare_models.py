#!/usr/bin/env python3
"""Download only official sherpa conversion releases, construct an offline pack and lockfile."""
import urllib.request, pathlib, tarfile, hashlib, json, concurrent.futures, shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
DEST=ROOT/'model-pack'; CACHE=pathlib.Path('/mnt/f/ReplikaToolchain/model-downloads');CACHE.mkdir(parents=True,exist_ok=True);DEST.mkdir(exist_ok=True)
BASE='https://github.com/k2-fsa/sherpa-onnx/releases/download/'
JOBS=[
 ('giga-v2',BASE+'asr-models/sherpa-onnx-nemo-transducer-giga-am-v2-russian-2025-04-19.tar.bz2',{'encoder.int8.onnx':'encoder.int8.onnx','decoder.onnx':'decoder.onnx','joiner.onnx':'joiner.onnx','tokens.txt':'tokens.txt'}),
 ('diar',BASE+'speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2',{'model.onnx':'segmentation.onnx'}),
 ('diar',BASE+'speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx',{'direct':'embedding.onnx'}),
 ('vad',BASE+'asr-models/silero_vad.onnx',{'direct':'silero_vad.onnx'}),
 ('whisper-tiny','https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin',{'direct':'ggml-tiny.bin'})]
def job(spec):
 group,url,files=spec;p=CACHE/url.rsplit('/',1)[1]
 if not p.exists():
  tmp=p.with_suffix('.part');print('Downloading',url,flush=True)
  with urllib.request.urlopen(url,timeout=90) as r, tmp.open('wb') as f:shutil.copyfileobj(r,f)
  tmp.rename(p)
 folder=DEST/group;folder.mkdir(exist_ok=True)
 if 'direct' in files:shutil.copyfile(p,folder/files['direct'])
 else:
  with tarfile.open(p) as t:
   for src,dst in files.items():
    m=next(m for m in t.getmembers() if pathlib.PurePosixPath(m.name).name==src)
    with t.extractfile(m) as s,(folder/dst).open('wb') as d:shutil.copyfileobj(s,d)
 return [dict(group=group,path=f'{group}/{dst}',url=url,archiveMember=None if src=='direct' else src,size=(folder/dst).stat().st_size,sha256=hashlib.file_digest((folder/dst).open('rb'),'sha256').hexdigest()) for src,dst in files.items()]
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:rows=sum(e.map(job,JOBS),[])
 lock={'source':'official sherpa-onnx release assets; SHA256 measured locally, not publisher signatures','files':rows}
 (DEST/'manifest.json').write_text(json.dumps(lock,indent=2))
 assets=ROOT/'app/src/main/assets';assets.mkdir(exist_ok=True);(assets/'models-lock.json').write_text(json.dumps(lock,indent=2))
 import zipfile
 with zipfile.ZipFile(DEST/'replika-offline-pack.zip','w',compression=zipfile.ZIP_STORED) as z:
  z.write(DEST/'manifest.json','manifest.json')
  for row in rows:z.write(DEST/row['path'],row['path'])
 print('Pack ready',sum(r['size'] for r in rows),flush=True)
