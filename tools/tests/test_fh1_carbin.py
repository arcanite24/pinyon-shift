import importlib.util
import struct
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "fh1_carbin.py"
SPEC = importlib.util.spec_from_file_location("fh1_carbin", MODULE_PATH)
fc = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = fc
SPEC.loader.exec_module(fc)


def subsection(name: str, lod: int, indices: list[int]) -> "fc.Subsection":
    return fc.Subsection(b"\x00" * 5, (0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0), b"\x00" * 36,
                         name, lod, 6, b"\x00" * 56, (4, 0), 2, indices, b"\x00" * 4)


def section(name: str, vertices: list[tuple], bounds=None, damage_flag=1) -> "fc.Section":
    pool = fc.Pool(len(vertices), 28, 1, 0x1234, vertices)
    empty = fc.Pool(0, 28, 0, None, [])
    table = b"".join(struct.pack(">I", 0x00C00000 + i) for i in range(len(vertices)))
    damage = [(3, len(vertices), 4, 1, table, b"\x00\x00\x00\x07"), (3, 0, 0, 0, b"", b"")]
    if not damage_flag:
        damage = [(3, 0, 0, 0, b"", b""), (3, 0, 0, 0, b"", b"")]
    return fc.Section(bounds or (0.0, 0.5, 0.0, -1.0, -0.5, -2.0, 1.0, 0.5, 2.0), b"\x00" * 28,
                      struct.pack(">I", 0), b"\x00" * 4, struct.pack(">I", 0), b"\x00" * 12, name,
                      3, pool, b"\x00" * 4,
                      [subsection("paint", 1, [0, 1, 2, 0xFFFF, 2, 1, 0])], b"\x00" * 4, empty,
                      1, damage_flag, damage)


def vertex(x: int, y: int, z: int) -> tuple:
    # position, scale word, UV0, UV1, a unit quaternion and the lighting bytes
    return (x, y, z, 16000, 100, 200, 0, 0, -16384, 16384, 16384, 16384, 1, 2, 3, 4)


def model() -> "fc.Carbin":
    head = struct.pack(">I", 5) + b"\x00" * 60 + b"\x05abcde"  # unaligned count
    body = section("body", [vertex(-32767, -32767, -32767), vertex(32767, 0, 0),
                            vertex(0, 32767, 32767)])
    glass = section("glassF", [vertex(0, 0, 0), vertex(100, 200, 300), vertex(-5, -6, -7)],
                    damage_flag=0)
    empty = section("roof1", [], bounds=(0.0, 0.0, 0.0) + (fc.FLT_MAX,) * 3 + (-fc.FLT_MAX,) * 3,
                    damage_flag=0)
    empty.subsections = []
    return fc.Carbin(head, [empty, body, glass], struct.pack(">6I", 1, 0, 1, 0, 1, 0))


class CarbinTests(unittest.TestCase):
    def test_reads_and_writes_every_part(self):
        data = model().encode()
        carbin = fc.parse(data)
        self.assertEqual(["roof1", "body", "glassF"], [s.name for s in carbin.sections])
        body = carbin.sections[1]
        self.assertEqual(3, len(body.lod_pool.vertices))
        self.assertEqual(0x1234, body.lod_pool.section_id)
        self.assertEqual([0, 1, 2, 0xFFFF, 2, 1, 0], body.subsections[0].indices)
        self.assertEqual((3, 3, 4, 1), body.damage[0][:4])
        self.assertEqual(0, carbin.sections[2].damage_flag)
        self.assertEqual(data, carbin.encode())

    def test_positions_use_the_section_box(self):
        carbin = fc.parse(model().encode())
        body = carbin.sections[1]
        points = fc.positions(body, body.lod_pool)
        self.assertAlmostEqual(-1.0, points[0][0], places=4)
        self.assertAlmostEqual(0.0, points[0][1], places=4)   # offset 0.5, half-extent 0.5
        self.assertAlmostEqual(2.0, points[2][2], places=4)

    def test_moved_positions_move_the_box_offset(self):
        carbin = fc.parse(model().encode())
        body = carbin.sections[1]
        moved = [(x * 0.8 + 0.3, y, z - 0.5) for x, y, z in fc.positions(body, body.lod_pool)]
        fc.set_positions(body, {"lod": moved})
        self.assertAlmostEqual(0.3, body.bounds[0], places=5)
        self.assertAlmostEqual(1.0, body.bounds[6], places=5)   # half-extent kept
        for want, got in zip(moved, fc.positions(body, body.lod_pool)):
            for a, b in zip(want, got):
                self.assertAlmostEqual(a, b, delta=1e-4)
        again = fc.parse(carbin.encode())
        self.assertEqual(carbin.encode(), again.encode())
        # Everything but the position shorts is kept.
        self.assertEqual(vertex(0, 0, 0)[3:], body.lod_pool.vertices[0][3:])

    def test_positions_wider_than_the_box_are_refused(self):
        carbin = fc.parse(model().encode())
        body = carbin.sections[1]
        moved = [(x * 1.25, y, z) for x, y, z in fc.positions(body, body.lod_pool)]
        self.assertRaises(fc.CarbinError, fc.set_positions, body, {"lod": moved})

    def test_a_model_without_parts_is_kept_whole(self):
        data = struct.pack(">I", 5) + b"\x00" * 1200 + struct.pack(">6I", 1, 0, 1, 0, 1, 0)
        carbin = fc.parse(data)
        self.assertEqual([], carbin.sections)
        self.assertEqual(data, carbin.encode())

    def test_roundtrip_reports_a_damaged_file(self):
        data = bytearray(model().encode())
        data[-30:] = b""
        self.assertRaises(fc.CarbinError, fc.parse, bytes(data))


if __name__ == "__main__":
    unittest.main()
