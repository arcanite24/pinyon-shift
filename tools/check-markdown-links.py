#!/usr/bin/env python3
"""Validate repository-relative links in tracked Markdown files."""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import urllib.parse


LINK = re.compile(r"(?<!!)\[[^\]]*\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")
SCHEMES = ("http://", "https://", "mailto:", "app://")


def tracked_markdown(root: pathlib.Path) -> list[pathlib.Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"], cwd=root, check=True, capture_output=True
    )
    return [root / path.decode("utf-8") for path in completed.stdout.split(b"\0") if path]


def failures(root: pathlib.Path, files: list[pathlib.Path]) -> list[str]:
    problems: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK.finditer(line):
                raw = match.group("target").strip("<>")
                if not raw or raw.startswith("#") or raw.lower().startswith(SCHEMES):
                    continue
                target_text = urllib.parse.unquote(raw.split("#", 1)[0].split("?", 1)[0])
                if not target_text:
                    continue
                # Public documentation must be portable. Machine-absolute links are
                # invalid even when they happen to exist on the CI machine.
                if pathlib.PureWindowsPath(target_text).is_absolute() or target_text.startswith("/"):
                    problems.append(f"{path.relative_to(root)}:{line_number}: absolute link: {raw}")
                    continue
                target = (path.parent / target_text).resolve()
                try:
                    target.relative_to(root.resolve())
                except ValueError:
                    problems.append(f"{path.relative_to(root)}:{line_number}: link escapes repository: {raw}")
                    continue
                if not target.exists():
                    problems.append(f"{path.relative_to(root)}:{line_number}: missing target: {raw}")
    return problems


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    try:
        problems = failures(root, tracked_markdown(root))
    except (OSError, subprocess.CalledProcessError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("Tracked Markdown links are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
