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
    def make_manifest(
        self,
        root: pathlib.Path,
        entries: list[dict],
        backend: str = "d3d12",
        device_features: int = 1,
    ) -> pathlib.Path:
        manifest = root / "shader-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": PACK.SCHEMA,
                    "backend": backend,
                    "translation": {
                        "translator_version": "20260827",
                        "device_features": device_features,
                        "bindless_resources": True,
                        "edram_rov": False,
                        "gamma_render_target_as_unorm8": True,
                        "msaa_2x": True,
                        "draw_resolution_scale_x": 1,
                        "draw_resolution_scale_y": 1,
                    },
                    "entries": entries,
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def make_shader(
        self, root: pathlib.Path, name: str, payload: bytes, magic: bytes = b"DXBC"
    ) -> dict:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        bytecode = magic + payload
        path.write_bytes(bytecode)
        return {
            "bytecode": name,
            "sha256": hashlib.sha256(bytecode).hexdigest(),
            "texture_bindings": [],
            "sampler_bindings": [],
            "used_texture_mask": 0,
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
            self.assertEqual(metadata["translator_version"], "20260827")
            self.assertEqual(metadata["backend"], "d3d12")
            self.assertEqual(metadata["device_features"], 1)
            self.assertEqual(metadata["geometry_shader_count"], 0)
            self.assertEqual(metadata["pack_sha256"], hashlib.sha256(first).hexdigest().upper())

    def test_shared_bytecode_file_matches_one_file_per_shader(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            identities = [("vertex", "0000000000000010"), ("pixel", "0000000000000001")]
            separate = [
                {"stage": stage, "guest_hash": guest_hash,
                 "specialization_mask": "0000000000000000",
                 **self.make_shader(root, f"{stage}.dxil", stage.encode())}
                for stage, guest_hash in identities
            ]
            expected = PACK.serialize(PACK.load_manifest(self.make_manifest(root, separate)))
            blob = bytearray()
            shared = []
            for entry in separate:
                bytecode = (root / entry["bytecode"]).read_bytes()
                shared.append({**entry, "bytecode": "dxil.blob",
                               "bytecode_offset": len(blob), "bytecode_size": len(bytecode)})
                blob.extend(bytecode)
            (root / "dxil.blob").write_bytes(bytes(blob))
            actual = PACK.serialize(PACK.load_manifest(self.make_manifest(root, shared)))
            self.assertEqual(actual, expected)
            shared[1]["bytecode_size"] += 1
            with self.assertRaisesRegex(PACK.PackError, "range exceeds"):
                PACK.load_manifest(self.make_manifest(root, shared))

    def test_bindings_round_trip_and_texture_mask_is_checked(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            entry = {
                "stage": "pixel",
                "guest_hash": "0000000000000001",
                "specialization_mask": "0000000000000002",
                **self.make_shader(root, "pixel.dxil", b"pixel"),
                "texture_bindings": [
                    {
                        "bindless_descriptor_index": 7,
                        "fetch_constant": 3,
                        "dimension": 1,
                        "is_signed": 0,
                    }
                ],
                "sampler_bindings": [
                    {
                        "bindless_descriptor_index": 5,
                        "fetch_constant": 3,
                        "mag_filter": 0,
                        "min_filter": 1,
                        "mip_filter": 2,
                        "aniso_filter": 3,
                    }
                ],
                "used_texture_mask": 1 << 3,
            }
            data = PACK.serialize(PACK.load_manifest(self.make_manifest(root, [entry])))
            self.assertEqual(PACK.verify_pack(data)["entry_count"], 1)
            entry["used_texture_mask"] = 0
            with self.assertRaisesRegex(PACK.PackError, "does not match bindings"):
                PACK.load_manifest(self.make_manifest(root, [entry]))

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

    def test_build_merges_manifests_with_the_same_configuration(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            first_entry = {
                "stage": "vertex",
                "guest_hash": "0000000000000001",
                "specialization_mask": "0000000000000000",
                **self.make_shader(root, "first.dxil", b"first"),
            }
            first = self.make_manifest(root, [first_entry])
            first = first.rename(root / "first.json")
            second_entry = {
                "stage": "pixel",
                "guest_hash": "0000000000000002",
                "specialization_mask": "0000000000000000",
                **self.make_shader(root, "second.dxil", b"second"),
            }
            second = self.make_manifest(root, [second_entry])
            second = second.rename(root / "second.json")
            output = root / "merged.pnsp"
            result = subprocess.run(
                [
                    sys.executable,
                    SCRIPT,
                    "build",
                    first,
                    second,
                    "--output",
                    output,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["entry_count"], 2)

    def test_stage_uses_exact_fh1_runtime_name_and_scale(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            entry = {
                "stage": "vertex",
                "guest_hash": "0000000000000001",
                "specialization_mask": "0000000000000000",
                **self.make_shader(root, "vertex.dxil", b"vertex"),
            }
            pack = root / "source.pnsp"
            pack.write_bytes(PACK.serialize(PACK.load_manifest(self.make_manifest(root, [entry]))))
            result = PACK._stage(
                type("Arguments", (), {"pack": pack, "state_root": root / "state", "scale": 1})
            )
            destination = pathlib.Path(result["destination"])
            self.assertEqual(
                destination.name, "4D5309C9.fh1-native-v3.d3d12.01.0D.1x1.pnsp"
            )
            self.assertEqual(destination.read_bytes(), pack.read_bytes())
            self.assertTrue(result["changed"])
            self.assertFalse(
                PACK._stage(
                    type("Arguments", (), {"pack": pack, "state_root": root / "state", "scale": 1})
                )["changed"]
            )
            with self.assertRaisesRegex(PACK.PackError, "requested 2x"):
                PACK._stage(
                    type("Arguments", (), {"pack": pack, "state_root": root / "state", "scale": 2})
                )

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
                with self.assertRaisesRegex(PACK.PackError, "not a d3d12 shader"):
                    PACK.load_manifest(self.make_manifest(root, [non_dxil]))
            finally:
                outside.unlink(missing_ok=True)

    def test_geometry_shaders_are_keyed_without_a_guest_shader(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            geometry = {
                "stage": "geometry",
                "guest_hash": "0000000000000000",
                "specialization_mask": "0000000000001234",
                **self.make_shader(root, "geometry.dxbc", b"geometry"),
            }
            pixel = {
                "stage": "pixel",
                "guest_hash": "0000000000000001",
                "specialization_mask": "0000000000000002",
                **self.make_shader(root, "pixel.dxbc", b"pixel"),
            }
            data = PACK.serialize(
                PACK.load_manifest(self.make_manifest(root, [geometry, pixel]))
            )
            metadata = PACK.verify_pack(data)
            self.assertEqual(metadata["entry_count"], 2)
            self.assertEqual(metadata["geometry_shader_count"], 1)
            with self.assertRaisesRegex(PACK.PackError, "no guest hash or bindings"):
                PACK.load_manifest(
                    self.make_manifest(root, [dict(geometry, guest_hash="0000000000000001")])
                )

    def test_vulkan_packs_hold_spirv_and_d3d12_features_are_checked(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-") as temporary:
            root = pathlib.Path(temporary)
            spirv = {
                "stage": "vertex",
                "guest_hash": "0000000000000010",
                "specialization_mask": "0000000000000000",
                **self.make_shader(root, "vertex.spv", b"\0" * 16, PACK.SPIRV_MAGIC),
            }
            data = PACK.serialize(
                PACK.load_manifest(
                    self.make_manifest(root, [spirv], backend="vulkan", device_features=0)
                )
            )
            self.assertEqual(PACK.verify_pack(data)["backend"], "vulkan")
            dxbc = {
                "stage": "vertex",
                "guest_hash": "0000000000000010",
                "specialization_mask": "0000000000000000",
                **self.make_shader(root, "vertex.dxbc", b"vertex"),
            }
            with self.assertRaisesRegex(PACK.PackError, "not a vulkan shader"):
                PACK.load_manifest(self.make_manifest(root, [dxbc], backend="vulkan"))
            with self.assertRaisesRegex(PACK.PackError, "unknown D3D12 bits"):
                PACK.load_manifest(self.make_manifest(root, [dxbc], device_features=2))
            with self.assertRaisesRegex(PACK.PackError, "d3d12 or vulkan"):
                PACK.load_manifest(self.make_manifest(root, [dxbc], backend="metal"))

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

    def test_public_format_is_runtime_capable_and_keeps_local_payload_boundary(self):
        document = (
            ROOT / "docs/native-renderer/SHADER_PACK_FORMAT.md"
        ).read_text(encoding="utf-8")
        self.assertIn("runtime renderer input", document)
        self.assertIn("texture and sampler binding metadata", document)
        self.assertIn("must remain under `.local`", document)
        self.assertIn("does not enable guest draw or resolve suppression", document)
        policy = json.loads(
            (ROOT / "config/repository-policy.json").read_text(encoding="utf-8")
        )
        self.assertIn(".dxil", policy["forbidden_extensions"])
        self.assertIn(".dxbc", policy["forbidden_extensions"])
        self.assertIn(".pnsp", policy["forbidden_extensions"])

    def test_runtime_pack_does_not_restore_the_removed_title_side_loader(self):
        source = (
            ROOT / "src/native_renderer/guest_output_renderer.cpp"
        ).read_text(encoding="utf-8")
        self.assertNotIn("pinyon_shift_native_shader_pack", source)
        self.assertNotIn("g_shader_pack", source)
        pipeline = (
            ROOT / "thirdparty/shiftglue-sdk/src/graphics/d3d12/pipeline_cache.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("fh1_shader_pack_.Find", pipeline)
        self.assertIn("REXGPU_FH1_SHADER_PRODUCER", pipeline)
        self.assertIn("translation.RejectPrecompiledMiss()", pipeline)
        self.assertNotIn("Fh1RequirePrecompiledShaders", pipeline)
        shutdown = pipeline.split("void PipelineCache::Shutdown()", 1)[1].split(
            "void PipelineCache::InitializeShaderStorage", 1
        )[0]
        self.assertLess(
            shutdown.index("WriteFh1ShaderAnalysisCatalog"),
            shutdown.index("ShutdownShaderStorage()"),
        )
        self.assertLess(
            shutdown.index("WriteFh1ShaderAnalysisCatalog"),
            shutdown.index("shaders_.clear()"),
        )
        analysis = pipeline.split(
            "void PipelineCache::AnalyzeShaderUcode", 1
        )[1].split("PipelineCache::GetCurrentVertexShaderModification", 1)[0]
        self.assertIn("if (shader.is_ucode_analyzed())", analysis)
        self.assertIn("fh1_analysis_catalog_dirty_", analysis)
        end_submission = pipeline.split(
            "void PipelineCache::EndSubmission()", 1
        )[1].split("bool PipelineCache::IsCreatingPipelines", 1)[0]
        self.assertIn("WriteFh1ShaderAnalysisCatalog", end_submission)
        for shader_hash in (
            "C41DD15CBD361350",
            "CE81AE65F9C5A57B",
            "D60688109AC80358",
            "81EF4F2E5B5DDBD1",
            "A81FE6B4247E184B",
            "D445FABAE890A455",
        ):
            self.assertIn(shader_hash, pipeline)
        report = (ROOT / "tools/pinyon_crash.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("native_shader_pack =", report)
        package = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        self.assertIn("'tools/native-shader-pack.py'", package)
        self.assertIn("'.dxil', '.pnsp'", package)
        self.assertIn("'.dxil', '.pnsp'", report)

    def test_runtime_pack_loader(self):
        executable = next(
            (
                candidate
                for candidate in (
                    ROOT / f"out/build/{name}/pinyon_shift_fh1_shader_pack_tests.exe"
                    for name in ("win-amd64-release", "win-amd64-relwithdebinfo")
                )
                if candidate.is_file()
            ),
            None,
        )
        if sys.platform != "win32" or executable is None:
            self.skipTest("Build pinyon_shift_fh1_shader_pack_tests for the Windows loader check")
        bytecode = b"DXBCpixel"
        entry = PACK.ShaderEntry(
            PACK.ShaderIdentity(2, 1, 2), bytecode, hashlib.sha256(bytecode).digest(),
            ((7, 3, 1, 0),), ((5, 3, 0, 1, 2, 3),), 1 << 3,
        )
        geometry_bytecode = b"DXBCgeometry"
        geometry = PACK.ShaderEntry(
            PACK.ShaderIdentity(3, 0, 0x1234), geometry_bytecode,
            hashlib.sha256(geometry_bytecode).digest(), (), (), 0,
        )
        config = PACK.TranslationConfig(0x20260827, 1, 1, 0xD, 1, 1)
        with tempfile.TemporaryDirectory(prefix="pinyon-shader-pack-runtime-") as temporary:
            fixture = pathlib.Path(temporary) / "fixture.pnsp"
            fixture.write_bytes(PACK.serialize(PACK.PackInput(config, (entry, geometry))))
            result = subprocess.run(
                [str(executable), str(fixture)], capture_output=True, text=True, timeout=30
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
