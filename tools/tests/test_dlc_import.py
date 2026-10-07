"""Import trust boundaries and content publication, with no game/save inputs."""
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("dlc", Path(__file__).parents[1] / "manage-fh1-dlc.py")
dlc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dlc)


class DlcImportTests(unittest.TestCase):
    def test_active_content_reverification_rejects_tampering_and_preserves_save(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, package = self.fixture(root)
            state = root / "state"
            active, inactive, header = dlc.package_paths(state, package["package_id"])
            active.mkdir(parents=True)
            (active / "offer.puboffer").write_bytes(b"owned")
            header.parent.mkdir(parents=True)
            header.write_bytes(bytes(328) + b"\1\0\0\0")
            (state / "dlc").mkdir()
            record = dict(package_id=package["package_id"], sha256=package["accepted"][0]["sha256"],
                          payload_sha256=package["payload_sha256"], license_mask="00000001",
                          header_sha256=hashlib.sha256(header.read_bytes()).hexdigest().upper())
            metadata = state / "dlc" / (package["package_id"] + ".json")
            metadata.write_text(json.dumps(record))
            save = state / "user/save-sentinel"
            save.write_bytes(b"keep")
            with patch.object(dlc, "catalog", return_value=manifest), patch.object(dlc.subprocess, "check_output", return_value=b""):
                self.assertTrue(dlc.set_enabled(state, package["package_id"], True)[0]["enabled"])
                (active / "offer.puboffer").write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "incomplete or changed"):
                    dlc.set_enabled(state, package["package_id"], True)
                (active / "offer.puboffer").write_bytes(b"owned")
                header.write_bytes(bytes(328) + b"\4\0\0\0")
                # Even updating the mutable header hash cannot widen the source entitlement.
                metadata.write_text(json.dumps(record | dict(license_mask="00000004",
                    header_sha256=hashlib.sha256(header.read_bytes()).hexdigest().upper())))
                with self.assertRaisesRegex(ValueError, "licence changed"):
                    dlc.verified_content(state, package["package_id"], require_enabled=True)
                dlc.set_enabled(state, package["package_id"], False)
                self.assertTrue(inactive.is_dir())
                self.assertEqual(save.read_bytes(), b"keep")

    def fixture(self, root):
        payload = root / "payload"
        payload.mkdir()
        (payload / "offer.puboffer").write_bytes(b"owned")
        _, digest = dlc.payload_catalog(payload)
        data = bytearray(0xA000)
        data[:4] = b"LIVE"
        data[0x344:0x348] = bytes.fromhex("00000002")
        data[0x360:0x364] = bytes.fromhex("4D5309C9")
        package = dict(package_id="A" * 42, content_id="00" * 20, display_name="Test DLC",
                       payload_sha256=digest, file_count=1, rejected=[], accepted=[dict(
                           sha256=hashlib.sha256(data).hexdigest().upper(), size=len(data), license_mask="00000001")])
        source = root / "source"
        source.write_bytes(data)
        return source, dict(title_id="4D5309C9", content_type="00000002", packages=[package]), package

    def test_rejects_wrong_title_changed_payload_and_zip_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, manifest, _ = self.fixture(root)
            data = bytearray(source.read_bytes())
            data[0x360] ^= 1
            source.write_bytes(data)
            with source.open("rb") as stream, self.assertRaisesRegex(ValueError, "another game"):
                dlc.inspect(stream, len(data), manifest)
            data[0x360] ^= 1
            data[-1] ^= 1
            source.write_bytes(data)
            with source.open("rb") as stream, self.assertRaisesRegex(ValueError, "SHA-256"):
                dlc.inspect(stream, len(data), manifest)
            with zipfile.ZipFile(root / "bad.zip", "w") as archive:
                archive.writestr("../escape", b"bad")
            with self.assertRaisesRegex(ValueError, "unsafe ZIP"):
                dlc.stage_inputs(root / "bad.zip", root, manifest)
            self.assertFalse((root.parent / "escape").exists())

    def test_failed_extraction_never_publishes_and_retry_preserves_save(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, manifest, package = self.fixture(root)
            state = root / "state"
            save = state / "user" / "save-sentinel"
            save.parent.mkdir(parents=True)
            save.write_bytes(b"preserve this save")
            active, inactive, header = dlc.package_paths(state, package["package_id"])
            def extract(args, **kwargs):
                destination = Path(args[3])
                folder = destination / dlc.CONTENT / "00000002" / package["package_id"]
                folder.mkdir(parents=True)
                (folder / "offer.puboffer").write_bytes(b"owned")
                sdk_header = destination / dlc.CONTENT / "Headers" / "00000002" / (package["package_id"] + ".header")
                sdk_header.parent.mkdir(parents=True)
                sdk_header.write_bytes(bytes(328) + b"\1\0\0\0")
                return subprocess.CompletedProcess(args, 0, "", "")
            with patch.object(dlc, "catalog", return_value=manifest), patch.object(dlc.subprocess, "check_output", return_value=b""):
                with patch.object(dlc.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "short read")):
                    with self.assertRaisesRegex(ValueError, "short read"):
                        dlc.import_content(source, state, root / "extractor")
                self.assertFalse(active.exists() or inactive.exists() or header.exists())
                self.assertFalse(list((state / "dlc").glob("staging-*")))
                with patch.object(dlc.subprocess, "run", side_effect=extract):
                    self.assertFalse(dlc.import_content(source, state, root / "extractor")[0]["enabled"])
                    self.assertTrue(dlc.set_enabled(state, package["package_id"], True)[0]["enabled"])
                    self.assertTrue(dlc.import_content(source, state, root / "extractor")[0]["enabled"])
                    (state / "dlc" / (package["package_id"] + ".json")).write_text("{")
                    self.assertEqual(dlc.import_content(source, state, root / "extractor")[0]["status"], "gameplay_unverified")
                    self.assertFalse(dlc.set_enabled(state, package["package_id"], False)[0]["enabled"])
                    header.unlink()
                    self.assertEqual(dlc.list_content(state)[0]["status"], "missing")
                    self.assertEqual(dlc.import_content(source, state, root / "extractor")[0]["status"], "gameplay_unverified")
                    (inactive / "offer.puboffer").write_bytes(b"changed")
                    dlc.import_content(source, state, root / "extractor")
                    self.assertEqual((inactive / "offer.puboffer").read_bytes(), b"owned")
                    retained = list((state / "dlc/replaced").glob("**/offer.puboffer"))
                    self.assertEqual(len(retained), 1)
                    self.assertEqual(retained[0].read_bytes(), b"changed")
                self.assertEqual(save.read_bytes(), b"preserve this save")

    def test_damaged_record_does_not_hide_other_packages_or_prevent_disable(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            id = "B" * 42
            active, inactive, header = dlc.package_paths(state, id)
            active.mkdir(parents=True)
            (active / "payload").write_bytes(b"preserve")
            metadata = state / "dlc"
            metadata.mkdir()
            record = metadata / (id + ".json")
            other = "D" * 42
            (metadata / (other + ".json")).write_text(json.dumps(dict(package_id=other)))
            for data in ("{", "[]", json.dumps(dict(package_id="C" * 42)),
                         json.dumps(dict(package_id=id, sha256=[]))):
                record.write_text(data)
                rows = dlc.list_content(state)
                self.assertEqual(rows[0]["status"], "metadata_invalid")
                self.assertTrue(rows[0]["enabled"])
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[1]["package_id"], other)
            with patch.object(dlc.subprocess, "check_output", return_value=b""):
                dlc.set_enabled(state, id, False)
            self.assertEqual((inactive / "payload").read_bytes(), b"preserve")
            self.assertFalse(active.exists())
            record.write_text(json.dumps(dict(package_id=id)))
            inactive.rename(active)
            with patch.object(dlc.subprocess, "check_output", return_value=b""):
                self.assertEqual(dlc.set_enabled(state, id, False)[0]["status"], "missing")
                with self.assertRaisesRegex(ValueError, "verified package"):
                    dlc.set_enabled(state, id, True)


if __name__ == "__main__":
    unittest.main()
