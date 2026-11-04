#!/usr/bin/env python3
"""Collect allowlisted public/controlled test outputs, never arbitrary user diagnostics."""
import argparse,os,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--initial-only',action='store_true');a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=True)
adb=os.environ.get('ADB','/mnt/f/ReplikaToolchain/v13-adb.exe')
names=['v13-long-auto-diarization.json','v13-pcm-read.json','v13-thread-comparison.json','v13-thermal.json','v13-long-single-diagnostics.json','v13-long-single-transcript.json',
 'android-pipeline-diagnostics.json','android-transcript.json','android-whisper-pipeline-diagnostics.json','android-whisper-transcript.json',
 'ml-asr-comparison.json','ml-vad-comparison.json','ml-diarization-comparison.json','android-diarization.json','all-in-one-real-worker-acceptance.json',
 'all-in-one-prepared-models.json','all-in-one-models-ui.json','v12-warning-pipeline.json','v12-warning-diagnostics.json','v12-warning-transcript.json','edit-persistence.json']
if a.initial_only: names=[n for n in names if n.startswith("v13-")]
for name in names:
 r=subprocess.run([adb,'exec-out','run-as','ru.replika.offline','cat','files/'+name],capture_output=True)
 if r.returncode==0:
  path=a.output/name
  if path.exists() and path.read_bytes()!=r.stdout:raise SystemExit('Evidence exists: '+str(path))
  path.write_bytes(r.stdout)
if not a.initial_only:
 r=subprocess.run([adb,'exec-out','run-as','ru.replika.offline','cat','files/provisioning-diagnostics/latest.json'],capture_output=True)
 if r.returncode==0:(a.output/'v13-provisioning.json').write_bytes(r.stdout)
for name in ['01-dialogue-controlled.png','02-reading-controlled.png']:
 r=subprocess.run([adb,'exec-out','run-as','ru.replika.offline','cat','files/human-review-v1.3/'+name],capture_output=True)
 if r.returncode==0:
  assert r.stdout.startswith(b'\x89PNG\r\n\x1a\n')
  (a.output/name).write_bytes(r.stdout)
