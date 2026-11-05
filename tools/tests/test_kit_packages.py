"""The ShiftGlue kit's own CMake packages win over a sysroot's (#1001)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "cmake/PinyonShiftKitPackages.cmake"


def cmake() -> str | None:
    pinned = sorted((ROOT / ".local/toolchain").glob("cmake-*/bin/cmake*"))
    return str(pinned[0]) if pinned else shutil.which("cmake")


class KitPackageTests(unittest.TestCase):
    def test_kit_packages_are_pinned_before_rexglue_is_found(self):
        rexglue = (ROOT / "cmake/PinyonShiftRexGlue.cmake").read_text(encoding="utf-8")
        pin = rexglue.index('pinyon_shift_use_kit_packages("${PINYON_SHIFT_SHIFTGLUE_KIT}")')
        self.assertLess(pin, rexglue.index("find_package(rexglue CONFIG REQUIRED"))

    @unittest.skipUnless(cmake(), "needs CMake")
    def test_every_kit_package_dir_is_set(self):
        with tempfile.TemporaryDirectory() as folder:
            kit = Path(folder) / "kit"
            for config in ("lib/cmake/SDL3/SDL3Config.cmake",
                           "lib/cmake/SDL3/SDL3ConfigVersion.cmake",
                           "lib/cmake/fmt/fmt-config.cmake",
                           "share/cmake/VulkanHeaders/VulkanHeadersConfig.cmake"):
                (kit / config).parent.mkdir(parents=True, exist_ok=True)
                (kit / config).write_text("", encoding="utf-8")
            script = Path(folder) / "probe.cmake"
            script.write_text(
                f'include("{MODULE.as_posix()}")\n'
                # A configure that once found the sysroot's copy cached it.
                'set(SDL3_DIR "/sysroot/usr/lib/cmake/SDL3" CACHE PATH "")\n'
                f'pinyon_shift_use_kit_packages("{kit.as_posix()}")\n'
                'foreach(name SDL3 SDL3ConfigVersion fmt VulkanHeaders)\n'
                '  message("${name}=${${name}_DIR}")\n'
                'endforeach()\n', encoding="utf-8")
            result = subprocess.run([cmake(), "-P", str(script)], capture_output=True,
                                    text=True, check=True)
        lines = dict(line.split("=", 1) for line in result.stderr.splitlines() if "=" in line)
        self.assertEqual(lines["SDL3"], f"{kit.as_posix()}/lib/cmake/SDL3")
        self.assertEqual(lines["fmt"], f"{kit.as_posix()}/lib/cmake/fmt")
        self.assertEqual(lines["VulkanHeaders"], f"{kit.as_posix()}/share/cmake/VulkanHeaders")
        self.assertEqual(lines["SDL3ConfigVersion"], "")


if __name__ == "__main__":
    unittest.main()
