#!/usr/bin/env python3
"""Stage verified integration inputs in our debuggable app; supports Linux and Windows ADB."""
import pathlib,subprocess,json,hashlib,os,sys,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
ADB=os.environ.get('ADB','/mnt/f/ReplikaToolchain/sdk/platform-tools/adb')
PKG='ru.replika.offline'
TEMP='/data/local/tmp/replika-stage-'+uuid.uuid4().hex

def adb(*args,**kw):return subprocess.run([ADB,*args],check=True,**kw)
def shell(command):return adb('shell',command)
def stage(local,remote):
 source=str(local)
 if ADB.lower().endswith('.exe'):source=subprocess.check_output(['wslpath','-w',source],text=True).strip()
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
 if '--pack' in sys.argv:stage(ROOT/'model-pack/replika-offline-pack.zip','files/integration-model-pack.zip')
 stage(pathlib.Path('/mnt/f/ReplikaToolchain/russian-example.wav'),'files/integration-example.wav')
 multi=pathlib.Path('/mnt/f/ReplikaToolchain/four-speakers-zh.wav')
 if multi.exists():stage(multi,'files/integration-multispeaker.wav')
finally:
 shell('rmdir '+TEMP)
