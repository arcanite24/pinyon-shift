#!/usr/bin/env python3
"""Pinyon Shift for Android, driven from the player's PC (AP-6.1).

The package holds the game translated from the player's own disc, so, like
pinyon_shift.exe, it is built on their PC and installed on their own device;
the device never compiles and nothing is uploaded anywhere. The extracted
game files travel from the PC to the device over adb.

  pinyon.py android doctor [--install [--accept-licenses]]
                                         check (or install) the SDK, NDK, JDK
  pinyon.py android build                cross-compile and package the APK
  pinyon.py android package              package already built libraries
  pinyon.py android install              adb install -r the package
  pinyon.py android push-data            copy the extracted game to the device
  pinyon.py android run [--null-gpu] [--route FILE [--seed DIR] --wait] [-- args]
  pinyon.py android pull-logs            copy the state's logs and crashes back
  pinyon.py android stop                 stop the game on the device

Every command takes --serial for adb when more than one device is connected.
Pinned versions live in config/android-toolchain.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"
CONFIG = json.loads((ROOT / "config" / "android-toolchain.json").read_text(encoding="utf-8"))
PACKAGE = CONFIG["package"]
ACTIVITY = CONFIG["activity"]
WORK = ROOT / ".local" / "android"
# Where tools/build-android.ps1 unpacks the pinned command-line tools and JDK
# when the PC has no Android SDK or JDK of its own.
LOCAL_SDK = ROOT / CONFIG["bootstrap"]["android_sdk_path"]
LOCAL_JDK = ROOT / CONFIG["bootstrap"]["jdk"]["install_path"]
DEVICE_FILES = f"/sdcard/Android/data/{PACKAGE}/files"
# The libraries the package carries besides the C++ runtime, in load order.
NATIVE_LIBRARIES = (
    "librexruntime.so",
    "librexgpu-fh1.so",
    "libpinyon_shift_SpeechFacade_default.so",
    "libpinyon_shift_XMediaFacade_default.so",
    "libmain.so",
)
# libadrenotools' hooks, which the app does not load: the custom GPU driver
# loader (Mesa Turnip) finds them in the native library folder.
ADRENOTOOLS_HOOKS = (
    "libhook_impl.so",
    "libmain_hook.so",
    "libfile_redirect_hook.so",
    "libgsl_alloc_hook.so",
)


class AndroidError(RuntimeError):
    pass


def _exe(name: str) -> str:
    return name + (".exe" if WINDOWS else "")


def _script(name: str) -> str:
    return name + (".bat" if WINDOWS else "")


def sdk_root() -> Path:
    candidates = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    if WINDOWS and os.environ.get("LOCALAPPDATA"):
        candidates.append(str(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk"))
    home = Path.home()
    candidates += [str(home / "Library" / "Android" / "sdk"), str(home / "Android" / "Sdk"),
                   str(LOCAL_SDK)]
    for candidate in candidates:
        if candidate and (Path(candidate) / "platform-tools").is_dir():
            return Path(candidate)
    # An SDK with only the command-line tools yet, which doctor --install
    # completes.
    for candidate in candidates:
        if candidate and (Path(candidate) / "cmdline-tools" / "latest" / "bin").is_dir():
            return Path(candidate)
    raise AndroidError("the Android SDK was not found; set ANDROID_HOME "
                       "(Android Studio's SDK Manager or the command-line tools install it)")


def java_home() -> Path | None:
    """JAVA_HOME, or the JDK tools/build-android.ps1 unpacked."""
    if os.environ.get("JAVA_HOME"):
        return Path(os.environ["JAVA_HOME"])
    if (LOCAL_JDK / "bin" / _exe("javac")).is_file():
        return LOCAL_JDK
    return None


def rexsdk_dir() -> Path:
    """The ShiftGlue SDK the game builds against: the submodule in a
    checkout, the pinned clone in .local/rexglue in a launcher install
    (tools/prepare-rexglue.ps1), or PINYON_REXSDK_DIR."""
    if os.environ.get("PINYON_REXSDK_DIR"):
        return Path(os.environ["PINYON_REXSDK_DIR"])
    submodule = ROOT / "thirdparty" / "shiftglue-sdk"
    if (submodule / "CMakeLists.txt").is_file():
        return submodule
    return ROOT / ".local" / "rexglue"


class Tools:
    def __init__(self) -> None:
        self.sdk = sdk_root()
        pins = CONFIG["android_sdk"]
        self.ndk = self.sdk / "ndk" / pins["ndk"]
        self.build_tools = self.sdk / "build-tools" / pins["build_tools"]
        self.android_jar = self.sdk / "platforms" / pins["platform"] / "android.jar"
        self.adb = self.sdk / "platform-tools" / _exe("adb")
        self.aapt2 = self.build_tools / _exe("aapt2")
        self.d8 = self.build_tools / _script("d8")
        self.zipalign = self.build_tools / _exe("zipalign")
        self.apksigner = self.build_tools / _script("apksigner")
        self.sdkmanager = self.sdk / "cmdline-tools" / "latest" / "bin" / _script("sdkmanager")
        self.java_home = java_home()
        java_bin = self.java_home / "bin" if self.java_home else None
        self.javac = self._find(java_bin, "javac")
        self.keytool = self._find(java_bin, "keytool")
        host = "windows-x86_64" if WINDOWS else f"{platform.system().lower()}-x86_64"
        self.llvm_bin = self.ndk / "toolchains" / "llvm" / "prebuilt" / host / "bin"
        self.strip = self.llvm_bin / _exe("llvm-strip")
        self.libcxx = (self.ndk / "toolchains" / "llvm" / "prebuilt" / host / "sysroot" / "usr"
                       / "lib" / "aarch64-linux-android" / "libc++_shared.so")
        local_cmake = (ROOT / ".local" / "toolchain" / "cmake-3.31.10-windows-x86_64" / "bin"
                       / "cmake.exe")
        self.cmake = Path(str(local_cmake if local_cmake.is_file() else shutil.which("cmake")))
        self.ninja = self._ninja()

    @staticmethod
    def _find(directory: Path | None, name: str) -> Path | None:
        if directory and (directory / _exe(name)).is_file():
            return directory / _exe(name)
        found = shutil.which(name)
        return Path(found) if found else None

    @staticmethod
    def _ninja() -> Path | None:
        found = shutil.which("ninja")
        if found:
            return Path(found)
        if WINDOWS:
            vswhere = (Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio"
                       / "Installer" / "vswhere.exe")
            if vswhere.is_file():
                vs = subprocess.run([str(vswhere), "-products", "*", "-latest", "-property",
                                     "installationPath"], capture_output=True, text=True)
                ninja = (Path(vs.stdout.strip()) / "Common7" / "IDE" / "CommonExtensions"
                         / "Microsoft" / "CMake" / "Ninja" / "ninja.exe")
                if ninja.is_file():
                    return ninja
        return None

    def missing(self) -> list[str]:
        required = {
            "NDK " + CONFIG["android_sdk"]["ndk"]: self.ndk / "build" / "cmake"
            / "android.toolchain.cmake",
            "build-tools " + CONFIG["android_sdk"]["build_tools"]: self.aapt2,
            CONFIG["android_sdk"]["platform"]: self.android_jar,
            "platform-tools (adb)": self.adb,
            "JDK " + str(CONFIG["jdk_major"]) + " (javac)": self.javac,
            "JDK keytool": self.keytool,
            "CMake": self.cmake,
            "Ninja": self.ninja,
        }
        return [name for name, path in required.items() if not path or not Path(path).exists()]


def run(command: list, **kwargs) -> subprocess.CompletedProcess:
    completed = subprocess.run([str(part) for part in command], **kwargs)
    if completed.returncode:
        raise AndroidError(f"{Path(str(command[0])).name} failed ({completed.returncode})")
    return completed


def adb(tools: Tools, args: argparse.Namespace, *command: str, **kwargs):
    prefix = [tools.adb] + (["-s", args.serial] if args.serial else [])
    return run(prefix + list(command), **kwargs)


def share_with_app(tools: Tools, args: argparse.Namespace, *remote: str) -> None:
    """What adb pushes into the app's folder belongs to the shell user, and
    the app cannot even list it on the Android 15 emulator (16 lets it).
    The shell may open its own files to everyone: the app's folder itself is
    closed to other apps, so this reaches the app alone."""
    for path in remote:
        adb(tools, args, "shell", f"find '{path}' -user shell -exec chmod a+rwX {{}} +")


def preset(args: argparse.Namespace) -> str:
    """The CMake preset: the v4 title-update build (TITLE_UPDATE_V4_BACKLOG,
    Release only, its own generated tree) or the base disc's."""
    if getattr(args, "title_update_v4", False):
        return "android-arm64-v4"
    return f"android-arm64-{args.configuration.lower()}"


