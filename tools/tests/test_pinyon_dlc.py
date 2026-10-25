"""UDLC browser helper and the real import/enable path, using synthetic packages."""
import argparse
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import pinyon_dlc
import test_dlc_import as fixtures

dlc = fixtures.dlc


class PinyonDlcTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        combined, manifest, extract = fixtures.DlcImportTests().community_fixture(self.root)
        self.downloads = self.root / "downloads"
        self.downloads.mkdir()
        self.archives = {}
        with zipfile.ZipFile(combined) as archive:
            for id, name in ((dlc.UDLC, "UDLCv1.2.zip"), (dlc.TRAFFIC, "Traffic_Unlocker.1.zip")):
                path = self.downloads / name
                with zipfile.ZipFile(path, "w") as output:
                    output.writestr(id, archive.read(id))
                self.archives[id] = dict(file=name, size=path.stat().st_size,
                                         md5=hashlib.md5(path.read_bytes()).hexdigest(),
                                         page=pinyon_dlc.UDLC_ARCHIVES[id]["page"])
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        for context in (patch.object(pinyon_dlc, "manager", return_value=dlc),
                        patch.object(pinyon_dlc, "UDLC_ARCHIVES", self.archives),
                        patch.object(pinyon_dlc.common, "require_extractor", return_value=self.root / "extractor"),
                        patch.object(pinyon_dlc.xe, "download_folders", return_value=[self.downloads]),
                        patch.object(dlc, "catalog", return_value=manifest),
                        patch.object(dlc.subprocess, "check_output", return_value=b""),
                        patch.object(dlc.subprocess, "run", side_effect=extract)):
            stack.enter_context(context)

    def args(self, *arguments):
        parser = argparse.ArgumentParser()
        pinyon_dlc.add_parser(parser.add_subparsers(dest="command"))
        return parser.parse_args(["dlc", "udlc", *arguments, "--state-root", str(self.root / "state"), "--json"])

    def test_find_accepts_browser_rename_and_ignores_partial_downloads(self):
        main = self.downloads / self.archives[dlc.UDLC]["file"]
        renamed = main.with_name("UDLCv1.2 (1).zip")
        main.rename(renamed)
        valid_zip = renamed.read_bytes()
        main.write_bytes(b"partial")
        renamed.with_suffix(".zip.crdownload").write_bytes(renamed.read_bytes())
        self.assertEqual(pinyon_dlc.find_udlc([self.downloads], [dlc.UDLC]), {dlc.UDLC: renamed})
        renamed.unlink()
        self.assertEqual(pinyon_dlc.find_udlc([self.downloads], [dlc.UDLC]), {})
        for name in ("UDLCv1.2(1).zip", "UDLCv1.2-2.zip", "UDLCv1.2 2.zip"):
            with self.subTest(name=name):
                path = self.downloads / name
                path.write_bytes(valid_zip)
                self.assertEqual(pinyon_dlc.find_udlc([self.downloads], [dlc.UDLC]), {dlc.UDLC: path})
                path.unlink()

    def test_partial_companion_record_still_has_a_name_in_the_json_result(self):
        metadata = self.root / "state/dlc"
        metadata.mkdir(parents=True)
        (metadata / (dlc.TRAFFIC + ".json")).write_text(json.dumps({"package_id": dlc.TRAFFIC}))
        result = pinyon_dlc.run(self.args("--find"))
        self.assertEqual(result["result"], "ok")
        traffic = next(p for p in result["packages"] if p["package_id"] == dlc.TRAFFIC)
        self.assertEqual(traffic["display_name"], "Traffic Car Unlocker")
        self.assertEqual(traffic["status"], "missing")

    def test_find_rejects_wrong_md5_and_names_the_missing_download(self):
        main = self.downloads / self.archives[dlc.UDLC]["file"]
        data = bytearray(main.read_bytes())
        data[-1] ^= 1
        main.write_bytes(data)
        with self.assertRaisesRegex(pinyon_dlc.common.CommandError, "failed its MD5 check"):
            pinyon_dlc.run(self.args("--find"))
        main.unlink()
        with self.assertRaisesRegex(pinyon_dlc.common.CommandError, "was not found.*udlcv12"):
            pinyon_dlc.run(self.args("--find"))
        self.assertFalse((self.root / "state").exists())

    def test_paths_import_and_enable_in_dependency_order_and_emit_one_json_object(self):
        paths = [str(self.downloads / self.archives[id]["file"]) for id in (dlc.TRAFFIC, dlc.UDLC)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(pinyon_dlc.main(self.args(*paths)), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["result"], "ok")
        self.assertEqual([p["package_id"] for p in result["packages"]], [dlc.UDLC, dlc.TRAFFIC])
        for package in result["packages"]:
            self.assertEqual(set(package), {"package_id", "display_name", "enabled", "status", "source", "author"})
            self.assertTrue(package["enabled"])
            self.assertEqual(package["source"], "community")
            self.assertEqual(package["status"], "gameplay_unverified")

    def test_find_opens_pages_and_waits_then_installs_both(self):
        saved = {p.name: p.read_bytes() for p in self.downloads.iterdir()}
        for path in self.downloads.iterdir():
            path.unlink()

        def finish(_):
            for name, data in saved.items():
                (self.downloads / name).write_bytes(data)

        with patch.object(pinyon_dlc.time, "sleep", side_effect=finish) as sleep, \
                patch.object(pinyon_dlc.webbrowser, "open") as opened:
            result = pinyon_dlc.run(self.args("--find", "--traffic", "--open-pages", "--wait", "60"))
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual([c.args[0] for c in opened.call_args_list], [a["page"] for a in self.archives.values()])
        self.assertTrue(all(p["enabled"] for p in result["packages"]))

    def test_error_json_and_old_version_rejection(self):
        main = self.downloads / self.archives[dlc.UDLC]["file"]
        with patch.object(dlc, "OLD_UDLC_SIZE", main.stat().st_size), \
                patch.object(dlc, "OLD_UDLC_MD5", hashlib.md5(main.read_bytes()).hexdigest()):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(pinyon_dlc.main(self.args(str(main))), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(set(result), {"result", "error"})
        self.assertEqual(result["result"], "error")
        self.assertTrue(result["error"].startswith("This is UDLC v1.11. Download UDLC v1.2 from ModDB:"))

    def test_invalid_wait_and_archive_failure_keep_the_json_contract(self):
        for wait in ("-1", "nan", "inf"):
            with self.subTest(wait=wait), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(pinyon_dlc.main(self.args("--wait", wait)), 1)
                self.assertEqual(json.loads(output.getvalue())["result"], "error")
        with patch.object(dlc, "import_content", side_effect=zipfile.BadZipFile("damaged ZIP")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(pinyon_dlc.main(self.args("--find")), 1)
        self.assertEqual(json.loads(output.getvalue()),
                         {"result": "error", "error": "UDLC could not be imported: damaged ZIP"})


if __name__ == "__main__":
    unittest.main()
