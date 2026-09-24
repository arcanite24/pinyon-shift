"""Prepare a checked current-run SNR-04 manifest while the game stays open."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time


TOOLS = Path(__file__).resolve().parent
STEMS = ("snr02-track", "snr02-items", "snr03-scene",
         "snr03-characters", "snr03-manager", "snr03-remainder")


def run(*args):
    result = subprocess.run([sys.executable, *map(str, args)],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name}: {result.stderr.strip()}")
    return result.stdout.strip()


def snapshot_logs(log_dir: Path, cutoff: str, destination: Path):
    queued = False
    with destination.open("w", encoding="utf-8") as sink:
        for path in sorted(log_dir.glob("runtime*.log"),
                           key=lambda item: item.stat().st_mtime):
            for line in path.open(encoding="utf-8", errors="replace"):
                if len(line) < 24 or line[0] != "[" or line[1:24] < cutoff:
                    continue
                sink.write(line)
                queued |= "FH1 SNR04 shared target queued" in line
    return queued


def prepare(args):
    start = datetime.now().strftime("%Y-%m-%d %H:%M:%S.000")
    work = args.manifest.with_suffix(".work")
    work.mkdir(parents=True, exist_ok=False)
    evidence = work / "evidence.log"
    deadline = time.monotonic() + args.timeout
    expected = [args.fixtures / f"{stem}-{args.source_frame}.bin"
                for stem in STEMS]
    if args.evidence:
        evidence.write_bytes(args.evidence.read_bytes())
    else:
        while time.monotonic() < deadline:
            if all(path.is_file() and path.stat().st_size > 16
                   for path in expected) and snapshot_logs(args.logs, start, evidence):
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("current-run fixtures or output callback missing")
    ledger, order = work / "ledger.json", work / "order.json"
    run(TOOLS / "summarize-snr01-frame-wide-census.py", evidence,
        "--source-frame", args.source_frame, "--require-candidate-boundary",
        "--output", ledger)
    run(TOOLS / "verify-snr04-complete-slice.py", args.fixtures,
        evidence, ledger, order)
    track, remainder = work / "track-shaders", work / "remainder-shaders"
    run(TOOLS / "extract-snr04-track-shaders.py", expected[0], args.pack, track)
    run(TOOLS / "extract-snr04-remainder-shaders.py", expected[5], evidence,
        ledger, args.pack, remainder)
    batch = work / "batch"
    run(TOOLS / "replay-snr04-complete-slice.py", "--msaa4", "--gpu-shared",
        "--manifest-only", order, args.fixtures, args.executable, remainder,
        track, args.dxil, args.vegetation_shader, batch)
    os.replace(batch / "gpu-shared.manifest", args.manifest)
    return order, args.manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fixtures", "logs", "pack", "dxil", "executable",
                 "vegetation_shader", "manifest"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--source-frame", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--evidence", type=Path,
                        help="reuse a completed log to check the preparation path")
    options = parser.parse_args()
    order_path, manifest_path = prepare(options)
    print(f"verified current-run order: {order_path}")
    print(f"published manifest: {manifest_path}")
