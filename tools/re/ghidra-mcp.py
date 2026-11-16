#!/usr/bin/env python3
"""Serve the local Ghidra workspace to MCP clients (stdio), headless.

Runs GhidraMCP (LaurieWired, Apache-2.0) in its headless mode over the
project `tools/re/ghidra-workspace.py` builds in `.local/re/ghidra`, so an
agent can ask Ghidra for decompilation, cross-references and callers
without the GUI. Nothing here is committed but this launcher; the tools live
under `.local/re` (docs/REVERSE_ENGINEERING.md, NL-2.2).

Setup, once:
  * build the workspace: `python tools/re/ghidra-workspace.py`;
  * put the GhidraMCP 2.0 release in `.local/re/downloads/ghidramcp-2.0`
    and create the venv:
      python -m venv .local/re/tools/ghidra-mcp-venv
      .local/re/tools/ghidra-mcp-venv/Scripts/python -m pip install \
        ".local/re/downloads/ghidramcp-2.0/GhidraMCP-release-2-0/ghidra_mcp-2.0.0-py3-none-any.whl[headless]"
  * register it for this checkout:
      claude mcp add ghidra -s local -- python tools/re/ghidra-mcp.py
    (or add the same stdio entry to the project's mcpServers in
    ~/.claude.json); it loads in new sessions.

By default the session discards its changes (renames, comments), so the
workspace stays what the knowledge base made it; pass --save to keep them.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RE = ROOT / ".local" / "re"
TOOLS = RE / "tools"


def project_dir() -> str:
    """GhidraMCP resolves the project path, which turns the 8.3 alias back
    into `.local`. So the project lives where no path element starts with a
    dot (%LOCALAPPDATA%/PinyonRE/ghidra on Windows) and `.local/re/ghidra` is
    a junction to it. Remove that junction with rmdir, not a recursive
    delete, which would follow it."""
    project = RE / "ghidra"
    real = project.resolve()
    if any(part.startswith(".") for part in real.parts):
        sys.exit(f"ghidra-mcp: {real} has a dot-prefixed element; move the project out of "
                 ".local and leave a junction (see project_dir)")
    return str(real)


def newest(pattern: str) -> Path:
    matches = sorted(TOOLS.glob(pattern))
    if not matches:
        sys.exit(f"ghidra-mcp: nothing matches {TOOLS / pattern}")
    return matches[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--xex", default=str(RE.parent / "game" / "base" / "default.xex"))
    parser.add_argument("--save", action="store_true", help="keep renames and comments")
    parser.add_argument("--transport", default="stdio")
    args = parser.parse_args()

    venv = TOOLS / "ghidra-mcp-venv"
    exe = venv / ("Scripts/ghidra-mcp.exe" if os.name == "nt" else "bin/ghidra-mcp")
    jar = next((RE / "downloads").glob("ghidramcp-*/**/GhidraMCP.jar"), None)
    if not exe.is_file() or jar is None:
        sys.exit("ghidra-mcp: venv or GhidraMCP.jar missing; see this file's docstring")
    env = dict(os.environ)
    env["JAVA_HOME"] = str(newest("jdk-*"))
    env["GHIDRA_INSTALL_DIR"] = str(newest("ghidra_*_PUBLIC"))
    command = [
        str(exe), "--headless", "--binary", args.xex,
        "--project", project_dir(), "--project-name", "fh1",
        "--no-analyze", "--save" if args.save else "--discard",
        "--extension-jar", str(jar), "--ready-timeout", "300",
        "--transport", args.transport,
    ]
    sys.exit(subprocess.call(command, env=env))


if __name__ == "__main__":
    main()
