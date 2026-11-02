# V1.2.1 evidence index

- test-summary.json —54uniqueAndroidJUnit methods,55executions,no failures/skips;2existing Worker methods called by the AIO wrapper.
- jvm/ —25passed JVM cases.
- first-launch/ —failed original UX attempt,including ANR trace/screens;retained without claiming success.
- first-launch-after-cold/ —fresh sameAPK reinstall,airplane mode,actualbyteprogress,Library,cold no-extract,forced interruption/stage reuse.
- acceptance/ —real models from APK before any external pack was staged:both Worker JSON/diagnostics,diarization,UI/safety evidence. The ERROR/font1.3 screenshot is explicitly an isolated rendering fixture.
- qa-cold-*.json/txt —differentPID and all8file SHA/mtime checks before legacy manual-import tests.
- regression/ —existing storage/audio/ASR/VAD/diar/review/recording/edit/persistence regressions;cache/exports contains manually corrected output,not raw inference.
- manual-import-fixture-staged-after-aio-acceptance.json —external ZIP staged only for later old importer regression,after bundled-only ASR acceptance.
- upgrade-*.json / standard-compatibility.json —sameID API35x86 update,no original data loss;raw private DB/audio snapshots stay outside Git.
- *static.json / signature.json / packaged-notices.json —ZIP+ELF native alignment,dependencies,ABI,8weight hashes and25notice assets;runtimearm64/16KiB not established.
- v1.2.1-*.log —separate clean/final/QA-test/upgrade/taskgraph build records. The initial preBuild pack-hook was corrected to variant mergeAssets;final standard graph excludes it.

No audio,APK,model weights,SDK,keystores or private application DB files are stored here. Parent V1.1/V1.2 evidence is retained. Full report:../../ALL_IN_ONE_TEST_REPORT.md.
