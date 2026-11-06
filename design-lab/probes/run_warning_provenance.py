#!/usr/bin/env python3
"""Read-only probe of compiled V1.3 production classes after build_local.py baseline."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[2]
base=Path('/dev/shm/replika-build');cache=base/'cache/caches/modules-2/files-2.1'
jars=[next((cache/'org.jetbrains.kotlin/kotlin-stdlib/2.1.20').rglob('kotlin-stdlib-2.1.20.jar')),next((cache/'org.json/json/20250107').rglob('json-*.jar'))]
output=Path('/tmp/replika-warning-probe');output.mkdir(exist_ok=True)
cp=':'.join([str(root/'app/build/tmp/kotlin-classes/debug')]+list(map(str,jars)))
subprocess.run([str(base/'jdk/bin/javac'),'-cp',cp,'-d',str(output),str(Path(__file__).with_name('WarningProvenance.java'))],check=True)
r=subprocess.run([str(base/'jdk/bin/java'),'-cp',str(output)+':'+cp,'WarningProvenance'],check=True,capture_output=True,text=True)
(root/'design-lab/evidence/warning-provenance-reproduction.json').write_text(r.stdout)
print(r.stdout)
