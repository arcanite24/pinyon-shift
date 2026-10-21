"""Managed SDK pin updates must keep valid local objects and repair dependencies."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pinyon_setup

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("git") and shutil.which("cmake") and shutil.which("ninja")
                     and (shutil.which("clang++") or shutil.which("c++")),
                     "Git, CMake, Ninja and a C++ compiler are required")
class SdkUpdateReuseTests(unittest.TestCase):
    def command(self, *args, cwd):
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def commit(self, directory):
        self.command("git", "add", ".", cwd=directory)
        self.command("git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                     "commit", "-qm", "test revision", cwd=directory)
        return self.command("git", "rev-parse", "HEAD", cwd=directory)

    def exercise(self, implementation):
        with tempfile.TemporaryDirectory(prefix="pinyon-sdk-update-") as temporary, \
                patch.dict(os.environ, {"GIT_ALLOW_PROTOCOL": "file", "PINYON_REXSDK_DIR": ""}):
            root = Path(temporary)
            origin, dependency, install = (root / name for name in ("origin", "dependency", "install"))
            for repo in (origin, dependency):
                repo.mkdir()
                self.command("git", "init", "-q", cwd=repo)
                (repo / ".gitignore").write_text("out/\n")
            (dependency / "CMakeLists.txt").write_text("add_library(dependency STATIC dependency.cpp)\n")
            (dependency / "dependency.cpp").write_text(
                "#ifndef DEPENDENCY_VALUE\n#define DEPENDENCY_VALUE 1\n#endif\n"
                "int dependency() { return DEPENDENCY_VALUE; }\n")
            self.commit(dependency)
            self.command("git", "submodule", "add", str(dependency), "thirdparty/dependency", cwd=origin)
            (origin / "CMakeLists.txt").write_text(
                'cmake_minimum_required(VERSION 3.25)\nproject(probe LANGUAGES CXX)\n'
                'add_subdirectory(thirdparty/dependency)\nadd_executable(probe main.cpp)\n'
                'target_link_libraries(probe PRIVATE dependency)\n')
            (origin / "main.cpp").write_text("int dependency(); int main() { return dependency() + 1; }\n")
            old = self.commit(origin)
            (origin / "main.cpp").write_text("int dependency(); int main() { return dependency() + 2; }\n")
            new = self.commit(origin)
            install.mkdir()
            tools = install / "tools"
            tools.mkdir()
            shutil.copyfile(ROOT / "tools/prepare-rexglue.ps1", tools / "prepare-rexglue.ps1")
            # Run the production PowerShell preparation script with only its
            # installation paths/logging supplied by this isolated installation.
            (tools / "release-common.ps1").write_text(r'''
function Get-PinyonRepoRoot { $env:PINYON_TEST_ROOT }
function Get-PinyonReleaseToolchain { Get-Content (Join-Path $env:PINYON_TEST_ROOT 'config.json') -Raw | ConvertFrom-Json }
function Get-PinyonGit { $env:PINYON_TEST_GIT }
function Resolve-PinyonRexGlueRoot { Join-Path $env:PINYON_TEST_ROOT '.local/rexglue' }
function Resolve-PinyonLocalPath { param($RelativePath) Join-Path $env:PINYON_TEST_ROOT $RelativePath }
function Write-PinyonEvent { param($Stage, $Percent, $Message, [switch]$JsonEvents) }
function Invoke-PinyonLoggedCommand {
    param($FilePath, $Arguments, $LogPath, [switch]$Append)
    & $FilePath @Arguments
    $global:LASTEXITCODE = $LASTEXITCODE
}
''')
            sdk = install / ".local/rexglue"

            def prepare(revision, succeeds=True):
                config = {"rexglue": {"repository": str(origin), "revision": revision,
                                      "fallback_path": ".local/rexglue"}}
                if implementation == "python":
                    with patch.object(pinyon_setup, "ROOT", install):
                        if succeeds:
                            self.assertEqual(pinyon_setup.prepare_shiftglue(lambda *args: None, config), sdk)
                        else:
                            with self.assertRaisesRegex(pinyon_setup.SetupError, "local changes"):
                                pinyon_setup.prepare_shiftglue(lambda *args: None, config)
                else:
                    (install / "config.json").write_text(json.dumps(config))
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                         str(tools / "prepare-rexglue.ps1")], capture_output=True, text=True,
                        env={**os.environ, "PINYON_TEST_ROOT": str(install),
                             "PINYON_TEST_GIT": shutil.which("git")})
                    if succeeds:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("local changes", result.stderr)
                self.assertEqual(self.command("git", "rev-parse", "HEAD", cwd=sdk),
                                 revision if succeeds else new)

            def build(flags=""):
                self.command("cmake", "-S", str(sdk), "-B", str(sdk / "out"), "-G", "Ninja",
                             "-DCMAKE_CXX_COMPILER=" + (shutil.which("clang++") or shutil.which("c++")),
                             "-DCMAKE_CXX_FLAGS=" + flags,
                             cwd=install)
                self.command("cmake", "--build", str(sdk / "out"), "--parallel", "2", cwd=install)
                binary = sdk / "out" / ("probe.exe" if os.name == "nt" else "probe")
                return subprocess.run([str(binary)]).returncode

            prepare(old)
            self.assertEqual(build(), 2)
            obj = next(path for path in (sdk / "out").rglob("dependency.cpp.*")
                       if path.suffix in (".obj", ".o"))
            stamp, contents = obj.stat().st_mtime_ns, obj.read_bytes()
            prepare(new)
            self.assertEqual(obj.stat().st_mtime_ns, stamp)
            self.assertEqual(obj.read_bytes(), contents)
            self.assertEqual(build(), 3)
            self.assertEqual(obj.stat().st_mtime_ns, stamp)
            # CMake must still invalidate a retained object when flags change.
            self.assertEqual(build("-DDEPENDENCY_VALUE=7"), 9)
            self.assertNotEqual(obj.stat().st_mtime_ns, stamp)
            # Same-pin setup repairs missing tracked dependency files (#580).
            (sdk / "thirdparty/dependency/dependency.cpp").unlink()
            prepare(new)
            self.assertTrue((sdk / "thirdparty/dependency/dependency.cpp").is_file())
            self.assertEqual(build(), 3)
            # Preserve the managed checkout's local edits and objects on refusal.
            (sdk / "main.cpp").write_text("local edit\n")
            prepare(old, succeeds=False)
            self.assertEqual((sdk / "main.cpp").read_text(), "local edit\n")
            self.assertTrue(obj.is_file())

    def test_python_managed_update(self):
        self.exercise("python")

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_powershell_managed_update(self):
        self.exercise("powershell")
