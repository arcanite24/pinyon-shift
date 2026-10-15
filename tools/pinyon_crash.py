#!/usr/bin/env python3
"""Crash bundles on every OS (LX-3.5): a sanitized ZIP and a prefilled issue.

  pinyon.py crash-report create --executable FILE --process-id N --exit-code N
                                --started-utc TIME [--state-root DIR] [--json]
  pinyon.py crash-report pending [--state-root DIR] [--json]

`create` is what tools/create-crash-report.ps1 did (that script is now a thin
wrapper over this one): it finds the session the crashed process wrote (its
event log, the crash text the reporter wrote beside it, the runtime log from
the start of the run and the performance counters), keeps only allowed
settings and system facts, replaces every local path and the user name with
placeholders, refuses to bundle anything that is a game file, a binary, a
save or a memory dump, writes <state>/reports/PinyonShift-<id>-<time>.zip
and <state>/reports/pending-report.json, and prints that pending record:
{"schema", "created_utc", "crash_id", "bundle", "issue_url", "exit_code_hex"}.

`pending` prints the pending record (or {"pending": false}); `pinyon.py
launch` removes it at the next start.

The crash text comes from src/crash_reporter_win.cpp on Windows (code=,
fault_module=, frames) and src/crash_reporter_posix.cpp elsewhere (signal=,
pc_module=, pc_offset=); both give the same report fields.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_common as common  # noqa: E402

FORBIDDEN_EXTENSIONS = ('.dmp', '.exe', '.dll', '.iso', '.xex', '.obj', '.lib', '.pdb',
                        '.dxil', '.pnsp', '.so', '.dylib', '.core')
ALLOWED_SETTINGS = (
    'pinyon_shift_config_schema', 'gpu_backend', 'gpu_record_thread', 'input_backend',
    'hid_mappings_file', 'mnk_mode', 'keybind_start',
    'd3d12_allow_variable_refresh_rate_and_tearing',
    'xma_relaxed_padding_admission',
    'pinyon_shift_capture_performance',
    'pinyon_shift_stabilize_vehicle_presentation', 'pinyon_shift_skip_opening_movies',
    'pinyon_shift_fh1_render_fps_limit',
    'pinyon_shift_fh1_source_presentation',
    'resolution', 'vsync', 'host_present_fps_limit',
    'host_present_sleep_spin',
    'anisotropic_override', 'swap_post_effect',
    'disable_motion_blur', 'disable_depth_of_field',
    'draw_resolution_scale_x', 'draw_resolution_scale_y', 'clear_memory_page_state',
)
XMA_COLUMNS = ('xma_no_space_stalls', 'xma_no_progress_stalls', 'xma_stall_recoveries')
PRESENTATION_COLUMNS = (
    'guest_vblank_count', 'guest_vblank_delta_ns',
    'simulation_tick_count', 'present_count', 'present_delta_ns',
    'present_queue_depth', 'present_deadline_misses',
    'duplicate_present_count', 'dropped_present_count',
)
RESOLVE_COLUMNS = (
    'resolve_readback_requests', 'resolve_readback_bytes',
    'resolve_readback_fast_copies', 'resolve_readback_cache_misses',
    'resolve_readback_full_waits', 'resolve_readback_wait_time_ns',
)
if common.WINDOWS:
    BINARIES = ('pinyon_shift.exe', 'rexruntime.dll', 'rexgpu-fh1.dll',
                'pinyon_shift_SpeechFacade_default.dll', 'pinyon_shift_XMediaFacade_default.dll')
else:
    _library = ".dylib" if common.MACOS else ".so"
    BINARIES = ('pinyon_shift', 'librexruntime' + _library, 'librexgpu-fh1' + _library,
                'libpinyon_shift_SpeechFacade_default' + _library,
                'libpinyon_shift_XMediaFacade_default' + _library)
# Any user profile path left after the known ones are replaced, whatever its
# separators: C:\Users\<name>, /home/<name>, /Users/<name>, /var/home/<name>.
PROFILE_PATTERNS = (
    re.compile(r"(?i)[A-Z]:(?:\\\\|[\\/])Users(?:\\\\|[\\/])[^\\/\s\"'<>]+"),
    re.compile(r"(?<![\w.-])/(?:home|Users|var/home|run/media)/[^/\s\"'<>]+"),
)


class CrashError(common.CommandError):
    pass


# --- Text --------------------------------------------------------------------------

def iso_utc(moment: datetime) -> str:
    """.NET's round-trip ("o") form for a UTC time: seven fractional digits."""
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond:06d}0Z"


def parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # fromisoformat takes at most six fractional digits before 3.11.
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def username_pattern(name: str) -> re.Pattern | None:
    if not name:
        return None
    return re.compile(r"(?i)(?<![A-Z0-9_.-])" + re.escape(name) + r"(?![A-Z0-9_.-])")


def protect(text: str, replacements: dict[str, str]) -> str:
    """Replace each known local path, then the user name, then any user
    profile path left. The longest path first, so the state root inside the
    repository keeps its own placeholder."""
    paths = sorted(((placeholder, value) for placeholder, value in replacements.items()
                    if placeholder != "<USERNAME>" and value and value.strip()),
                   key=lambda item: len(item[1]), reverse=True)
    for placeholder, value in paths:
        variants = dict.fromkeys((value, value.replace("\\", "/"), value.replace("\\", "\\\\"),
                                  value.replace("/", "\\")))
        for variant in variants:
            text = re.sub(re.escape(variant), lambda _: placeholder, text, flags=re.IGNORECASE)
    pattern = username_pattern(replacements.get("<USERNAME>", ""))
    if pattern is not None:
        text = pattern.sub("<USERNAME>", text)
    for profile in PROFILE_PATTERNS:
        text = profile.sub("<USER_PROFILE>", text)
    return text


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def tail_lines(path: Path, count: int) -> list[str]:
    lines = read_text(path).splitlines()
    return lines[-count:]


TIMESTAMP = re.compile(r"^\[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]")


def write_sanitized_tail(source: Path, destination: Path, count: int,
                         replacements: dict[str, str], since: datetime | None = None) -> bool:
    if not source.is_file():
        return False
    lines = tail_lines(source, count)
    if since is not None:
        kept, current = [], False
        for line in lines:
            match = TIMESTAMP.match(line)
            if match:
                # The runtime log's times are local.
                local = datetime.strptime(match.group("time"), "%Y-%m-%d %H:%M:%S.%f")
                current = local.astimezone(timezone.utc) >= since
            if current:
                kept.append(line)
        lines = kept
        if not lines:
            return False
    content = protect(os.linesep.join(lines) + os.linesep, replacements)
    destination.write_bytes(content.encode("utf-8"))
    return True


def crash_details(text: str) -> dict:
    header = re.search(r"(?im)^code=(?P<code>0x[0-9a-f]+)\s+address=(?P<address>(?:0x)?[0-9a-f]+)"
                       r"(?:\s+operation=(?P<operation>\w+))?", text)
    module = re.search(r"(?im)^fault_module=(?P<module>[^\s]+)\s+fault_offset=(?P<offset>0x[0-9a-f]+)",
                       text)
    frame = re.search(r"(?im)^#\d+\s+0x[0-9a-f]+(?:\s+(?P<symbol>[^\s(]+))?", text)
    details = {
        "exception_code": header.group("code").upper() if header else None,
        "operation": (header.group("operation").lower()
                      if header and header.group("operation") else "unspecified"),
        "fault_module": module.group("module").lower() if module else None,
        "fault_offset": module.group("offset").lower() if module else None,
        "top_frame": frame.group("symbol").lower() if frame and frame.group("symbol") else None,
    }
    if details["exception_code"] is None:
        # The POSIX reporter: signal=, pc_module=, pc_offset=.
        signal = re.search(r"(?im)^signal=(?P<signal>\w+)", text)
        if signal:
            details["exception_code"] = signal.group("signal").upper()
        pc_module = re.search(r"(?im)^pc_module=(?P<module>.+)$", text)
        pc_offset = re.search(r"(?im)^pc_offset=(?P<offset>0x[0-9a-f]+)", text)
        if pc_module and details["fault_module"] is None:
            details["fault_module"] = Path(pc_module.group("module").strip()).name.lower()
            # The reporter prints 16 hex digits; keep the Windows form.
            if pc_offset:
                details["fault_offset"] = hex(int(pc_offset.group("offset"), 16))
    return details


