#!/usr/bin/env python3
"""Stage verified test weights in our debuggable app only; never into a production app."""
import pathlib,subprocess,json,hashlib,os
ROOT=pathlib.Path(__file__).resolve().parents[1];ADB=os.environ.get('ADB','/mnt/f/ReplikaToolchain/sdk/platform-tools/adb');PKG='ru.replika.offline'
def shell(command,**kw):return subprocess.run([ADB,'shell','-T',command],check=True,**kw)
for spec in json.loads((ROOT/'app/src/main/assets/models-lock.json').read_text())['files']:
 p=ROOT/'model-pack'/spec['path'];assert p.stat().st_size==spec['size'];assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==spec['sha256']
 shell(f"run-as {PKG} mkdir -p files/models/{spec['group']}")
 with p.open('rb') as f:shell(f"run-as {PKG} sh -c 'cat > files/models/{spec['path']}'",stdin=f)
 print('staged',spec['path'],flush=True)
with open('/mnt/f/ReplikaToolchain/russian-example.wav','rb') as f:shell(f"run-as {PKG} sh -c 'cat > files/integration-example.wav'",stdin=f)
