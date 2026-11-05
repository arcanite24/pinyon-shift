#!/usr/bin/env python3
"""Packages the Linux and macOS launchers (LX-8.5, MAC-8).

  python tools/package-launcher.py --platform linux-x64
  python tools/package-launcher.py --platform osx-arm64      (on a Mac)
  python tools/package-launcher.py --platform osx-x64        (on a Mac; Intel, experimental)

Both ship the Avalonia launcher in launcher/PinyonShift.Launcher.Desktop and
the same source payload as the Windows release. The payload's file list is
the one in tools/package-launcher.ps1, so the releases cannot drift apart.

  .artifacts/PinyonShift-Launcher-linux-x86_64.tar.gz
      PinyonShift/PinyonShiftLauncher, PinyonShift/pinyon-shift-source.zip
  .artifacts/PinyonShift-Launcher-macos-arm64.zip
  .artifacts/PinyonShift-Launcher-macos-x86_64.zip
      Pinyon Shift.app (ad-hoc signed; the payload is in Contents/Resources)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts" / "launcher-desktop"
PROJECT = ROOT / "launcher" / "PinyonShift.Launcher.Desktop" / "PinyonShift.Launcher.Desktop.csproj"
FIXED_TIME = (2026, 7, 23, 0, 0, 0)  # 1784764800, as package-launcher.ps1
FORBIDDEN = {".exe", ".dll", ".obj", ".lib", ".pdb", ".iso", ".xex", ".dxil", ".pnsp",
             ".so", ".apk", ".aab", ".idsig", ".keystore", ".jks", ".dex"}


def payload_include() -> list[str]:
    script = (ROOT / "tools" / "package-launcher.ps1").read_text(encoding="utf-8")
    block = script.split("$include = @(", 1)[1].split("\n)", 1)[0]
    items = []
    for line in block.splitlines():
        line = line.split("#", 1)[0]
        items += [part.strip().strip("'") for part in line.split(",") if part.strip()]
    return items


def git(*arguments: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT)] + list(arguments), capture_output=True,
                          text=True, check=True).stdout.strip()


def pin_prebuilt(config: bytes, assets: Path, base_url: str) -> bytes:
    """The toolchain config with the release's prebuilt assets pinned
    (tools/apply-prebuilt-pins.py), as the Windows packager pins them."""
    spec = importlib.util.spec_from_file_location("apply_prebuilt_pins",
                                                  ROOT / "tools" / "apply-prebuilt-pins.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = json.loads(config)
    print("\n".join(module.apply(data, assets, base_url)))
    return (json.dumps(data, indent=2) + "\n").encode()


def build_payload(destination: Path, assets: Path | None = None, base_url: str = "") -> None:
    """The source payload, as the Windows release builds it."""
    files: list[tuple[str, bytes]] = []
    for relative in payload_include():
        source = ROOT / relative
        if not source.exists():
            raise SystemExit(f"payload source is missing: {relative}")
        paths = [source] if source.is_file() else sorted(
            path for path in source.rglob("*") if path.is_file()
            and not (relative == "config/rexglue" and "generated" in path.relative_to(source).parts[:1]))
        for path in paths:
            if path.suffix.lower() in FORBIDDEN:
                raise SystemExit(f"forbidden file entered the payload: {path}")
            data = path.read_bytes()
            if assets is not None and path.relative_to(ROOT).as_posix() == "config/release-toolchain.json":
                data = pin_prebuilt(data, assets, base_url)
            files.append((path.relative_to(ROOT).as_posix(), data))
    provenance = {"schema_version": 1, "repository": "https://github.com/arcanite24/pinyon-shift",
                  "commit": git("rev-parse", "HEAD"),
                  "dirty": bool(git("status", "--porcelain"))}
    files.append(("config/source-provenance.json",
                  (json.dumps(provenance, indent=2) + "\n").encode()))
    write_zip(destination, sorted(files))


def write_zip(destination: Path, files: list[tuple[str, bytes]], modes: dict | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in files:
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ((modes or {}).get(name, 0o644) | 0o100000) << 16
            info.create_system = 3  # Unix, so the modes count
            archive.writestr(info, data)


def publish(runtime: str, version: str, output: Path) -> None:
    file_version = version.split("-", 1)[0] + ".0"
    subprocess.run(["dotnet", "publish", str(PROJECT), "-c", "Release", "-r", runtime,
                    "--self-contained", "true", "-o", str(output),
                    f"-p:BaseOutputPath={ARTIFACTS / 'build'}/",
                    f"-p:Version={version}", f"-p:FileVersion={file_version}"], check=True)


def package_linux(version: str, payload: Path, published: Path | None = None) -> Path:
    if published is None:
        published = ARTIFACTS / "publish-linux-x64"
        publish("linux-x64", version, published)
    release = ROOT / ".artifacts" / "PinyonShift-Launcher-linux-x86_64.tar.gz"
    entries = [("PinyonShift/PinyonShiftLauncher", published / "PinyonShiftLauncher", 0o755),
               ("PinyonShift/pinyon-shift-source.zip", payload, 0o644)]
    with tarfile.open(release, "w:gz") as archive:
        for name, path, mode in entries:
            info = archive.gettarinfo(str(path), arcname=name)
            info.mode, info.uid, info.gid, info.uname, info.gname = mode, 0, 0, "", ""
            info.mtime = 1784764800
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    return release


INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Pinyon Shift</string>
  <key>CFBundleDisplayName</key><string>Pinyon Shift</string>
  <key>CFBundleIdentifier</key><string>studio.deimos.pinyonshift.launcher</string>
  <key>CFBundleVersion</key><string>{version}</string>
  <key>CFBundleShortVersionString</key><string>{version}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>PinyonShiftLauncher</string>
  <key>CFBundleIconFile</key><string>PinyonShift.icns</string>
  <key>LSMinimumSystemVersion</key><string>{minimum}</string>
  <key>LSArchitecturePriority</key><array><string>{architecture}</string></array>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
"""


