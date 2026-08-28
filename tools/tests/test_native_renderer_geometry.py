import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_renderer_geometry",
    ROOT / "tools/build-native-geometry-contract.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def selection(**overrides):
    candidate = {
        "signature": "E184D75768958828",
        "primitive": 13,
        "indexed": False,
        "source_select": 2,
        "index_count_min": 3,
        "index_count_max": 3,
        "index_state": "format=0;endianness=2",
        "index_buffer_address": "E0180000",
        "index_buffer_length_min": 6,
        "vertex_index_range": "offset=0;min=0;max=16777215",
        "vertex_binding_count": 1,
        "vertex_fetches": "0:E0100000:120:10:2",
        "vertex_attribute_count": 2,
        "vertex_attributes": (
            "0:0:0:10:6:1:0:0:0:0:F:688:0;"
            "0:0:4:10:37:3:0:0:0:1:3:688:1"
        ),
    }
    candidate.update(overrides)
    return {"schema": MODULE.SELECTION_SCHEMA, "candidates": [candidate]}


def index_census(decoded_hash="0123456789ABCDEF"):
    return {
        "schema": MODULE.CENSUS_SCHEMA,
        "index_scans": [
            {
                "signature": "E184D75768958828",
                "status": "scanned",
                "index_count": "3",
                "bytes_read": "6",
                "index_buffer_address": "E0180000",
                "index_buffer_length": "6",
                "index_format": "0",
                "index_endianness": "2",
                "index_reset_enabled": "false",
                "index_reset": "0000FFFF",
                "decoded_minimum": "0",
                "decoded_maximum": "2",
                "effective_minimum": "0",
                "effective_maximum": "2",
                "non_reset_count": "3",
                "reset_count": "0",
                "decoded_hash": decoded_hash,
                "vertex_binding_size": "120",
            }
        ],
    }


class NativeRendererGeometryTests(unittest.TestCase):
    def test_decodes_every_pinned_xenos_vertex_format_word_shape(self):
        expected = {
            6: 0x1,
            7: 0x1,
            16: 0x1,
            17: 0x1,
            25: 0x1,
            26: 0x3,
            31: 0x1,
            32: 0x3,
            33: 0x1,
            34: 0x3,
            35: 0xF,
            36: 0x1,
            37: 0x3,
            38: 0xF,
            57: 0x7,
        }
        self.assertEqual(set(expected), set(MODULE.VERTEX_FORMATS))
        for data_format, word_mask in expected.items():
            self.assertEqual(
                word_mask,
                MODULE.needed_vertex_words(data_format, 0xF),
                data_format,
            )

    def test_builds_bounded_nonindexed_contract(self):
        result = MODULE.build(selection())

        self.assertEqual(MODULE.SCHEMA, result["schema"])
        self.assertEqual(0x00100000, result["binding"]["physical_address"])
        self.assertEqual(40, result["binding"]["stride_bytes"])
        self.assertEqual("8in32", result["binding"]["endianness_name"])
        self.assertEqual(2, result["bounds"]["maximum_vertex"])
        self.assertEqual(104, result["bounds"]["required_bytes"])
        self.assertEqual("8_8_8_8", result["attributes"][0]["format_name"])
        self.assertEqual("none", result["attributes"][0]["result_storage_target_name"])
        self.assertEqual("xyzw", result["attributes"][0]["result_write_components"])
        self.assertEqual("xyzw", result["attributes"][0]["result_swizzle"])
        self.assertEqual("xyzw", result["attributes"][0]["used_source_components"])
        self.assertTrue(result["attributes"][1]["mini_fetch"])
        self.assertEqual("uint16", result["index"]["format_name"])
        self.assertEqual("8in32", result["index"]["endianness_name"])
        self.assertTrue(result["bounds"]["validated"])
        self.assertFalse(result["safety"]["guest_payload_read"])
        self.assertFalse(result["safety"]["native_draw"])
        self.assertFalse(result["safety"]["suppression_allowed"])
        self.assertTrue(result["safety"]["xenos_authority"])

    def test_rejects_undersized_vertex_fetch(self):
        with self.assertRaisesRegex(ValueError, "needs 104 bytes, has 100"):
            MODULE.build(selection(vertex_fetches="0:E0100000:100:10:2"))

    def test_rejects_attribute_past_stride(self):
        document = selection(
            vertex_attribute_count=1,
            vertex_attributes="0:0:10:10:6:1:0:0:0:0:F:688:0",
        )
        with self.assertRaisesRegex(ValueError, "beyond its binding stride"):
            MODULE.build(document)

    def test_rejects_vertex_index_wrap(self):
        document = selection(vertex_index_range="offset=16777215;min=0;max=16777215")
        with self.assertRaisesRegex(ValueError, "24-bit vertex index wrap"):
            MODULE.build(document)

    def test_rejects_unknown_vertex_format(self):
        document = selection(
            vertex_attribute_count=1,
            vertex_attributes="0:0:0:10:63:F:0:0:0:0:F:688:0",
        )
        with self.assertRaisesRegex(ValueError, "unsupported Xenos vertex format 63"):
            MODULE.build(document)

    def test_rejects_inconsistent_fetch_word_mask(self):
        document = selection(
            vertex_attribute_count=1,
            vertex_attributes="0:0:0:10:6:F:0:0:0:0:F:688:0",
        )
        with self.assertRaisesRegex(ValueError, "fetch word mask disagrees"):
            MODULE.build(document)

    def test_indexed_candidate_requires_future_payload_scan(self):
        document = deepcopy(selection())
        document["candidates"][0]["indexed"] = True
        result = MODULE.build(document)
        self.assertEqual("requires_index_scan", result["bounds"]["status"])
        self.assertFalse(result["bounds"]["validated"])
        self.assertEqual(0x00180000, result["index"]["buffer"]["physical_address"])
        self.assertEqual(6, result["index"]["buffer"]["required_bytes_before_scan"])
        self.assertFalse(result["safety"]["guest_payload_read"])

    def test_rejects_undersized_index_fetch_before_scan(self):
        document = deepcopy(selection(index_buffer_length_min=5))
        document["candidates"][0]["indexed"] = True
        with self.assertRaisesRegex(ValueError, "index fetch needs 6 bytes, has 5"):
            MODULE.build(document)

    def test_validates_repeatable_bounded_index_scan(self):
        document = deepcopy(selection())
        document["candidates"][0]["indexed"] = True

        result = MODULE.build(document, index_censuses=[index_census(), index_census()])

        self.assertEqual("bounded_index_scan", result["bounds"]["status"])
        self.assertTrue(result["bounds"]["validated"])
        self.assertEqual(2, result["bounds"]["scan_captures"])
        self.assertEqual(104, result["bounds"]["required_vertex_bytes"])
        self.assertTrue(result["safety"]["guest_payload_read"])
        self.assertEqual("bounded_index_only", result["safety"]["guest_payload_scope"])
        self.assertFalse(result["safety"]["native_draw"])

    def test_rejects_index_payload_drift(self):
        document = deepcopy(selection())
        document["candidates"][0]["indexed"] = True
        with self.assertRaisesRegex(ValueError, "changed across captures"):
            MODULE.build(
                document,
                index_censuses=[index_census(), index_census("FEDCBA9876543210")],
            )


if __name__ == "__main__":
    unittest.main()
