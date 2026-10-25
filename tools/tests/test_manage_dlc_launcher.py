"""The Windows launcher's PowerShell bridge preserves UDLC arguments/errors."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
class ManageDlcLauncherTests(unittest.TestCase):
    def test_udlc_paths_switches_and_failure_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(Path(__file__).parents[1] / "manage-dlc.ps1", root / "manage-dlc.ps1")
            python = sys.executable.replace("'", "''")
            (root / "release-common.ps1").write_text(
                f"function Get-PinyonPython {{ '{python}' }}\n", encoding="utf-8")
            (root / "pinyon.py").write_text(
                "import json, sys\nprint(json.dumps(sys.argv[1:]))\n"
                "print('the exact tool error', file=sys.stderr)\nsys.exit(1)\n", encoding="utf-8")
            result = subprocess.run([
                "pwsh", "-NoLogo", "-NoProfile", "-File", str(root / "manage-dlc.ps1"),
                "-Action", "udlc", "-StateRoot", str(root / "state"),
                "-Find", "-OpenPages", "-Wait", "14400", "-Traffic",
                "UDLC pack.zip", "Traffic unlocker.zip",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.strip(), "the exact tool error")
            self.assertEqual(json.loads(result.stdout), [
                "dlc", "udlc", "UDLC pack.zip", "Traffic unlocker.zip",
                "--find", "--open-pages", "--wait", "14400", "--traffic",
                "--state-root", str(root / "state"), "--json",
            ])
