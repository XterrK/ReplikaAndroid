#!/usr/bin/env python3
"""Collect only this debuggable app's test evidence, never other apps' data."""
import pathlib,subprocess,os
ROOT=pathlib.Path(__file__).resolve().parents[1]
ADB=os.environ.get('ADB','/mnt/f/ReplikaToolchain/sdk/platform-tools/adb')
PKG='ru.replika.offline'
def collect(remote,local):
 r=subprocess.run([ADB,'exec-out','run-as',PKG,'cat',remote],capture_output=True)
 if r.returncode!=0:return False
 local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(r.stdout);return True
for name in ['android-diarization.json','android-pipeline-diagnostics.json','android-transcript.json','android-whisper.txt','integration-result.txt']:
 collect('files/'+name,ROOT/'docs/test-evidence'/name)
r=subprocess.run([ADB,'shell','run-as',PKG,'ls','files/human-review'],capture_output=True,text=True)
for name in r.stdout.splitlines():
 name=name.strip()
 if name.endswith('.png') and pathlib.PurePosixPath(name).name==name:
  destination=ROOT/'docs/human-review'/name
  if collect('files/human-review/'+name,destination):
   assert destination.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),name
   print('captured',name)
