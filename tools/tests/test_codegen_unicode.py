"""Exercise Windows UTF-8 manifests with the real locally built code generator."""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from tools.tests.test_setup_failure_report import run_powershell

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / 'thirdparty/shiftglue-sdk/out/win-amd64/Release/rexglue.exe'


@unittest.skipUnless(os.name == 'nt' and CLI.is_file() and shutil.which('powershell'),
                     'Windows and a locally built ReXGlue CLI required')
class CodegenUnicodeTests(unittest.TestCase):
    def test_embedded_utf8_manifest_preserves_unicode_paths_and_diagnostics(self):
        result = run_powershell("$taskEnv = Enter-PinyonBuildEnvironment\n[Console]::Out.Write((Get-Command mt.exe).Source)")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        mt = result.stdout.strip()
        with tempfile.TemporaryDirectory(prefix='pinyon-codegen-utf8-') as directory:
            root = pathlib.Path(directory)
            exe = root / 'rexglue.exe'
            shutil.copy2(CLI, exe)
            environment = os.environ.copy()
            environment['PATH'] = str(CLI.parent) + os.pathsep + environment['PATH']
            # A no-op incremental rebuild embeds it again; merging must be repeatable.
            for _ in range(2):
                result = subprocess.run([mt, '-nologo', '-inputresource:' + str(exe) + ';#1',
                    '-manifest', str(ROOT / 'config/rexglue/codegen-windows.manifest'),
                    '-outputresource:' + str(exe) + ';#1'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for folder in ('ascii', '\u0418\u043b\u0430\u043d\u0430 \u6f22\u5b57 (space)'):
                for valid in (False, True):
                    with self.subTest(folder=folder, valid=valid):
                        data = root / folder / str(valid)
                        data.mkdir(parents=True)
                        manifest = data / 'project.toml'
                        manifest.write_text(('[project]\nname = "probe"\nsdk_version = "0.10.0"\n'
                            'game_root = "missing-game"\n' if valid else '') +
                            '[entrypoint]\nfile_path = "missing-game/default.xex"\n'
                            'out_directory_path = "generated"\n', encoding='utf-8')
                        result = subprocess.run([str(exe), '--log-file', str(data / 'native.log'),
                            'codegen', str(manifest)], env=environment, capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        output = result.stdout + result.stderr
                        self.assertIn(str(data), output)
                        self.assertIn('Entrypoint XEX not found' if valid else 'no [project] section', output)
                        self.assertTrue((data / 'native.log').is_file())
                        if valid:
                            self.assertTrue((data / 'generated/rexglue.cmake').is_file())
                        capture = data / 'console.log'
                        probe = run_powershell(r"""
$savedEncoding = [Console]::OutputEncoding.WebName
Invoke-PinyonLoggedCommand -FilePath $env:PINYON_PROBE_EXE -Arguments @('--log-file', $env:PINYON_PROBE_LOG, 'codegen', $env:PINYON_PROBE_MANIFEST) -LogPath $env:PINYON_PROBE_CAPTURE -Utf8Output | Out-Null
if ($LASTEXITCODE -ne 1) { throw 'Wrong native exit code' }
if ([Console]::OutputEncoding.WebName -ne $savedEncoding) { throw 'Caller output encoding changed' }
""", {**environment, 'PINYON_PROBE_EXE': str(exe), 'PINYON_PROBE_LOG': str(data / 'native.log'),
       'PINYON_PROBE_MANIFEST': str(manifest), 'PINYON_PROBE_CAPTURE': str(capture)})
                        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
                        self.assertIn(str(data), capture.read_text(encoding='utf-8'))



if __name__ == '__main__':
    unittest.main()
