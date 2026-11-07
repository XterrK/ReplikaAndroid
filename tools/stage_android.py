#!/usr/bin/env python3
"""Stage verified integration inputs in our debuggable app; supports Linux and Windows ADB."""
import pathlib,subprocess,json,hashlib,os,sys,uuid,shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
ADB=os.environ.get('ADB') or shutil.which('adb') or shutil.which('adb.exe') or 'adb'
FIXTURES=ROOT/'benchmark/fixtures'
PKG='ru.replika.offline'
TEMP='/data/local/tmp/replika-stage-'+uuid.uuid4().hex

def adb(*args,**kw):return subprocess.run([ADB,*args],check=True,**kw)
def shell(command):return adb('shell',command)
def stage(local,remote):
 source=str(local)
 if os.name!='nt' and ADB.lower().endswith('.exe'):source=subprocess.check_output(['wslpath','-w',source],text=True).strip()
 staged=TEMP+'/'+pathlib.PurePosixPath(remote).name
 adb('push',source,staged)
 parent=str(pathlib.PurePosixPath(remote).parent)
 shell(f'run-as {PKG} mkdir -p {parent}')
 shell(f'run-as {PKG} cp {staged} {remote}')
 shell(f'rm {staged}')
 print('staged',remote,flush=True)

shell('mkdir -p '+TEMP)
try:
 rows=json.loads((ROOT/'app/src/main/assets/models-lock.json').read_text())['files']
 for spec in rows:
  p=ROOT/'model-pack'/spec['path']
  assert p.stat().st_size==spec['size']
  assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==spec['sha256']
  if '--pack' not in sys.argv:stage(p,'files/models/'+spec['path'])
 if '--pack' in sys.argv:stage(ROOT/'model-pack/replika-offline-pack-v1.6.zip','files/integration-model-pack.zip')
 stage(FIXTURES/'russian-example.wav','files/integration-example.wav')
 for ext in ['mp3','m4a']:
  source=FIXTURES/('russian-example.'+ext)
  if source.exists():stage(source,'files/integration-example.'+ext)
 multi=FIXTURES/'four-speakers-zh.wav'
 if multi.exists():stage(multi,'files/integration-multispeaker.wav')
finally:
 shell('rmdir '+TEMP)
