import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


CODEGEN = load("verify_codegen_log", ROOT / "tools/verify-codegen-log.py")
LINKS = load("check_markdown_links", ROOT / "tools/check-markdown-links.py")


class RepositoryQualityTests(unittest.TestCase):
    def test_codegen_allowlist_accepts_known_warnings_and_rejects_new_one(self):
        allowlist = ROOT / "config/rexglue/accepted-codegen-warnings.json"
        known = [
            "Function 0x8241A370 is 2536144 bytes, exceeds max_file_size_bytes (2097152)",
            "bdz at 82AD8138 branches outside function to 82AD836C",
            "bdz at 82AD813C branches outside function to 82AD836C",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            log = pathlib.Path(temporary) / "codegen.log"
            log.write_text("\n".join(f"[warning] [codegen] [t1] {line}" for line in known), encoding="utf-8")
            result = CODEGEN.verify(log, allowlist)
            self.assertEqual(result["warning_count"], 3)
            log.write_text(log.read_text(encoding="utf-8") + "\n[warning] [codegen] surprise", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unrecognized warnings"):
                CODEGEN.verify(log, allowlist)

    def test_tracked_markdown_links_are_valid(self):
        self.assertEqual(LINKS.failures(ROOT, LINKS.tracked_markdown(ROOT)), [])

    def test_release_tag_matches_declared_version(self):
        version = json.loads((ROOT / "config/release.json").read_text(encoding="utf-8"))["version"]
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools/verify-release-tag.py"),
             "--tag", f"v{version}", "--main-ref", "HEAD"],
            capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        wrong = subprocess.run(
            [sys.executable, str(ROOT / "tools/verify-release-tag.py"),
             "--tag", "v0.0.0-wrong", "--main-ref", "HEAD"],
            capture_output=True, text=True,
        )
        self.assertEqual(wrong.returncode, 2)
        self.assertIn("does not match", wrong.stderr)


if __name__ == "__main__":
    unittest.main()
