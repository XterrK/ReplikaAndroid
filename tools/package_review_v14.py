#!/usr/bin/env python3
"""Package V1.4 source, public evidence and one APK; preserve prior archives/private data."""
from pathlib import Path
import hashlib,json,subprocess,zipfile
root=Path(__file__).resolve().parents[1]
apk=root/'release/REPLIKA-V1.4-AllInOne-arm64.apk'
report=json.loads((root/'docs/human-review/v1.4/evidence/arm64-static.json').read_text())
sha=hashlib.file_digest(apk.open('rb'),'sha256').hexdigest()
assert sha==report['sha256'] and not report['errors']
files=[]
for name in ['README.md','PROJECT_STATE.md','HUMAN_CONCEPT_REVIEW.md','DESIGN_SYSTEM.md','LIQUID_ORB_TECHNICAL_SPEC.md','MOTION_DESIGN.md','UX_BEFORE_AFTER.md','TEST_REPORT_V1_4.md','KNOWN_ISSUES.md','build.gradle.kts','settings.gradle.kts','gradle.properties','app/build.gradle.kts','app/src/main/AndroidManifest.xml','release/REPLIKA-V1.4-AllInOne-arm64.apk.sha256','tools/package_review_v14.py']:
 files.append(root/name)
for folder in ['app/src/main/java','app/src/main/cpp','app/src/main/res','app/src/main/assets/licenses','app/src/test/java/ru/replika','app/src/androidTest/java/ru/replika','docs/human-review/v1.4']:
 files.extend(p for p in (root/folder).rglob('*') if p.is_file())
files.append(root/'app/src/main/assets/models-lock.json')
for name in ['DESIGN_SYSTEM.md','index.html','screen.html','screen.css','screen.js','orb.js','lab.css','README.md','tools/verify-v14.cjs','review/HUMAN_CONCEPT_REVIEW.md']:
 files.append(root/'design-lab'/name)
files.extend(p for p in (root/'design-lab/assets/fonts').iterdir() if p.is_file())
files.extend([root/'design-lab/concepts/c-overview.png',root/'design-lab/concepts/b-overview.png'])
files=sorted(set(files));dest=root/'review/HUMAN_REVIEW_V1_4.zip'
assert not dest.exists(),'Preserve existing review archive; select a new name explicitly'
manifest={'baselineCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'workingTree':'Uncommitted implementation; existing unrelated untracked files excluded; no push','apkSha256':sha,'apkBytes':apk.stat().st_size,'status':'Implemented; physical-device microphone/performance acceptance pending; automatic diarization remains open','files':[]}
with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
 for f in files:
  name=str(f.relative_to(root));z.write(f,name);manifest['files'].append({'path':name,'sha256':hashlib.file_digest(f.open('rb'),'sha256').hexdigest()})
 z.write(apk,str(apk.relative_to(root)));z.writestr('v1.4-delivery.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(dest) as z:assert z.testzip() is None
result={'archive':str(dest.relative_to(root)),'bytes':dest.stat().st_size,'sha256':hashlib.file_digest(dest.open('rb'),'sha256').hexdigest(),'entries':len(files)+2}
(root/'review/HUMAN_REVIEW_V1_4.zip.sha256').write_text(result['sha256']+'  '+dest.name+'\n')
print(json.dumps(result,indent=2))
