"""Compile the actual startup gate with the real host config/file services.

The gate lives in the app's anonymous namespace, so extract it verbatim rather
than duplicate migration logic or link the game and GPU into a file-I/O test.
Run Windows checks inside the repository's build environment.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
_KEYS = (ROOT / 'src/config/default_keys.h').read_text(encoding='utf-8')
SCHEMA28_KEYS = dict(re.findall(r'\{"(keybind_\w+)", "([^"]*)"\}',
                                _KEYS[_KEYS.index('kSchema28Keys[]'):]
                                [:_KEYS[_KEYS.index('kSchema28Keys[]'):].index('};')]))
CXX = os.environ.get('PINYON_STARTUP_CONFIG_TEST_CXX') or ((ROOT / '.local/toolchain/llvm-20.1.8/bin/clang++.exe') if os.name == 'nt' else shutil.which('clang++') or shutil.which('g++'))
AVAILABLE = bool(CXX and Path(CXX).is_file() and (os.name != 'nt' or os.environ.get('INCLUDE')))


@unittest.skipUnless(AVAILABLE, 'C++ compiler/build environment required')
class StartupConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='pinyon-config-gate-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        app = (ROOT / 'src/pinyon_shift_app.cpp').read_text(encoding='utf-8')
        helper = app.find('std::string DefaultConfigText(')
        start = helper if helper >= 0 else app.index('bool EnsureSupportedConfig(')
        gate = app.index('bool EnsureSupportedConfig(')
        end = app.index('\n}\n', gate) + len('\n}')
        cls.schema = int(re.search(r'constexpr uint32_t kConfigSchema = (\d+);', app)[1])
        source = '#include <filesystem>\n#include <fstream>\n#include <sstream>\n#include <regex>\n#include <string>\n#include <cstdint>\n#include <iostream>\n#include <toml++/toml.hpp>\n#include "platform/host_platform.h"\n#include "config/host_config.h"\n#include "config/default_keys.h"\n'
        source += f'constexpr uint32_t kConfigSchema = {cls.schema};\n' + app[start:end]
        source += '\nint main(int argc,char** argv) { bool created=false,migrated=false; bool valid=EnsureSupportedConfig(argv[1],created,migrated); std::cout<<valid<<" "<<created<<" "<<migrated; return valid?0:2; }\n'
        cpp = cls.root / 'gate.cpp'
        cpp.write_text(source, encoding='utf-8')
        cls.exe = cls.root / ('gate.exe' if os.name == 'nt' else 'gate')
        command = [str(CXX), '-std=c++23', '-I' + str(ROOT / 'src'),
            '-I' + str(ROOT / 'thirdparty/shiftglue-sdk/thirdparty/tomlplusplus/include'), str(cpp),
            str(ROOT / 'src/config/host_config.cpp'), str(ROOT / 'src/platform/host_platform.cpp')]
        if os.name == 'nt':
            command += ['-luser32', '-lkernel32']
        compiled = subprocess.run(command + ['-o', str(cls.exe)], capture_output=True, text=True)
        if compiled.returncode:
            raise RuntimeError(compiled.stderr)

    def run_gate(self, data):
        directory = Path(tempfile.mkdtemp(dir=self.root))
        path = directory / 'pinyon_shift.toml'
        if data is not None:
            path.write_bytes(data)
        result = subprocess.run([str(self.exe), str(path)], capture_output=True, text=True)
        return path, result

    def test_current_bom_config_loads_without_rewriting(self):
        for newline in ('\n', '\r\n'):
            data = ('\ufeff' + f'pinyon_shift_config_schema = {self.schema} # current' + newline + 'user_name = "Neri"' + newline).encode()
            path, result = self.run_gate(data)
            self.assertEqual((result.returncode, result.stdout), (0, '1 0 0'))
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_old_bom_migration_retains_exact_original_backup(self):
        old = self.schema - 1
        data = f'\ufeffpinyon_shift_config_schema = {old}\r\ncustom_value = 77\r\n'.encode()
        path, result = self.run_gate(data)
        self.assertEqual((result.returncode, result.stdout), (0, '1 0 1'))
        self.assertEqual(Path(str(path) + f'.schema{old}.bak').read_bytes(), data)
        updated = path.read_bytes()
        self.assertFalse(updated.startswith(b'\xef\xbb\xbf'))
        self.assertIn(f'pinyon_shift_config_schema = {self.schema}'.encode(), updated)
        self.assertIn(b'custom_value = 77', updated)
        again = subprocess.run([str(self.exe), str(path)], capture_output=True, text=True)
        self.assertEqual((again.returncode, again.stdout), (0, '1 0 0'))
        self.assertEqual(path.read_bytes(), updated)

    def test_future_schema_loads_without_rewriting(self):
        data = f'\ufeffpinyon_shift_config_schema = {self.schema + 1}\r\nfuture_setting = 77\r\n'.encode()
        path, result = self.run_gate(data)
        self.assertEqual((result.returncode, result.stdout), (0, '1 0 0'))
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_invalid_schema_stays_untouched(self):
        for body in ('pinyon_shift_config_schema = 0\n',
                     'pinyon_shift_config_schema = "invalid"\n'):
            data = ('\ufeff' + body).encode()
            path, result = self.run_gate(data)
            self.assertEqual((result.returncode, result.stdout), (2, '0 0 0'))
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_future_schema_is_preserved(self):
        data = f'pinyon_shift_config_schema = {self.schema + 1}\nvsync = false\n'.encode()
        path, result = self.run_gate(data)
        self.assertEqual((result.returncode, result.stdout), (0, '1 0 0'))
        self.assertEqual(path.read_bytes(), data)

    def test_missing_schema_keeps_settings_and_exact_backup(self):
        data = b'vsync = false\ncustom_value = 77\n'
        path, result = self.run_gate(data)
        self.assertEqual((result.returncode, result.stdout), (0, '1 0 1'))
        self.assertEqual(Path(str(path) + '.noschema.bak').read_bytes(), data)
        self.assertIn(data, path.read_bytes())

    def test_mod_builder_config_gains_all_fresh_start_defaults(self):
        fresh, created = self.run_gate(None)
        self.assertEqual((created.returncode, created.stdout), (0, '1 1 0'))
        data = b'enabled_mods = "immersive_camera"\n'
        path, result = self.run_gate(data)
        self.assertEqual((result.returncode, result.stdout), (0, '1 0 1'))
        repaired = path.read_bytes()
        self.assertEqual(Path(str(path) + '.noschema.bak').read_bytes(), data)
        for line in fresh.read_bytes().splitlines():
            if b'=' in line:
                self.assertIn(line, repaired.splitlines())
        self.assertIn(b'gpu_backend = "vulkan"\n', repaired)
        self.assertIn(data, repaired)
        again = subprocess.run([str(self.exe), str(path)], capture_output=True, text=True)
        self.assertEqual((again.returncode, again.stdout), (0, '1 0 0'))
        self.assertEqual(path.read_bytes(), repaired)
        self.assertEqual(Path(str(path) + '.noschema.bak').read_bytes(), data)

    def test_schema_repair_keeps_saved_values_and_exact_backup(self):
        for newline in ('\n', '\r\n'):
            data = ('\ufeff# saved settings' + newline +
                    'vsync = false' + newline +
                    'draw_resolution_scale_x = 2' + newline +
                    'keybind_a = "Space,LMB"' + newline +
                    'custom_value = 77' + newline).encode()
            path, result = self.run_gate(data)
            self.assertEqual((result.returncode, result.stdout), (0, '1 0 1'))
            self.assertEqual(Path(str(path) + '.noschema.bak').read_bytes(), data)
            repaired = path.read_bytes()
            for line in (b'vsync = false', b'draw_resolution_scale_x = 2',
                         b'keybind_a = "Space,LMB"', b'custom_value = 77',
                         b'gpu_backend = "vulkan"', b'gpu_record_thread = true'):
                self.assertIn(line, repaired.splitlines())
            self.assertEqual(repaired.count(b'keybind_a = '), 1)
            self.assertFalse(repaired.startswith(b'\xef\xbb\xbf'))

    def test_schema_repair_preserves_toml_syntax_and_comments(self):
        fresh, _ = self.run_gate(None)
        defaults = tomllib.loads(fresh.read_text(encoding='utf-8'))
        for newline in ('\n', '\r\n'):
            body = newline.join((
                '# retain my settings',
                '"vsync" = false # explicit override',
                "'gpu_backend' = 'vulkan'",
                'keybind_a = """Space,',
                'LMB""" # multiline string',
                'custom-name = "hash # in a string" # unknown key',
                'custom_array = [',
                '  "first", # array comment',
                '  "second",',
                ']',
                '[custom_table]',
                'value = 77',
            ))  # Also cover a file without a trailing newline.
            data = ('\ufeff' + body).encode()
            path, result = self.run_gate(data)
            self.assertEqual((result.returncode, result.stdout), (0, '1 0 1'))
            self.assertEqual(Path(str(path) + '.noschema.bak').read_bytes(), data)
            repaired = path.read_text(encoding='utf-8')
            # Saved settings make it an earlier player's file: missing pad
            # keys come from schema 28.
            expected = defaults | SCHEMA28_KEYS | tomllib.loads(body)
            self.assertEqual(tomllib.loads(repaired), expected)
            self.assertIn(body.encode(), path.read_bytes())
            again = subprocess.run([str(self.exe), str(path)], capture_output=True, text=True)
            self.assertEqual((again.returncode, again.stdout), (0, '1 0 0'))
            self.assertEqual(path.read_text(encoding='utf-8'), repaired)

    def test_schema_repair_gives_earlier_players_their_keys(self):
        path, result = self.run_gate(b'vsync = false\n')
        self.assertEqual((result.returncode, result.stdout), (0, '1 0 1'))
        repaired = tomllib.loads(path.read_text(encoding='utf-8'))
        self.assertTrue(SCHEMA28_KEYS)
        for name, keys in SCHEMA28_KEYS.items():
            self.assertEqual(repaired[name], keys)

    def test_mod_builder_config_gets_driving_first_keys(self):
        fresh, _ = self.run_gate(None)
        defaults = tomllib.loads(fresh.read_text(encoding='utf-8'))
        path, result = self.run_gate(b'enabled_mods = "immersive_camera"\n')
        self.assertEqual((result.returncode, result.stdout), (0, '1 0 1'))
        repaired = tomllib.loads(path.read_text(encoding='utf-8'))
        for name in SCHEMA28_KEYS:
            self.assertEqual(repaired[name], defaults[name])
        self.assertNotEqual(repaired['keybind_start'], SCHEMA28_KEYS['keybind_start'])

    def test_empty_values_become_empty_strings(self):
        for newline in ('\n', '\r\n'):
            data = newline.join((f'pinyon_shift_config_schema = {self.schema}',
                                 'cheat_gps_destination = ', 'cheat_set_profile_fields =',
                                 'vsync = false', '')).encode()
            path, result = self.run_gate(data)
            self.assertEqual((result.returncode, result.stdout), (0, '1 0 1'))
            self.assertEqual(Path(str(path) + '.emptyvalue.bak').read_bytes(), data)
            repaired = tomllib.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(repaired['cheat_gps_destination'], '')
            self.assertEqual(repaired['cheat_set_profile_fields'], '')
            self.assertIs(repaired['vsync'], False)
            again = subprocess.run([str(self.exe), str(path)], capture_output=True, text=True)
            self.assertEqual((again.returncode, again.stdout), (0, '1 0 0'))

    def test_empty_schema_less_config_matches_first_launch(self):
        fresh, _ = self.run_gate(None)
        path, result = self.run_gate(b'')
        self.assertEqual((result.returncode, result.stdout), (0, '1 0 1'))
        self.assertEqual(path.read_bytes(), fresh.read_bytes())
        self.assertEqual(Path(str(path) + '.noschema.bak').read_bytes(), b'')

    def test_invalid_schema_less_toml_stays_untouched(self):
        for data in (b'vsync = false\nvsync = true\n', b'custom_array = [\n',
                     b'"pinyon_shift_config_schema" = "invalid"\n'):
            path, result = self.run_gate(data)
            self.assertEqual((result.returncode, result.stdout), (2, '0 0 0'))
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(list(path.parent.iterdir()), [path])
