#!/usr/bin/env python3
"""Replay a recorded FH1 frame dump offline and compare its front buffer.

A dump comes from a run with `--fh1_frame_dump_frame=<frame>` and
`--fh1_frame_dump_path=<file>`. The replay launches the preview with the title
suspended (`--fh1_frame_replay`), restores the recorded registers, shaders and
guest memory, executes the recorded packets and writes `<dump>.replay.json`
(and the replayed front buffer bytes as `<dump>.replay.bin`). With a golden
replay stored next to the dump (`--write-golden`), any difference from it fails
the run: that is the offline executor regression test.

Run from a pinned seed like the render tests: the seed is copied to a private
state directory, so neither the seed nor the AppData save is written.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path


def load_runner():
    path = Path(__file__).with_name("run-fh1-render-test.py")
    spec = importlib.util.spec_from_file_location("run_fh1_render_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay(args: argparse.Namespace) -> dict[str, object]:
    runner = load_runner()
    dump = args.dump.resolve()
    if not dump.is_file():
        raise ValueError(f"missing frame dump: {dump}")
    result_path = Path(str(dump) + ".replay.json")
    result_bin = Path(str(dump) + ".replay.bin")
    for stale in (result_path, result_bin):
        stale.unlink(missing_ok=True)
    state = args.work.resolve()
    if state.exists():
        shutil.rmtree(state)
    runner.prepare_isolated_state(args.state_root.resolve(), state)
    runner.seed_fh1_shader_storage(args.state_root.resolve(), state)
    if args.shader_pack:
        subprocess.run(
            [sys.executable, str(Path(__file__).with_name("native-shader-pack.py")), "stage",
             str(args.shader_pack.resolve()), "--state-root", str(state)],
            capture_output=True, text=True, check=True)
    # Pipelines are created synchronously: an asynchronous creation drops the
    # draw that requested it, which would make replays nondeterministic.
    # Replay executes packets directly on the GPU thread. A seed that enables
    # the decoder/recorder split otherwise queues work without executing draws.
    game_arguments = [f"--fh1_frame_replay={dump}", "--async_shader_compilation=false",
                      "--gpu_record_thread=false"]
    game_arguments += args.game_argument or []
    command = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        str(Path(__file__).with_name("launch-preview.ps1")),
        "-StateRoot", str(state),
        "-RenderTestTimeoutSeconds", str(args.timeout),
        "-GameArgumentsJson", json.dumps(game_arguments),
        "-SkipShaderPreparation",
        "-Json",
    ]
    if args.configuration:
        command += ["-Configuration", args.configuration]
    if getattr(args, "build_directory", None):
        command += ["-BuildDirectory", str(args.build_directory.resolve())]
    if args.hidden:
        command.append("-Hidden")
    process = subprocess.run(command, capture_output=True, text=True,
                             timeout=args.timeout + 60, check=False)
    if not result_path.is_file():
        raise RuntimeError(
            f"replay wrote no result ({process.returncode}):\n{process.stdout}\n{process.stderr}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if args.max_differing_words is not None and result["differing_words"] > args.max_differing_words:
        result["failure"] = "front buffer differs from the recording"
    # Replays are deterministic, so a golden replay of the same dump is an
    # exact regression reference for executor changes. The ".native" infix
    # dates from when a renderer could be chosen; existing goldens keep it.
    golden = Path(f"{dump}.native.golden.bin")
    actual = result_bin.read_bytes()
    if args.write_golden:
        golden.write_bytes(actual)
        result["golden"] = "written"
    elif golden.is_file():
        expected = golden.read_bytes()
        differing = sum(1 for i in range(0, min(len(actual), len(expected)), 4)
                        if actual[i:i + 4] != expected[i:i + 4])
        differing += abs(len(actual) - len(expected)) // 4
        result["golden_differing_words"] = differing
        if differing:
            result["failure"] = "front buffer differs from the golden replay"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dump", type=Path)
    parser.add_argument("--state-root", type=Path, required=True,
                        help="pinned render seed (see tools/create-render-seed.py)")
    parser.add_argument("--work", type=Path, default=Path(".local/replay/state"),
                        help="private state directory, replaced on every run")
    parser.add_argument("--shader-pack", type=Path)
    parser.add_argument("--configuration")
    parser.add_argument("--build-directory", type=Path,
                        help="the build to run, such as out/build/win-amd64-vulkan")
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-differing-words", type=int,
                        help="fail when more front buffer words differ")
    parser.add_argument("--write-golden", action="store_true",
                        help="store this replay as <dump>.native.golden.bin")
    parser.add_argument("--game-argument", action="append")
    args = parser.parse_args()
    try:
        result = replay(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 1 if "failure" in result else 0


if __name__ == "__main__":
    sys.exit(main())
