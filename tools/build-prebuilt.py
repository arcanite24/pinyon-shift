"""Build this platform's prebuilt release assets (Linux and macOS).

TP-1 to TP-3 (docs/TIME_TO_PLAY_BACKLOG.md), run by .github/workflows/release.yml
on each host: the trimmed LLVM and sniper sysroot (Linux) and the ShiftGlue
kit, each with the .json sidecar tools/apply-prebuilt-pins.py reads. Windows
runs tools/build-shiftglue-kit.ps1 and tools/repack-toolchain.py directly.

    python3 tools/build-prebuilt.py --output .artifacts/prebuilt
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pinyon_setup  # noqa: E402


def run(*command: str) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True, cwd=str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--jobs", type=int)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = pinyon_setup.host_platform()
    config = pinyon_setup.toolchain_config()
    tools = pinyon_setup.platform_tools(config, name)
    revision = config["rexglue"]["revision"][:12]
    setup = [sys.executable, str(ROOT / "tools" / "pinyon_setup.py"), "setup"]
    jobs = ["--jobs", str(args.jobs)] if args.jobs else []
    # The upstream tools and the ShiftGlue submodule, as a player's setup
    # without prebuilt assets gets them.
    run(*setup, "--tools-only")
    repack = [sys.executable, str(ROOT / "tools" / "repack-toolchain.py")]
    if name == "linux-x86_64":
        llvm = tools["llvm"]
        run(*repack, "llvm", "--platform", name, "--source", str(ROOT / llvm["install_path"]),
            "--version", llvm["version"],
            "--output", str(output / f"llvm-{llvm['version']}-pinyon1-{name}.tar.xz"))
        sysroot = tools["sysroot"]
        run(*repack, "sysroot", "--source", str(ROOT / sysroot["install_path"]),
            "--version", sysroot["version"],
            "--output", str(output / f"sniper-sysroot-{sysroot['version']}-pinyon1.tar.xz"))
    kit = output / f"shiftglue-kit-{revision}-{name}.tar.xz"
    run(*setup, "--build-kit", str(kit), *jobs)
    print(json.dumps(sorted(path.name for path in output.iterdir()), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
