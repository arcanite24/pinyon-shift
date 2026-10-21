"""Exercise the real ExternalProject boundary without fetching or compiling AMD code."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CMAKE = shutil.which("cmake")
NINJA = shutil.which("ninja")


@unittest.skipUnless(CMAKE and NINJA, "CMake and Ninja are required")
class FidelityFxToolchainTests(unittest.TestCase):
    def test_clean_and_update_configures_inherit_the_parent_toolchain(self):
        with tempfile.TemporaryDirectory(prefix="ffx toolchain ") as temp:
            root = Path(temp)
            sdk = root / "sdk"
            (sdk / "cmake").mkdir(parents=True)
            child = sdk / "thirdparty/fidelityfx-vk"
            child.mkdir(parents=True)
            shutil.copyfile(ROOT / "thirdparty/shiftglue-sdk/cmake/rexglue_helpers.cmake",
                            sdk / "cmake/rexglue_helpers.cmake")
            toolchain = root / "toolchain.cmake"
            toolchain.write_text('set(TEST_FROM_TOOLCHAIN "${TEST_SDK_ROOT}")\n')
            expected = {
                "CMAKE_TOOLCHAIN_FILE": toolchain.as_posix(),
                "CMAKE_SYSROOT": (root / "sysroot").as_posix(),
                "CMAKE_SYSROOT_COMPILE": (root / "compile sysroot").as_posix(),
                "CMAKE_SYSROOT_LINK": (root / "link sysroot").as_posix(),
                "CMAKE_C_COMPILER": (root / "bin/clang").as_posix(),
                "CMAKE_CXX_COMPILER": (root / "bin/clang++").as_posix(),
                "CMAKE_C_COMPILER_TARGET": "x86_64-linux-gnu",
                "CMAKE_CXX_COMPILER_TARGET": "x86_64-linux-gnu",
                "CMAKE_C_COMPILER_EXTERNAL_TOOLCHAIN": (root / "gcc").as_posix(),
                "CMAKE_CXX_COMPILER_EXTERNAL_TOOLCHAIN": (root / "gcc").as_posix(),
                "CMAKE_C_FLAGS": "-msse4.1 -DTEST_C=1",
                "CMAKE_CXX_FLAGS": "-msse4.1 -DTEST_CXX=1",
                "CMAKE_C_FLAGS_RELEASE": "-O2 -DNDEBUG",
                "CMAKE_CXX_FLAGS_RELEASE": "-O2 -DNDEBUG",
                "CMAKE_EXE_LINKER_FLAGS": '-fuse-ld=lld -L"path with spaces"',
                "CMAKE_SHARED_LINKER_FLAGS": "-fuse-ld=lld -static-libstdc++",
                "CMAKE_MODULE_LINKER_FLAGS": "-fuse-ld=lld",
                "CMAKE_EXE_LINKER_FLAGS_RELEASE": "-Wl,--as-needed",
                "CMAKE_SHARED_LINKER_FLAGS_RELEASE": "-Wl,--as-needed",
                "CMAKE_MODULE_LINKER_FLAGS_RELEASE": "-Wl,--as-needed",
                "CMAKE_OSX_ARCHITECTURES": "arm64;x86_64",
                "CMAKE_TRY_COMPILE_PLATFORM_VARIABLES": "TEST_SDK_ROOT;TEST_OTHER",
                "TEST_SDK_ROOT": (root / "custom sdk").as_posix(),
                "TEST_OTHER": "first;second with spaces",
            }
            names = [*expected, "TEST_FROM_TOOLCHAIN"]
            contents = "\n".join(f"{name}=${{{name}}}" for name in names)
            (child / "CMakeLists.txt").write_text(
                'cmake_minimum_required(VERSION 3.25)\nproject(child NONE)\n'
                f'file(WRITE "${{CMAKE_BINARY_DIR}}/received.txt" "{contents}")\n')
            (root / "CMakeLists.txt").write_text(
                'cmake_minimum_required(VERSION 3.25)\nproject(parent NONE)\n'
                'set(WIN32 FALSE)\nset(APPLE FALSE)\nset(ANDROID FALSE)\n'
                'set(REXGLUE_USE_VULKAN ON)\nset(REXGLUE_FFX_API_INCLUDE_DIR unused)\n'
                'include("${CMAKE_SOURCE_DIR}/sdk/cmake/rexglue_helpers.cmake")\n'
                'add_executable(probe IMPORTED)\n'
                'set_target_properties(probe PROPERTIES IMPORTED_LOCATION "${CMAKE_BINARY_DIR}/probe")\n'
                '_rexglue_stage_fidelityfx_runtime(probe)\n'
                'ExternalProject_Add_StepTargets(rexglue_fidelityfx_runtime configure)\n')
            for updating in (False, True):
                if updating:
                    expected["CMAKE_C_FLAGS"] = "-march=x86-64-v3"
                    expected["CMAKE_SHARED_LINKER_FLAGS"] = ""
                    expected["TEST_SDK_ROOT"] += " updated"
                configure = [CMAKE, "-S", str(root), "-B", str(root / "build"), "-G", "Ninja",
                             f"-DCMAKE_MAKE_PROGRAM={NINJA}"]
                configure += [f"-D{name}:STRING={value}" for name, value in expected.items()]
                for command in (configure, [CMAKE, "--build", str(root / "build"), "--target",
                                            "rexglue_fidelityfx_runtime-configure"]):
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                received = dict(line.split("=", 1) for line in
                                (root / "build/fidelityfx-vk/received.txt").read_text().splitlines())
                self.assertEqual(received, {**expected, "TEST_FROM_TOOLCHAIN": expected["TEST_SDK_ROOT"]})
