#!/usr/bin/env python3
"""Package only reviewed documentation/evidence; never audio, models, APKs or toolchains."""
from pathlib import Path
import hashlib,json,subprocess,zipfile,datetime
ROOT=Path(__file__).resolve().parents[1]
paths=[ROOT/n for n in ['README.md','ARCHITECTURE.md','MODEL_RESEARCH.md','BENCHMARKS.md','TEST_REPORT.md','PROJECT_STATE.md','app/src/main/assets/models-lock.json','benchmark/reference.example.json']]
paths += sorted((ROOT/'docs/human-review/v1.1').rglob('*'))
paths += sorted((ROOT/'docs/test-evidence/v1.1').rglob('*'))
paths=[p for p in paths if p.is_file()]
allowed={'.md','.json','.txt','.xml','.png','.log','.tsv'}
assert all(p.suffix in allowed for p in paths)
assert all(p.stat().st_size<10*1024*1024 for p in paths)
manifest={'generatedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'workingTree':subprocess.check_output(['git','status','--porcelain=v1'],cwd=ROOT,text=True).strip(),'files':{str(p.relative_to(ROOT)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in paths},'excluded':'models, APK, SDK, raw audio, private files, intermediate builds'}
out=ROOT/'review/REPLIKA_V1_1_HUMAN_REVIEW.zip';out.parent.mkdir(exist_ok=True)
if out.exists():out.rename(out.with_name(out.stem+'.'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.zip'))
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for p in paths:z.write(p,p.relative_to(ROOT))
 z.writestr('REVIEW_MANIFEST.json',json.dumps(manifest,indent=2,ensure_ascii=False))
with zipfile.ZipFile(out) as z:assert z.testzip() is None
print(out);print('bytes',out.stat().st_size);print('sha256',hashlib.file_digest(out.open('rb'),'sha256').hexdigest())
