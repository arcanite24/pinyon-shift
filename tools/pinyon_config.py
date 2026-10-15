#!/usr/bin/env python3
"""The launcher's runtime settings (<state>/config/pinyon_shift.toml).

This is the one implementation of the launchers' Settings panel:
tools/set-graphics-experiment.ps1 is a thin wrapper over it for the Windows
launcher, and the Desktop launcher calls it directly.

  pinyon.py config get                  the settings the panel shows
  pinyon.py config apply [--resolution-scale N] [--output-scaling M]
                         [--treasure-map true|false] [--game-preset P] ...
  pinyon.py config reset                back up the file, write the defaults
  pinyon.py config restore              back up the file, restore the newest backup
  pinyon.py config treasure-map on|off  the Treasure Map DLC switch

Every command takes --state-root (default .local/preview) and --json, and
prints one pinyon-shift.graphics-settings.v2 object. `apply` writes only the
settings passed: the in-game settings screen edits the same file.

The file is edited by the rules of tools/host-config.ps1 and
src/config/host_config.cpp (tools/tests/test_host_config.py checks they write
the same bytes):

- A setting is the first line whose name, after leading spaces or tabs, is
  followed by optional spaces or tabs and '='.
- Its value runs to a '#' or the end of the line, trimmed, with the
  surrounding quotes of a string removed; an empty value counts as absent.
- Setting a value replaces that line (not its line ending) with
  `name = value`, or appends the line using the file's line ending.
- Files are written through a temporary file and end with one line ending.
- A backup is a copy in config/backups/pinyon_shift-<UTC time>.toml.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_common as common  # noqa: E402

SCHEMA = 29

# --- host-config.ps1 ------------------------------------------------------------------


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def get_value(text: str, name: str, default: str | None) -> str | None:
    match = re.search(r"(?m)^[ \t]*" + re.escape(name) + r"[ \t]*=(?P<value>[^#\r\n]*)", text)
    if match:
        value = match.group("value").strip().strip('"')
        if value:
            return value
    return default


def has_setting(text: str, name: str) -> bool:
    return re.search(r"(?m)^[ \t]*" + re.escape(name) + r"[ \t]*=", text) is not None


def set_value(text: str, name: str, value: str) -> str:
    pattern = re.compile(r"(?m)^[ \t]*" + re.escape(name) + r"[ \t]*=[^\r\n]*")
    replacement = f"{name} = {value}"
    if pattern.search(text):
        return pattern.sub(lambda _: replacement, text, count=1)
    newline = newline_of(text)
    trimmed = text.rstrip("\r\n")
    return f"{trimmed}{newline}{replacement}{newline}" if trimmed else f"{replacement}{newline}"


def remove_value(text: str, name: str) -> str:
    return re.sub(r"(?m)^[ \t]*" + re.escape(name) + r"[ \t]*=[^\r\n]*(?:\r?\n|$)", "", text)


def read_config(path: Path) -> str:
    # utf-8-sig: a byte-order mark is not part of the first setting's name.
    # Bytes, not text mode: universal newlines would turn CRLF into LF.
    return path.read_bytes().decode("utf-8-sig") if path.is_file() else ""


def write_config(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes((text.rstrip("\r\n") + newline_of(text)).encode("utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def backup_config(path: Path) -> str | None:
    if not path.is_file():
        return None
    directory = path.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}Z"
    destination = directory / f"pinyon_shift-{stamp}.toml"
    while destination.exists():
        # Two backups in the same millisecond keep both.
        destination = directory / f"pinyon_shift-{stamp}-{uuid.uuid4().hex[:6]}.toml"
    shutil.copy2(path, destination)
    return str(destination)


# --- set-graphics-experiment.ps1 --------------------------------------------------------

DEFAULT_CONFIG = """\
# Pinyon Shift host configuration.
# Schema 29 writes every keyboard bind (#432); schema 28 supports only Vulkan with the split GPU commands thread; schema 26
# stops re-uploading CPU-written memory every frame; schema 25 keeps one
# occlusion-query path; schema 24 retired the renderer choice.
pinyon_shift_config_schema = 29
input_backend = "sdl"
hid_mappings_file = "gamecontrollerdb.txt"
mnk_mode = true
keybind_a = "Space,Return,LMB"
keybind_b = "E,Backspace"
keybind_x = "Q"
keybind_y = "R"
keybind_left_trigger = "S"
keybind_right_trigger = "W"
keybind_left_shoulder = "Z"
keybind_right_shoulder = "C"
keybind_lstick_up = "Up"
keybind_lstick_down = "Down"
keybind_lstick_left = "A,Left"
keybind_lstick_right = "D,Right"
keybind_lstick_press = "F"
keybind_rstick_up = "I"
keybind_rstick_down = "K"
keybind_rstick_left = "J"
keybind_rstick_right = "L"
keybind_rstick_press = "V"
keybind_dpad_up = "Shift+Up"
keybind_dpad_down = "Shift+Down"
keybind_dpad_left = "Shift+Left"
keybind_dpad_right = "Shift+Right"
keybind_back = "Tab,M"
keybind_start = "Escape"
d3d12_allow_variable_refresh_rate_and_tearing = false
gpu_backend = "vulkan"
gpu_record_thread = true
vsync = true
host_present_fps_limit = 0
host_present_sleep_spin = true
pinyon_shift_stabilize_vehicle_presentation = false
pinyon_shift_skip_opening_movies = false
pinyon_shift_fh1_render_fps_limit = 60
pinyon_shift_fh1_source_presentation = true
xma_relaxed_padding_admission = false
anisotropic_override = -1
present_effect = "bilinear"
swap_post_effect = "none"
disable_bloom = true
disable_motion_blur = true
disable_depth_of_field = true
fh1_msaa_single_sample = true
draw_resolution_scale_x = 1
draw_resolution_scale_y = 1
clear_memory_page_state = false"""

# The keys configurations had through schema 28; schema 29 writes them into
# older files that lack them, as the game does (src/config/default_keys.h).
SCHEMA_28_KEYS = {
    "keybind_a": "LMB,Space", "keybind_b": "Quote,Backspace", "keybind_x": "L",
    "keybind_y": "P", "keybind_left_trigger": "Q,I", "keybind_right_trigger": "E,O",
    "keybind_left_shoulder": "1", "keybind_right_shoulder": "3", "keybind_lstick_up": "W",
    "keybind_lstick_down": "S", "keybind_lstick_left": "A", "keybind_lstick_right": "D",
    "keybind_lstick_press": "F", "keybind_rstick_up": "Up", "keybind_rstick_down": "Down",
    "keybind_rstick_left": "Left", "keybind_rstick_right": "Right", "keybind_rstick_press": "K",
    "keybind_dpad_up": "Shift+Up", "keybind_dpad_down": "Shift+Down",
    "keybind_dpad_left": "Shift+Left", "keybind_dpad_right": "Shift+Right",
    "keybind_back": "Z,Tab", "keybind_start": "Return",
}

# Settings a config file may still carry from an earlier release. Apply writes
# the current schema, so the game's own migration never sees the file again:
# drop every setting that migration retires (src/pinyon_shift_app.cpp).
RETIRED_SETTINGS = (
    "pinyon_shift_fh1_guest_vblank_hz",
    "pinyon_shift_native_renderer_texture_bridge",
    "pinyon_shift_native_renderer",
    "pinyon_shift_native_renderer_sky_horizon_suppression",
    "pinyon_shift_native_renderer_census",
    "pinyon_shift_fh1_native_v4",
    "readback_resolve_half_pixel_offset",
    "readback_memexport",
    "readback_memexport_fast",
    "fh1_renderer",
    "fh1_native_shadow",
    "fh1_native_shadow_dump_dir",
    "fh1_native_shadow_dump_frames",
    "fh1_native_shadow_verify",
    "fh1_native_shadow_verify_draws",
    "fh1_discovery_sampling",
    "fh1_owned_depth_clear",
    "fh1_owned_depth_tile_clear",
    "fh1_native_reflection_mips",
    "fh1_mip_decode_probe",
    "fh1_native_ui_boundary_probe",
    "fh1_glow_probe",
    "fh1_recycle_geometry_buffers",
    "fh1_contain_geometry_windows",
    "fh1_cache_geometry_rejections",
    "fh1_geometry_cache_mb",
    "native_stencil_value_output",
    "native_stencil_value_output_d3d12_intel",
    "pinyon_shift_native_race",
    "pinyon_shift_native_race_capture_start_frame",
    "pinyon_shift_native_ui_live",
    "pinyon_shift_native_ui_replay_source_frame",
    "pinyon_shift_native_ui_scene_probe",
    "pinyon_shift_native_ui_shadow_start_frame",
    "pinyon_shift_native_ui_clear_probe",
    "pinyon_shift_native_output_clear_probe",
    "pinyon_shift_native_scene_clear_probe",
    "pinyon_shift_native_scene_triangle_probe",
    "pinyon_shift_native_small_target_probe",
    "pinyon_shift_native_track_probe",
    "pinyon_shift_native_ordered_live_probe",
    "pinyon_shift_fh1_clear_producer_trace",
    "pinyon_shift_fh1_scene_dump",
    "pinyon_shift_snr01_trace_following_frame",
    "pinyon_shift_snr01_trace_resident_packet_writers",
    "pinyon_shift_snr01_trace_source_frame",
    "pinyon_shift_snr01_watch_packet_pages",
    "pinyon_shift_snr02_item_payload_probe",
    "pinyon_shift_snr02_trace_first_rebuild_after_frame",
    "pinyon_shift_snr02_trace_view_call",
    "pinyon_shift_snr02_track_payload_probe",
    "pinyon_shift_snr03_probe_following_frame",
    "pinyon_shift_snr03_probe_frame",
    "pinyon_shift_snr04_live_continuous",
    "pinyon_shift_snr04_live_handoff",
    "pinyon_shift_snr04_live_source_frame",
    "pinyon_shift_snr04_live_worker",
    "pinyon_shift_snr_m02_trace_source_frame",
    "occlusion_query",
    "zpd_end_policy",
    "zpd_end_fallback",
)

# The values of each in-game preset, as its row in the settings screen sets
# them (Vulkan and the recorder thread are always set by Apply). Every preset
# sets shadows, the reflection rate and single-pass scene back to the desktop
# defaults that ULTRA LOW 30 turns down, as the game does.
GAME_PRESETS = {
    "ultra_low_30": {"draw_resolution_scale_x": "1", "draw_resolution_scale_y": "1",
                     "present_effect": '"bilinear"', "fh1_msaa_single_sample": "true",
                     "host_present_fps_limit": "0", "pinyon_shift_fh1_render_fps_limit": "30",
                     "anisotropic_override": "-1", "swap_post_effect": '"none"',
                     "pinyon_shift_fh1_shadows": "false", "pinyon_shift_fh1_env_map_rate": "0.25",
                     "fh1_untile_predicated_tiling": "true"},
    "low_spec_60": {"draw_resolution_scale_x": "1", "draw_resolution_scale_y": "1",
                    "present_effect": '"bilinear"', "fh1_msaa_single_sample": "true",
                    "host_present_fps_limit": "0", "pinyon_shift_fh1_render_fps_limit": "60",
                    "anisotropic_override": "-1", "swap_post_effect": '"none"',
                    "pinyon_shift_fh1_shadows": "true", "pinyon_shift_fh1_env_map_rate": "1",
                    "fh1_untile_predicated_tiling": "false"},
    "balanced_40": {"draw_resolution_scale_x": "1", "draw_resolution_scale_y": "1",
                    "present_effect": '"bilinear"', "fh1_msaa_single_sample": "true",
                    "host_present_fps_limit": "0", "pinyon_shift_fh1_render_fps_limit": "40",
                    "anisotropic_override": "-1", "swap_post_effect": '"none"',
                    "pinyon_shift_fh1_shadows": "true", "pinyon_shift_fh1_env_map_rate": "1",
                    "fh1_untile_predicated_tiling": "false"},
    "performance_120": {"draw_resolution_scale_x": "1", "draw_resolution_scale_y": "1",
                        "present_effect": '"fsr"', "fh1_msaa_single_sample": "true",
                        "host_present_fps_limit": "0", "pinyon_shift_fh1_render_fps_limit": "120",
                        "pinyon_shift_fh1_shadows": "true", "pinyon_shift_fh1_env_map_rate": "1",
                        "fh1_untile_predicated_tiling": "false"},
    "quality_60": {"draw_resolution_scale_x": "2", "draw_resolution_scale_y": "2",
                   "present_effect": '"bilinear"', "fh1_msaa_single_sample": "false",
                   "host_present_fps_limit": "0", "pinyon_shift_fh1_render_fps_limit": "60",
                   "pinyon_shift_fh1_shadows": "true", "pinyon_shift_fh1_env_map_rate": "1",
                   "fh1_untile_predicated_tiling": "false"},
}

PRESET_DEFAULTS = {
    "present_effect": '"bilinear"', "fh1_msaa_single_sample": "false",
    "host_present_fps_limit": "0", "anisotropic_override": "-1", "swap_post_effect": '"none"',
    "pinyon_shift_fh1_render_fps_limit": "0", "draw_resolution_scale_x": "1",
    "draw_resolution_scale_y": "1", "pinyon_shift_fh1_shadows": "true",
    "pinyon_shift_fh1_env_map_rate": "1", "fh1_untile_predicated_tiling": "false",
}

ANISOTROPY_TO_OVERRIDE = {0: -1, 4: 3, 8: 4, 16: 5}
OVERRIDE_TO_ANISOTROPY = {3: 4, 4: 8, 5: 16}


def to_int(value: str | None) -> int:
    text = (value or "0").strip()
    try:
        return int(text)
    except ValueError:
        return int(round(float(text)))


def default_config() -> str:
    """The defaults in the platform's line ending, as set-graphics-experiment.ps1
    (a CRLF file on Windows) writes them."""
    return DEFAULT_CONFIG.replace("\n", "\r\n") if common.WINDOWS else DEFAULT_CONFIG


def game_preset_of(text: str) -> str:
    """The in-game preset the file matches, as the settings screen shows it."""
    for name, settings in GAME_PRESETS.items():
        if all((get_value(text, key, PRESET_DEFAULTS[key]) or "").strip('"').lower() ==
               value.strip('"').lower() for key, value in settings.items()):
            return name
    return "custom"


def schema_of(text: str) -> int:
    match = re.search(r"(?m)^\s*pinyon_shift_config_schema\s*=\s*(?P<value>[0-9]+)\s*(?:#.*)?$",
                      text)
    # A file without one was saved by the old F4 overlay with only changed
    # settings; the game keeps them under the current schema, so do the same.
    return int(match.group("value")) if match else SCHEMA


def settings_result(text: str, config: Path, backup: str | None, operation: str) -> dict:
    def flag(name: str, default: str) -> bool:
        return get_value(text, name, default) == "true"

    resolution_scale = to_int(get_value(text, "draw_resolution_scale_x", "1"))
    vsync = flag("vsync", "true")
    if resolution_scale == 2:
        preset = "experimental_2x"
    elif resolution_scale == 3:
        preset = "experimental_3x"
    elif resolution_scale == 1 and vsync:
        preset = "shipping_1x"
    else:
        preset = "custom"
    return {
        "schema": "pinyon-shift.graphics-settings.v2",
        "operation": operation.lower(),
        "config_path": str(config),
        "backup_path": backup,
        "settings": {
            "anisotropy": OVERRIDE_TO_ANISOTROPY.get(
                to_int(get_value(text, "anisotropic_override", "-1")), 0),
            "post_effect": get_value(text, "swap_post_effect", "none"),
            "disable_bloom": flag("disable_bloom", "true"),
            "disable_motion_blur": flag("disable_motion_blur", "true"),
            "disable_depth_of_field": flag("disable_depth_of_field", "true"),
            "preset": preset,
            "game_preset": game_preset_of(text),
            "resolution_scale": resolution_scale,
            # Player settings use Vulkan; schema 28 migrates legacy selections.
            "graphics_api": "vulkan",
            "output_scaling": (get_value(text, "present_effect", '"bilinear"') or "")
                              .strip('"').lower(),
            # Where the image lands, for the launcher's resolution line.
            "fullscreen": flag("fullscreen", "true"),
            "monitor": to_int(get_value(text, "monitor", "0")),
            "window_width": to_int(get_value(text, "window_width", "0")),
            "window_height": to_int(get_value(text, "window_height", "0")),
            "letterbox": flag("present_letterbox", "true"),
            # The game turns the Treasure Map on unless the file says false.
            "treasure_map": flag("pinyon_shift_dlc_treasure_map", "true"),
            "clear_memory_page_state": flag("clear_memory_page_state", "false"),
            "vsync": vsync,
            "host_present_fps_limit": to_int(get_value(text, "host_present_fps_limit", "0")),
            "fh1_render_fps_limit": to_int(get_value(text, "pinyon_shift_fh1_render_fps_limit",
                                                     "0")),
            "host_present_sleep_spin": flag("host_present_sleep_spin", "true"),
        },
        "restart_required": operation.lower() != "get",
    }


def check_schema(text: str, what: str = "Unsupported host configuration schema") -> None:
    schema = schema_of(text)
    if schema < 1 or schema > SCHEMA:
        raise common.CommandError(f"{what}: {schema}")


def apply_settings(text: str, options: dict) -> str:
    """Apply: migrate to the current schema, then write only the options
    passed (a None value is an option not passed)."""
    schema = schema_of(text)
    # The retired guest vblank rate became the render limit, which now
    # defaults to 60 (LOW-SPEC 60), not the display's rate.
    had_legacy_vblank = has_setting(text, "pinyon_shift_fh1_guest_vblank_hz")
    for retired in RETIRED_SETTINGS:
        text = remove_value(text, retired)
    # readback_resolve is a developer setting; only launchers before schema
    # 24 wrote it for players (src/pinyon_shift_app.cpp).
    if schema < 24:
        text = remove_value(text, "readback_resolve")
    # Schema 26 turned clear_memory_page_state off (src/pinyon_shift_app.cpp).
    if schema < 26:
        text = set_value(text, "clear_memory_page_state", "false")
    # Schema 28 makes Vulkan the only supported player backend.
    text = set_value(text, "gpu_backend", '"vulkan"')
    text = set_value(text, "gpu_record_thread", "true")
    # Schema 28 turns off depth of field once, as the game does; a choice
    # passed below still wins.
    if schema < 28:
        text = set_value(text, "disable_depth_of_field", "true")
    if schema < 29:
        for key, value in SCHEMA_28_KEYS.items():
            if not has_setting(text, key):
                text = set_value(text, key, f'"{value}"')
    text = set_value(text, "pinyon_shift_config_schema", str(SCHEMA))
    text = set_value(text, "pinyon_shift_fh1_source_presentation", "true")
    if not has_setting(text, "xma_relaxed_padding_admission"):
        text = set_value(text, "xma_relaxed_padding_admission", "false")
    resolution = {"shipping_1x": 1, "experimental_2x": 2, "experimental_3x": 3}.get(
        options.get("preset") or "custom")
    if resolution is None and options.get("resolution_scale") is not None:
        resolution = options["resolution_scale"]
    if resolution is not None:
        text = set_value(text, "draw_resolution_scale_x", str(resolution))
        text = set_value(text, "draw_resolution_scale_y", str(resolution))
    if options.get("treasure_map") is not None:
        text = set_value(text, "pinyon_shift_dlc_treasure_map", options["treasure_map"])
    if options.get("output_scaling") is not None:
        text = set_value(text, "present_effect", f'"{options["output_scaling"]}"')
    if options.get("anisotropy") is not None:
        text = set_value(text, "anisotropic_override",
                         str(ANISOTROPY_TO_OVERRIDE[options["anisotropy"]]))
    if options.get("post_effect") is not None:
        text = set_value(text, "swap_post_effect", f'"{options["post_effect"]}"')
    for option, key in (("disable_bloom", "disable_bloom"),
                        ("disable_motion_blur", "disable_motion_blur"),
                        ("disable_depth_of_field", "disable_depth_of_field")):
        if options.get(option) is not None:
            text = set_value(text, key, options[option])
    if options.get("presentation_fps") is not None:
        text = set_value(text, "host_present_fps_limit", str(options["presentation_fps"]))
    if options.get("render_fps") is not None or had_legacy_vblank:
        render_fps = options.get("render_fps")
        text = set_value(text, "pinyon_shift_fh1_render_fps_limit",
                         str(60 if render_fps is None else render_fps))
    if options.get("game_preset"):
        for key, value in GAME_PRESETS[options["game_preset"]].items():
            text = set_value(text, key, value)
    return set_value(text, "host_present_sleep_spin", "true")


def run(args: argparse.Namespace) -> dict:
    state = common.state_root(args.state_root)
    directory = state / "config"
    config = directory / "pinyon_shift.toml"
    backups = directory / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    action = args.config_command
    backup = None
    if action == "get":
        text = read_config(config) if config.is_file() else default_config()
        check_schema(text)
    elif action == "reset":
        backup = backup_config(config)
        text = default_config()
        write_config(config, text)
    elif action == "restore":
        candidates = sorted(backups.glob("pinyon_shift-*.toml"),
                            key=lambda path: path.stat().st_mtime_ns,
                            reverse=True) if backups.is_dir() else []
        candidates = [path for path in candidates if path.is_file()]
        if not candidates:
            raise common.CommandError("No runtime-settings backup is available.")
        source = candidates[0]
        backup = backup_config(config)
        text = read_config(source)
        check_schema(text, "Backup uses unsupported schema")
        write_config(config, text)
    else:
        text = read_config(config) if config.is_file() else default_config()
        check_schema(text)
        if action == "treasure-map":
            options = {"treasure_map": "true" if args.state == "on" else "false"}
        else:
            options = {name: getattr(args, name) for name in (
                "anisotropy", "post_effect", "resolution_scale", "output_scaling",
                "treasure_map", "preset", "game_preset", "presentation_fps", "render_fps",
                "disable_bloom", "disable_motion_blur", "disable_depth_of_field")}
        backup = backup_config(config)
        text = apply_settings(text, options)
        write_config(config, text)
    operation = {"treasure-map": "apply"}.get(action, action)
    return settings_result(text, config, backup, operation)


def add_parser(commands) -> None:
    parser = commands.add_parser("config", help="the launcher's runtime settings")
    sub = parser.add_subparsers(dest="config_command", required=True)
    sub.add_parser("get", help="show the settings")
    sub.add_parser("reset", help="back up the settings file and write the defaults")
    sub.add_parser("restore", help="restore the newest settings backup")
    treasure = sub.add_parser("treasure-map", help="turn the Treasure Map DLC on or off")
    treasure.add_argument("state", choices=("on", "off"))
    apply = sub.add_parser("apply", help="write the settings passed")
    booleans = ("true", "false")
    apply.add_argument("--anisotropy", type=int, choices=(0, 4, 8, 16))
    apply.add_argument("--post-effect", choices=("none", "fxaa", "fxaa_extreme"))
    apply.add_argument("--resolution-scale", type=int, choices=(1, 2, 3, 4))
    apply.add_argument("--graphics-api", choices=("vulkan",))
    apply.add_argument("--output-scaling", choices=("bilinear", "cas", "fsr"))
    apply.add_argument("--treasure-map", choices=booleans)
    apply.add_argument("--preset", choices=("custom", "shipping_1x", "experimental_2x",
                                            "experimental_3x"))
    apply.add_argument("--game-preset", choices=tuple(GAME_PRESETS))
    apply.add_argument("--presentation-fps", type=int, choices=(0, 30, 60, 120, 240))
    apply.add_argument("--render-fps", type=int, choices=range(0, 241), metavar="0-240")
    apply.add_argument("--disable-bloom", choices=booleans)
    apply.add_argument("--disable-motion-blur", choices=booleans)
    apply.add_argument("--disable-depth-of-field", choices=booleans)
    for action in sub.choices.values():
        action.add_argument("--state-root", type=Path)
        action.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return common.run_command(run, args)
