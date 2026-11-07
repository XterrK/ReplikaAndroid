from pathlib import Path
import subprocess,os,json,hashlib
root=Path(__file__).resolve().parent;project=Path.cwd();toolchain=root.parents[1];cache=toolchain/'gradle-cache/caches/modules-2/files-2.1';jdk=toolchain/'jdk17'
def artifact(group,name,version):
 paths=list((cache/group/name/version).glob('*/*.jar'))
 if len(paths)!=1:raise RuntimeError((group,name,version,paths))
 return paths[0]
stdlib=artifact('org.jetbrains.kotlin','kotlin-stdlib','2.1.20')
compiler=[artifact('org.jetbrains.kotlin','kotlin-compiler-embeddable','2.1.20'),stdlib,artifact('org.jetbrains.kotlin','kotlin-script-runtime','2.1.20'),artifact('org.jetbrains.kotlin','kotlin-reflect','1.6.10'),artifact('org.jetbrains.kotlin','kotlin-daemon-embeddable','2.1.20'),artifact('org.jetbrains.intellij.deps','trove4j','1.0.20200330'),artifact('org.jetbrains.kotlinx','kotlinx-coroutines-core-jvm','1.8.0'),artifact('org.jetbrains','annotations','23.0.0')]
libs=[stdlib,artifact('org.jetbrains','annotations','23.0.0'),artifact('org.json','json','20250107'),artifact('junit','junit','4.13.2'),artifact('org.hamcrest','hamcrest-core','1.3')]
classes=root/'classes';classes.mkdir(exist_ok=True)
files=[project/'app/src/main/java/ru/replika/domain/Transcript.kt',root/'SpeakerRefiner.kt',root/'SpeakerRefinerDraftTest.kt',root/'SpeakerRefinerProbe.kt']
cmd=[str(jdk/'bin/java'),'-Xmx128m','-XX:+UseSerialGC','-XX:ActiveProcessorCount=2','-XX:ReservedCodeCacheSize=32m','-XX:MaxMetaspaceSize=128m','-cp',os.pathsep.join(map(str,compiler)),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-classpath',os.pathsep.join(map(str,libs)),'-jvm-target','17','-d',str(classes),*map(str,files)]
with(root/'compile.log').open('w')as log:rc=subprocess.run(['/usr/bin/time','-v',*cmd],stdout=log,stderr=subprocess.STDOUT).returncode
state={'compile_returncode':rc,'runtime_classpath':os.pathsep.join(map(str,[classes,*libs])),'jdk':str(jdk),'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in files},'compiler_artifacts':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in compiler},'scope':'Standalone Kotlin compiler only; no Android Gradle/app changes/NN'}
(root/'build-state.json').write_text(json.dumps(state,indent=2)+'\n')
print('compile_returncode',rc)
if rc:print((root/'compile.log').read_text()[-9000:]);raise SystemExit(rc)
with(root/'junit.log').open('w')as log:rc=subprocess.run([str(jdk/'bin/java'),'-Xmx128m','-cp',state['runtime_classpath'],'org.junit.runner.JUnitCore','ru.replika.domain.SpeakerRefinerDraftTest'],stdout=log,stderr=subprocess.STDOUT).returncode
print((root/'junit.log').read_text());raise SystemExit(rc)
