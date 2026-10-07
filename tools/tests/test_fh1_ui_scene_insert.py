import importlib.util
from pathlib import Path
import struct
import sys
import unittest

spec = importlib.util.spec_from_file_location(
    'scene_insert', Path(__file__).parents[1] / 'fh1-ui-scene-insert.py')
scene = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scene
spec.loader.exec_module(scene)


class CompanionRelocationTests(unittest.TestCase):
    def test_clone_animation_references_owned_styles_and_track_keys(self):
        word = lambda value: struct.pack('>I', value)
        section = lambda body: word(len(body)) + body
        style = lambda owner: word(owner) + bytes(8)
        track = lambda owner: (word(owner) + word(1) + word(123) + word(1)
                               + word(owner) * 2 + word(456) + word(0x10000000) + word(7))
        # Both domains use source index zero, but grow to different indexes.
        # References to the other row stay in the original tables.
        entries = b''.join(struct.pack('>BBH', *entry) for entry in
                           ((0, 1, 0), (1, 0, 0), (0, 0, 1), (1, 1, 1)))
        animation = bytes(16) + word(3) + bytes(9) + word(1)
        animation += word(3) + bytes(1) + word(0) + word(4) + entries
        header = bytearray(0x88)
        scene.put_u32be(header, scene.STYLE_COUNT_OFFSET, 3)
        scene.put_u32be(header, scene.TRACK_COUNT_OFFSET, 2)
        scene.put_u32be(header, scene.ANIMATION_COUNT_OFFSET, 1)
        data = bytes(header) + section(style(3) + style(9) * 2)
        data += section(track(3) + track(9)) + word(0) + section(animation)
        encoded, counts = scene.clone_companion_sections(data, len(header), {3: 12})
        cloned_track = word(12) + track(3)[4:16] + word(12) * 2 + track(3)[24:]
        cloned_entries = b''.join(struct.pack('>BBH', *entry) for entry in
                                  ((0, 1, 3), (1, 0, 2), (0, 0, 1), (1, 1, 1)))
        cloned_animation = animation[:16] + word(12) + animation[20:33]
        cloned_animation += word(12) + animation[37:46] + cloned_entries
        expected = section(style(3) + style(9) * 2 + style(12))
        expected += section(track(3) + track(9) + cloned_track) + word(0)
        expected += section(animation + cloned_animation)
        self.assertEqual(encoded, expected)
        self.assertEqual(counts['animation_events'], 4)

    def test_clone_rejects_animation_reference_overflow(self):
        word = lambda value: struct.pack('>I', value)
        section = lambda body: word(len(body)) + body
        header = bytearray(0x88)
        scene.put_u32be(header, scene.STYLE_COUNT_OFFSET, 0x4000)
        scene.put_u32be(header, scene.ANIMATION_COUNT_OFFSET, 1)
        styles = word(3) + bytes(8) + (word(9) + bytes(8)) * 0x3fff
        animation = bytes(16) + word(3) + bytes(9) + word(1)
        animation += word(3) + bytes(1) + word(0) + word(1) + bytes(4)
        data = bytes(header) + section(styles) + word(0) * 2 + section(animation)
        with self.assertRaisesRegex(scene.SceneInsertError, '14-bit index'):
            scene.clone_companion_sections(data, len(header), {3: 12})

    def test_clone_grows_native_binding_table_without_lowering_existing_ceiling(self):
        word = lambda value: struct.pack('>I', value)
        section = lambda body: word(len(body)) + body
        header = bytearray(0x88)
        header[:14] = b'\x01\x04\0\0\0\x1aAnarkBGF'
        strings = [section(b'x') for _ in range(524)]
        scene.put_u32be(header, scene.IDENTITY_COUNT_OFFSET, len(strings))
        items = []
        for row, name in enumerate(scene.PAUSE_ROW_NAMES):
            items.append(struct.pack('>IIIBB', name, 0xFFFFFFFF, 19, 7, 4)
                         + bytes(5) + word(0))
            properties = b''.join(word(1) + word(20 + row * 72 + i)
                                  for i in range(72))
            items.append(struct.pack('>IIIBB', scene.PAUSE_ROW_CONTRACT,
                                     row * 2, 0, 8, 0) + word(72) + properties)
        items.append(struct.pack('>IIIBB', 0, 0xFFFFFFFF, 0, 0, 0) + word(0))
        for offset, value in ((0x24, 8), (0x28, 7), (0x2C, 504),
                              (0x70, 8), (0x74, 7), (0x78, 504),
                              (0x30, 7), (0x34, 7), (0x7C, 7), (0x80, 7)):
            scene.put_u32be(header, offset, value)
        relations = b''.join(word(row * 2) + word(1) + word(0)
                             for row in range(7))
        for ceiling in (763, 900):
            scene.put_u32be(header, scene.NATIVE_OBJECT_CEILING_OFFSET, ceiling)
            source = bytes(header) + section(b''.join(strings))
            source += section(b''.join(items)) + section(relations) + word(0) * 4
            output, _ = scene.encode_subtree(source, 0, {19: 799})
            self.assertEqual(scene.u32be(output, scene.NATIVE_OBJECT_CEILING_OFFSET),
                             max(ceiling, 799))
            self.assertEqual(scene.u32be(source, scene.NATIVE_OBJECT_CEILING_OFFSET),
                             ceiling)

    def test_insert_relocates_existing_owners_and_preserves_source_for_clone(self):
        word = lambda value: struct.pack('>I', value)
        section = lambda body: word(len(body)) + body
        style = lambda owner: word(owner) + bytes(8)
        track = word(9) + word(1) + word(123) + word(1)
        track += word(3) + word(9) + bytes(12)
        animation = bytes(16) + word(9) + bytes(9) + word(1)
        animation += word(9) + bytes(1) + word(0) + word(0)
        header = bytearray(0x88)
        scene.put_u32be(header, scene.STYLE_COUNT_OFFSET, 2)
        scene.put_u32be(header, scene.TRACK_COUNT_OFFSET, 1)
        scene.put_u32be(header, scene.ANIMATION_COUNT_OFFSET, 1)
        data = bytes(header) + section(style(3) + style(9))
        data += section(track) + section(b'') + section(animation)
        encoded, counts = scene.clone_companion_sections(
            data, len(header), {3: 12}, {9: 15})
        moved_track = word(15) + track[4:20] + word(15) + track[24:]
        moved_animation = animation[:16] + word(15) + animation[20:33]
        moved_animation += word(15) + animation[37:]
        expected = section(style(3) + style(15) + style(12))
        expected += section(moved_track) + section(b'') + section(moved_animation)
        self.assertEqual(encoded, expected)
        self.assertEqual(counts['styles'], 1)
        self.assertEqual(counts['tracks'], 0)
        self.assertEqual(counts['animations'], 0)

    def test_clone_remaps_string_keys_without_changing_numeric_literals(self):
        word = lambda value: struct.pack('>I', value)
        section = lambda body: word(len(body)) + body
        # Both key values equal a copied identity index; only type 20 is a
        # string lookup. Numeric animation and track values must stay literal.
        track = word(3) + word(1) + word(123) + word(2)
        track += word(3) + word(3) + word(456) + word(0xA0000000) + word(3)
        track += word(3) + word(3) + word(456) + word(0x10000000) + word(3)
        animation = bytes(16) + word(3) + bytes(9) + word(1)
        animation += word(3) + bytes(1) + word(2)
        animation += word(0xE0000000) + word(3) + word(0x10000000) + word(3)
        animation += word(0)
        header = bytearray(0x88)
        scene.put_u32be(header, scene.TRACK_COUNT_OFFSET, 1)
        scene.put_u32be(header, scene.ANIMATION_COUNT_OFFSET, 1)
        data = bytes(header) + section(b'') + section(track)
        data += section(b'') + section(animation)
        encoded, counts = scene.clone_companion_sections(
            data, len(header), {3: 12}, identity_map={3: 1006})
        cloned_track = word(12) + track[4:16]
        cloned_track += word(12) + word(12) + word(456) + word(0xA0000000) + word(1006)
        cloned_track += word(12) + word(12) + word(456) + word(0x10000000) + word(3)
        cloned_animation = animation[:16] + word(12) + animation[20:33]
        cloned_animation += word(12) + animation[37:46] + word(1006) + animation[50:]
        expected = section(b'') + section(track + cloned_track)
        expected += section(b'') + section(animation + cloned_animation)
        self.assertEqual(encoded, expected)
        self.assertEqual(counts['tracks'], 1)
        self.assertEqual(counts['animations'], 1)


if __name__ == '__main__':
    unittest.main()
