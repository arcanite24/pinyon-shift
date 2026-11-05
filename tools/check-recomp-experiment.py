"""Reject an experiment build that escaped its generated snapshot or IPO scope."""
import argparse
import json
from pathlib import Path


def check(build: Path, generated: Path, ipo: bool, pgo: str = "off") -> int:
    commands = json.loads((build / "compile_commands.json").read_text())
    shards = [c for c in commands
              if Path(c["file"]).name.startswith("pinyon_shift_recomp.")]
    if not shards:
        raise ValueError("No translated shards found")
    for item in shards:
        source = Path(item["file"]).resolve()
        if not source.is_relative_to(generated.resolve()):
            raise ValueError(f"Source escaped snapshot: {source}")
        command = item["command"]
        if ("-flto=thin" in command) != ipo:
            raise ValueError(f"Unexpected ThinLTO setting: {source}")
        if "-msse4.1" not in command or "-fasync-exceptions" not in command:
            raise ValueError(f"Missing CPU/exception contract: {source}")
        if pgo == "generate":
            valid_profile = "-fprofile-generate" in command and "-fprofile-update=atomic" in command
        elif pgo == "use":
            valid_profile = "-fprofile-use=" in command and "-fprofile-generate" not in command
        else:
            valid_profile = "-fprofile-" not in command
        if not valid_profile:
            raise ValueError(f"Unexpected PGO mode: {source}")
    for item in commands:
        command = item["command"].replace("\\", "/")
        if "CMakeFiles/rexruntime.dir/" in command and "-flto" in command:
            raise ValueError("Recomp-only IPO unexpectedly affects runtime")
        if "CMakeFiles/rexruntime.dir/" in command and "-fprofile-" in command:
            raise ValueError("Recomp-only PGO unexpectedly affects runtime")
    if "Generating dependency-tracked recompiled code" in (build / "build.ninja").read_text():
        raise ValueError("Build can invoke codegen; snapshot is not frozen")
    return len(shards)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("generated", type=Path)
    parser.add_argument("--ipo", action="store_true")
    parser.add_argument("--pgo", choices=("off", "generate", "use"), default="off")
    args = parser.parse_args()
    print(f"PASS: {check(args.build, args.generated, args.ipo, args.pgo)} isolated shards")
