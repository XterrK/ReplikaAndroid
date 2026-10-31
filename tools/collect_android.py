#!/usr/bin/env python3
"""Collect only this debuggable app's test evidence, never other apps' data."""
import pathlib,subprocess,os,argparse
ROOT=pathlib.Path(__file__).resolve().parents[1]
ADB=os.environ.get('ADB','/mnt/f/ReplikaToolchain/sdk/platform-tools/adb')
PKG='ru.replika.offline'
parser=argparse.ArgumentParser();parser.add_argument('--version',default='v1.1');args=parser.parse_args()
EVIDENCE=ROOT/'docs/test-evidence'/args.version
SHOTS=ROOT/'docs/human-review'/args.version
def collect(remote,local):
 r=subprocess.run([ADB,'exec-out','run-as',PKG,'cat',remote],capture_output=True)
 if r.returncode!=0:return False
 local.parent.mkdir(parents=True,exist_ok=True)
 if local.exists() and local.read_bytes()!=r.stdout:
  import datetime
  backup=local.with_name(local.stem+'.'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+local.suffix)
  local.rename(backup)
 local.write_bytes(r.stdout);return True
for name in ['android-diarization.json','android-pipeline-diagnostics.json','android-transcript.json','android-whisper.txt','android-whisper-pipeline-diagnostics.json','android-whisper-transcript.json','integration-result.txt','ml-asr-comparison.json','ml-vad-comparison.json','ml-diarization-comparison.json','media-formats.json','edit-persistence.json']:
 collect('files/'+name,EVIDENCE/name)
r=subprocess.run([ADB,'shell','run-as',PKG,'ls','files/human-review'],capture_output=True,text=True)
for name in r.stdout.splitlines():
 name=name.strip()
 if name.endswith('.png') and pathlib.PurePosixPath(name).name==name:
  destination=SHOTS/name
  if collect('files/human-review/'+name,destination):
   assert destination.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),name
   print('captured',name)
