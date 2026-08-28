import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererResourceIdentityContractTests(unittest.TestCase):
    def test_preview_compiles_resource_identity(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertEqual(cmake.count("src/native_renderer/resource_identity.cpp"), 3)
        self.assertIn("pinyon_shift_resource_identity_tests EXCLUDE_FROM_ALL", cmake)

    def test_physical_identity_is_canonical_and_generation_aware(self):
        header = (
            ROOT / "src/native_renderer/resource_identity.h"
        ).read_text(encoding="utf-8")
        source = (
            ROOT / "src/native_renderer/resource_identity.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("kGuestPhysicalAddressMask = 0x1FFFFFFF", header)
        self.assertIn("graphics_address & kGuestPhysicalAddressMask", header)
        self.assertIn("CanonicalPhysicalAddress(graphics_address)", source)
        self.assertIn("BufferResourceKey", header)
        self.assertIn("TextureResourceKey", header)
        self.assertIn("ResourceFingerprint content", header)

    def test_invalidation_marks_overlap_without_owning_destruction(self):
        header = (
            ROOT / "src/native_renderer/resource_identity.h"
        ).read_text(encoding="utf-8")
        source = (
            ROOT / "src/native_renderer/resource_identity.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("std::vector<ResourceInvalidation> Invalidate", header)
        self.assertIn("range.Overlaps(written_range)", source)
        self.assertNotIn("delete ", source)
        self.assertNotIn("Release()", source)


if __name__ == "__main__":
    unittest.main()
