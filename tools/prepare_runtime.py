#!/usr/bin/env python3
"""Pinned native runtime/source bootstrap. Does not modify any SDK."""
import pathlib,urllib.request,tarfile,hashlib,shutil,json
ROOT=pathlib.Path(__file__).resolve().parents[1]
CACHE=pathlib.Path('/mnt/f/ReplikaToolchain');CACHE.mkdir(exist_ok=True)
def fetch(url,name):
 p=CACHE/name
 if not p.exists():urllib.request.urlretrieve(url,p)
 expected=next((r["sha256"] for r in json.loads((ROOT/"tools/native-lock.json").read_text()) if r["file"]==name),None)
 if expected:assert hashlib.file_digest(p.open("rb"),"sha256").hexdigest()==expected, "Runtime checksum mismatch: "+name
 return p
s=fetch('https://github.com/k2-fsa/sherpa-onnx/releases/download/v2.0.1/sherpa-onnx-v2.0.1-android.tar.bz2','sherpa.tar.bz2')
with tarfile.open(s) as t:
 for m in t.getmembers():
  for abi in ['arm64-v8a','x86_64']:
   if '/'+abi+'/' in '/'+m.name and pathlib.PurePosixPath(m.name).name in ['libsherpa-onnx-jni.so','libonnxruntime.so']:
    p=ROOT/'app/src/main/jniLibs'/abi/pathlib.PurePosixPath(m.name).name;p.parent.mkdir(parents=True,exist_ok=True)
    with t.extractfile(m) as src,p.open('wb') as dst:shutil.copyfileobj(src,dst)
print(s.name,hashlib.file_digest(s.open('rb'),'sha256').hexdigest())