# --- Evidence ----------------------------------------------------------------------

def session_log(logs: Path, process_id: int, started: datetime) -> tuple[Path | None, list[dict]]:
    """The event log the crashed process wrote, not whichever was modified
    last, and its logging.ready and graphics.device.selected events."""
    if not logs.is_dir():
        return None, []
    candidates = sorted((path for path in logs.glob("*.jsonl") if path.is_file()),
                        key=lambda path: path.stat().st_mtime_ns, reverse=True)
    for candidate in candidates:
        try:
            with candidate.open(encoding="utf-8", errors="replace") as stream:
                first = json.loads(stream.readline())
            if (first.get("event") != "process.start" or str(first.get("pid")) != str(process_id)
                    or parse_utc(str(first.get("utc"))) < started - timedelta(seconds=2)):
                continue
            events = []
            wanted = re.compile(r'"event"\s*:\s*"(?:logging.ready|graphics.device.selected)"')
            for line in read_text(candidate).splitlines():
                if not wanted.search(line):
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue  # A partial JSON line is possible after a crash.
                if str(event.get("pid")) == str(process_id) and \
                        event.get("session") == first.get("session"):
                    events.append(event)
            return candidate, events
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return None, []


def counter_sums(perf: Path | None, columns: tuple[str, ...]) -> dict | None:
    if perf is None:
        return None
    with perf.open(encoding="utf-8", errors="replace", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or any(column not in reader.fieldnames for column in columns):
            return None
        totals = {column: 0 for column in columns}
        for row in reader:
            for column in columns:
                try:
                    totals[column] += int(row[column] or 0)
                except (TypeError, ValueError):
                    pass
    return totals


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def allowed_settings(config: Path) -> dict:
    settings = {}
    if config.is_file():
        for line in read_text(config).splitlines():
            match = re.match(r"^\s*(?P<key>[a-zA-Z0-9_]+)\s*=\s*(?P<value>.+?)\s*(?:#.*)?$", line)
            if match and match.group("key") in ALLOWED_SETTINGS:
                settings[match.group("key")] = match.group("value")
    return settings


def _run(command: list[str], timeout: float = 20) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              errors="replace").stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def system_facts() -> dict:
    """OS, CPU, memory and graphics adapters: nothing that names the user."""
    facts = {"os": None, "os_version": None, "os_build": None, "cpu": None,
             "logical_processors": os.cpu_count(), "memory_bytes": None, "gpu": []}
    if common.WINDOWS:
        script = ("$o = Get-CimInstance Win32_OperatingSystem | Select-Object -First 1; "
                  "$c = Get-CimInstance Win32_Processor | Select-Object -First 1; "
                  "$g = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion); "
                  "[ordered]@{ os = $o.Caption; os_version = $o.Version; os_build = $o.BuildNumber; "
                  "cpu = $c.Name; logical_processors = $c.NumberOfLogicalProcessors; "
                  "memory_bytes = [uint64]$o.TotalVisibleMemorySize * 1KB; gpu = $g } | "
                  "ConvertTo-Json -Depth 4 -Compress")
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if shell:
            data = None
            try:
                data = json.loads(_run([shell, "-NoProfile", "-NonInteractive", "-Command", script]))
            except ValueError:
                pass
            if isinstance(data, dict):
                gpus = data.get("gpu") or []
                data["gpu"] = [gpus] if isinstance(gpus, dict) else gpus
                facts.update(data)
        return facts
    if common.MACOS:
        version = platform.mac_ver()[0]
        facts.update(os=f"macOS {version}".strip(), os_version=version,
                     os_build=_run(["sw_vers", "-buildVersion"]).strip() or None,
                     cpu=_run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip() or None)
        memory = _run(["sysctl", "-n", "hw.memsize"]).strip()
        facts["memory_bytes"] = int(memory) if memory.isdigit() else None
        try:
            displays = json.loads(_run(["system_profiler", "-json", "SPDisplaysDataType"]))
            facts["gpu"] = [{"Name": item.get("sppci_model") or item.get("_name"),
                             "DriverVersion": item.get("spdisplays_mtlgpufamilysupport")}
                            for item in displays.get("SPDisplaysDataType", [])]
        except (ValueError, AttributeError):
            pass
        return facts
    release = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            release[key] = value.strip().strip('"')
    except OSError:
        pass
    facts.update(os=release.get("PRETTY_NAME") or "Linux", os_version=release.get("VERSION_ID"),
                 os_build=platform.release())
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model name"):
                facts["cpu"] = line.split(":", 1)[1].strip()
                break
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemTotal:"):
                facts["memory_bytes"] = int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    if shutil.which("lspci"):
        facts["gpu"] = [{"Name": line.split('"')[5] + " " + line.split('"')[3]
                         if line.count('"') >= 6 else line, "DriverVersion": None}
                        for line in _run(["lspci", "-mm"]).splitlines()
                        if re.search(r'"(VGA compatible controller|3D controller|Display controller)"',
                                     line)]
    return facts


