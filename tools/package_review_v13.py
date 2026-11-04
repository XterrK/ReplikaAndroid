#!/usr/bin/env python3
"""Package the committed V1.3 candidate, public test evidence and exactly one installable APK."""
from pathlib import Path
import hashlib,json,subprocess,zipfile
root=Path(__file__).resolve().parents[1]
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root).strip(),'Commit reviewable changes before packaging'
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
apk=root/'release/REPLIKA-V1.3-AllInOne-arm64.apk'
assert apk.is_file()
static=json.loads((root/'docs/test-evidence/v1.3/arm64-static.json').read_text())
sha=hashlib.file_digest(apk.open('rb'),'sha256').hexdigest()
assert sha==static['sha256'] and not static['errors']
files=[root/n for n in ['REAL_DEVICE_FINDINGS.md','PERFORMANCE_ANALYSIS.md','DIARIZATION_FIX_REPORT.md','VAD_BOUNDARY_REPORT.md','TEST_REPORT_V1_3.md','PROJECT_STATE.md','README.md','app/build.gradle.kts','app/src/main/AndroidManifest.xml','app/src/main/cpp/whisper_jni.cpp','app/src/main/cpp/CMakeLists.txt','app/src/main/assets/models-lock.json','docs/ALL_IN_ONE_LICENSE_AUDIT.md','docs/human-review/v1.3/REVIEW_GUIDE.md','release/REPLIKA-V1.3-AllInOne-arm64.apk.sha256']]
for folder in ['docs/test-evidence/v1.3','app/src/main/java/ru/replika','app/src/test/java/ru/replika','app/src/androidTest/java/ru/replika']:
 files.extend(p for p in (root/folder).rglob('*') if p.is_file())
files.extend(root/p for p in ['tools/benchmark_v13_host.py','tools/check_upgrade_v13.py','tools/run_android_v13.py','tools/collect_v13_evidence.py','tools/check_perf_log_v13.py','tools/package_review_v13.py'])
files=sorted(set(files));dest=root/'review/HUMAN_REVIEW_V1_3.zip'
assert not dest.exists(),'Preserve prior review archive; choose an explicit new name/version'
manifest={'commit':commit,'workingTree':'clean at packaging','apkSha256':sha,'apkBytes':apk.stat().st_size,'status':'PARTIAL: automatic diarization and original vivo boundary acceptance remain open','files':[]}
with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
 for f in files:
  name=str(f.relative_to(root));z.write(f,name)
  manifest['files'].append({'path':name,'sha256':hashlib.file_digest(f.open('rb'),'sha256').hexdigest()})
 z.write(apk,str(apk.relative_to(root)));z.writestr('v1.3-delivery.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(dest) as z:assert z.testzip() is None
print(json.dumps({'archive':str(dest),'bytes':dest.stat().st_size,'sha256':hashlib.file_digest(dest.open('rb'),'sha256').hexdigest(),'commit':commit,'entries':len(files)+2},indent=2))
