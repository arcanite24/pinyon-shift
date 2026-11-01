"""tools/apk_sign.py: the JDK-free zipalign and v2 signer (TP-5).

apksigner verify and a device install of a real package were checked by
hand (docs/TIME_TO_PLAY_BACKLOG.md); these keep the pieces honest."""
from __future__ import annotations

import io
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apk_sign  # noqa: E402


def sample_apk() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest" * 50, zipfile.ZIP_DEFLATED)
        archive.writestr("resources.arsc", b"r" * 333, zipfile.ZIP_STORED)
        archive.writestr("lib/arm64-v8a/libmain.so", b"\x7fELF" + b"s" * 5000, zipfile.ZIP_STORED)
        archive.writestr("classes.dex", b"dex\n" * 900, zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


class ApkSignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.key = apk_sign.RsaKey.generate(1024)
        cls.certificate = apk_sign.self_signed_certificate(cls.key, "test")

    def test_aes_matches_fips_197(self) -> None:
        apk_sign._aes_tables()
        for key, cipher in ((bytes(range(16)), "69c4e0d86a7b0430d8cdb78070b4c55a"),
                            (bytes(range(32)), "8ea2b7ca516745bfeafc49904b496089")):
            plain = apk_sign._decrypt_block(apk_sign._expand_key(key), bytes.fromhex(cipher))
            self.assertEqual(plain.hex(), "00112233445566778899aabbccddeeff")

    def test_zipalign_aligns_stored_entries_and_libraries_to_16_kib(self) -> None:
        aligned = apk_sign.zipalign(sample_apk())
        with zipfile.ZipFile(io.BytesIO(aligned)) as archive:
            self.assertIsNone(archive.testzip())
            for info in archive.infolist():
                header = info.header_offset
                name_length, extra_length = struct.unpack_from("<HH", aligned, header + 26)
                start = header + 30 + name_length + extra_length
                if info.compress_type == zipfile.ZIP_STORED:
                    self.assertEqual(start % (16384 if info.filename.endswith(".so") else 4), 0,
                                     info.filename)

    def test_signature_verifies_and_a_changed_byte_does_not(self) -> None:
        signed = apk_sign.sign(sample_apk(), self.key, self.certificate)
        result = apk_sign.verify_v2(signed)
        self.assertEqual(result["scheme"], "v2")
        with zipfile.ZipFile(io.BytesIO(signed)) as archive:
            self.assertIsNone(archive.testzip())
        tampered = bytearray(signed)
        tampered[100] ^= 1
        with self.assertRaises(ValueError):
            apk_sign.verify_v2(bytes(tampered))

    def test_key_round_trips_through_pkcs8_and_is_kept(self) -> None:
        restored = apk_sign.RsaKey.from_pkcs8(self.key.pkcs8())
        self.assertEqual((restored.n, restored.d), (self.key.n, self.key.d))
        with tempfile.TemporaryDirectory() as directory:
            first = apk_sign.signing_key(Path(directory))
            again = apk_sign.signing_key(Path(directory))
            self.assertEqual(first[1], again[1])
            self.assertEqual(first[0].n, again[0].n)


if __name__ == "__main__":
    unittest.main()
