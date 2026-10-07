#!/usr/bin/env python3
"""Verify a local FH1 title update against the three base executables.

Each patch is applied with the SDK loader (through the archive extractor) and
every page of the result is checked against the hash chain in the patched
headers. A base built for another disc pressing can still be compatible: the
patch only needs the regions it copies from to be identical, and the page
hashes prove the result. Nothing is installed or written beside the inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(path: Path) -> tuple[int, str]:
    with path.open("rb") as file:
        return path.stat().st_size, hashlib.file_digest(file, "sha256").hexdigest().upper()


def xex_headers(data: bytes) -> tuple[int, dict[int, int]]:
    if len(data) < 24 or data[:4] != b"XEX2":
        raise ValueError("not a XEX2 executable or patch")
    _, _, size, _, security, count = struct.unpack_from(">6I", data)
    if not 24 + count * 8 <= size <= len(data):
        raise ValueError("invalid XEX2 header bounds")
    headers = dict(struct.iter_unpack(">II", data[24:24 + count * 8]))
    if len(headers) != count:
        raise ValueError("duplicate XEX2 optional header")
    return security, headers


def header_data(data: bytes, headers: dict[int, int], key: int, size: int) -> bytes:
    offset = headers.get(key, 0)
    limit = struct.unpack_from(">I", data, 8)[0]
    table_end = 24 + struct.unpack_from(">I", data, 20)[0] * 8
    if offset < table_end or offset + size > limit:
        raise ValueError(f"missing or invalid XEX2 header {key:08X}")
    return data[offset:offset + size]


PAGE_SIZE_4KB = 0x10000000


def verify_pages(headers: bytes, image: bytes) -> dict:
    """Check every page against the patched security info's hash chain.

    Each descriptor's digest covers the following block plus that block's own
    descriptor; the first block is covered by the section digest."""
    xex_headers(headers)
    security = struct.unpack_from(">I", headers, 16)[0]
    if security + 0x184 > len(headers):
        raise ValueError("invalid XEX2 security header")
    flags, = struct.unpack_from(">I", headers, security + 0x10C)
    page = 0x1000 if flags & PAGE_SIZE_4KB else 0x10000
    count, = struct.unpack_from(">I", headers, security + 0x180)
    if security + 0x184 + count * 24 > len(headers):
        raise ValueError("invalid XEX2 page descriptor table")
    expected = headers[security + 0x114:security + 0x128]
    offset, failing = 0, []
    for index in range(count):
        descriptor = headers[security + 0x184 + index * 24:security + 0x184 + (index + 1) * 24]
        size = (struct.unpack_from(">I", descriptor)[0] >> 4) * page
        block = image[offset:offset + size]
        if len(block) != size or hashlib.sha1(block + descriptor).digest() != expected:
            failing.append(index)
        expected = descriptor[4:]
        offset += size
    return {"pages": count, "failing_pages": failing, "covers_image": offset == len(image),
            "verified": not failing and offset == len(image)}


def apply_patch(extractor: Path, base: Path, patch: Path, work: Path) -> tuple[bytes, bytes]:
    headers, image = work / (patch.name + ".headers"), work / (patch.name + ".image")
    result = subprocess.run([str(extractor.resolve()), "--title-update-image", str(base.resolve()),
                             str(patch.resolve()), str(headers), str(image)],
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"patch application failed with exit {result.returncode}")
    return headers.read_bytes(), image.read_bytes()


def check_source(base: bytes, patch: bytes, update: dict) -> dict:
    security, headers = xex_headers(base)
    _, patch_headers = xex_headers(patch)
    execution = header_data(base, headers, 0x40006, 24)
    descriptor = header_data(patch, patch_headers, 0x5FF, 0x4C)
    if security < 24 + len(headers) * 8 or security + 264 > struct.unpack_from(">I", base, 8)[0]:
        raise ValueError("invalid XEX2 security header")
    media, version, _, title = struct.unpack_from(">4I", execution)
    _, target, source = struct.unpack_from(">3I", descriptor)
    signature = hashlib.sha1(base[security + 8:security + 264]).hexdigest().upper()
    expected_signature = descriptor[12:32].hex().upper()
    checks = {
        "title_id_matches": f"{title:08X}" == update["title_id"],
        "media_id_matches": f"{media:08X}" == update["media_id"],
        "source_version_matches": version == source,
        "source_signature_matches": signature == expected_signature,
    }
    if f"{source:08X}" != update["source_version"] or f"{target:08X}" != update["target_version"]:
        raise ValueError("patch versions do not match the verified update manifest")
    return {"compatible": all(checks.values()), "media_id": f"{media:08X}",
            "version": f"{version:08X}", "source_signature_sha1": signature,
            "required_signature_sha1": expected_signature, **checks}


INSTALL_FOLDER = "title-update-v4"


def install(extracted: Path, update: dict, state_root: Path) -> dict:
    """Publish the verified update files into <state>/title-update-v4.

    The folder is replaced atomically; a different earlier copy is kept as
    title-update-v4.previous-<n>. The v4 build mounts this folder as update:."""
    target = state_root / INSTALL_FOLDER
    wanted = {file["guest_path"]: (file["size_bytes"], file["sha256"]) for file in update["files"]}
    if target.is_dir() and {path.name: fingerprint(path) for path in target.iterdir()} == wanted:
        return {"installed": str(target), "reused": True}
    state_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=INSTALL_FOLDER + ".staging-", dir=state_root))
    try:
        for name in wanted:
            shutil.copyfile(extracted / name, staging / name)
            if fingerprint(staging / name) != wanted[name]:
                raise ValueError(f"copied file failed verification: {name}")
        if target.exists():
            n = 1
            while (state_root / f"{INSTALL_FOLDER}.previous-{n}").exists():
                n += 1
            target.rename(state_root / f"{INSTALL_FOLDER}.previous-{n}")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"installed": str(target), "reused": False}


def verify(package: Path, base_root: Path, extractor: Path, install_root: Path | None = None) -> dict:
    if package.is_dir():
        candidates = list(package.rglob("tu00000001_00000000"))
        if len(candidates) != 1:
            raise ValueError("expected exactly one tu00000001_00000000 package in the folder")
        package = candidates[0]
    manifest = json.loads((ROOT / "config/supported-title-updates.json").read_text())
    size, digest = fingerprint(package)
    update = next((entry for entry in manifest["updates"]
                   if (entry["package"]["size_bytes"], entry["package"]["sha256"]) ==
                   (size, digest)), None)
    if update is None:
        raise ValueError("title update has no exact size and SHA-256 match")
    pinned_bases = {module["base_sha256"]: module for base in update.get("verified_bases", [])
                    for module in base["modules"]}
    if not extractor.is_file():
        raise ValueError("build the pinyon_shift_fh1_archive_extract target first")
    with tempfile.TemporaryDirectory(prefix="pinyon-tu-") as temporary:
        extracted = Path(temporary) / "files"
        extraction = subprocess.run([str(extractor.resolve()), "--title-update-files",
                                     str(package.resolve()), str(extracted)],
                                    capture_output=True, text=True)
        if extraction.returncode:
            raise ValueError(extraction.stderr.strip() or
                             f"title-update extraction failed with exit {extraction.returncode}")
        if {file.name for file in extracted.iterdir()} != {file["guest_path"] for file in update["files"]}:
            raise ValueError("unexpected title-update file list")
        sources = []
        for file in update["files"]:
            path = extracted / file["guest_path"]
            if fingerprint(path) != (file["size_bytes"], file["sha256"]):
                raise ValueError(f"extracted file failed verification: {path.name}")
            if path.suffix == ".xexp":
                base_path = base_root / path.name[:-1]
                source = {"guest_path": base_path.name}
                if not base_path.is_file():
                    source.update(compatible=False, error="base executable is missing")
                    sources.append(source)
                    continue
                # Signature fields describe the disc the patch was built for;
                # they are informational once the patched pages verify.
                built_for = check_source(base_path.read_bytes(), path.read_bytes(), update)
                source["built_for_this_base"] = built_for.pop("compatible")
                source.update(built_for)
                try:
                    headers, image = apply_patch(extractor, base_path, path, Path(temporary))
                except ValueError as error:
                    source.update(compatible=False, error=str(error))
                    sources.append(source)
                    continue
                pages = verify_pages(headers, image)
                pinned = pinned_bases.get(fingerprint(base_path)[1], {})
                image_sha256 = hashlib.sha256(image).hexdigest().upper()
                source.update(pages_verified=f"{pages['pages'] - len(pages['failing_pages'])}/{pages['pages']}",
                              failing_pages=pages["failing_pages"], image_sha256=image_sha256,
                              image_matches_pinned=pinned.get("image_sha256") == image_sha256 if pinned else None,
                              compatible=pages["verified"] and (not pinned or pinned["image_sha256"] == image_sha256))
                sources.append(source)
        with zipfile.ZipFile(extracted / "media.zip") as media:
            # FH1 uses a custom compression method; the pinned whole-file hash
            # above verifies its payload without pretending zipfile can decode it.
            media_files = sum(not file.is_dir() for file in media.infolist())
        compatible = all(source["compatible"] for source in sources)
        installation = None
        if install_root is not None:
            if not compatible:
                raise ValueError("not installed: the update does not verify against these executables")
            installation = install(extracted, update, install_root)
        return {"update_id": update["id"], "package_verified": True, "install": installation,
                "compatible": compatible,
                "native_port_ready": False, "built_for_media_id": update["media_id"],
                "built_for_source_version": update["source_version"],
                "media_files": media_files, "executables": sources}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--base-root", type=Path, default=ROOT / ".local/game/base")
    parser.add_argument("--extractor", type=Path,
                        default=ROOT / "out/build/win-amd64-release/pinyon_shift_fh1_archive_extract.exe")
    parser.add_argument("--install", type=Path, metavar="STATE_ROOT",
                        help=f"after verification, publish the update into STATE_ROOT/{INSTALL_FOLDER}")
    args = parser.parse_args()
    try:
        result = verify(args.package, args.base_root, args.extractor, args.install)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print(json.dumps({"package_verified": False, "error": str(error)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["compatible"] else 1


if __name__ == "__main__":
    sys.exit(main())
