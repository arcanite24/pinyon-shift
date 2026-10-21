"""Exercise the real consumer CMake graph with small, synthetic translations."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULES = ("default", "speech", "xmedia")


def emit_snapshot(root):
    """Stand in for the CLI, including write-if-changed outputs and a depfile."""
    manifest = root / "manifest.json"
    state = json.loads(manifest.read_text())
    if state.get("fail"):
        raise SystemExit("synthetic translation failure")
    generated = root / state["generated"]
    for module in MODULES:
        directory = generated / module
        directory.mkdir(parents=True, exist_ok=True)
        sources = ["pinyon_shift_init.cpp", "pinyon_shift_register.cpp"]
        files = {"pinyon_shift_register.cpp": "// registration stub\n"}
        for header in ("pch", "init", "funcs"):
            files[f"pinyon_shift_{header}.h"] = "#pragma once\n"
        declarations = []
        values = []
        if state["folds"]:
            sources.append("pinyon_shift_folds.cpp")
            files["pinyon_shift_folds.cpp"] = (
                "extern const int PPCFoldedRanges = 3;\n"
                "extern const int PPCFoldedHash = 7;\n"
            )
            declarations += ["extern const int PPCFoldedRanges, PPCFoldedHash;"]
            values += ["PPCFoldedRanges", "PPCFoldedHash"]
        for index in range(state["partitions"]):
            sources.append(f"pinyon_shift_recomp.{index}.cpp")
            files[sources[-1]] = f"int partition{index}() {{ return {index + 1}; }}\n"
            declarations.append(f"int partition{index}();")
            values.append(f"partition{index}()")
        files["pinyon_shift_init.cpp"] = (
            "\n".join(declarations) + '\nextern "C"\n'
            '#ifdef _WIN32\n__declspec(dllexport)\n#endif\n'
            "int entry() { return " + " + ".join(values) + "; }\n"
        )
        files["sources.cmake"] = "set(GENERATED_SOURCES\n" + "".join(
            f'  "${{CMAKE_CURRENT_LIST_DIR}}/{source}"\n' for source in sources
        ) + ")\n"
        for name, contents in files.items():
            path = directory / name
            if not path.exists() or path.read_text() != contents:
                path.write_text(contents)
        for path in directory.glob("pinyon_shift_*.cpp"):
            if path.name not in files:
                path.unlink()
    stamp = generated / "default/codegen.build.stamp"
    escape = lambda path: path.as_posix().replace(":", "\\:").replace(" ", "\\ ")
    (stamp.parent / "codegen.d").write_text(f"{escape(stamp)}: {escape(manifest)}\n")
    stamp.write_text("complete\n")
    with (root / "generations.log").open("a") as log:
        log.write("generated\n")


@unittest.skipUnless(shutil.which("cmake") and shutil.which("ninja") and
                     (shutil.which("clang++") or shutil.which("c++")),
                     "CMake, Ninja and a C++ compiler are required")
class CodegenBuildGraphTests(unittest.TestCase):
    def command(self, *arguments, succeeds=True):
        result = subprocess.run(arguments, capture_output=True, text=True)
        if succeeds:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_clean_and_update_builds(self):
        for generated in (".local/generated", ".local/generated-v4"):
            with self.subTest(generated=generated), tempfile.TemporaryDirectory(
                prefix="pinyon-codegen-"
            ) as temporary:
                root = Path(temporary)
                sdk = root / "sdk"
                sdk.mkdir()
                (sdk / "CMakeLists.txt").write_text(
                    "add_library(rexruntime INTERFACE)\n"
                    "add_library(rex::runtime ALIAS rexruntime)\n"
                    "function(rexglue_configure_module_target target)\nendfunction()\n"
                )
                (root / "config").mkdir()
                shutil.copyfile(ROOT / "config/release.json", root / "config/release.json")
                launcher = root / ("codegen.cmd" if os.name == "nt" else "codegen.sh")
                launch = f'"{sys.executable}" "{Path(__file__).resolve()}" --emit "{root}"\n'
                launcher.write_text(("@echo off\n" if os.name == "nt" else "#!/bin/sh\n") + launch)
                launcher.chmod(0o755)
                (root / "CMakeLists.txt").write_text(f'''
cmake_minimum_required(VERSION 3.25)
project(codegen_graph LANGUAGES CXX)
# Skip the application's CPU-baseline policy in this synthetic consumer.
set(CMAKE_SYSTEM_PROCESSOR synthetic)
set(REXSDK_DIR "${{CMAKE_SOURCE_DIR}}/sdk")
set(PINYON_SHIFT_REXGLUE_CODEGEN "{launcher.as_posix()}")
set(PINYON_SHIFT_MANIFEST "${{CMAKE_SOURCE_DIR}}/manifest.json")
set(PINYON_SHIFT_GENERATED_ROOT "${{CMAKE_SOURCE_DIR}}/{generated}")
set(PINYON_SHIFT_GENERATED_DIR "${{PINYON_SHIFT_GENERATED_ROOT}}/default")
include("{(ROOT / 'cmake/PinyonShiftRexGlue.cmake').as_posix()}")
add_library(default SHARED ${{PINYON_SHIFT_GENERATED_SOURCES}})
add_dependencies(default pinyon_shift_codegen)
''')
                manifest = root / "manifest.json"

                def state(folds, partitions, fail=False):
                    manifest.write_text(json.dumps(dict(
                        generated=generated, folds=folds, partitions=partitions, fail=fail
                    )))

                def build(succeeds=True):
                    return self.command("cmake", "--build", str(root / "build"),
                                        "--parallel", "2", succeeds=succeeds)

                def generations():
                    return (root / "generations.log").read_text().count("generated")

                # Clean/bootstrap from the old layout, with no folds source.
                state(False, 1)
                emit_snapshot(root)
                self.command("cmake", "-G", "Ninja", "-S", str(root),
                             "-B", str(root / "build"),
                             "-DCMAKE_CXX_COMPILER=" + (shutil.which("clang++") or shutil.which("c++")))
                build()
                before = generations()
                build()
                self.assertEqual(generations(), before)

                # A single build must translate, reconfigure, then link all three.
                state(True, 2)
                build()
                graph = (root / "build/build.ninja").read_text()
                for module in MODULES:
                    self.assertIn(f"{module}/pinyon_shift_folds.cpp", graph)
                    self.assertIn(f"{module}/pinyon_shift_recomp.1.cpp", graph)
                before = generations()
                build()
                self.assertEqual(generations(), before)

                # Removing a partition must also update the graph before compiling.
                state(True, 1)
                build()
                graph = (root / "build/build.ninja").read_text()
                self.assertNotIn("pinyon_shift_recomp.1.cpp", graph)
                # Unchanged source lists must not cause reconfiguration loops.
                state(True, 1)
                build()
                before = generations()
                build()
                self.assertEqual(generations(), before)

                state(True, 2, fail=True)
                build(succeeds=False)
                state(True, 2)
                build()

                # A missing included list is repaired through the same build edge.
                for module in MODULES:
                    (root / generated / module / "sources.cmake").unlink()
                    build()

                # A clean configure/build of the current layout also succeeds.
                self.command("cmake", "-G", "Ninja", "-S", str(root),
                             "-B", str(root / "clean"),
                             "-DCMAKE_CXX_COMPILER=" + (shutil.which("clang++") or shutil.which("c++")))
                self.command("cmake", "--build", str(root / "clean"), "--parallel", "2")

                # Frozen snapshots must never invoke the generator.
                self.command("cmake", "-S", str(root), "-B", str(root / "build"),
                             "-DPINYON_SHIFT_FROZEN_CODEGEN=ON")
                before = generations()
                state(False, 1)
                build()
                self.assertEqual(generations(), before)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--emit":
        emit_snapshot(Path(sys.argv[2]))
    else:
        unittest.main()
