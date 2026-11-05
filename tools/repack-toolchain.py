"""Repack the pinned LLVM release into the trimmed archive setup downloads.

TP-1 (docs/TIME_TO_PLAY_BACKLOG.md): the build calls a handful of LLVM's
tools, and several of those are one binary under different names. The
archive keeps each binary once and lists the other names in
pinyon-links.json; setup recreates them as hard links (Windows) or the
archive holds them as symbolic links (Linux).

The output is deterministic: sorted entries, fixed times and modes, so a
repack of the same LLVM release has the same SHA-256 on any machine, and
the CI job that publishes it can be checked against the pinned hash.

    python tools/repack-toolchain.py llvm --platform windows-x64 \
        --source .local/toolchain/llvm-20.1.8 --output llvm.zip
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import lzma
import os
import re
import stat
import sys
import tarfile
import zipfile
from pathlib import Path

# 1980-01-01, the earliest time a zip entry can hold, for both formats.
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_EPOCH = 315532800

# Each kept binary, and the names the build and tools call it by. clang
# picks its driver mode from its own name, llvm-ar its archiver mode, and
# lld its flavour, so the other names are the same file.
LLVM_TOOLS = {
    "windows-x64": {
        "suffix": ".exe",
        "binaries": {
            "clang": ["clang++", "clang-cl", "clang-cpp"],
            "lld": ["lld-link", "ld.lld"],
            "llvm-ar": ["llvm-ranlib", "llvm-lib", "llvm-dlltool"],
            "llvm-nm": [],
            "llvm-rc": [],
            "llvm-mt": [],
            "llvm-profdata": [],
            "llvm-symbolizer": [],
            "llvm-objcopy": ["llvm-strip"],
        },
    },
    "linux-x86_64": {
        "suffix": "",
        # On Linux, clang is a link to clang-20, the real binary.
        "binaries": {
            "clang-20": ["clang", "clang++", "clang-cpp"],
            "lld": ["ld.lld"],
            "llvm-ar": ["llvm-ranlib"],
            "llvm-nm": [],
            "llvm-profdata": [],
            "llvm-symbolizer": [],
            "llvm-objcopy": ["llvm-strip"],
            "llvm-readobj": ["llvm-readelf"],
        },
    },
}

# The compiler's own headers and runtime libraries (lib/clang/<major>).
LLVM_TREES = ["lib/clang"]
LICENSE_FILES = ["LICENSE.TXT"]


def llvm_files(source: Path, platform: str) -> tuple[list[tuple[str, Path]], dict[str, str]]:
    spec = LLVM_TOOLS[platform]
    suffix = spec["suffix"]
    files: list[tuple[str, Path]] = []
    links: dict[str, str] = {}
    for binary, aliases in spec["binaries"].items():
        path = source / "bin" / f"{binary}{suffix}"
        if not path.is_file():
            raise SystemExit(f"{path} is missing from the LLVM release")
        files.append((f"bin/{binary}{suffix}", path.resolve()))
        for alias in aliases:
            links[f"bin/{alias}{suffix}"] = f"{binary}{suffix}"
    for tree in LLVM_TREES:
        root = source / tree
        if not root.is_dir():
            raise SystemExit(f"{root} is missing from the LLVM release")
        for directory, _, names in os.walk(root):
            for name in names:
                path = Path(directory) / name
                files.append((path.relative_to(source).as_posix(), path))
    for name in LICENSE_FILES:
        path = source / name
        if path.is_file():
            files.append((name, path))
    files.sort()
    return files, dict(sorted(links.items()))


def executable(name: str) -> bool:
    return name.startswith("bin/")


def write_zip(output: Path, top: str, files: list[tuple[str, Path]], links: dict[str, str]) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        def add(name: str, data: bytes) -> None:
            info = zipfile.ZipInfo(f"{top}/{name}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            mode = 0o755 if executable(name) else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, data, compresslevel=9)

        for name, path in files:
            add(name, path.read_bytes())
        add("pinyon-links.json", (json.dumps(links, indent=2) + "\n").encode())


def write_tar_xz(output: Path, top: str, files: list[tuple[str, Path]], links: dict[str, str]) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        entries: list[tuple[str, tarfile.TarInfo, bytes | None]] = []
        for name, path in files:
            data = path.read_bytes()
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            info.mode = 0o755 if executable(name) else 0o644
            entries.append((name, info, data))
        for name, target in links.items():
            info = tarfile.TarInfo(f"{top}/{name}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            info.mode = 0o777
            entries.append((name, info, None))
        data = (json.dumps(links, indent=2) + "\n").encode()
        info = tarfile.TarInfo(f"{top}/pinyon-links.json")
        info.size = len(data)
        info.mode = 0o644
        entries.append(("pinyon-links.json", info, data))
        for _, info, data in sorted(entries, key=lambda entry: entry[0]):
            info.mtime = FIXED_EPOCH
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data) if data is not None else None)
    output.write_bytes(lzma.compress(buffer.getvalue(), preset=9 | lzma.PRESET_EXTREME))


def write_sidecar(output: Path, **meta: str) -> None:
    """<output>.json, which tools/apply-prebuilt-pins.py reads to pin the
    asset in a release's toolchain config."""
    sidecar = output.with_name(output.name + ".json")
    sidecar.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def repack_llvm(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    files, links = llvm_files(source, args.platform)
    top = args.top or args.output.name.split(".")[0]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_name(args.output.name + ".partial")
    if args.platform.startswith("windows"):
        write_zip(partial, top, files, links)
    else:
        write_tar_xz(partial, top, files, links)
    partial.replace(args.output)
    write_sidecar(args.output, kind="llvm", platform=args.platform, version=args.version)
    unpacked = sum(path.stat().st_size for _, path in files)
    print(json.dumps({
        "output": str(args.output),
        "sha256": sha256(args.output),
        "size": args.output.stat().st_size,
        "unpacked": unpacked,
        "files": len(files),
        "links": len(links),
    }, indent=2))
    return 0


# The Steam Runtime sniper SDK sysroot holds a whole development system: the
# i386 multiarch half, GCC's and LLVM 11's compilers, Python, Perl, locales
# and documentation. The build reads its headers, its amd64 libraries, the
# pkg-config files, GCC 14's and GCC 10's libraries and headers, and runs
# wayland-scanner and pkg-config from it (cmake/toolchains/linux-x86_64-sniper.cmake).
SYSROOT_DROP = [
    "var/", "usr/share/locale/", "usr/share/i18n/", "usr/share/doc/", "usr/share/man/",
    "usr/share/info/", "usr/share/perl/", "usr/share/perl5/", "usr/share/fish/",
    "usr/share/zoneinfo/", "usr/share/gir-1.0/", "usr/share/cmake-3.25/", "usr/share/lintian/",
    "usr/share/bash-completion/", "usr/share/zsh/", "usr/share/gdb/", "usr/share/python3/",
    "usr/lib/i386-linux-gnu/", "lib/i386-linux-gnu/", "usr/i686-linux-gnu/", "usr/lib32/",
    "usr/libx32/", "lib32/", "libx32/", "usr/lib/gcc-cross/", "usr/lib/llvm-11/",
    "usr/lib/python3/", "usr/lib/python3.9/", "usr/lib/git-core/", "usr/libexec/",
    "usr/lib/x86_64-linux-gnu/dri/", "usr/lib/x86_64-linux-gnu/perl/",
    "usr/lib/x86_64-linux-gnu/perl-base/", "usr/lib/x86_64-linux-gnu/gconv/",
    "usr/lib/gcc-14/libexec/", "usr/lib/gcc-14/bin/",
]
SYSROOT_DROP_NAMES = re.compile(
    r"^(cc1|cc1plus|cc1obj|cc1objplus|lto1|lto-wrapper|collect2|f951)$"
    r"|^lib(LLVM|clang|python3|perl)[-.0-9]")
SYSROOT_KEEP_BINARIES = {"usr/bin/wayland-scanner", "usr/bin/pkg-config", "usr/bin/pkgconf",
                         "usr/bin/x86_64-linux-gnu-pkg-config"}


def sysroot_kept(name: str) -> bool:
    if any(name.startswith(prefix) for prefix in SYSROOT_DROP):
        return False
    if name.startswith(("usr/bin/", "bin/", "sbin/", "usr/sbin/")):
        return name in SYSROOT_KEEP_BINARIES
    return not SYSROOT_DROP_NAMES.match(name.rsplit("/", 1)[-1])


def repack_sysroot(args: argparse.Namespace) -> int:
    """The sniper sysroot without what the build never reads, as a
    deterministic tar.xz that keeps its symbolic links."""
    source = args.source.resolve()
    buffer = io.BytesIO()
    kept = dropped = 0
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        entries = []
        for directory, folders, names in os.walk(source):
            folders.sort()
            for name in folders + names:
                path = Path(directory) / name
                relative = path.relative_to(source).as_posix()
                if path.is_dir() and not path.is_symlink():
                    continue
                if not sysroot_kept(relative):
                    dropped += path.lstat().st_size
                    continue
                entries.append((relative, path))
        for relative, path in sorted(entries):
            info = tarfile.TarInfo(f"{args.top}/{relative}")
            status = path.lstat()
            info.mtime = FIXED_EPOCH
            info.uid = info.gid = 0
            info.mode = 0o755 if status.st_mode & 0o111 else 0o644
            if path.is_symlink():
                info.type = tarfile.SYMTYPE
                info.linkname = os.readlink(path)
                info.mode = 0o777
                archive.addfile(info)
                continue
            info.size = status.st_size
            kept += status.st_size
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_name(args.output.name + ".partial")
    partial.write_bytes(lzma.compress(buffer.getvalue(), preset=args.preset))
    partial.replace(args.output)
    write_sidecar(args.output, kind="sysroot", platform="linux-x86_64", version=args.version)
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output),
                      "size": args.output.stat().st_size, "unpacked": kept,
                      "dropped": dropped}, indent=2))
    return 0


