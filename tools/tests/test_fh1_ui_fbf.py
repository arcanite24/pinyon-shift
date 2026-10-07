import importlib.util
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location(
    "fbf", Path(__file__).parents[1] / "fh1-ui-fbf.py")
fbf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fbf)


def word(value):
    return struct.pack(">I", value)


class FbfTests(unittest.TestCase):
    def test_pause_clone_native_name_matches_new_wrapper(self):
        row = lambda identity, name: word(0) + word(identity) + word(len(name)) + name
        source = word(1008) + word(2) + row(19, b'Button0') + row(764, b'Button0') + bytes(12)
        output = fbf.name_pause_clone(source, 764)
        self.assertEqual(len(output), len(source))
        self.assertEqual([(r['identity'], r['name']) for r in fbf.parse(output)['records']],
                         [(19, 'Button0'), (764, 'Button7')])
        self.assertEqual(sum(a != b for a, b in zip(source, output)), 1)
        with self.assertRaisesRegex(fbf.FbfError, 'unique Button7'):
            fbf.name_pause_clone(output, 764)
        with self.assertRaisesRegex(fbf.FbfError, 'unique Button7'):
            fbf.name_pause_clone(source, 999)

    def test_pause_clone_uses_authored_spacing_without_moving_existing_rows(self):
        header = b'\x01\x04\0\0' + word(24) + b'FGBkranA' + word(2) + bytes(12)
        def graph(count):
            nodes = []
            for index in range(count):
                node = bytearray(word(0xFFFFFFFF if index == 0 else 0)
                                 + word(index + 1) + bytes(88))
                struct.pack_into('>f', node, 16, -(index - 1) * 53 if index else 0)
                nodes.append(bytes(node))
            return header + word(8) + word(count) + word(0) + word(count * 96) + b''.join(nodes) + word(0)
        source, clone = graph(8), bytearray(graph(9))
        # The copied first-row root initially overlaps the first row at Y=0.
        struct.pack_into('>f', clone, 48 + 8 * 96 + 16, 0)
        clone = bytes(clone)
        output = fbf.position_pause_clone(source, clone, list(range(2, 9)), 9)
        last = fbf.parse_bsg(output)['nodes'][-1]['start']
        self.assertEqual(struct.unpack_from('>f', output, last + 16)[0], -371)
        self.assertEqual(output[:last + 16], clone[:last + 16])
        self.assertEqual(output[last + 20:], clone[last + 20:])
        with self.assertRaisesRegex(fbf.FbfError, 'aliases'):
            fbf.position_pause_clone(source, clone, list(range(2, 9)), 8)
        broken = bytearray(source)
        struct.pack_into('>f', broken, 48 + 3 * 96 + 16, -107)
        with self.assertRaisesRegex(fbf.FbfError, 'regular layout'):
            fbf.position_pause_clone(bytes(broken), clone, list(range(2, 9)), 9)

    def test_material_id_is_independent_of_string_table_indexes(self):
        record = word(5) + word(28) + word(8) + b"Material" + bytes(104)
        data = word(1008) + word(1) + record + bytes(12)
        parsed = fbf.parse(data)
        self.assertEqual(parsed["records"][0]["identity"], 28)
        self.assertEqual(data[parsed["records"][0]["start"]:parsed["records"][0]["end"]], record)
        items = [SimpleNamespace(kind=5, value=28),
                 SimpleNamespace(kind=5, value=1015),
                 SimpleNamespace(kind=8, value=0)]
        self.assertEqual(fbf.missing_objects(items, parsed["records"]),
                         [dict(item=1, kind=5, native_object_id=1015)])

    def test_rejects_duplicate_ids_and_truncated_payload(self):
        record = word(2) + word(9) + word(0) + bytes(64)
        with self.assertRaisesRegex(fbf.FbfError, "duplicate"):
            fbf.parse(word(1008) + word(2) + record * 2 + bytes(12))
        with self.assertRaisesRegex(fbf.FbfError, "truncated"):
            fbf.parse(word(1008) + word(1) + record[:-1])

    def test_consumes_geometry_and_gpu_tail_exactly(self):
        data = word(1008) + word(0) + word(1) + word(3) + word(4) + bytes(103)
        self.assertEqual(fbf.parse(data)["geometry_objects"], 1)
        with self.assertRaisesRegex(fbf.FbfError, "unconsumed"):
            fbf.parse(data + b"x")
        with self.assertRaisesRegex(fbf.FbfError, "truncated"):
            fbf.parse(data[:-1])

    def test_bsg_parent_indexes_and_separate_pool(self):
        header = b"\x01\x04\0\0" + word(24) + b"FGBkranA" + word(2) + bytes(12)
        root = word(0xFFFFFFFF) + word(1) + bytes(88)
        child = word(0) + word(19) + bytes(88)
        data = header + word(8) + word(2) + word(1) + word(192)
        data += root + child + word(5) + word(28) + b'\x06'
        parsed = fbf.parse_bsg(data)
        self.assertEqual(parsed["nodes"][1]["parent"], 0)
        self.assertEqual(parsed["pool_records"], 1)
        broken = bytearray(data)
        struct.pack_into(">I", broken, 144, 1)
        with self.assertRaisesRegex(fbf.FbfError, "unavailable parent"):
            fbf.parse_bsg(bytes(broken))
        with self.assertRaisesRegex(fbf.FbfError, "file length"):
            fbf.parse_bsg(data[:-1])

    def test_clone_has_independent_material_texture_and_scene_owners(self):
        def record(kind, identity, payload):
            return word(kind) + word(identity) + word(0) + payload
        material = bytes(68) + word(23) + bytes(32)
        texture = word(28) + word(0) + bytes(116)
        source = word(1008) + word(5)
        source += record(0, 1, b'') + record(0, 19, b'')
        source += record(4, 23, bytes(8)) + record(5, 28, material)
        source += record(7, 29, texture) + bytes(12)
        header = b"\x01\x04\0\0" + word(24) + b"FGBkranA" + word(2) + bytes(12)
        node = lambda parent, identity: word(parent) + word(identity) + bytes(88)
        graph = header + word(8) + word(3) + word(2) + word(288)
        graph += node(0xFFFFFFFF, 1) + node(0, 19) + node(1, 23)
        graph += word(10) + word(28) + b'\x06' + word(29) + b'\x07'
        native, scene, mapping = fbf.clone_objects(source, graph, [19, 23, 28, 29])
        self.assertEqual(mapping, {19: 30, 23: 31, 28: 32, 29: 33})
        parsed = fbf.parse(native)
        self.assertEqual(len(parsed['records']), 9)
        self.assertEqual(native[8:fbf.parse(source)['tail']], source[8:-12])
        self.assertEqual(native[-12:], source[-12:])
        copies = {r['identity']: r for r in parsed['records']}
        self.assertEqual(struct.unpack_from('>I', native, copies[32]['body'] + 68)[0], 31)
        self.assertEqual(struct.unpack_from('>I', native, copies[33]['body'])[0], 32)
        nodes = fbf.parse_bsg(scene)['nodes']
        self.assertEqual([(n['parent'], n['identity']) for n in nodes[-2:]], [(0, 30), (3, 31)])
        with self.assertRaisesRegex(fbf.FbfError, 'external mutable owner'):
            fbf.clone_objects(source, graph, [28, 29])


if __name__ == "__main__":
    unittest.main()