# --- Bundle ------------------------------------------------------------------------

def create(state: Path, executable: Path, started: datetime, process_id: int, exit_code: int,
           repository: str = common.REPOSITORY_URL) -> dict:
    executable = executable.resolve()
    if not executable.is_file():
        raise CrashError(f"the executable {executable} does not exist")
    reports = state / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    home = str(Path.home())
    replacements = {
        "<REPOSITORY>": str(common.ROOT),
        "<STATE_ROOT>": str(state),
        "<GAME_ROOT>": str(common.default_game_root()),
        "<EXECUTABLE_DIR>": str(executable.parent),
        "<USER_PROFILE>": os.environ.get("USERPROFILE") or home,
        "<USERNAME>": os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser(),
    }
    # Crash reports stage in the temporary folder the launcher hands down
    # (portable installs point it into their data folder).
    staging = Path(tempfile.gettempdir()) / f"PinyonShiftReport-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        event_log, events = session_log(state / "logs", process_id, started)
        crash_files = []
        crashes = state / "crashes"
        if event_log is not None and crashes.is_dir():
            cutoff = (started - timedelta(seconds=2)).timestamp()
            crash_files = [path for path in crashes.iterdir()
                           if path.is_file() and path.name.startswith(event_log.stem + "-")
                           and path.stat().st_mtime >= cutoff]
        texts = sorted((path for path in crash_files if path.suffix.lower() == ".txt"),
                       key=lambda path: (path.name.endswith("-unhandled.txt"), path.stat().st_mtime))
        crash_text = read_text(texts[-1]) if texts else ""
        details = crash_details(crash_text)
        executable_hash = sha256_file(executable)
        identity = "\n".join((
            "pinyon-shift.crash.v1",
            f"executable={executable_hash.lower()}",
            f"exit={exit_code}",
            f"code={details['exception_code'] or ''}",
            f"operation={details['operation']}",
            f"module={details['fault_module'] or ''}",
            f"offset={details['fault_offset'] or ''}",
            f"frame={details['top_frame'] or ''}",
        ))
        fingerprint = "pscrash-v1-" + sha256_text(identity)[:20].lower()
        if crash_text:
            (staging / "crash.txt").write_bytes(protect(crash_text, replacements).encode("utf-8"))

        logging_ready = next((e for e in reversed(events) if e.get("event") == "logging.ready"),
                             None)
        selected = next((e for e in reversed(events)
                         if e.get("event") == "graphics.device.selected"), None)
        runtime_log = state / "logs" / "runtime.log"
        if logging_ready is not None and runtime_log.is_file() and \
                runtime_log.stat().st_mtime >= started.timestamp():
            write_sanitized_tail(runtime_log, staging / "runtime-tail.log", 2500, replacements,
                                 started)
        if event_log is not None:
            write_sanitized_tail(event_log, staging / "session-events.jsonl", 1000, replacements)

        perf = None
        if logging_ready is not None and event_log is not None:
            candidate = event_log.with_suffix(".perf.csv")
            if candidate.is_file() and candidate.stat().st_mtime >= started.timestamp():
                perf = candidate
        xma = counter_sums(perf, XMA_COLUMNS)
        xma_stalls = {"available": xma is not None,
                      "no_space": (xma or {}).get("xma_no_space_stalls", 0),
                      "no_progress": (xma or {}).get("xma_no_progress_stalls", 0),
                      "recoveries": (xma or {}).get("xma_stall_recoveries", 0)}
        presentation = counter_sums(perf, PRESENTATION_COLUMNS)
        presentation_counters = {"available": presentation is not None}
        presentation_counters.update(presentation or {c: 0 for c in PRESENTATION_COLUMNS})
        resolve = counter_sums(perf, RESOLVE_COLUMNS)
        resolve_counters = {"available": resolve is not None}
        resolve_counters.update(resolve or {c: 0 for c in RESOLVE_COLUMNS})

        settings = allowed_settings(state / "config" / "pinyon_shift.toml")
        system = system_facts()
        release = read_json(common.ROOT / "config" / "release.json") or {}
        setup_state = read_json(common.ROOT / ".local" / "setup-state.json") or {}
        binaries = {name: sha256_file(executable.parent / name) for name in BINARIES
                    if (executable.parent / name).is_file()}
        dumps = [{"name": path.name, "size_bytes": path.stat().st_size,
                  "sha256": sha256_file(path), "sharing": "kept_local_not_included"}
                 for path in crash_files if path.suffix.lower() in (".dmp", ".core")]
        exit_hex = f"0x{exit_code & 0xFFFFFFFF:08X}"
        manifest = {
            "schema": "pinyon-shift.crash-report.v1",
            "created_utc": iso_utc(datetime.now(timezone.utc)),
            "crash_id": fingerprint,
            "process": {
                "process_id": process_id,
                "started_utc": iso_utc(started),
                "session_id": event_log.stem if event_log is not None else None,
                "exit_code_signed": exit_code,
                "exit_code_hex": exit_hex,
            },
            "exception": details,
            "build": {"binaries": binaries,
                      "provenance": read_json(executable.parent / "pinyon_shift_build.json")},
            "release": {"version": release.get("version"), "channel": release.get("channel"),
                        "dump_id": setup_state.get("dump_id")},
            "system": {key: system.get(key) for key in (
                "os", "os_version", "os_build", "cpu", "logical_processors", "memory_bytes", "gpu")},
            "settings": settings,
            "audio": {"xma_stalls": xma_stalls},
            "graphics": {
                # The native renderer is the only renderer; there is no choice to report.
                "renderer": "native",
                "backend": selected.get("backend") if selected else None,
                "backend_requested": logging_ready.get("renderer") if logging_ready else None,
                "logging_initialized": logging_ready is not None,
                "selected_device": {key: selected.get(key) for key in (
                    "backend", "name", "vendor_id", "device_id", "api_version",
                    "driver_version")} if selected else None,
                "resolve_readback": resolve_counters,
                "presentation": presentation_counters,
            },
            "local_dumps": dumps,
            "privacy": {
                "paths_redacted": True,
                "game_files_included": False,
                "save_data_included": False,
                "generated_code_included": False,
                "memory_dump_included": False,
                "input_capture_included": False,
                "audio_payload_included": False,
            },
        }
        # The system facts and the device come from the OS and the driver,
        # but pass through the same filter as the logs.
        report = protect(json.dumps(manifest, indent=2, ensure_ascii=False), replacements)
        (staging / "report.json").write_bytes((report + os.linesep).encode("utf-8"))

        installed = "; ".join(str(gpu.get("Name")) for gpu in system.get("gpu") or []
                              if isinstance(gpu, dict))
        platform_line = (f"- Windows build: `{system.get('os_build') or ''}`" if common.WINDOWS
                         else f"- OS: `{system.get('os') or ''} ({system.get('os_build') or ''})`")
        title = f"[Crash] {fingerprint}"
        body = "\n".join((
            "### What happened?",
            "",
            "<!-- Tell us what you were doing immediately before the crash. -->",
            "",
            "### Reproduction steps",
            "",
            "1. ",
            "2. ",
            "3. ",
            "",
            "### Crash details",
            "",
            f"- Crash ID: `{fingerprint}`",
            f"- Exit code: `{exit_hex}`",
            f"- Exception: `{details['exception_code'] or ''}`",
            platform_line,
            (f"- GPU selected: `{selected.get('name')}`" if selected
             else f"- GPU selected: unknown; installed adapters: `{installed}`"),
            "",
            "### Diagnostic report",
            "",
            "<!-- Drag the ZIP selected by the launcher into this issue. It excludes game files, "
            "saves, generated code, and memory dumps. -->",
        ))
        body = protect(body, replacements)
        (staging / "issue-body.md").write_bytes(body.encode("utf-8"))
        (staging / "README.txt").write_bytes(
            ("Attach this ZIP to the GitHub issue opened by the launcher.\r\n"
             "No game files, saves, generated code, input capture, or memory dumps are included.\r\n"
             "Local crash dumps remain only in your crashes folder for private follow-up.\r\n")
            .encode("utf-8"))

        name_pattern = username_pattern(replacements["<USERNAME>"])
        for path in staging.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in FORBIDDEN_EXTENSIONS:
                raise CrashError(f"Forbidden diagnostic attachment: {path.name}")
            content = path.read_text(encoding="utf-8", errors="replace")
            if name_pattern is not None and name_pattern.search(content):
                raise CrashError(f"A local user name remained in the diagnostic report: {path.name}")

        archive = reports / f"PinyonShift-{fingerprint}-{timestamp}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(staging).as_posix())
        issue_url = (f"{repository}/issues/new?title={urllib.parse.quote(title, safe='')}"
                     f"&body={urllib.parse.quote(body, safe='')}&labels=crash")
        pending = {"schema": 1, "created_utc": iso_utc(datetime.now(timezone.utc)),
                   "crash_id": fingerprint, "bundle": str(archive), "issue_url": issue_url,
                   "exit_code_hex": exit_hex}
        (reports / "pending-report.json").write_bytes(
            (json.dumps(pending, indent=2) + os.linesep).encode("utf-8"))
        return pending
    finally:
        temporary = Path(tempfile.gettempdir()).resolve()
        resolved = staging.resolve()
        if resolved.parent == temporary and resolved.name.startswith("PinyonShiftReport-"):
            shutil.rmtree(resolved, ignore_errors=True)


