#!/usr/bin/env python3
"""Verify release version/tag agreement and main-branch ancestry."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys


def git(root: pathlib.Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], cwd=root, text=True, capture_output=True)


def verify(root: pathlib.Path, tag: str | None, main_ref: str) -> dict:
    release = json.loads((root / "config/release.json").read_text(encoding="utf-8"))
    version = release.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?", version):
        raise ValueError("config/release.json contains an invalid version")
    expected_tag = f"v{version}"
    if tag and tag != expected_tag:
        raise ValueError(f"release tag {tag!r} does not match {expected_tag!r}")

    ancestry = git(root, "merge-base", "--is-ancestor", "HEAD", main_ref)
    if ancestry.returncode != 0:
        if ancestry.returncode == 1:
            raise ValueError(f"tagged commit is not contained in {main_ref}")
        raise ValueError(ancestry.stderr.strip() or f"unable to inspect {main_ref}")
    return {
        "schema": "pinyon-shift.release-tag-verification.v1",
        "version": version,
        "expected_tag": expected_tag,
        "tag": tag,
        "main_ref": main_ref,
        "main_contains_head": True,
    }


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME"))
    parser.add_argument("--main-ref", default="refs/remotes/origin/main")
    parser.add_argument("--allow-no-tag", action="store_true")
    args = parser.parse_args()
    if not args.tag and not args.allow_no_tag:
        print("error: no release tag was provided", file=sys.stderr)
        return 2
    try:
        print(json.dumps(verify(root, args.tag, args.main_ref), indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
