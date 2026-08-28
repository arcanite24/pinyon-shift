import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "texture_provenance", ROOT / "tools" / "build-native-texture-provenance.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def capture(session="one", address="10000000", second_address="10004000"):
    signature = "FA45AAFDC22C8625"
    return {
        "schema": MODULE.CENSUS_SCHEMA,
        "session": session,
        "texture_scans": [{"signature": signature, "status": "scanned", "resources": "2"}],
        "texture_fingerprints": [
            {
                "signature": signature, "fetch_constant": "0",
                "base_address": address, "base_bytes": "16384",
                "base_hash": "1111111111111111", "mip_address": "00000000",
                "mip_bytes": "0", "mip_hash": "",
            },
            {
                "signature": signature, "fetch_constant": "2",
                "base_address": second_address, "base_bytes": "16384",
                "base_hash": "2222222222222222", "mip_address": "00000000",
                "mip_bytes": "0", "mip_hash": "",
            },
        ],
    }


class TextureProvenanceTests(unittest.TestCase):
    def test_accepts_stable_content_at_relocated_addresses(self):
        result = MODULE.build(
            [capture(), capture("two", "12000000", "12004000")],
            "FA45AAFDC22C8625",
        )
        self.assertTrue(result["qualification"]["content_stable_across_captures"])
        self.assertTrue(all(item["addresses_relocated_across_captures"] for item in result["resources"]))
        self.assertFalse(result["safety"]["native_draw"])

    def test_rejects_changed_content(self):
        second = capture("two")
        second["texture_fingerprints"][0]["base_hash"] = "3333333333333333"
        with self.assertRaisesRegex(ValueError, "content differs"):
            MODULE.build([capture(), second], "FA45AAFDC22C8625")

    def test_requires_two_captures(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            MODULE.build([capture()], "FA45AAFDC22C8625")

    def test_rejects_missing_successful_scan(self):
        second = capture("two")
        second["texture_scans"] = []
        with self.assertRaisesRegex(ValueError, "successful texture scan"):
            MODULE.build([capture(), second], "FA45AAFDC22C8625")


if __name__ == "__main__":
    unittest.main()