# The .NET runtime identifier, the release asset's suffix and Info.plist's
# architecture and minimum macOS version for each macOS launcher.
MAC_RUNTIMES = {"osx-arm64": ("macos-arm64", "arm64", "13.0"),
                "osx-x64": ("macos-x86_64", "x86_64", "13.3")}


def package_mac(version: str, payload: Path, published: Path | None = None,
                runtime: str = "osx-arm64") -> Path:
    if sys.platform != "darwin":
        raise SystemExit("package the macOS launcher on a Mac: the app must be signed there")
    suffix, architecture, minimum = MAC_RUNTIMES[runtime]
    if published is None:
        published = ARTIFACTS / f"publish-{runtime}"
        publish(runtime, version, published)
    bundle = ARTIFACTS / "Pinyon Shift.app"
    if bundle.exists():
        shutil.rmtree(bundle)
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    (bundle / "Contents" / "Resources").mkdir()
    # On macOS the single-file host leaves Avalonia's and Skia's native
    # libraries beside it; they belong next to the executable in the bundle.
    for item in published.iterdir():
        if item.is_file() and item.suffix != ".pdb":
            shutil.copy2(item, bundle / "Contents" / "MacOS" / item.name)
    (bundle / "Contents/MacOS/PinyonShiftLauncher").chmod(0o755)
    shutil.copy2(payload, bundle / "Contents/Resources/pinyon-shift-source.zip")
    (bundle / "Contents" / "Info.plist").write_text(INFO_PLIST.format(
        version=version.split("-", 1)[0], architecture=architecture,
        minimum=minimum), encoding="utf-8")
    make_icns(bundle / "Contents" / "Resources" / "PinyonShift.icns")
    # Apple silicon runs only signed code; an ad-hoc signature is enough for
    # an app the player opens themselves (docs/MACOS.md).
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)
    release = ROOT / ".artifacts" / f"PinyonShift-Launcher-{suffix}.zip"
    if release.exists():
        release.unlink()
    # ditto keeps the signature and the bundle's attributes.
    subprocess.run(["ditto", "-c", "-k", "--keepParent", str(bundle), str(release)], check=True)
    return release


def make_icns(path: Path) -> None:
    icon = ROOT / "config" / "steam" / "icon.png"
    iconset = path.with_suffix(".iconset")
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256):
        for scale in (1, 2):
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            subprocess.run(["sips", "-z", str(size * scale), str(size * scale), str(icon),
                            "--out", str(iconset / name)], check=True, capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(path)], check=True)
    shutil.rmtree(iconset)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--platform", choices=("linux-x64", *MAC_RUNTIMES), required=True)
    parser.add_argument("--published", type=Path,
                        help="an existing dotnet publish folder for the platform, made on "
                             "another machine (.NET cross-publishes), instead of publishing here")
    parser.add_argument("--payload", type=Path,
                        help="a source payload built in a checkout, for packaging outside one")
    parser.add_argument("--prebuilt-assets", type=Path,
                        help="the release's prebuilt assets to pin in the payload (TP-1 to TP-3)")
    parser.add_argument("--release-base-url", default="",
                        help="the URL the prebuilt assets are attached at")
    args = parser.parse_args()
    if args.prebuilt_assets and not args.release_base_url:
        parser.error("--prebuilt-assets needs --release-base-url")
    version = json.loads((ROOT / "config" / "release.json").read_text(encoding="utf-8"))["version"]
    payload = args.payload or ARTIFACTS / "pinyon-shift-source.zip"
    if args.payload is None:
        build_payload(payload, args.prebuilt_assets, args.release_base_url)
    release = package_linux(version, payload, args.published) if args.platform == "linux-x64" \
        else package_mac(version, payload, args.published, args.platform)
    print(release)
    return 0


if __name__ == "__main__":
    sys.exit(main())
