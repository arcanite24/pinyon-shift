import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('powershell'), 'Windows PowerShell required')
class ExtractedGameTests(unittest.TestCase):
    def test_complete_catalog_and_reject_modified_missing_extra_or_linked_inputs(self):
        with tempfile.TemporaryDirectory(prefix='pinyon-folder-') as temporary:
            root = Path(temporary)
            script = root / 'tools/verify-extracted-game.ps1'
            script.parent.mkdir()
            shutil.copyfile(ROOT / 'tools/verify-extracted-game.ps1', script)
            config = root / 'config'
            config.mkdir()
            game = root / 'game with spaces'
            game.mkdir()
            contents = {'default.xex': b'executable', 'media/example.zip': b'assets', 'media/colours.dat': b'data'}
            expected = []
            for name, data in contents.items():
                path = game / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(data)
                expected.append(dict(guest_path=name, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
            (config / 'catalog.json').write_text(json.dumps(dict(schema_version=1, dump_id='fixture', iso_sha256='fixture-iso', files=expected)))
            (config / 'supported-dumps.json').write_text(json.dumps(dict(dumps=[dict(id='fixture', status='fixture', title_id='4D5309C9', serial='MS-2505', iso=dict(sha256='fixture-iso'), extraction=dict(file_catalog='catalog.json', file_count=3))])))

            def verify(valid):
                result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-ExtractedRoot', str(game), '-Json'], capture_output=True)
                self.assertEqual(result.returncode, 0 if valid else 1, result.stderr.decode(errors='replace'))
                report = json.loads(result.stdout)
                self.assertEqual(report['recognized'], valid)
                if valid:
                    self.assertIsNone(report['iso_sha256'])
                else:
                    self.assertTrue(report['mismatches'])
                return report

            verify(True)
            asset = game / 'media/example.zip'
            asset.write_bytes(b'ASSETS')
            self.assertIn('SHA-256 mismatch: media/example.zip', verify(False)['mismatches'])
            asset.unlink()
            self.assertIn('Missing: media/example.zip', verify(False)['mismatches'])
            asset.write_bytes(b'assets')
            extra = game / 'unexpected.bin'
            extra.write_bytes(b'extra')
            verify(False)
            extra.unlink()
            update = game / '$SystemUpdate'
            update.mkdir()
            (update / 'update.bin').write_bytes(b'not game input')
            verify(True)
            junction = game / 'linked-media'
            command = "New-Item -ItemType Junction -Path '{}' -Target '{}' | Out-Null".format(junction, game / 'media')
            subprocess.run(['powershell', '-NoProfile', '-Command', command], check=True, capture_output=True)
            try:
                result = subprocess.run(['powershell', '-NoProfile', '-File', str(script), '-ExtractedRoot', str(game), '-Json'], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'Linked game input is unsupported', result.stderr)
            finally:
                # Removing this private junction does not touch its target.
                junction.rmdir()
            for name, data in contents.items():
                self.assertEqual((game / name).read_bytes(), data)

            # Exercise actual setup orchestration, replacing only costly build
            # stages. The real verifier, source copy and destination checks run.
            shutil.copyfile(ROOT / 'tools/setup-preview.ps1', root / 'tools/setup-preview.ps1')
            shutil.copyfile(ROOT / 'tools/release-common.ps1', root / 'tools/release-common.ps1')
            shutil.copyfile(ROOT / 'config/release-toolchain.json', config / 'release-toolchain.json')
            for name in ('provision-toolchain', 'prepare-rexglue', 'build-preview', 'prepare-fh1-shaders'):
                (root / f'tools/{name}.ps1').write_text("param([switch]$JsonEvents, [string]$GameRoot)\nAdd-Content -LiteralPath (Join-Path $PSScriptRoot '../stages.txt') '" + name + "'\n")
            command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(root / 'tools/setup-preview.ps1'), '-GamePath', str(game), '-JsonEvents']
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            cache = root / '.local/game/base'
            for name, data in contents.items():
                self.assertEqual((cache / name).read_bytes(), data)
                self.assertEqual((game / name).read_bytes(), data)
            self.assertFalse((cache / '$SystemUpdate').exists())
            state = json.loads((root / '.local/setup-state.json').read_text())
            self.assertEqual(state['source_kind'], 'extracted')
            self.assertIsNone(state['iso_sha256'])
            self.assertEqual((root / 'stages.txt').read_text().splitlines(), ['provision-toolchain', 'prepare-rexglue', 'build-preview', 'prepare-fh1-shaders'])
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertIn(b'"stage":"play"', result.stdout)
            # A source nested inside the destination must survive rejection.
            nested = cache / 'nested-source'
            shutil.copytree(game, nested)
            result = subprocess.run(command[:-3] + ['-ExtractedPath', str(nested), '-JsonEvents'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'must be separate', result.stdout + result.stderr)
            for name, data in contents.items():
                self.assertEqual((nested / name).read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