def tree_files(source: Path) -> list[tuple[str, Path]]:
    files = []
    for directory, _, names in os.walk(source):
        for name in names:
            path = Path(directory) / name
            files.append((path.relative_to(source).as_posix(), path))
    return sorted(files)


def repack_kit(args: argparse.Namespace) -> int:
    """A built kit folder (tools/build-shiftglue-kit.ps1, pinyon_setup.py
    kit) as a deterministic archive: zip on Windows, tar.xz elsewhere."""
    source = args.source.resolve()
    files = tree_files(source)
    links: dict[str, str] = {}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_name(args.output.name + ".partial")
    if args.output.suffix == ".zip":
        write_zip(partial, args.top, files, links)
    else:
        write_tar_xz(partial, args.top, files, links)
    partial.replace(args.output)
    kit = json.loads((source / "kit.json").read_text(encoding="utf-8"))
    write_sidecar(args.output, kind=args.kind, platform=kit["platform"],
                  revision=kit["shiftglue_revision"])
    print(json.dumps({
        "output": str(args.output),
        "sha256": sha256(args.output),
        "size": args.output.stat().st_size,
        "unpacked": sum(path.stat().st_size for _, path in files),
        "files": len(files),
    }, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    llvm = commands.add_parser("llvm", help="trim and repack an LLVM release")
    llvm.add_argument("--platform", required=True, choices=sorted(LLVM_TOOLS))
    llvm.add_argument("--source", required=True, type=Path, help="the unpacked LLVM release")
    llvm.add_argument("--output", required=True, type=Path)
    llvm.add_argument("--top", help="top-level folder in the archive (default: the output's stem)")
    llvm.add_argument("--version", required=True, help="the LLVM release, as the config pins it")
    kit = commands.add_parser("kit", help="archive a built ShiftGlue kit folder")
    kit.add_argument("--source", required=True, type=Path)
    kit.add_argument("--output", required=True, type=Path, help=".zip or .tar.xz")
    kit.add_argument("--top", default="shiftglue-kit")
    kit.add_argument("--kind", default="kit", choices=["kit", "apk-shell"])
    sysroot = commands.add_parser("sysroot", help="trim and repack the Linux sniper sysroot")
    sysroot.add_argument("--source", required=True, type=Path)
    sysroot.add_argument("--output", required=True, type=Path)
    sysroot.add_argument("--top", default="sysroot")
    sysroot.add_argument("--preset", type=int, default=6, help="xz preset")
    sysroot.add_argument("--version", required=True, help="the sysroot release, as the config pins it")
    args = parser.parse_args(argv)
    return {"llvm": repack_llvm, "kit": repack_kit, "sysroot": repack_sysroot}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
