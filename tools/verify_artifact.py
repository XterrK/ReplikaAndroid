#!/usr/bin/env python3
import pathlib,zipfile,hashlib,json,subprocess,os
root=pathlib.Path(__file__).resolve().parents[1];apk=root/'app/build/outputs/apk/debug/app-debug.apk';sdk=pathlib.Path(os.environ.get('ANDROID_HOME','/mnt/f/ReplikaToolchain/sdk'))
with zipfile.ZipFile(apk) as z:
 weights=[n for n in z.namelist() if n.endswith(('.onnx','.bin')) and n.startswith('assets/')]
 assert not weights,weights
 native=[n for n in z.namelist() if n.startswith('lib/') and n.endswith('.so')]
 assert any('arm64-v8a/libreplika-whisper.so' in n for n in native)
 assert any('x86_64/libreplika-whisper.so' in n for n in native)
 for abi in ['arm64-v8a','x86_64']:
  assert f'lib/{abi}/libsherpa-onnx-jni.so' in native
  assert f'lib/{abi}/libonnxruntime.so' in native
result=subprocess.run([str(sdk/'build-tools/35.0.0/zipalign'),'-c','-P','16','4',str(apk)],capture_output=True,text=True)
assert result.returncode==0,result.stderr
out={'apk':str(apk),'bytes':apk.stat().st_size,'sha256':hashlib.file_digest(apk.open('rb'),'sha256').hexdigest(),'zipAlignment16Kb':'PASS','weightsBundled':False,'nativeLibraries':native}
(root/'docs/test-evidence/apk-verification.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
