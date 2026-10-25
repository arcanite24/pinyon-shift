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
    def community_fixture(self, root):
        source, manifest, package = self.fixture(root)
        package.update(package_id=dlc.UDLC, source="community")
        data = bytearray(source.read_bytes())
        data[0x32C] = 1
        traffic = package | dict(package_id=dlc.TRAFFIC, content_id=data[0x32C:0x340].hex().upper(),
                                 display_name="Traffic Car Unlocker", requires=[dlc.UDLC],
                                 accepted=[package["accepted"][0] | dict(
                                     sha256=hashlib.sha256(data).hexdigest().upper())])
        manifest["packages"].append(traffic)
        archive = root / "udlc.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr(package["package_id"], source.read_bytes())
            output.writestr(traffic["package_id"], data)

        def extract(args, **kwargs):
            destination, id = Path(args[3]), args[4]
            folder = destination / dlc.CONTENT / "00000002" / id
            folder.mkdir(parents=True)
            (folder / "offer.puboffer").write_bytes(b"owned")
            header = destination / dlc.CONTENT / "Headers/00000002" / (id + ".header")
            header.parent.mkdir(parents=True)
            header.write_bytes(bytes(328) + b"\1\0\0\0")
            return subprocess.CompletedProcess(args, 0, "", "")

        return archive, manifest, extract

    def test_pinned_community_import_requires_parent_and_disable_cascades(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, manifest, extract = self.community_fixture(root)
            state = root / "state"
            with patch.object(dlc, "catalog", return_value=manifest), \
                    patch.object(dlc.subprocess, "check_output", return_value=b""), \
                    patch.object(dlc.subprocess, "run", side_effect=extract):
                rows = dlc.import_content(archive, state, root / "extractor")
                self.assertEqual([(p["source"], p["enabled"]) for p in rows],
                                 [("community", False), ("community", False)])
                with self.assertRaisesRegex(ValueError, "requires.*enable it first.*also disables"):
                    dlc.set_enabled(state, dlc.TRAFFIC, True)
                dlc.set_enabled(state, dlc.UDLC, True)
                rows = dlc.set_enabled(state, dlc.TRAFFIC, True)
                self.assertTrue(all(p["enabled"] for p in rows))
                rows = dlc.set_enabled(state, dlc.UDLC, False)
                self.assertFalse(any(p["enabled"] for p in rows))
                manifest["packages"][0]["accepted"][0]["sha256"] = "F" * 64
                with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                    dlc.import_content(archive, state, root / "extractor")

    def test_old_udlc_is_recognized_by_zip_size_and_md5_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, manifest, _ = self.community_fixture(root)
            with archive.open("rb") as stream:
                md5 = hashlib.file_digest(stream, "md5").hexdigest()
            with patch.object(dlc, "OLD_UDLC_SIZE", archive.stat().st_size), \
                    patch.object(dlc, "OLD_UDLC_MD5", md5):
                with self.assertRaisesRegex(ValueError,
                        r"This is UDLC v1.11. Download UDLC v1.2 from ModDB: https://.*udlcv12"):
                    dlc.stage_inputs(archive, root, manifest)
                with patch.object(dlc, "OLD_UDLC_MD5", "0" * 32):
                    self.assertEqual(len(dlc.stage_inputs(archive, root, manifest)), 2)

    def test_payload_digest_order_is_the_same_on_every_platform(self):
        # The catalog digests were made on Windows, where paths sort without
        # case; macOS and Linux must list the files in the same order.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("Media/audio/b.fsb", "Media/AnimatedObjects/a.pgeo", "Media/1.puboffer",
                         "spa.bin", "Media/aIOpenWorld/r.owt"):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(name.encode())
            files, _ = dlc.payload_catalog(root)
        self.assertEqual([f["path"] for f in files],
                         ["Media/1.puboffer", "Media/aIOpenWorld/r.owt",
                          "Media/AnimatedObjects/a.pgeo", "Media/audio/b.fsb", "spa.bin"])

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

    def test_unsupported_packages_are_named_from_their_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, manifest, _ = self.fixture(root)
            data = bytearray(source.read_bytes())
            name = "Promo Car".encode("utf-16-be")
            data[0x411:0x411 + len(name)] = name
            data[0x32C] = 1
            source.write_bytes(data)
            with source.open("rb") as stream, self.assertRaisesRegex(
                    ValueError, '"Promo Car": this DLC package is not in the verified catalog'):
                dlc.inspect(stream, len(data), manifest)
            data[0x32C] = 0
            data[0x344:0x348] = bytes.fromhex("000D0000")
            source.write_bytes(data)
            with source.open("rb") as stream, self.assertRaisesRegex(
                    ValueError, '"Promo Car": content type 000D0000 is not Marketplace DLC'):
                dlc.inspect(stream, len(data), manifest)

    def test_unreadable_game_zips_in_a_folder_are_skipped(self):
        # An installed package's Media/DLCZips use a method Python cannot
        # inflate; choosing such a folder names the problem, not a traceback.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, _ = self.fixture(root)
            folder = root / "installed/Media/DLCZips"
            folder.mkdir(parents=True)
            archive_path = folder / "1300_pri_65.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("Media/cars/a.bin", b"LIVE game data")
            data = bytearray(archive_path.read_bytes())
            for signature, offset in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
                at = data.index(signature) + offset
                data[at:at + 2] = (9).to_bytes(2, "little")  # Deflate64
            archive_path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "no FH1 DLC packages found"):
                dlc.stage_inputs(root / "installed", root, manifest)
            with self.assertRaisesRegex(ValueError, "cannot be read"):
                dlc.stage_inputs(archive_path, root, manifest)

    def xenia_folder(self, root, package, mask=1):
        """Xenia's installed copy: <title>/00000002/<id> and its header."""
        title = root / "xenia" / "content" / "0000000000000000" / "4D5309C9"
        folder = title / "00000002" / package["package_id"]
        folder.mkdir(parents=True)
        (folder / "offer.puboffer").write_bytes(b"owned")
        header = bytearray(332)
        header[0:8] = bytes.fromhex("0000000100000002")
        header[0x108:0x108 + 42] = package["package_id"].encode()
        header[0x140:0x144] = bytes.fromhex("4D5309C9")
        header[328:332] = mask.to_bytes(4, "little")
        path = title / "Headers" / "00000002" / (package["package_id"] + ".header")
        path.parent.mkdir(parents=True)
        path.write_bytes(header)
        return title, folder, path

    def test_imports_xenias_installed_package_folders(self):
        # A player's DLC was already installed in Xenia: the unpacked folders
        # and their headers import without the original packages (#596).
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, package = self.fixture(root)
            title, folder, _ = self.xenia_folder(root, package)
            # A Deflate64 game ZIP inside the payload is not scanned.
            (folder / "Media").mkdir()
            (folder / "Media" / "DLCZips.zip").write_bytes(b"PK not readable")
            _, manifest["packages"][0]["payload_sha256"] = dlc.payload_catalog(folder)
            state = root / "state"
            active, inactive, header = dlc.package_paths(state, package["package_id"])
            with patch.object(dlc, "catalog", return_value=manifest),                     patch.object(dlc.subprocess, "check_output", return_value=b""),                     patch.object(dlc.subprocess, "run") as run:
                for chosen in (title, title.parent, title / "00000002"):
                    rows = dlc.import_content(chosen, state, root / "extractor")
                    self.assertEqual(rows[0]["license_mask"], "00000001")
                    self.assertFalse(rows[0]["enabled"])
                run.assert_not_called()
                self.assertTrue(inactive.is_dir())
                self.assertEqual(int.from_bytes(header.read_bytes()[328:332], "little"), 1)
                self.assertTrue(dlc.set_enabled(state, package["package_id"], True)[0]["enabled"])
                dlc.verified_content(state, package["package_id"], require_enabled=True)
            # Xenia's own copy is untouched.
            self.assertEqual((folder / "offer.puboffer").read_bytes(), b"owned")

    def test_xenia_folder_needs_its_header_and_a_verified_licence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest, package = self.fixture(root)
            title, folder, header = self.xenia_folder(root, package, mask=4)
            with self.assertRaisesRegex(ValueError, "licence does not match"):
                dlc.stage_inputs(title, root, manifest)
            header.unlink()
            with self.assertRaisesRegex(ValueError, "without its header"):
                dlc.stage_inputs(folder, root, manifest)
            (folder / "offer.puboffer").write_bytes(b"changed")
            self.xenia_folder(root / "other", package)
            changed = root / "other" / "xenia" / "content" / "0000000000000000" / "4D5309C9"
            (changed / "00000002" / package["package_id"] / "offer.puboffer").write_bytes(b"changed")
            state = root / "state"
            with patch.object(dlc, "catalog", return_value=manifest),                     patch.object(dlc.subprocess, "check_output", return_value=b""):
                with self.assertRaisesRegex(ValueError, "failed verification"):
                    dlc.import_content(changed, state, root / "extractor")
            self.assertFalse(any(dlc.package_paths(state, package["package_id"])[i].exists()
                                 for i in range(3)))

    def test_a_folder_with_a_package_and_a_deflate64_zip_imports_the_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, manifest, package = self.fixture(root)
            folder = root / "downloads"
            folder.mkdir()
            (folder / "rally").write_bytes(source.read_bytes())
            archive_path = folder / "big.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("LIVE", b"LIVE data")
            data = bytearray(archive_path.read_bytes())
            for signature, offset in ((b"PK", 8), (b"PK", 10)):
                at = data.index(signature) + offset
                data[at:at + 2] = (9).to_bytes(2, "little")
            archive_path.write_bytes(data)
            inputs = dlc.stage_inputs(folder, root, manifest)
            self.assertEqual([i[1]["package_id"] for i in inputs], [package["package_id"]])
            only = root / "only"
            only.mkdir()
            archive_path.rename(only / "big.zip")
            with self.assertRaisesRegex(ValueError, r"big.zip \(it uses a compression method"):
                dlc.stage_inputs(only, root, manifest)

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

    def test_licence_variants_combine_without_replacing_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, manifest, package = self.fixture(root)
            # A second purchase of the same payload with another licence bit.
            other = bytearray(source.read_bytes())
            other[-1] ^= 1
            second = root / "second"
            second.write_bytes(other)
            package["accepted"].append(dict(sha256=hashlib.sha256(other).hexdigest().upper(),
                                            size=len(other), license_mask="00000002"))
            masks = {v["sha256"]: int(v["license_mask"], 16) for v in package["accepted"]}
            state = root / "state"
            _, inactive, header = dlc.package_paths(state, package["package_id"])
            extractions = []
            def extract(args, **kwargs):
                extractions.append(args[2])
                destination = Path(args[3])
                folder = destination / dlc.CONTENT / "00000002" / package["package_id"]
                folder.mkdir(parents=True)
                (folder / "offer.puboffer").write_bytes(b"owned")
                mask = masks[hashlib.sha256(Path(args[2]).read_bytes()).hexdigest().upper()]
                sdk_header = destination / dlc.CONTENT / "Headers" / "00000002" / (package["package_id"] + ".header")
                sdk_header.parent.mkdir(parents=True)
                sdk_header.write_bytes(bytes(328) + mask.to_bytes(4, "little"))
                return subprocess.CompletedProcess(args, 0, "", "")
            with patch.object(dlc, "catalog", return_value=manifest), \
                    patch.object(dlc.subprocess, "check_output", return_value=b""), \
                    patch.object(dlc.subprocess, "run", side_effect=extract):
                rows = dlc.import_content(source, state, root / "extractor")
                self.assertEqual(rows[0]["license_mask"], "00000001")
                rows = dlc.import_content(second, state, root / "extractor")
                # Only the header grows; the verified payload is not re-extracted.
                self.assertEqual(len(extractions), 1)
                self.assertEqual(rows[0]["license_mask"], "00000003")
                self.assertEqual(int.from_bytes(header.read_bytes()[328:332], "little"), 3)
                self.assertEqual(rows[0]["sha256"], package["accepted"][0]["sha256"])
                self.assertFalse((state / "dlc/replaced").exists())
                self.assertTrue(dlc.set_enabled(state, package["package_id"], True)[0]["enabled"])
                self.assertEqual(dlc.import_content(source, state, root / "extractor")[0]["license_mask"], "00000003")
                self.assertEqual(len(extractions), 1)
                # A record naming a variant outside the catalog is rejected.
                metadata = state / "dlc" / (package["package_id"] + ".json")
                record = json.loads(metadata.read_text())
                metadata.write_text(json.dumps(record | dict(variants=record["variants"] + ["F" * 64])))
                with self.assertRaisesRegex(ValueError, "damaged"):
                    dlc.verified_content(state, package["package_id"])
            # Both variants supplied together in one folder import as one package.
            batch = root / "batch"
            batch.mkdir()
            (batch / "a").write_bytes(source.read_bytes())
            (batch / "b").write_bytes(other)
            fresh = root / "fresh"
            with patch.object(dlc, "catalog", return_value=manifest), \
                    patch.object(dlc.subprocess, "check_output", return_value=b""), \
                    patch.object(dlc.subprocess, "run", side_effect=extract):
                rows = dlc.import_content(batch, fresh, root / "extractor")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["license_mask"], "00000003")
            self.assertEqual(len(rows[0]["variants"]), 2)

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
