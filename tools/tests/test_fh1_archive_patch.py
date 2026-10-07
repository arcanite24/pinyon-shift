"""Guest payload offsets, opaque XMem preservation and original-file protection."""
import importlib.util
import struct
import tempfile
import subprocess
import unittest
import zipfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("archive_patch",
    Path(__file__).parents[1] / "patch-fh1-archive.py")
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)
EXTRACTOR = Path(__file__).parents[2] / 'out/build/win-amd64-release/pinyon_shift_fh1_archive_extract.exe'


class ArchivePatchTests(unittest.TestCase):
    @unittest.skipUnless(EXTRACTOR.is_file(), 'build the archive extractor for LZX integration checks')
    def test_xmem_replacement_decodes_multiple_frames_odd_tail_and_e8_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, decoded = root / 'source.zip', root / 'out.zip', root / 'decoded.bin'
            with zipfile.ZipFile(source, 'w') as archive:
                member = zipfile.ZipInfo('scene.bgf')
                member.extra = struct.pack('<HHI', 0x1123, 4, 0)
                archive.writestr(member, b'original')
            original = source.read_bytes()
            data = bytes(range(256)) * 384 + b'\xe8\x10\x00\x00\x00xx'
            patcher.patch_archive(source, output, {'scene.bgf': data}, xmem=True)
            self.assertEqual(source.read_bytes(), original)
            with zipfile.ZipFile(output) as archive:
                member = archive.getinfo('scene.bgf')
                self.assertEqual(member.compress_type, 21)
                self.assertEqual(member.file_size, len(data))
            subprocess.run([str(EXTRACTOR), '--archive-member', str(output),
                            'scene.bgf', str(decoded)], check=True, capture_output=True)
            self.assertEqual(decoded.read_bytes(), data)

    def test_recalculates_guest_offsets_and_preserves_opaque_xmem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "original.zip", root / "patched.zip"
            with zipfile.ZipFile(source, "w") as archive:
                for name, data in (("flow.xml", b"old flow"), ("asset.bin", b"opaque compressed payload")):
                    member = zipfile.ZipInfo(name)
                    member.extra = struct.pack("<HHI", 0x1123, 4, 0)
                    archive.writestr(member, data)
            raw = bytearray(source.read_bytes())
            with zipfile.ZipFile(source) as archive:
                cursor = archive.start_dir
                for member in archive.infolist():
                    name_size, extra_size = struct.unpack_from("<HH", raw, member.header_offset + 26)
                    payload = member.header_offset + 30 + name_size + extra_size
                    struct.pack_into("<I", raw, cursor + 46 + len(member.filename) + 4, payload)
                    if member.filename == "asset.bin":
                        # Method 21 cannot be read by Python's ZIP implementation.
                        # The patcher must keep this opaque member byte-for-byte.
                        struct.pack_into("<H", raw, member.header_offset + 8, 21)
                        struct.pack_into("<H", raw, cursor + 10, 21)
                    cursor += 46 + len(member.filename) + len(member.extra)
            source.write_bytes(raw)
            replacement = b"new flow substantially longer than its original"
            patcher.patch_archive(source, output, {"FLOW.XML": replacement})
            self.assertEqual(source.read_bytes(), raw)
            patched = output.read_bytes()
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read("flow.xml"), replacement)
                self.assertEqual(archive.getinfo("asset.bin").compress_type, 21)
                for member in archive.infolist():
                    payload = struct.unpack_from("<I", member.extra, 4)[0]
                    expected = replacement if member.filename == "flow.xml" else b"opaque compressed payload"
                    self.assertEqual(patched[payload:payload + member.compress_size], expected)

    def test_rejects_unknown_member_and_existing_output_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.zip", Path(directory) / "out.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("flow.xml", b"original")
            with self.assertRaises(ValueError):
                patcher.patch_archive(source, output, {"unknown": b"new"})
            self.assertFalse(output.exists())
            output.write_bytes(b"retain this")
            with self.assertRaises(FileExistsError):
                patcher.patch_archive(source, output, {"flow.xml": b"new"})
            self.assertEqual(output.read_bytes(), b"retain this")
            with self.assertRaises(FileExistsError):
                patcher.patch_archive(source, source, {"flow.xml": b"new"})
            with zipfile.ZipFile(source) as archive:
                self.assertEqual(archive.read("flow.xml"), b"original")


if __name__ == "__main__":
    unittest.main()