def build_directory(args: argparse.Namespace) -> Path:
    return ROOT / "out" / "build" / preset(args)


def release_version() -> tuple[str, int]:
    release = json.loads((ROOT / "config" / "release.json").read_text(encoding="utf-8"))
    name = str(release["version"])
    major, minor, patch = (int(part) for part in name.split("-")[0].split(".")[:3])
    return name, major * 10000 + minor * 100 + patch


def doctor(args: argparse.Namespace) -> int:
    tools = Tools()
    missing = tools.missing()
    if missing and args.install:
        if not tools.sdkmanager.is_file():
            raise AndroidError("the SDK's command-line tools are needed to install packages")
        packages = CONFIG["android_sdk"]["packages"]
        environment = dict(os.environ)
        if tools.java_home:
            environment["JAVA_HOME"] = str(tools.java_home)
        command = [tools.sdkmanager, f"--sdk_root={tools.sdk}", "--install", *packages]
        if args.accept_licenses:
            # The player accepted the Android SDK license (the launcher
            # shows it before the build); otherwise sdkmanager asks here.
            run(command, input="y\n" * 16, text=True, env=environment)
        else:
            run(command, env=environment)
        missing = Tools().missing()
    for line in (f"sdk: {tools.sdk}", f"ndk: {tools.ndk}", f"build-tools: {tools.build_tools}",
                 f"javac: {tools.javac}", f"cmake: {tools.cmake}", f"ninja: {tools.ninja}"):
        print(line)
    if missing:
        print("missing: " + ", ".join(missing), file=sys.stderr)
        return 1
    print("ready")
    return 0


