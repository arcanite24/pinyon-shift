#!/usr/bin/env python3
"""Create and validate exact-build manual visual-baseline sessions."""
from __future__ import annotations

import argparse, hashlib, json, struct, subprocess
from datetime import datetime, timezone
from pathlib import Path

SCENES = ("front-end", "garage", "open-world-day", "open-world-night", "traffic", "race", "rewind", "ui-heavy")
ROOT = Path(__file__).resolve().parents[1]

def fingerprint(executable: Path | None = None) -> dict:
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=True)
        return result.stdout.strip()
    patch_hasher = hashlib.sha256()
    for patch in sorted((ROOT / "patches" / "rexglue").glob("*.patch")):
        patch_hasher.update(patch.name.encode()); patch_hasher.update(b"\0"); patch_hasher.update(patch.read_bytes())
    data = {"repository_commit": git("rev-parse", "HEAD"),
            "rexglue_patch_set_sha256": patch_hasher.hexdigest()}
    try: data["rexglue_commit"] = git("-C", str(ROOT / ".local" / "rexglue"), "rev-parse", "HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError): data["rexglue_commit"] = None
    if executable and executable.is_file():
        data["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    else: data["executable_sha256"] = None
    material = json.dumps(data, sort_keys=True).encode()
    data["id"] = hashlib.sha256(material).hexdigest()[:16]
    return data

def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"not a valid PNG: {path.name}")
    return struct.unpack(">II", header[16:24])

def create_session(output: Path, executable: Path | None) -> Path:
    build = fingerprint(executable)
    session = output / build["id"]
    (session / "captures").mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "pinyon-shift.visual-baseline.v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                "build": build, "scenes": [{"label": scene, "file": f"captures/{scene}.png"} for scene in SCENES]}
    (session / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return session

def validate(session: Path, allow_missing: bool = False) -> dict:
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    labels = [item["label"] for item in manifest.get("scenes", [])]
    if labels != list(SCENES): raise ValueError("manifest scene labels are missing, reordered, or mismatched")
    missing, dimensions = [], {}
    for item in manifest["scenes"]:
        capture = session / item["file"]
        if not capture.is_file(): missing.append(item["label"])
        else: dimensions[item["label"]] = png_size(capture)
    if missing and not allow_missing: raise ValueError("missing captures: " + ", ".join(missing))
    return {"schema": manifest["schema"], "build": manifest["build"], "missing": missing, "dimensions": dimensions}

def contact_sheet(session: Path) -> Path:
    result = validate(session)
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    width, tile_height = 1440, 430
    rows = (len(SCENES) + 1) // 2
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{rows*tile_height}" viewBox="0 0 {width} {rows*tile_height}">',
             '<rect width="100%" height="100%" fill="#101410"/>']
    for index, item in enumerate(manifest["scenes"]):
        x, y = (index % 2) * 720, (index // 2) * tile_height
        href = item["file"].replace("\\", "/")
        parts += [f'<image href="{href}" x="{x+10}" y="{y+10}" width="700" height="370" preserveAspectRatio="xMidYMid meet"/>',
                  f'<text x="{x+18}" y="{y+408}" fill="#f1ae36" font-family="sans-serif" font-size="20">{item["label"]}</text>']
    parts.append("</svg>")
    target = session / "contact-sheet.svg"
    target.write_text("\n".join(parts) + "\n", encoding="utf-8")
    (session / "validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return target

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("init", "validate", "contact-sheet"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "init" and not args.executable:
            raise ValueError("init requires --executable so the capture folder identifies the exact binary")
        result = create_session(args.path, args.executable) if args.action == "init" else (
            validate(args.path, args.allow_missing) if args.action == "validate" else contact_sheet(args.path))
        print(json.dumps(result if isinstance(result, dict) else {"path": str(result)}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"visual baseline error: {exc}\n")
if __name__ == "__main__": raise SystemExit(main())
