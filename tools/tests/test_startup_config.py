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
import unittest

ROOT = Path(__file__).resolve().parents[2]
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
        start = app.index('bool EnsureSupportedConfig(')
        end = app.index('\n}  // namespace', start)
        cls.schema = int(re.search(r'constexpr uint32_t kConfigSchema = (\d+);', app)[1])
        source = '#include <filesystem>\n#include <fstream>\n#include <sstream>\n#include <regex>\n#include <string>\n#include <cstdint>\n#include <iostream>\n#include "platform/host_platform.h"\n#include "config/host_config.h"\n'
        source += f'constexpr uint32_t kConfigSchema = {cls.schema};\n' + app[start:end]
        source += '\nint main(int argc,char** argv) { bool created=false,migrated=false; bool valid=EnsureSupportedConfig(argv[1],created,migrated); std::cout<<valid<<" "<<created<<" "<<migrated; return valid?0:2; }\n'
        cpp = cls.root / 'gate.cpp'
        cpp.write_text(source, encoding='utf-8')
        cls.exe = cls.root / ('gate.exe' if os.name == 'nt' else 'gate')
        command = [str(CXX), '-std=c++23', '-I' + str(ROOT / 'src'), str(cpp),
            str(ROOT / 'src/config/host_config.cpp'), str(ROOT / 'src/platform/host_platform.cpp')]
        if os.name == 'nt':
            command += ['-luser32', '-lkernel32']
        compiled = subprocess.run(command + ['-o', str(cls.exe)], capture_output=True, text=True)
        if compiled.returncode:
            raise RuntimeError(compiled.stderr)

    def run_gate(self, data):
        directory = Path(tempfile.mkdtemp(dir=self.root))
        path = directory / 'pinyon_shift.toml'
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

    def test_unsupported_or_missing_schema_stays_untouched(self):
        for body in (f'pinyon_shift_config_schema = {self.schema + 1}\n',
                     'pinyon_shift_config_schema = 0\n',
                     'pinyon_shift_config_schema = "invalid"\n', 'vsync = false\n'):
            data = ('\ufeff' + body).encode()
            path, result = self.run_gate(data)
            self.assertEqual((result.returncode, result.stdout), (2, '0 0 0'))
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(list(path.parent.iterdir()), [path])