def build(args: argparse.Namespace) -> int:
    tools = Tools()
    missing = tools.missing()
    if missing:
        raise AndroidError("missing " + ", ".join(missing) + " (pinyon.py android doctor --install)")
    generated = "generated-v4" if args.title_update_v4 else "generated"
    if not (ROOT / ".local" / generated / "default" / "sources.cmake").is_file():
        raise AndroidError("the generated game code is missing; build the game on this PC "
                           "first (the launcher, tools/build-preview.ps1 or, for v4, "
                           "tools/build-v4.ps1)")
    directory = build_directory(args)
    environment = dict(os.environ, ANDROID_NDK_HOME=str(tools.ndk))
    if not (directory / "CMakeCache.txt").is_file():
        run([tools.cmake, "--preset", preset(args),
             f"-DREXSDK_DIR={rexsdk_dir().as_posix()}",
             f"-DCMAKE_MAKE_PROGRAM={tools.ninja}", f"-DPYTHON_EXECUTABLE={sys.executable}",
             f"-DPython3_EXECUTABLE={sys.executable}"], cwd=ROOT, env=environment)
    # The game, and libadrenotools' hooks, which nothing links (they are
    # loaded from the native library folder for a custom GPU driver).
    command = [tools.cmake, "--build", directory, "--target", "pinyon_shift",
               *(Path(name).stem.removeprefix("lib") for name in ADRENOTOOLS_HOOKS)]
    if args.jobs:
        command += ["-j", str(args.jobs)]
    run(command, cwd=ROOT, env=environment)
    return package(args, tools)


def _keystore(tools: Tools) -> Path:
    """A signing key made on this PC for this player's own installs."""
    keystore = WORK / "signing" / "pinyon-shift-local.keystore"
    if not keystore.is_file():
        keystore.parent.mkdir(parents=True, exist_ok=True)
        run([tools.keytool, "-genkeypair", "-keystore", keystore, "-storepass", "pinyon-local",
             "-keypass", "pinyon-local", "-alias", "pinyon-local", "-keyalg", "RSA",
             "-keysize", "3072", "-validity", "10000", "-dname", "CN=Pinyon Shift local build"],
            stdout=subprocess.DEVNULL)
    return keystore


def _git(*command: str, cwd: Path = ROOT) -> str:
    """Git's answer, or "unknown" (a launcher install is no Git checkout and
    may have only the pinned MinGit)."""
    git = shutil.which("git")
    if not git:
        toolchain = json.loads((ROOT / "config" / "release-toolchain.json").read_text(
            encoding="utf-8"))["git"]
        mingit = ROOT / toolchain["install_path"] / toolchain["executable"]
        if not mingit.is_file():
            return "unknown"
        git = str(mingit)
    try:
        completed = subprocess.run([git, *command], cwd=cwd, capture_output=True, text=True)
    except OSError:
        return "unknown"
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _source_commit() -> str:
    commit = _git("rev-parse", "HEAD")
    if commit != "unknown":
        return commit
    # A launcher payload records the commit it was packaged from.
    provenance = ROOT / "config" / "source-provenance.json"
    if provenance.is_file():
        return str(json.loads(provenance.read_text(encoding="utf-8")).get("commit", "unknown"))
    return "unknown"


def _dirty(status: str) -> str:
    return "unknown" if status == "unknown" else str(bool(status)).lower()


