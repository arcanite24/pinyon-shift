#!/usr/bin/env python3
"""Record operator-driven qualification markers and package sanitized evidence."""
from __future__ import annotations

import argparse, hashlib, json, zipfile
from datetime import datetime, timezone
from pathlib import Path

MARKERS = ("cold-boot", "menu", "race", "save", "clean-exit", "relaunch", "reload")

def utc() -> str: return datetime.now(timezone.utc).isoformat()
def digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path: Path) -> dict: return json.loads(path.read_text(encoding="utf-8"))
def save(path: Path, value: dict) -> None: path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

def start(root: Path, build_manifest: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    session = root / timestamp
    session.mkdir(parents=True)
    manifest = {"schema": "pinyon-shift.qualification.v1", "started_utc": utc(),
                "build_manifest": json.loads(build_manifest.read_text(encoding="utf-8")), "markers": []}
    save(session / "manifest.json", manifest)
    return session

def mark(session: Path, name: str, note: str | None) -> dict:
    manifest = load(session / "manifest.json")
    if name not in MARKERS: raise ValueError("unsupported marker")
    if any(item["name"] == name for item in manifest["markers"]): raise ValueError(f"marker already recorded: {name}")
    expected = MARKERS[len(manifest["markers"])] if len(manifest["markers"]) < len(MARKERS) else None
    if name != expected: raise ValueError(f"expected marker {expected}, got {name}")
    entry = {"name": name, "recorded_utc": utc()}
    if note: entry["note"] = note[:240]
    manifest["markers"].append(entry); save(session / "manifest.json", manifest)
    return entry

def package(session: Path, evidence: list[Path]) -> Path:
    manifest_path = session / "manifest.json"; manifest = load(manifest_path)
    names = [item["name"] for item in manifest["markers"]]
    if names != list(MARKERS): raise ValueError("qualification is incomplete; missing ordered markers")
    allowed = {".json", ".jsonl", ".log", ".txt", ".csv", ".md", ".svg"}
    records = []
    target = session / "qualification-evidence.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(manifest_path, "manifest.json")
        for path in evidence:
            resolved = path.resolve()
            if not resolved.is_file() or resolved.suffix.lower() not in allowed:
                raise ValueError(f"unsafe evidence file: {path}")
            record = {"name": resolved.name, "sha256": digest(resolved), "size_bytes": resolved.stat().st_size}
            records.append(record); archive.write(resolved, f"evidence/{resolved.name}")
        archive.writestr("evidence-index.json", json.dumps(records, indent=2) + "\n")
    return target

def main() -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("start"); p.add_argument("root", type=Path); p.add_argument("--build-manifest", type=Path, required=True)
    p = sub.add_parser("mark"); p.add_argument("session", type=Path); p.add_argument("name", choices=MARKERS); p.add_argument("--note")
    p = sub.add_parser("package"); p.add_argument("session", type=Path); p.add_argument("--evidence", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        result = start(args.root, args.build_manifest) if args.action == "start" else (mark(args.session, args.name, args.note) if args.action == "mark" else package(args.session, args.evidence))
        print(json.dumps(result if isinstance(result, dict) else {"path": str(result)}, indent=2)); return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc: parser.exit(2, f"qualification error: {exc}\n")
if __name__ == "__main__": raise SystemExit(main())
