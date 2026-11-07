# Android collector contracts

v2 focused33 tests and real read-only10case preflight PASS; no NN or ADB by the
contract test author. Actual Android inference is a separate run.

v1 passed mocks but independent integration review found a real format mismatch:
Room stores a compact scalar/config diagnostic, the private QA sidecar stores the
full tree/vectors. v2 compares the compact projection to Room and independently
replays the full sidecar. Prior source/logs remain in v1-before-review. This is a
validator correction, no APK or quality-gate change. All four semantic validation
modules have SHA pins. Every new output path must be fresh.
