"""Guard tests only. No production ZIP, APK, report or baseline is created/changed."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("package_review_v15", Path(__file__).resolve().parents[1] / "package_review_v15.py")
pkg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkg)


class ReviewPackageGuards(unittest.TestCase):
    def test_payload_allows_reproducible_source_and_only_the_final_apk(self):
        positive = [str(pkg.APK), "gradlew", "gradle/wrapper/gradle-wrapper.jar",
                    "app/src/main/java/com/k2fsa/sherpa/Model.kt", "app/src/main/res/font/onest.ttf",
                    "app/src/main/assets/licenses/3d-weights-modelcard.md",
                    "app/src/androidTest/assets/media-import/multi-audio.mp4",
                    "tools/compare_onnx_initializers_v15.py", "design-lab/concepts/c-overview.png",
                    "docs/human-review/v1.5/evidence/android/orb-demo.mp4"]
        negative = ["release/REPLIKA-V1.4-AllInOne-arm64.apk", "review/HUMAN_REVIEW_V1_4.zip",
                    "docs/human-review/v1.5/evidence/replika.db", "docs/test-evidence/v1.5/data.sqlite3",
                    "docs/human-review/v1.5/evidence/replika.db-wal", "app/src/main/jniLibs/arm64-v8a/libmodel.so",
                    "docs/human-review/v1.5/private.sqlite3-wal", "docs/human-review/v1.5/Private.SQLITE3-SHM",
                    "docs/human-review/v1.5/private.db-journal", "docs/test-evidence/v1.5/model.ort",
                    "app/src/main/assets/model/encoder.onnx", "docs/test-evidence/v1.5/weights.bin",
                    "tools/__pycache__/prepare_runtime.pyc", "local.properties", ".env", "../private.md",
                    "design-lab/evidence/browser/a-recording.png", "design-lab/concepts/a-overview.png",
                    "video-production-fi-20261105/video.mp4"]
        for name in positive:
            self.assertTrue(pkg.allowed_payload(name), name)
        for name in negative:
            self.assertFalse(pkg.allowed_payload(name), name)

    def test_existing_zip_or_checksum_is_refused_without_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "review.zip"
            destination.write_bytes(b"existing review bytes")
            before = pkg.sha256(destination)
            with self.assertRaises(pkg.PackageError):
                pkg.validate_destination(destination)
            self.assertEqual(before, pkg.sha256(destination))
            destination.unlink()
            checksum = Path(str(destination) + ".sha256")
            checksum.write_text("existing checksum")
            with self.assertRaises(pkg.PackageError):
                pkg.validate_destination(destination)
            self.assertEqual("existing checksum", checksum.read_text())
            checksum.unlink()
            destination.symlink_to(Path(directory) / "not-present")
            with self.assertRaises(pkg.PackageError):
                pkg.validate_destination(destination)

    def test_preservation_detects_old_artifact_changes_and_never_rewrites_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = {}
            for name in ("release/REPLIKA-V1.4-AllInOne-arm64.apk", "review/HUMAN_REVIEW_V1_4.zip"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
                artifacts[name] = pkg.sha256(path)
            record = root / pkg.BASELINE
            record.parent.mkdir(parents=True)
            record.write_text(json.dumps({"baselineGitHead": "a" * 40, **artifacts}))
            self.assertEqual(artifacts, pkg.validate_preservation(root)[1])
            previous_zip = root / "review/HUMAN_REVIEW_V1_4.zip"
            (root / "release/REPLIKA-V1.4-AllInOne-arm64.apk").write_bytes(b"changed APK")
            with self.assertRaisesRegex(pkg.PackageError, "Previous artifact changed"):
                pkg.validate_preservation(root)
            self.assertEqual(artifacts["review/HUMAN_REVIEW_V1_4.zip"], pkg.sha256(previous_zip))

    def test_static_report_must_match_final_bytes_and_have_no_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / pkg.APK
            apk.parent.mkdir()
            apk.write_bytes(b"public dummy APK bytes; not an installable artifact")
            report = {"apk": str(apk), "sha256": pkg.sha256(apk), "bytes": apk.stat().st_size,
                      "errors": [], "staticVerification": "PASS", "actualAbis": ["arm64-v8a"],
                      "expectedAbis": ["arm64-v8a"], "embeddedPackCopies": 1, "looseModelAssets": []}
            path = root / pkg.STATIC_REPORT
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(report))
            self.assertEqual(pkg.sha256(apk), pkg.validate_apk(root)[1])
            report["errors"] = ["alignment failed"]
            path.write_text(json.dumps(report))
            with self.assertRaises(pkg.PackageError):
                pkg.validate_apk(root)
            report["errors"] = []
            path.write_text(json.dumps(report))
            apk.write_bytes(b"a later build")
            with self.assertRaisesRegex(pkg.PackageError, "differs"):
                pkg.validate_apk(root)

    def test_collection_includes_fixtures_but_excludes_private_and_weight_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in pkg.REQUIRED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("public fixture")
            (root / "docs/licenses").mkdir(parents=True)
            for name in ("app/src/androidTest/assets/media-import/no-audio.mp4",
                         "docs/test-evidence/v1.5/summary.json", "docs/human-review/v1.5/private.sqlite",
                         "app/src/main/assets/models/encoder.onnx", "release/old.apk"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            names = {path.relative_to(root).as_posix() for path in pkg.collect_payload(root)}
            self.assertIn("app/src/androidTest/assets/media-import/no-audio.mp4", names)
            self.assertIn("docs/test-evidence/v1.5/summary.json", names)
            self.assertNotIn("docs/human-review/v1.5/private.sqlite", names)
            self.assertNotIn("app/src/main/assets/models/encoder.onnx", names)
            self.assertEqual([str(pkg.APK)], [name for name in names if name.endswith(".apk")])

    def test_renamed_sqlite_content_is_rejected_before_it_is_written(self):
        class MemorySink:
            def open(self, *_args, **_kwargs):
                return io.BytesIO()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "renamed-evidence.json"
            path.write_bytes(b"SQLite format 3\x00" + b"private fixture content")
            with self.assertRaisesRegex(pkg.PackageError, "Database content excluded"):
                pkg.write_payload(MemorySink(), path, root)


if __name__ == "__main__":
    unittest.main()
