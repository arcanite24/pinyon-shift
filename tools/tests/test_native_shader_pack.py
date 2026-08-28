import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/native-shader-pack.py"


def load_module():
    spec = importlib.util.spec_from_file_location("native_shader_pack", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PACK = load_module()


class NativeShaderPackTests(unittest.TestCase):
    def make_manifest(self, root: pathlib.Path, entries: list[dict]) -> pathlib.Path:
        manifest = root / "shader-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": PACK.SCHEMA,
                    "backend": "d3d12",
                    "entries": entries,
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def make_shader(self, root: pathlib.Path, name: str, payload: bytes) -> dict:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        bytecode = b"DXBC" + payload
        path.write_bytes(bytecode)
        return {
            "bytecode": name,
            "sha256": hashlib.sha256(bytecode).hexdigest(),
        }

    def test_manifest_order_does_not_change_pack(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            vertex = {
                "stage": "vertex",
                "guest_hash": "0000000000000010",
                "specialization_mask": "0000000000000000",
                **self.make_shader(root, "vertex.dxil", b"vertex"),
            }
            pixel = {
                "stage": "pixel",
                "guest_hash": "0000000000000001",
                "specialization_mask": "0000000000000002",
                **self.make_shader(root, "pixel.dxil", b"pixel"),
            }
            first = PACK.serialize(PACK.load_manifest(self.make_manifest(root, [pixel, vertex])))
            second = PACK.serialize(PACK.load_manifest(self.make_manifest(root, [vertex, pixel])))
            self.assertEqual(first, second)
            metadata = PACK.verify_pack(first)
            self.assertEqual(metadata["entry_count"], 2)
            self.assertEqual(metadata["pack_sha256"], hashlib.sha256(first).hexdigest().upper())

    def test_duplicate_identity_and_hash_mismatch_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            shared = self.make_shader(root, "shader.dxil", b"shader")
            entry = {
                "stage": "vertex",
                "guest_hash": "0000000000000001",
                "specialization_mask": "0000000000000000",
                **shared,
            }
            with self.assertRaisesRegex(PACK.PackError, "duplicates"):
                PACK.load_manifest(self.make_manifest(root, [entry, dict(entry)]))
            bad = dict(entry, sha256="00" * 32)
            with self.assertRaisesRegex(PACK.PackError, "does not match"):
                PACK.load_manifest(self.make_manifest(root, [bad]))

    def test_path_escape_and_non_dxil_input_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            outside = root.parent / f"{root.name}-outside.dxil"
            outside.write_bytes(b"DXBCoutside")
            try:
                escaped = {
                    "stage": "pixel",
                    "guest_hash": "0000000000000001",
                    "specialization_mask": "0000000000000000",
                    "bytecode": f"../{outside.name}",
                    "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                }
                with self.assertRaisesRegex(PACK.PackError, "escapes"):
                    PACK.load_manifest(self.make_manifest(root, [escaped]))

                invalid = root / "invalid.dxil"
                invalid.write_bytes(b"SPIR-V")
                non_dxil = dict(
                    escaped,
                    bytecode=invalid.name,
                    sha256=hashlib.sha256(invalid.read_bytes()).hexdigest(),
                )
                with self.assertRaisesRegex(PACK.PackError, "not a DXIL"):
                    PACK.load_manifest(self.make_manifest(root, [non_dxil]))
            finally:
                outside.unlink(missing_ok=True)

    def test_content_and_entry_corruption_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            entry = {
                "stage": "vertex",
                "guest_hash": "A2347A8A0640CBFA",
                "specialization_mask": "0000000000000000",
                **self.make_shader(root, "shader.dxil", b"candidate"),
            }
            data = bytearray(PACK.serialize(PACK.load_manifest(self.make_manifest(root, [entry]))))
            data[-1] ^= 0xFF
            with self.assertRaisesRegex(PACK.PackError, "content SHA-256"):
                PACK.verify_pack(bytes(data))

    def test_cli_build_and_verify_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            entry = {
                "stage": "pixel",
                "guest_hash": "F891D6525E633C08",
                "specialization_mask": "0000000000000000",
                **self.make_shader(root, "shader.dxil", b"candidate"),
            }
            manifest = self.make_manifest(root, [entry])
            output = root / "pack.pnsp"
            build = subprocess.run(
                [sys.executable, SCRIPT, "build", manifest, "--output", output],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertEqual(json.loads(build.stdout)["entry_count"], 1)
            verify = subprocess.run(
                [sys.executable, SCRIPT, "verify", output],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertEqual(
                json.loads(build.stdout)["pack_sha256"],
                json.loads(verify.stdout)["pack_sha256"],
            )

    def test_public_format_keeps_xenos_fallback_and_local_payload_boundary(self):
        document = (
            ROOT / "docs/native-renderer/SHADER_PACK_FORMAT.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Xenos remains authoritative", document)
        self.assertIn("must remain under `.local`", document)
        self.assertIn("does not enable guest draw or resolve suppression", document)
        policy = json.loads(
            (ROOT / "config/repository-policy.json").read_text(encoding="utf-8")
        )
        self.assertIn(".dxil", policy["forbidden_extensions"])
        self.assertIn(".pnsp", policy["forbidden_extensions"])

    def test_runtime_load_is_restart_scoped_and_never_changes_xenos_authority(self):
        source = (
            ROOT / "src/native_renderer/guest_output_renderer.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn('pinyon_shift_native_shader_pack, ""', source)
        self.assertIn("g_shader_pack.Load", source)
        self.assertIn('"native_renderer.shader_pack.ready"', source)
        self.assertIn('"native_renderer.shader_pack.failure"', source)
        self.assertIn('{"fallback", "xenos"}', source)
        self.assertLess(
            source.index("g_shader_pack.Load"),
            source.index('diagnostics::RecordEvent("native_renderer.output.state"'),
        )
        report = (ROOT / "tools/create-crash-report.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("native_shader_pack = $nativeShaderPack", report)
        self.assertIn("'native_renderer.shader_pack.ready'", report)
        self.assertIn("'native_renderer.shader_pack.failure'", report)
        self.assertNotIn("pinyon_shift_native_shader_pack'", report)
        package = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        self.assertIn("'tools/native-shader-pack.py'", package)
        self.assertIn("'.dxil', '.pnsp'", package)
        self.assertIn("'.dxil', '.pnsp'", report)


if __name__ == "__main__":
    unittest.main()
