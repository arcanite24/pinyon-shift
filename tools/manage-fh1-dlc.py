#!/usr/bin/env python3
"""Import verified owned FH1 content into the runtime's existing content tree."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CONTENT = Path("0000000000000000/4D5309C9")
PACKAGE_ID = re.compile(r"[0-9A-F]{1,42}\Z")
MAGIC = (b"LIVE", b"PIRS", b"CON ")
MAX_PACKAGE = 2 * 1024**3
RALLY = "6F6992766050D818245ADD408031E280FB5F4E634D"


def long_path(path: Path) -> Path:
    path = path.resolve()
    if os.name == "nt" and not str(path).startswith("\\\\?\\"):
        value = str(path)
        return Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)
    return path


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def catalog() -> dict:
    return json.loads((ROOT / "config/supported-dlc.json").read_text(encoding="utf-8"))


def import_record(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if (isinstance(record, dict) and record.get("package_id") == path.stem and
                isinstance(record.get("display_name", path.stem), str) and
                all(isinstance(record[key], str) and re.fullmatch(r"[0-9A-F]{64}", record[key])
                    for key in ("sha256", "payload_sha256", "header_sha256") if key in record)):
            return record
    except (OSError, ValueError):
        pass
    return None


def package_paths(state: Path, package_id: str) -> tuple[Path, Path, Path]:
    if not PACKAGE_ID.fullmatch(package_id):
        raise ValueError("invalid package ID")
    title = state / "user" / CONTENT
    return (title / "00000002" / package_id,
            title / "Disabled" / "00000002" / package_id,
            title / "Headers" / "00000002" / (package_id + ".header"))


def payload_catalog(root: Path) -> tuple[list[dict], str]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("content contains a symbolic link")
        if path.is_file():
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest().upper()
            files.append(dict(path=path.relative_to(root).as_posix(),
                              size=path.stat().st_size, sha256=digest))
    digest = hashlib.sha256(json.dumps(files, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest().upper()
    return files, digest


def inspect(stream, size: int, manifest: dict) -> tuple[dict, dict]:
    header = stream.read(0x971A)
    if len(header) != 0x971A or header[:4] not in MAGIC:
        raise ValueError("not an Xbox 360 content package")
    if header[0x360:0x364].hex().upper() != manifest["title_id"]:
        raise ValueError("package belongs to another game")
    if header[0x344:0x348].hex().upper() != manifest["content_type"]:
        raise ValueError("expected Marketplace DLC, not a title update or save")
    if not len(header) <= size <= MAX_PACKAGE:
        raise ValueError("invalid DLC package size")
    content_id = header[0x32C:0x340].hex().upper()
    package = next((p for p in manifest["packages"] if p["content_id"] == content_id), None)
    if package is None:
        raise ValueError("this DLC package is not in the verified catalog")
    digest = hashlib.sha256(header)
    total = len(header)
    while block := stream.read(4 * 1024**2):
        total += len(block)
        if total > size:
            raise ValueError("package size changed while reading")
        digest.update(block)
    if total != size:
        raise ValueError("incomplete DLC package")
    sha = digest.hexdigest().upper()
    for rejected in package["rejected"]:
        if rejected["sha256"] == sha:
            raise ValueError(f'{package["display_name"]}: {rejected["reason"]}')
    variant = next((v for v in package["accepted"] if v["size"] == size and v["sha256"] == sha), None)
    if variant is None:
        raise ValueError(f'{package["display_name"]}: SHA-256 differs from the verified inputs')
    return package, variant


def safe_archive_path(name: str) -> None:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in name or "\0" in name:
        raise ValueError("unsafe ZIP member path")


def stage_inputs(source: Path, temporary: Path, manifest: dict) -> list[tuple[Path, dict, dict]]:
    """Read only the inputs; never extract wrapper member paths to the host."""
    found = {}

    def accept(stream, size: int) -> None:
        if size > MAX_PACKAGE:
            raise ValueError("DLC package exceeds the supported size")
        path = temporary / f"input-{len(found)}.stfs"
        with path.open("wb") as output:
            # Bound ZIP inflation even if its size fields are inconsistent.
            copied = 0
            while block := stream.read(4 * 1024**2):
                copied += len(block)
                if copied > size:
                    raise ValueError("package exceeds its declared size")
                output.write(block)
        with path.open("rb") as file:
            package, variant = inspect(file, size, manifest)
        id = package["package_id"]
        if id in found:
            previous = found[id][2]
            if previous["sha256"] != variant["sha256"]:
                raise ValueError(f'{package["display_name"]}: conflicting package variants; select one input')
            path.unlink()
            return
        found[id] = (path, package, variant)

    inputs = sorted(source.rglob("*")) if source.is_dir() else [source]
    for path in inputs:
        if path.is_symlink():
            raise ValueError("input folder contains a symbolic link")
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            magic = stream.read(4)
        if magic in MAGIC:
            with path.open("rb") as stream:
                accept(stream, path.stat().st_size)
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    safe_archive_path(member.filename)
                    if member.is_dir():
                        continue
                    with archive.open(member) as stream:
                        prefix = stream.read(4)
                    if prefix in MAGIC:
                        with archive.open(member) as stream:
                            accept(stream, member.file_size)
        elif not source.is_dir():
            raise ValueError("choose a raw DLC package, DLC folder or ZIP")
    if not found:
        raise ValueError("no FH1 DLC packages found")
    return list(found.values())


@contextlib.contextmanager
def mutation_lock(state: Path):
    metadata = state / "dlc"
    metadata.mkdir(parents=True, exist_ok=True)
    with (metadata / "import.lock").open("a+b") as lock:
        lock.seek(0)
        lock.write(b"\0")
        lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if os.name == "nt":
                running = subprocess.check_output(
                    ["tasklist.exe", "/FI", "IMAGENAME eq pinyon_shift.exe", "/FO", "CSV", "/NH"],
                    creationflags=subprocess.CREATE_NO_WINDOW)
                if b'"pinyon_shift.exe"' in running.lower():
                    raise ValueError("close the game before changing DLC")
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def verified_content(state: Path, id: str, *, require_enabled: bool = False) -> tuple[Path, dict, dict]:
    """Validate the installed payload and original licence before using it."""
    state = long_path(state)
    active, inactive, header = package_paths(state, id)
    if active.exists() and inactive.exists():
        raise ValueError("both enabled and disabled copies exist")
    content = active if active.is_dir() else inactive
    if not content.is_dir() or not header.is_file():
        raise ValueError("import the verified package first")
    if require_enabled and content != active:
        raise ValueError("enable the imported package first")
    record = import_record(state / "dlc" / (id + ".json"))
    package = next((p for p in catalog()["packages"] if p["package_id"] == id), None)
    variant = next((v for v in package["accepted"] if record and v["sha256"] == record.get("sha256")), None) if package else None
    if not variant:
        raise ValueError("import record is damaged; import the original package again")
    data = header.read_bytes()
    if (len(data) not in (328, 332) or
            record.get("header_sha256") != hashlib.sha256(data).hexdigest().upper() or
            record.get("license_mask") != variant["license_mask"] or
            int.from_bytes(data[328:332], "little") != int(variant["license_mask"], 16)):
        raise ValueError("content header or licence changed; import the original package again")
    _, digest = payload_catalog(content)
    if digest != package["payload_sha256"] or record.get("payload_sha256") != digest:
        raise ValueError("installed content is incomplete or changed; import the original package again")
    return content, package, record


def list_content(state: Path) -> list[dict]:
    state = long_path(state)
    records = []
    metadata = state / "dlc"
    for path in sorted(metadata.glob("*.json")):
        id = path.stem
        if not PACKAGE_ID.fullmatch(id):
            continue
        enabled, disabled, header = package_paths(state, id)
        record = import_record(path)
        if record is None:
            records.append(dict(package_id=id, display_name=id, enabled=enabled.is_dir(),
                                status="metadata_invalid"))
            continue
        record["enabled"] = enabled.is_dir()
        record["status"] = ("conflict" if enabled.exists() and disabled.exists() else
                            "missing" if not (enabled.is_dir() or disabled.is_dir()) or not header.is_file()
                            else "gameplay_unverified")
        if header.is_file() and record.get("header_sha256") != hashlib.sha256(header.read_bytes()).hexdigest().upper():
            record["status"] = "missing"
        if id == RALLY:
            # Report generated assets separately from gameplay qualification.
            try:
                prepared = json.loads((state / "cache/rally_adapter/preparation.json").read_text())
                recipe = prepared["recipe"]
                record["rally_assets_cached"] = (prepared["schema"] == "pinyon-shift.rally-preparation.v1" and
                    recipe["package_sha256"] == record["sha256"] and
                    recipe["header_sha256"] == record["header_sha256"] and
                    (state / "cache/rally_adapter/game/media/db/gamedb.slt").is_file() and
                    (state / "cache/rally_adapter/rally-stage.toml").is_file() and
                    (state / "cache/rally_adapter/rally-pace.toml").is_file())
            except (OSError, ValueError, KeyError, TypeError):
                record["rally_assets_cached"] = False
        records.append(record)
    known = {r["package_id"] for r in records}
    for folder in (state / "user" / CONTENT / "00000002",
                   state / "user" / CONTENT / "Disabled" / "00000002"):
        if not folder.exists():
            continue
        for path in folder.iterdir():
            if path.is_dir() and path.name not in known:
                records.append(dict(package_id=path.name, display_name=path.name,
                                    enabled=folder.name == "00000002" and folder.parent.name == "4D5309C9",
                                    status="unmanaged"))
    return records


def import_content(source: Path, state: Path, extractor: Path) -> list[dict]:
    state = long_path(state)
    with mutation_lock(state), tempfile.TemporaryDirectory(prefix="staging-", dir=state / "dlc") as directory:
        staging = Path(directory)
        inputs = stage_inputs(source, staging, catalog())
        repair = set()
        # Reject batch conflicts before publishing any package.
        for _, package, variant in inputs:
            id = package["package_id"]
            enabled, disabled, _ = package_paths(state, id)
            record_path = state / "dlc" / (id + ".json")
            if enabled.exists() or disabled.exists():
                if enabled.exists() and disabled.exists():
                    raise ValueError(f'{package["display_name"]}: both enabled and disabled copies exist')
                if not record_path.is_file():
                    raise ValueError(f'{package["display_name"]}: existing unmanaged content; leave it in place')
                record = import_record(record_path)
                if record and record.get("sha256") and record["sha256"] != variant["sha256"]:
                    raise ValueError(f'{package["display_name"]}: a different variant is already installed')
                _, digest = payload_catalog(enabled if enabled.exists() else disabled)
                if digest != package["payload_sha256"]:
                    repair.add(id)
        for index, (input_path, package, variant) in enumerate(inputs):
            id = package["package_id"]
            enabled, disabled, header = package_paths(state, id)
            record_path = state / "dlc" / (id + ".json")
            if id not in repair and (enabled.exists() or disabled.exists()) and header.is_file():
                record = import_record(record_path)
                if record and record.get("header_sha256") == hashlib.sha256(header.read_bytes()).hexdigest().upper():
                    continue
            extracted = staging / str(index)
            result = subprocess.run([str(extractor), "--dlc-files", str(input_path), str(extracted), id],
                                    capture_output=True, text=True)
            if result.returncode:
                raise ValueError(result.stderr.strip() or "DLC extraction failed")
            content = extracted / CONTENT / "00000002" / id
            _, digest = payload_catalog(content)
            if digest != package["payload_sha256"]:
                raise ValueError(f'{package["display_name"]}: extracted content failed verification')
            staged_header = extracted / CONTENT / "Headers" / "00000002" / (id + ".header")
            header_data = staged_header.read_bytes()
            if len(header_data) not in (328, 332) or int.from_bytes(header_data[328:332], "little") != int(variant["license_mask"], 16):
                raise ValueError("content header failed verification")
            record = dict(package_id=id, display_name=package["display_name"],
                          sha256=variant["sha256"], payload_sha256=digest,
                          license_mask=variant["license_mask"], file_count=package["file_count"],
                          header_sha256=hashlib.sha256(header_data).hexdigest().upper())
            header.parent.mkdir(parents=True, exist_ok=True)
            disabled.parent.mkdir(parents=True, exist_ok=True)
            # An orphan header/record is recoverable; content becomes visible last.
            staged_header.replace(header)
            write_json(record_path, record)
            if id in repair:
                installed = enabled if enabled.exists() else disabled
                retained = state / "dlc" / "replaced" / id / uuid.uuid4().hex
                retained.parent.mkdir(parents=True, exist_ok=True)
                installed.rename(retained)
                try:
                    content.rename(installed)
                except OSError:
                    retained.rename(installed)
                    raise
            elif not (enabled.exists() or disabled.exists()):
                content.rename(disabled)
    return list_content(state)


def set_enabled(state: Path, id: str, enabled: bool) -> list[dict]:
    state = long_path(state)
    with mutation_lock(state):
        record_path = state / "dlc" / (id + ".json")
        active, inactive, header = package_paths(state, id)
        if not record_path.is_file() or (enabled and not header.is_file()):
            raise ValueError("import the verified package first")
        source, destination = (inactive, active) if enabled else (active, inactive)
        if enabled:
            # Repeated enable must also reject an already active damaged package.
            verified_content(state, id)
        if destination.exists():
            if source.exists():
                raise ValueError("both enabled and disabled copies exist")
            return list_content(state)
        if not source.is_dir():
            raise ValueError("the imported content is missing")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
    return list_content(state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "import", "enable", "disable"))
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--package-id")
    parser.add_argument("--game-root", type=Path, default=ROOT / ".local/game/base")
    parser.add_argument("--extractor", type=Path, default=ROOT / "out/build/win-amd64-release/pinyon_shift_fh1_archive_extract.exe")
    args = parser.parse_args()
    try:
        state = args.state_root.resolve()
        if args.action == "list":
            records = list_content(state)
        elif args.action == "import":
            if args.source is None:
                raise ValueError("choose a DLC input")
            records = import_content(args.source.resolve(), state, args.extractor.resolve())
        else:
            if args.package_id is None:
                raise ValueError("choose an imported package")
            records = set_enabled(state, args.package_id, args.action == "enable")
            if args.action == "enable" and args.package_id == RALLY:
                prepared = subprocess.run([sys.executable, str(ROOT / "tools/prepare-fh1-rally.py"),
                    "--state-root", str(state), "--game-root", str(args.game_root.resolve()),
                    "--extractor", str(args.extractor.resolve())], capture_output=True, text=True)
                if prepared.returncode:
                    raise ValueError("Rally is enabled, but asset preparation failed: " +
                                     (prepared.stderr.strip() or "preparation stopped"))
                records = list_content(state)
        print(json.dumps(dict(packages=records)))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
