import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("title_update", ROOT / "tools/verify-fh1-title-update.py")
TITLE_UPDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TITLE_UPDATE)


class TitleUpdateTests(unittest.TestCase):
    def test_source_checks_reject_each_mismatch(self):
        base = bytearray(512)
        struct.pack_into(">6I", base, 0, 0x58455832, 0, 512, 0, 128, 1)
        struct.pack_into(">2I", base, 24, 0x40006, 64)
        struct.pack_into(">4I", base, 64, 0x4000D145, 12, 12, 0x4D5309C9)
        patch = bytearray(512)
        struct.pack_into(">6I", patch, 0, 0x58455832, 0x50, 512, 0, 128, 1)
        struct.pack_into(">2I", patch, 24, 0x5FF, 64)
        struct.pack_into(">3I", patch, 64, 0x4C, 0x40C, 12)
        patch[76:96] = TITLE_UPDATE.hashlib.sha1(base[136:392]).digest()
        update = {"title_id": "4D5309C9", "media_id": "4000D145",
                  "source_version": "0000000C", "target_version": "0000040C"}
        self.assertTrue(TITLE_UPDATE.check_source(base, patch, update)["compatible"])
        for offset, value, check in ((64, 0x2DC7007B, "media_id_matches"),
                                     (68, 10, "source_version_matches"),
                                     (76, 0, "title_id_matches"),
                                     (136, 1, "source_signature_matches")):
            changed = bytearray(base)
            struct.pack_into(">I", changed, offset, value)
            result = TITLE_UPDATE.check_source(changed, patch, update)
            self.assertFalse(result["compatible"])
            self.assertFalse(result[check])

    @staticmethod
    def chained_headers(blocks):
        """Build headers whose descriptors chain over 4 KiB-page blocks."""
        security = 64
        headers = bytearray(security + 0x184 + 24 * len(blocks))
        struct.pack_into(">6I", headers, 0, 0x58455832, 0, len(headers), 0, security, 0)
        struct.pack_into(">I", headers, security + 0x10C, TITLE_UPDATE.PAGE_SIZE_4KB)
        struct.pack_into(">I", headers, security + 0x180, len(blocks))
        digest = b""
        for index in reversed(range(len(blocks))):
            offset = security + 0x184 + index * 24
            struct.pack_into(">I", headers, offset, (len(blocks[index]) // 0x1000) << 4)
            headers[offset + 4:offset + 24] = digest or bytes(20)
            digest = TITLE_UPDATE.hashlib.sha1(blocks[index] + headers[offset:offset + 24]).digest()
        headers[security + 0x114:security + 0x128] = digest
        return bytes(headers)

    def test_pages_verify_through_the_descriptor_chain(self):
        blocks = [bytes([1]) * 0x1000, bytes([2]) * 0x2000, bytes(0x1000)]
        headers, image = self.chained_headers(blocks), b"".join(blocks)
        self.assertTrue(TITLE_UPDATE.verify_pages(headers, image)["verified"])
        for page in range(3):
            changed = bytearray(image)
            changed[sum(len(b) for b in blocks[:page]) + 5] ^= 1
            result = TITLE_UPDATE.verify_pages(headers, bytes(changed))
            self.assertFalse(result["verified"])
            self.assertEqual(result["failing_pages"], [page])
        self.assertFalse(TITLE_UPDATE.verify_pages(headers, image + bytes(0x1000))["verified"])
        self.assertFalse(TITLE_UPDATE.verify_pages(headers, image[:-1])["verified"])
        # A descriptor change breaks the digest that covers it.
        bad = bytearray(headers)
        bad[64 + 0x184 + 24 + 4] ^= 1
        self.assertEqual(TITLE_UPDATE.verify_pages(bytes(bad), image)["failing_pages"], [1, 2])

    def test_install_publishes_reuses_and_keeps_the_previous_copy(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extracted, state = root / "files", root / "state"
            extracted.mkdir()
            files = {"default.xexp": b"patch", "media.zip": b"media"}
            for name, data in files.items():
                (extracted / name).write_bytes(data)
            update = {"files": [{"guest_path": name, "size_bytes": len(data),
                                 "sha256": TITLE_UPDATE.hashlib.sha256(data).hexdigest().upper()}
                                for name, data in files.items()]}
            first = TITLE_UPDATE.install(extracted, update, state)
            self.assertFalse(first["reused"])
            target = state / TITLE_UPDATE.INSTALL_FOLDER
            self.assertEqual((target / "media.zip").read_bytes(), b"media")
            self.assertTrue(TITLE_UPDATE.install(extracted, update, state)["reused"])
            (target / "media.zip").write_bytes(b"older")
            self.assertFalse(TITLE_UPDATE.install(extracted, update, state)["reused"])
            self.assertEqual((state / "title-update-v4.previous-1" / "media.zip").read_bytes(), b"older")
            self.assertEqual((target / "media.zip").read_bytes(), b"media")
            # A copy that fails verification publishes nothing new.
            update["files"][0]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                TITLE_UPDATE.install(extracted, update, state)
            self.assertEqual(sorted(p.name for p in state.iterdir()),
                             ["title-update-v4", "title-update-v4.previous-1"])

    def test_malformed_headers_are_rejected(self):
        for data in (b"", b"XEX2" + bytes(20),
                     struct.pack(">6I", 0x58455832, 0, 24, 0, 0, 100)):
            with self.assertRaises(ValueError):
                TITLE_UPDATE.xex_headers(data)
        data = struct.pack(">6I", 0x58455832, 0, 24, 0, 0, 0)
        with self.assertRaises(ValueError):
            TITLE_UPDATE.header_data(data, {0x40006: 24}, 0x40006, 24)


if __name__ == "__main__":
    unittest.main()
