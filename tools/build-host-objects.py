"""Build and package the prebuilt host objects for one platform and variant.

TP-3 host split (docs/TIME_TO_PLAY_BACKLOG.md): the host code that includes
no generated header compiles once per release, from the prebuilt ShiftGlue
kit and with the player's preset, into pinyon_shift_host
(PINYON_SHIFT_HOST_OBJECTS_ONLY). The archive holds the objects and
host-objects.json with the fingerprint the game build checks
(pinyon_shift_host_fingerprint in cmake/PinyonShiftRexGlue.cmake); the .json
sidecar beside it is what tools/apply-prebuilt-pins.py reads. Nothing in it is
game-derived.

Run it in the build environment setup uses: on Windows after
Enter-PinyonBuildEnvironment with the fetched MSVC sysroot.

    python tools/build-host-objects.py --kit .local/shiftglue-kit --platform windows-x64 \
        --preset win-amd64-release --variant base --output .artifacts/prebuilt
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True, cwd=str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kit", required=True, type=Path, help="unpacked ShiftGlue kit")
    parser.add_argument("--platform", required=True,
                        choices=("windows-x64", "linux-x86_64", "macos-arm64", "macos-x86_64",
                                 "android-arm64"))
    parser.add_argument("--preset", required=True, help="the configure preset setup uses")
    parser.add_argument("--variant", required=True, choices=("base", "v4"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--define", action="append", default=[],
                        help="extra -D setting, as setup passes it (repeatable)")
    args = parser.parse_args(argv)

    kit = args.kit.resolve()
    meta = json.loads((kit / "kit.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "config/release-toolchain.json").read_text(encoding="utf-8"))
    version = json.loads((ROOT / "config/release.json").read_text(encoding="utf-8"))["version"]
    build = (args.build_dir or ROOT / "out/build" / f"host-objects-{args.platform}-{args.variant}").resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    defines = [f"-D{item}" for item in args.define]
    if args.variant == "v4":
        defines.append("-DPINYON_SHIFT_TITLE_UPDATE_V4=ON")
    run(args.cmake, "--preset", args.preset, "-B", str(build), "-DREXSDK_DIR=",
        f"-DPINYON_SHIFT_SHIFTGLUE_KIT={kit.as_posix()}", "-DPINYON_SHIFT_HOST_OBJECTS_ONLY=ON",
        f"-DPYTHON_EXECUTABLE={sys.executable}", f"-DPython3_EXECUTABLE={sys.executable}", *defines)
    run(args.cmake, "--build", str(build), "--target", "pinyon_shift_host", "--parallel", str(args.jobs))

    listing = build / "host-objects"
    fingerprint = (listing / "fingerprint.txt").read_text(encoding="utf-8").strip()
    objects = [Path(line) for line in (listing / "objects.txt").read_text(encoding="utf-8").splitlines() if line]
    name = f"host-objects-{version}-{args.platform}-{args.variant}"
    staging = build / "package" / name
    shutil.rmtree(staging.parent, ignore_errors=True)
    (staging / "objects").mkdir(parents=True)
    names = []
    for index, source in enumerate(objects):
        target = f"objects/{index:03d}-{source.name}"
        shutil.copyfile(source, staging / target)
        names.append(target)
    manifest = {
        "schema_version": 1,
        "platform": args.platform,
        "variant": args.variant,
        "version": version,
        "shiftglue_revision": meta["shiftglue_revision"],
        "fingerprint": fingerprint,
        "objects": names,
    }
    (staging / "host-objects.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if args.platform == "windows-x64":
        archive = output / f"{name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(staging.parent).as_posix())
    else:
        archive = output / f"{name}.tar.xz"
        with tarfile.open(archive, "w:xz", preset=9) as bundle:
            bundle.add(staging, arcname=name)
    sidecar = {"kind": "host-objects", "platform": args.platform, "variant": args.variant,
               "revision": config["rexglue"]["revision"], "version": version}
    Path(f"{archive}.json").write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    print(f"{archive.name}: {len(names)} objects, {archive.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