def _build_manifest(tools: Tools, version_name: str, libraries: list[Path]) -> dict:
    """The provenance the game logs at start and puts in crash reports
    (AP-6.4), as tools/build-preview.ps1 writes it beside the executable."""
    sdk = rexsdk_dir()
    main = next(path for path in libraries if path.name == "libmain.so")
    return {
        "schema_version": 3,
        "configuration": "Release",
        "platform": "android-arm64",
        "version": version_name,
        "cpu_baseline": "armv8-a",
        "ndk": CONFIG["android_sdk"]["ndk"],
        "min_sdk": CONFIG["min_sdk"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "executable": "libmain.so",
        "executable_sha256": hashlib.sha256(main.read_bytes()).hexdigest().upper(),
        "generated_locally": True,
        "pinyon_shift_commit": _source_commit(),
        "pinyon_shift_dirty": _dirty(_git("status", "--porcelain", "--", ".", ":!BUGS.md",
                                          ":!docs")),
        "rexglue_commit": _git("rev-parse", "HEAD", cwd=sdk),
        "rexglue_dirty": _dirty(_git("status", "--porcelain", cwd=sdk)),
    }


# GPU drivers packaged as assets/drivers/<name>, which the activity installs
# into state/drivers and android_gpu_driver "auto" picks by GPU: the binary
# from .local/android/drivers/<name> (not in the repository), its notice from
# android/drivers/<name>.
BUNDLED_DRIVERS = ["turnip-gen8-v37"]


def bundled_driver_files() -> list[tuple[Path, str]]:
    files = []
    for name in BUNDLED_DRIVERS:
        binary = WORK / "drivers" / name
        notice = ROOT / "android" / "drivers" / name
        found = sorted(binary.glob("*")) if binary.is_dir() else []
        if not any(path.suffix == ".so" for path in found):
            print(f"warning: bundled driver {name} is missing from {binary}; not packaged")
            continue
        for path in found + sorted(notice.glob("*")):
            if path.is_file():
                files.append((path, f"assets/drivers/{name}/{path.name}"))
    return files


# The Khronos validation layer (Apache-2.0), from the release's Android
# binaries unpacked into .local/vulkan-validation-android/<release>/. The
# loader finds a layer in the app's native library folder, and
# SETTINGS > GRAPHICS > KHRONOS VALIDATION enables it; with it on, the
# Adreno smear (issue #403) has not been seen.
VALIDATION_LAYER = "libVkLayer_khronos_validation.so"


def validation_layer() -> Path | None:
    found = sorted((ROOT / ".local" / "vulkan-validation-android").glob(
        f"*/{CONFIG['abi']}/{VALIDATION_LAYER}"))
    if not found:
        print(f"warning: {VALIDATION_LAYER} is not in .local/vulkan-validation-android; "
              "KHRONOS VALIDATION will have no layer to load")
        return None
    return found[-1]


def package(args: argparse.Namespace, tools: Tools | None = None) -> int:
    tools = tools or Tools()
    directory = build_directory(args)
    libraries = []
    for name in NATIVE_LIBRARIES + ADRENOTOOLS_HOOKS:
        found = list(directory.glob(f"**/{name}"))
        found = [path for path in found if "CMakeFiles" not in path.parts]
        if not found:
            raise AndroidError(f"{name} is not built in {directory}")
        libraries.append(max(found, key=lambda path: path.stat().st_mtime))
    libraries.append(tools.libcxx)

    staging = WORK / "package"
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "classes").mkdir(parents=True)
    (staging / "dex").mkdir()
    (staging / "lib").mkdir()

    version_name, version_code = release_version()
    manifest = (ROOT / "android" / "AndroidManifest.xml").read_text(encoding="utf-8")
    manifest = manifest.replace("<manifest ", f'<manifest package="{PACKAGE}" ', 1)
    (staging / "AndroidManifest.xml").write_text(manifest, encoding="utf-8")
    unsigned = staging / "unsigned.apk"
    # The manifest's resources (the game mode config) compiled for the link.
    resources = staging / "resources.zip"
    run([tools.aapt2, "compile", "--dir", ROOT / "android" / "res", "-o", resources])
    run([tools.aapt2, "link", "-o", unsigned, "-I", tools.android_jar,
         "--manifest", staging / "AndroidManifest.xml", resources,
         "--min-sdk-version", str(CONFIG["min_sdk"]),
         "--target-sdk-version", str(CONFIG["target_sdk"]),
         "--version-name", version_name, "--version-code", str(version_code),
         *(["--debug-mode"] if getattr(args, "debuggable", False) else [])])

    sdl_java = rexsdk_dir() / "thirdparty" / "sdl3" / "android-project" / "app" / "src" / "main" \
        / "java"
    sources = sorted(sdl_java.rglob("*.java")) + sorted((ROOT / "android" / "java").rglob("*.java"))
    run([tools.javac, "-source", "1.8", "-target", "1.8", "-nowarn", "-Xlint:-options",
         "-bootclasspath", tools.android_jar, "-classpath", tools.android_jar,
         "-encoding", "UTF-8", "-d", staging / "classes", *sources])
    classes = sorted((staging / "classes").rglob("*.class"))
    run([tools.d8, "--release", "--min-api", str(CONFIG["min_sdk"]), "--lib", tools.android_jar,
         "--output", staging / "dex", *classes])

    # The device gets libraries without debug sections; the PC keeps the
    # originals for symbolizing crash reports.
    stripped = []
    for library in libraries:
        target = staging / "lib" / library.name
        run([tools.strip, "--strip-debug", "-o", target, library])
        stripped.append(target)

    manifest = _build_manifest(tools, version_name, libraries)
    (staging / "pinyon_shift_build.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                                     encoding="utf-8")
    # Android 15 devices with 16 KiB pages refuse libraries whose load
    # segments are aligned to less (AP-3.5).
    readelf = tools.llvm_bin / _exe("llvm-readelf")
    for library in stripped:
        segments = subprocess.run([str(readelf), "-lW", str(library)], capture_output=True,
                                  text=True).stdout.splitlines()
        aligns = {int(line.split()[-1], 16) for line in segments
                  if line.strip().startswith("LOAD")}
        if not aligns or min(aligns) < 0x4000:
            raise AndroidError(f"{library.name} has load segments aligned below 16 KiB")
    layer = validation_layer()

    with zipfile.ZipFile(unsigned, "a", compression=zipfile.ZIP_DEFLATED) as apk:
        apk.write(staging / "dex" / "classes.dex", "classes.dex")
        apk.write(staging / "pinyon_shift_build.json", "assets/pinyon_shift_build.json")
        for library in stripped:
            apk.write(library, f"lib/{CONFIG['abi']}/{library.name}")
        if layer:
            apk.write(layer, f"lib/{CONFIG['abi']}/{VALIDATION_LAYER}")
        for path, name in bundled_driver_files():
            apk.write(path, name)

    aligned = staging / "aligned.apk"
    run([tools.zipalign, "-P", "16", "-f", "4", unsigned, aligned])
    output = WORK / "pinyon-shift.apk"
    keystore = _keystore(tools)
    run([tools.apksigner, "sign", "--ks", keystore, "--ks-pass", "pass:pinyon-local",
         "--key-pass", "pass:pinyon-local", "--out", output, aligned])
    size = output.stat().st_size
    print(json.dumps({"apk": str(output), "bytes": size, "version": version_name,
                      "libraries": [path.name for path in stripped]
                      + ([VALIDATION_LAYER] if layer else [])}))
    return 0


def install(args: argparse.Namespace) -> int:
    tools = Tools()
    apk = WORK / "pinyon-shift.apk"
    if not apk.is_file():
        raise AndroidError("build the package first (pinyon.py android build)")
    adb(tools, args, "install", "-r", apk)
    return 0


def push_data(args: argparse.Namespace) -> int:
    """The extracted game, pushed with --sync so an interrupted copy resumes
    and an unchanged file is not sent again."""
    tools = Tools()
    game = (args.game_root or ROOT / ".local" / "game" / "base").resolve()
    if not (game / "default.xex").is_file():
        raise AndroidError(f"the extracted game is not at {game}")
    adb(tools, args, "shell", "mkdir", "-p", f"{DEVICE_FILES}/game/base", f"{DEVICE_FILES}/state")
    adb(tools, args, "push", "--sync", f"{game}{os.sep}.", f"{DEVICE_FILES}/game/base")
    share_with_app(tools, args, f"{DEVICE_FILES}/game", f"{DEVICE_FILES}/state")
    return 0


def push_driver(args: argparse.Namespace) -> int:
    """A custom Vulkan driver (Mesa Turnip) packaged for adrenotools, a .zip
    with meta.json and the .so or a folder of them, into the state folder's
    drivers/<name>; the game loads it with --android_gpu_driver=<name>."""
    tools = Tools()
    source = args.driver.resolve()
    name = args.name or source.stem
    staging = WORK / "driver-staging" / name
    if staging.exists():
        shutil.rmtree(staging)
    if source.is_dir():
        shutil.copytree(source, staging)
    else:
        with zipfile.ZipFile(source) as archive:
            archive.extractall(staging)
    if not any(staging.glob("*.so")):
        raise AndroidError(f"{source} holds no driver library (.so)")
    remote = f"{DEVICE_FILES}/state/drivers/{name}"
    adb(tools, args, "shell", "rm", "-rf", remote)
    adb(tools, args, "shell", "mkdir", "-p", remote)
    adb(tools, args, "push", f"{staging}{os.sep}.", remote, stdout=subprocess.DEVNULL)
    share_with_app(tools, args, f"{DEVICE_FILES}/state/drivers")
    print(f"driver {name}: run with --android_gpu_driver={name}")
    return 0


def migrate(args: argparse.Namespace) -> int:
    """Brings a device's game and state from an install under an earlier
    package name (com.pinyonshift.fh1) into this one's folder, which Android
    keeps apart. The state (saves, settings, drivers) is copied and the
    earlier copy left as it was; the extracted game (7.2 GB) is moved, as it
    is rebuilt from the disc with push-data. Nothing already in this
    package's state is overwritten."""
    tools = Tools()
    serial = ["-s", args.serial] if args.serial else []

    def shell(command: str) -> str:
        return subprocess.run([str(tools.adb)] + serial + ["shell", command],
                              capture_output=True, text=True).stdout.strip()

    sources = [name for name in CONFIG.get("previous_packages", [])
               if shell(f"[ -d /sdcard/Android/data/{name}/files/state ] && echo yes") == "yes"]
    if not sources:
        print("no earlier install's files on the device")
        return 0
    old = f"/sdcard/Android/data/{sources[0]}/files"
    adb(tools, args, "shell", "am", "force-stop", PACKAGE)
    for name in sources:
        adb(tools, args, "shell", "am", "force-stop", name)
    adb(tools, args, "shell", "mkdir", "-p", f"{DEVICE_FILES}/state", f"{DEVICE_FILES}/game")
    # cp -n: the new install's own files win; logs are not carried over.
    for entry in shell(f"ls '{old}/state'").split():
        if entry == "logs":
            continue
        adb(tools, args, "shell", "cp", "-R", "-n", f"{old}/state/{entry}", f"{DEVICE_FILES}/state/")
    if shell(f"[ -d '{old}/game/base' ] && echo yes") == "yes":
        if shell(f"[ -e '{DEVICE_FILES}/game/base' ] && echo yes") == "yes":
            print(f"game files already in {DEVICE_FILES}/game/base; the earlier copy is left")
        else:
            adb(tools, args, "shell", "mv", f"{old}/game/base", f"{DEVICE_FILES}/game/base")
    share_with_app(tools, args, f"{DEVICE_FILES}/game", f"{DEVICE_FILES}/state")
    print(f"migrated {old} into {DEVICE_FILES}; uninstall {sources[0]} once the game "
          "shows your save (its state stays until then)")
    return 0


def push_title_update(args: argparse.Namespace) -> int:
    """The verified v4 title update (tools/verify-fh1-title-update.py
    --install <state>) into the device state's title-update-v4, which the v4
    build mounts as update:."""
    tools = Tools()
    source = (args.state_root / "title-update-v4").resolve()
    names = ["default.xexp", "SpeechFacade_default.xexp", "XMediaFacade_default.xexp", "media.zip"]
    if not all((source / name).is_file() for name in names):
        raise AndroidError(f"no verified title update in {source}; install it with "
                           "tools/verify-fh1-title-update.py --install")
    remote = f"{DEVICE_FILES}/state/title-update-v4"
    adb(tools, args, "shell", "mkdir", "-p", remote)
    adb(tools, args, "push", "--sync", *(str(source / name) for name in names), remote,
        stdout=subprocess.DEVNULL)
    share_with_app(tools, args, remote)
    return 0


def _pid(tools: Tools, args: argparse.Namespace) -> str:
    completed = subprocess.run([str(tools.adb)] + (["-s", args.serial] if args.serial else [])
                               + ["shell", "pidof", PACKAGE], capture_output=True, text=True)
    return completed.stdout.strip()


def run_game(args: argparse.Namespace) -> int:
    tools = Tools()
    extras: list[str] = []
    game_arguments = list(args.game_arguments)
    if args.null_gpu:
        game_arguments.append("--gpu_backend=null")
    if args.seed:
        # Routes start from a pinned seed (tools/create-render-seed.py), never
        # from the device's own progress: its user and config replace the
        # state's; the seed on the PC is only read.
        seed = args.seed.resolve()
        if not (seed / "user").is_dir():
            raise AndroidError(f"{seed} is not a render seed (no user folder)")
        # Like the Windows runner's private state per run: nothing a previous
        # run left (caches, backups, mods, repaired saves) carries over; only
        # the logs, crash reports and route output stay.
        kept = ("logs", "crashes", "reports", "render-tests", "render-test-output", "drivers")
        listing = subprocess.run([str(tools.adb)] + (["-s", args.serial] if args.serial else [])
                                 + ["shell", "ls", f"{DEVICE_FILES}/state/"],
                                 capture_output=True, text=True).stdout.split()
        stale = [f"{DEVICE_FILES}/state/{name}" for name in listing
                 if name not in kept and name != "cache"]
        # The title's cache partition is reset, but not the compiled
        # pipelines a player keeps from run to run (cache/shaders).
        if "cache" in listing:
            cache = subprocess.run([str(tools.adb)] + (["-s", args.serial] if args.serial else [])
                                   + ["shell", "ls", f"{DEVICE_FILES}/state/cache/"],
                                   capture_output=True, text=True).stdout.split()
            stale += [f"{DEVICE_FILES}/state/cache/{name}" for name in cache if name != "shaders"]
        if stale:
            adb(tools, args, "shell", "rm", "-rf", *stale)
        for folder in ("user", "config"):
            if (seed / folder).is_dir():
                adb(tools, args, "push", seed / folder, f"{DEVICE_FILES}/state/{folder}",
                    stdout=subprocess.DEVNULL)
    if args.route:
        remote_route = f"{DEVICE_FILES}/state/render-tests/{args.route.name}"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        remote_output = f"{DEVICE_FILES}/state/render-test-output/{args.route.stem}-{stamp}"
        adb(tools, args, "shell", "mkdir", "-p", f"{DEVICE_FILES}/state/render-tests")
        adb(tools, args, "push", args.route.resolve(), remote_route, stdout=subprocess.DEVNULL)
        # A device that slept between runs shows the route over its lock.
        extras += ["--ez", "show_when_locked", "true"]
        extras += ["--es", "env.PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT", remote_route,
                   "--es", "env.PINYON_SHIFT_FH1_RENDER_TEST_OUTPUT", remote_output]
        game_arguments.append("--pinyon_shift_skip_opening_movies=true")
        # As tools/run-fh1-render-test.py does: seeds are fixed snapshots, so
        # keep their car cards (and thumbnails) as saved unless asked.
        if not any("pinyon_shift_repair_car_cards" in argument for argument in game_arguments):
            game_arguments.append("--pinyon_shift_repair_car_cards=false")
        print(f"route output: {remote_output}")
    if args.seed or args.route:
        share_with_app(tools, args, f"{DEVICE_FILES}/state")
    if game_arguments:
        extras += ["--esa", "args", ",".join(game_arguments)]
    adb(tools, args, "shell", "am", "start", "-S", "-W", "-n", f"{PACKAGE}/{ACTIVITY}", *extras,
        stdout=subprocess.DEVNULL)
    if not args.wait:
        return 0
    deadline = time.monotonic() + args.timeout
    time.sleep(3)
    while _pid(tools, args):
        if time.monotonic() > deadline:
            adb(tools, args, "shell", "am", "force-stop", PACKAGE)
            raise AndroidError(f"timed out after {args.timeout} seconds")
        time.sleep(2)
    if not args.route:
        return 0
    result = route_result(tools, args)
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "pass" else 1


def route_result(tools: Tools, args: argparse.Namespace) -> dict:
    """The newest session's events, judged as tools/run-fh1-render-test.py
    judges a Windows run's (AP-8.1): completed once, every capture taken, no
    failure event."""
    listing = subprocess.run([str(tools.adb)] + (["-s", args.serial] if args.serial else [])
                             + ["shell", "ls", "-t", f"{DEVICE_FILES}/state/logs/"],
                             capture_output=True, text=True).stdout.split()
    sessions = [name for name in listing if name.endswith(".jsonl")]
    if not sessions:
        return {"result": "fail", "reason": "no session log on the device"}
    destination = WORK / "device-logs" / "routes"
    destination.mkdir(parents=True, exist_ok=True)
    for suffix in (".jsonl", ".perf.csv"):
        name = sessions[0][: -len(".jsonl")] + suffix
        subprocess.run([str(tools.adb)] + (["-s", args.serial] if args.serial else [])
                       + ["pull", f"{DEVICE_FILES}/state/logs/{name}", str(destination / name)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    events = []
    for line in (destination / sessions[0]).read_text(encoding="utf-8",
                                                     errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # a line cut off when the process was stopped
    names = [str(event.get("event", "")) for event in events]
    failures = [event for event in events if str(event.get("event", "")).endswith(".failure")]
    completed = [event for event in events if event.get("event") == "fh1.render_test.complete"]
    captures = [event for event in events if event.get("event") == "fh1.render_test.capture"]
    result = {
        "result": "pass" if completed and not failures else "fail",
        "session": sessions[0],
        "captures": [{"name": event.get("name"), "frame": event.get("frame"),
                      "vehicle": [event.get(f"vehicle_{axis}") for axis in "xyz"]
                      if event.get("vehicle_pose_valid") == "1" else None}
                     for event in captures],
        "failures": failures[:3],
        "events": len(names),
        "log": str(destination / sessions[0]),
    }
    perf = destination / (sessions[0][: -len(".jsonl")] + ".perf.csv")
    if perf.is_file():
        summary = subprocess.run([sys.executable, str(ROOT / "tools" / "summarize-performance.py"),
                                  str(perf), "--format", "json"], capture_output=True, text=True)
        try:
            performance = json.loads(summary.stdout)
            result["simulation_time"] = performance.get("presentation", {}).get("simulation_time")
            result["frame_time_us"] = performance["frames"]["frame_time_us"]
        except (json.JSONDecodeError, KeyError):
            pass
    return result


def stop(args: argparse.Namespace) -> int:
    adb(Tools(), args, "shell", "am", "force-stop", PACKAGE)
    return 0


def pull_logs(args: argparse.Namespace) -> int:
    tools = Tools()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = (args.output or WORK / "device-logs" / stamp).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for folder in ("logs", "crashes", "reports", "render-test-output"):
        subprocess.run([str(tools.adb)] + (["-s", args.serial] if args.serial else [])
                       + ["pull", f"{DEVICE_FILES}/state/{folder}", str(destination)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with (destination / "logcat.txt").open("w", encoding="utf-8", errors="replace") as stream:
        subprocess.run([str(tools.adb)] + (["-s", args.serial] if args.serial else [])
                       + ["logcat", "-d", "-b", "main,crash"], stdout=stream)
    print(destination)
    return 0


def add_parser(commands) -> None:
    android = commands.add_parser("android", help="build and run the game on an Android device")
    sub = android.add_subparsers(dest="android_command", required=True)

    def command(name: str, handler, help_text: str) -> argparse.ArgumentParser:
        parser = sub.add_parser(name, help=help_text)
        parser.add_argument("--serial", help="adb device serial")
        parser.add_argument("--configuration", choices=("Release", "RelWithDebInfo"),
                            default="Release")
        parser.set_defaults(android_handler=handler)
        return parser

    parser = command("doctor", doctor, "check the Android toolchain")
    parser.add_argument("--install", action="store_true", help="install missing SDK packages")
    parser.add_argument("--accept-licenses", action="store_true",
                        help="answer yes to the Android SDK licenses sdkmanager shows")
    parser = command("build", build, "cross-compile the game and package the APK")
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--title-update-v4", action="store_true",
                        help="the v4 title-update build (tools/build-v4.ps1 generates its code)")
    parser.add_argument("--debuggable", action="store_true",
                        help="let adb attach (thread dumps with debuggerd, run-as)")
    parser = command("package", package, "package already built libraries into the APK")
    parser.add_argument("--title-update-v4", action="store_true",
                        help="package the v4 title-update build")
    parser.add_argument("--debuggable", action="store_true",
                        help="let adb attach (thread dumps with debuggerd, run-as)")
    command("install", install, "install the APK on the device")
    parser = command("push-data", push_data, "copy the extracted game files to the device")
    parser.add_argument("--game-root", type=Path)
    parser = command("push-driver", push_driver,
                     "copy a custom Vulkan driver package (Mesa Turnip) to the device")
    parser.add_argument("driver", type=Path, help="an adrenotools driver .zip or folder")
    parser.add_argument("--name", help="the folder name on the device (default: the file's)")
    parser = command("push-title-update", push_title_update,
                     "copy the verified v4 title update to the device")
    parser.add_argument("--state-root", type=Path, required=True,
                        help="the state root it was installed into")
    command("migrate", migrate,
            "bring an earlier package name's game and saves into this install")
    parser = command("run", run_game, "start the game on the device")
    parser.add_argument("--null-gpu", action="store_true", help="no renderer (gpu_backend=null)")
    parser.add_argument("--route", type=Path, help="a render-test route to run")
    parser.add_argument("--seed", type=Path,
                        help="a render seed whose user and config replace the device state's")
    parser.add_argument("--wait", action="store_true", help="wait until the game exits")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("game_arguments", nargs="*", help="after --, passed to the game")
    command("stop", stop, "stop the game on the device")
    parser = command("pull-logs", pull_logs, "copy logs, crashes and route output to the PC")
    parser.add_argument("--output", type=Path)


def main(args: argparse.Namespace) -> int:
    try:
        return args.android_handler(args)
    except AndroidError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    top = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_parser(top.add_subparsers(dest="command", required=True))
    sys.exit(main(top.parse_args()))
