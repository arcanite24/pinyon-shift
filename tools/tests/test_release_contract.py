import hashlib
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class ReleaseContractTests(unittest.TestCase):
    def test_supported_dump_uses_exact_hash_and_size(self):
        data = json.loads((ROOT / "config/supported-dumps.json").read_text())
        self.assertEqual(data["policy"]["match"], "exact_sha256_and_size")
        self.assertEqual(data["policy"]["unknown_dump_action"], "reject")
        for dump in data["dumps"]:
            self.assertGreater(dump["iso"]["size_bytes"], 0)
            self.assertRegex(dump["iso"]["sha256"], r"^[0-9A-F]{64}$")

    def test_downloads_are_https_and_sha256_pinned(self):
        data = json.loads((ROOT / "config/release-toolchain.json").read_text())
        for key in ("git", "llvm", "extract_xiso"):
            item = data[key]
            self.assertTrue(item["url"].startswith("https://"))
            self.assertRegex(item["sha256"], r"^[0-9A-F]{64}$")
        self.assertTrue(data["visual_studio"]["bootstrap_url"].startswith("https://"))
        self.assertRegex(data["rexglue"]["base_commit"], r"^[0-9a-f]{40}$")

    def test_rexglue_patches_have_stable_order_and_no_binary_payload(self):
        patches = sorted((ROOT / "patches/rexglue").glob("*.patch"))
        self.assertGreater(len(patches), 0)
        self.assertEqual(len(patches), len({path.name[:4] for path in patches}))
        for path in patches:
            text = path.read_text(encoding="utf-8", errors="strict")
            self.assertIn("diff --git", text)
            self.assertNotIn("GIT binary patch", text)

    def test_launcher_payload_has_every_required_script(self):
        required = {
            "build-preview.ps1", "install-build-tools.ps1", "launch-preview.ps1",
            "prepare-rexglue.ps1", "provision-toolchain.ps1", "release-common.ps1",
            "setup-preview.ps1", "verify-game.ps1",
        }
        self.assertTrue(required.issubset({p.name for p in (ROOT / "tools").glob("*.ps1")}))


if __name__ == "__main__":
    unittest.main()
