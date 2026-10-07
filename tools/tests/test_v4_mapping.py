import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V4MAP = load("v4map", "tools/map-fh1-v4-addresses.py")
PORT = load("v4port", "tools/port-fh1-v4-analysis.py")
LOAD = 0x82000000
CODE = 0x1000
BLR, BCTR, MTCTR_R11, NOP = 0x4E800020, 0x4E800420, 0x7D6903A6, 0x60000000


def bl(pc, target, link=True):
    return 0x48000000 | ((target - pc) & 0x03FFFFFC) | (1 if link else 0)


def lis(rd, imm):
    return (15 << 26) | (rd << 21) | (imm & 0xFFFF)


def addi(rd, ra, imm):
    return (14 << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def lwz(rd, ra, displacement):
    return (32 << 26) | (rd << 21) | (ra << 16) | (displacement & 0xFFFF)


class Builder:
    """A minimal PE image: a .pdata table and big-endian code words."""

    def __init__(self, size=0x8000):
        self.data = bytearray(size)
        self.functions = []
        struct.pack_into("<I", self.data, 0x3C, 0x80)

    def put(self, address, words):
        struct.pack_into(f">{len(words)}I", self.data, address - LOAD, *words)

    def function(self, address, words):
        self.put(address, words)
        self.functions.append((address, len(words) * 4))

    def image(self):
        pdata = 0x400
        for i, (address, size) in enumerate(self.functions):
            struct.pack_into(">II", self.data, pdata + i * 8, address, (size // 4) << 8)
        struct.pack_into("<II", self.data, 0x80 + 24 + 120, pdata, len(self.functions) * 8)
        return V4MAP.Image(bytes(self.data), LOAD)


def body(n, seed):
    return [addi(3, 3, seed + i) for i in range(n)]


class MappingTests(unittest.TestCase):
    def test_normalize_masks_branch_and_address_immediates(self):
        words = [bl(LOAD + 0x1000, LOAD + 0x2000), lis(11, 0x8300), addi(11, 11, 0x1234), lwz(3, 4, 8)]
        normalized = V4MAP.normalize(words)
        self.assertEqual(normalized[0], 0x48000001)
        self.assertEqual(normalized[1] & 0xFFFF, 0)
        self.assertEqual(normalized[2] & 0xFFFF, 0)
        self.assertEqual(normalized[3], words[3])  # unrelated register keeps its displacement

    def test_shape_masks_displacements(self):
        self.assertEqual(V4MAP.shape([lwz(3, 4, 0x3B70)]), V4MAP.shape([lwz(3, 4, 0x3B80)]))
        self.assertNotEqual(V4MAP.shape([lwz(3, 4, 0)]), V4MAP.shape([lwz(5, 4, 0)]))

    def test_exact_anchored_and_aligned_mapping(self):
        f, g = LOAD + CODE, LOAD + CODE + 0x400
        base, v4 = Builder(), Builder()
        shift = 0x100
        caller = [NOP, NOP, bl(f + 8, g)] + body(12, 0x100) + [BLR]
        callee = body(16, 0x200) + [BLR]
        base.function(f, caller)
        base.function(g, callee)
        v4_caller = [NOP, NOP, bl(f + shift + 8, g + shift)] + body(12, 0x100) + [BLR]
        v4_callee = body(4, 0x300) + body(16, 0x200) + [BLR]  # code inserted at the start
        v4.function(f + shift, v4_caller)
        v4.function(g + shift, v4_callee)
        mapper = V4MAP.Mapper(base.image(), v4.image())
        self.assertEqual(mapper.map(f + 12)[0], f + shift + 12)
        self.assertEqual(mapper.map(f + 12)[1], "exact")
        self.assertIn(g, mapper.anchored)
        mapped, method = mapper.map(g + 20)
        self.assertEqual((mapped, method), (g + shift + 16 + 20, "aligned"))

    def test_branch_consistency_rejects_a_shifted_thunk(self):
        f = LOAD + CODE
        base, v4 = Builder(), Builder()
        target_a, target_b = LOAD + CODE + 0x200, LOAD + CODE + 0x300
        base.function(target_a, body(8, 0x10) + [BLR])
        base.function(target_b, body(8, 0x20) + [BLR])
        v4.function(target_a, body(8, 0x10) + [BLR])
        v4.function(target_b, body(8, 0x20) + [BLR])
        base.put(f, [addi(3, 3, -4), bl(f + 4, target_a, link=False)])
        v4.put(f, [addi(3, 3, -4), bl(f + 4, target_b, link=False)])
        v4.put(f + 8, [addi(3, 3, -4), bl(f + 12, target_a, link=False)])
        mapper = V4MAP.Mapper(base.image(), v4.image())
        self.assertFalse(mapper.branches_consistent(f, f, 2))
        self.assertTrue(mapper.branches_consistent(f, f + 8, 2))

    def test_vcall_thunks_are_found_outside_pdata(self):
        builder = Builder()
        thunk = LOAD + CODE + 0x800
        builder.put(thunk, [0x81630000, lwz(11, 11, 0x40), MTCTR_R11, BCTR])
        user = LOAD + CODE
        builder.function(user, [lis(4, thunk >> 16), addi(4, 4, thunk & 0xFFFF), BLR])
        self.assertEqual(V4MAP.vcall_thunks(builder.image()), {thunk: 16})

    def test_reference_at_forms_the_lis_addi_address(self):
        builder = Builder()
        user = LOAD + CODE
        builder.function(user, [lis(4, 0x8301), NOP, addi(4, 4, 0x8000 + 0x10), BLR])
        image = builder.image()
        self.assertEqual(V4MAP.reference_at(image, user + 8), (0x83010000 - 0x8000 + 0x10) & 0xFFFFFFFF)
        self.assertIsNone(V4MAP.reference_at(image, user + 12))


class PortTests(unittest.TestCase):
    def test_port_rewrites_addresses_and_marks_unmapped_entries(self):
        f, g = LOAD + CODE, LOAD + CODE + 0x400
        shift = 0x100
        base, v4 = Builder(), Builder()
        base.function(f, body(20, 0x100) + [BLR])
        base.function(g, body(20, 0x500) + [BLR])
        v4.function(f + shift, body(20, 0x100) + [BLR])
        v4.function(g + shift, body(20, 0x900) + [BLR])  # unrelated in v4
        mapper = V4MAP.Mapper(base.image(), v4.image())
        source = (
            "includes = [\"other.toml\"]\n"
            f"setjmp_address = 0x{f + 8:08X}\n\n"
            "# kept comment\n"
            "[[midasm_hook]]\n"
            f"address = 0x{f + 16:08X}\n"
            "name = \"Hook\"\n\n"
            "[[midasm_hook]]\n"
            f"address = 0x{g + 16:08X}\n"
            "name = \"Lost\"\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "main-xex.toml"
            path.write_text(source, encoding="utf-8")
            report = {"methods": {}, "unmapped": [], "rejected": []}
            text = PORT.port_file(path, mapper, {}, report)
        self.assertIn(f"setjmp_address = 0x{f + shift + 8:08X}", text)
        self.assertIn(f"address = 0x{f + shift + 16:08X}", text)
        self.assertIn("# kept comment", text)
        self.assertIn(f"# UNMAPPED address = 0x{g + 16:08X}", text)
        self.assertIn("# UNMAPPED name = \"Lost\"", text)
        self.assertEqual([u["address"] for u in report["unmapped"]], [f"{g + 16:08X}"])

    def test_overrides_take_precedence(self):
        f = LOAD + CODE
        base, v4 = Builder(), Builder()
        base.function(f, body(10, 0x100) + [BLR])
        v4.function(f, body(10, 0x100) + [BLR])
        mapper = V4MAP.Mapper(base.image(), v4.image())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "x.toml"
            path.write_text(f"[[midasm_hook]]\naddress = 0x{f + 4:08X}\nname = \"H\"\n", encoding="utf-8")
            report = {"methods": {}, "unmapped": [], "rejected": []}
            text = PORT.port_file(path, mapper, {f + 4: 0x83000000}, report)
        self.assertIn("address = 0x83000000", text)
        self.assertEqual(report["methods"].get("override"), 1)


if __name__ == "__main__":
    unittest.main()
