import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fh1_aot_pipelines as aot  # noqa: E402


def corpus(directory: Path, programs: list[tuple[int, bytes]]) -> None:
    blob = bytearray(struct.pack("<4sII", b"FH1C", 1, len(programs)))
    for stage, code in programs:
        blob += struct.pack("<BBHI", stage, 0, 0, len(code)) + code
    directory.mkdir(parents=True)
    (directory / "corpus.blob").write_bytes(bytes(blob))


def description(vertex: int, pixel: int, state: int) -> bytes:
    return struct.pack("<QQQQ", vertex, 0, pixel, 0) + state.to_bytes(26, "little")


class RecipeTests(unittest.TestCase):
    def test_a_recipe_rebuilds_the_linked_program(self):
        base = bytes(range(48))
        linked = bytearray(base)
        linked[12:24] = aot.NOP
        linked[40] ^= 0x05
        edits = aot.recipe(bytes(linked), base)
        self.assertEqual(edits[0], [1])
        self.assertEqual(aot.apply(base, edits), bytes(linked))

    def test_states_are_shared_between_pairs_with_a_shader_in_common(self):
        a, b, c = description(1, 2, 7), description(1, 3, 8), description(4, 3, 9)
        expanded = set(aot.expand([a, b, c]))
        self.assertIn(description(1, 2, 8), expanded)
        self.assertIn(description(4, 3, 8), expanded)
        self.assertNotIn(description(1, 2, 9), expanded)

    def test_the_windows_layout_becomes_portable(self):
        with tempfile.TemporaryDirectory() as name:
            storage = Path(name)
            portable = description(1, 2, 0x1234)
            windows = portable[:42] + bytes(2) + portable[42:]
            (storage / "4D5309C9.fbo.vk.xpso").write_bytes(
                b"XEPS" + bytes(8) + bytes(8) + windows)
            self.assertEqual(aot.read_descriptions(storage), {portable})

    def test_generate_writes_only_pipelines_whose_shaders_the_disc_gives(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            vertex, pixel = bytes(range(24)), bytes(range(1, 25))
            corpus(root / "corpus", [(0, vertex), (1, pixel)])
            linked = aot.NOP + vertex[12:]
            catalog = {
                "schema": aot.SCHEMA,
                "description_version": f"{aot.DESCRIPTION_VERSION:08X}",
                "shaders": {
                    "0000000000000001": ["vertex", hashlib.sha256(vertex).hexdigest().upper(),
                                         aot.recipe(linked, vertex)],
                    "0000000000000002": ["pixel", hashlib.sha256(pixel).hexdigest().upper(), []],
                    "0000000000000003": ["pixel", "0" * 64, []],
                },
                "pipelines": [description(1, 2, 5).hex(), description(1, 3, 5).hex()],
            }
            (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
            result = aot.generate(root / "corpus", root / "catalog.json", root / "out.xpso", False)
            self.assertEqual(result["pipelines"], 1)
            data = (root / "out.xpso").read_bytes()
            self.assertEqual(struct.unpack_from("<4sIII", data), (b"XEAO", aot.DESCRIPTION_VERSION,
                                                                  2, 1))
            self.assertEqual(data[16 + 12 : 16 + 12 + 24], linked)
            self.assertEqual(data[-aot.PORTABLE:], description(1, 2, 5))


if __name__ == "__main__":
    unittest.main()
