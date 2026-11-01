"""Pin a release's prebuilt assets in the launcher payload's toolchain config.

TP-1 to TP-3 (docs/TIME_TO_PLAY_BACKLOG.md): the release workflow builds the
trimmed LLVM, the trimmed Linux sysroot and the ShiftGlue kits, attaches them
to the release, and rewrites the payload's config/release-toolchain.json so
setup downloads them from that release by SHA-256. The checked-in config
keeps the upstream downloads and no kit, so a developer checkout builds
from source.

Each asset has the sidecar <asset>.json that tools/repack-toolchain.py
writes beside it: {"kind": "llvm" | "sysroot" | "kit" | "apk-shell",
"platform": ..., "version": ... (tools) or "revision": ... (kits)}.

    python tools/apply-prebuilt-pins.py --config payload/config/release-toolchain.json \
        --assets .artifacts/prebuilt \
        --base-url https://github.com/arcanite24/pinyon-shift/releases/download/v0.8.0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PLATFORMS = ("windows-x64", "linux-x86_64", "macos-arm64", "android-arm64")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def tools_for(config: dict, platform: str) -> dict:
    """The section of the config that holds a platform's tools."""
    if platform == "windows-x64":
        return config
    return config["posix"][platform]


def apply(config: dict, assets: Path, base_url: str) -> list[str]:
    changes = []
    revision = config["rexglue"]["revision"]
    for sidecar in sorted(assets.glob("*.json")):
        asset = sidecar.with_suffix("")
        if not asset.is_file():
            raise SystemExit(f"{sidecar.name} describes a missing asset")
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        platform = meta["platform"]
        if platform not in PLATFORMS:
            raise SystemExit(f"{sidecar.name}: unknown platform {platform}")
        url = f"{base_url.rstrip('/')}/{asset.name}"
        digest = sha256(asset)
        kind = meta["kind"]
        if kind in ("llvm", "sysroot"):
            item = tools_for(config, platform)[kind]
            if meta.get("version") != item["version"]:
                raise SystemExit(f"{asset.name} repacks {kind} {meta.get('version')}, "
                                 f"but the config pins {item['version']}")
            item["url"] = url
            item["sha256"] = digest
            item["repacked"] = True
        elif kind in ("kit", "apk-shell"):
            if meta.get("revision") != revision:
                raise SystemExit(f"{asset.name} was built from ShiftGlue {meta.get('revision')}, "
                                 f"but the config pins {revision}")
            section = "shiftglue_kit" if kind == "kit" else "android_shell"
            config.setdefault(section, {})[platform] = {
                "revision": revision, "url": url, "sha256": digest}
        else:
            raise SystemExit(f"{sidecar.name}: unknown kind {kind}")
        changes.append(f"{kind} {platform}: {asset.name} {digest}")
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    changes = apply(config, args.assets, args.base_url)
    args.config.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print("\n".join(changes) if changes else "No prebuilt assets to pin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