def pending(state: Path) -> dict:
    record = read_json(state / "reports" / "pending-report.json")
    if not isinstance(record, dict) or not record.get("bundle"):
        return {"pending": False}
    record["pending"] = Path(record["bundle"]).is_file()
    return record


def run(args: argparse.Namespace) -> dict:
    state = common.state_root(args.state_root)
    if args.crash_command == "pending":
        return pending(state)
    started = parse_utc(args.started_utc)
    return create(state, args.executable, started, args.process_id, args.exit_code,
                  args.repository_url)


def add_parser(commands) -> None:
    parser = commands.add_parser("crash-report", help="bundle a crash for an issue report")
    sub = parser.add_subparsers(dest="crash_command", required=True)
    making = sub.add_parser("create", help="bundle the crash of one game process")
    making.add_argument("--executable", type=Path, required=True)
    making.add_argument("--started-utc", required=True, help="when the process started (ISO 8601)")
    making.add_argument("--process-id", type=int, required=True)
    making.add_argument("--exit-code", type=int, required=True)
    making.add_argument("--repository-url", default=common.REPOSITORY_URL)
    sub.add_parser("pending", help="the report the last crash left, if any")
    for action in sub.choices.values():
        action.add_argument("--state-root", type=Path)
        action.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return common.run_command(run, args)
