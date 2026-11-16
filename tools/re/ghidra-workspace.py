#!/usr/bin/env python3
"""Build the local Ghidra workspace from the player's own dump (NEXT_LEVEL_RESEARCH.md NL-2.2).

The workspace lives in `.local/re/ghidra` and is never committed. The tool:

  1. writes `.local/re/ghidra-import.tsv` from what the repository already
     knows: ShiftGlue's function starts (the generated function table), the
     recorded names and address records (`tools/re/kb.py symbols`) and the
     vtables (`classes.json` from the generator, when present);
  2. imports the executable with Ghidra's headless analyzer and the XEX
     loader extension, applying that table before auto-analysis
     (`tools/re/ghidra/ApplyPinyonKnowledge.java`), so the analysis follows
     ShiftGlue's boundaries.

Ghidra 12.1.3, a JDK 21 and the XEXLoaderWV extension for that Ghidra
version are expected under `.local/re/tools` (see docs/NEXT_LEVEL_RESEARCH.md
NL-2.2 for where they come from). Names drafted with Ghidra or an LLM bridge
stay at "guess" until a route or hook confirms them, as every finding does.

    python -I tools/re/ghidra-workspace.py
    python -I tools/re/ghidra-workspace.py --table-only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RE = ROOT / ".local" / "re"
TOOLS = RE / "tools"


def find_one(pattern: str) -> Path | None:
    found = sorted(TOOLS.glob(pattern))
    return found[-1] if found else None


def short_path(path: Path) -> str:
    """Ghidra refuses a project path with an element starting with '.', as
    `.local` does; on Windows its 8.3 form (`LOCAL~1`) is accepted."""
    # Resolve first: `.local/re/ghidra` may be a junction to a dot-free path.
    if not any(part.startswith(".") for part in path.resolve().parts) or os.name != "nt":
        return str(path.resolve())
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.kernel32.GetShortPathNameW(str(path.resolve()), buffer, len(buffer)):
        return buffer.value
    sys.exit(f"Ghidra cannot use {path} (an element starts with '.') and it has no short name; pass --project")


def generated_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    for name in ("generated", "generated-nl"):
        d = ROOT / ".local" / name / "default"
        if (d / "pinyon_shift_init.cpp").is_file():
            return d
    sys.exit("no generated tree with pinyon_shift_init.cpp; build the game first")


def write_table(generated: Path, out: Path) -> dict[str, int]:
    rows: list[str] = []
    counts = {"function": 0, "name": 0, "vtable": 0, "note": 0}
    init = (generated / "pinyon_shift_init.cpp").read_text(encoding="utf-8", errors="replace")
    # Highest address first: a function's body then stops at the next start,
    # which already exists, instead of flowing over it and swallowing it.
    starts = sorted(set(re.findall(r"\{ 0x([0-9A-F]{8}), (\w+) \}", init)), reverse=True)
    for addr, name in starts:
        rows.append(f"function\t{addr}\t{name}")
        counts["function"] += 1
    symbols = json.loads(subprocess.check_output(
        [sys.executable, "-I", str(ROOT / "tools" / "re" / "kb.py"), "symbols"], text=True,
        encoding="utf-8"))
    confidence_of = {}
    for record in symbols.get("addresses", []):
        text = " ".join(f"{record.get('name', '')}".split())
        address = record.get("address", "")
        m = re.fullmatch(r"0x([0-9A-Fa-f]{8})", address)
        if not m or not text:
            continue
        confidence = record.get("confidence", "guess")
        confidence_of[text] = confidence
        rows.append(f"note\t{m.group(1).upper()}\t{text}\t{confidence}")
        counts["note"] += 1
    for sub, name in symbols.get("names", {}).items():
        m = re.fullmatch(r"sub_([0-9A-F]{8})", sub)
        if m:
            text = " ".join(name.split())
            rows.append(f"name\t{m.group(1)}\t{text}\t{confidence_of.get(text, 'probable')}")
            counts["name"] += 1
    classes = generated / "classes.json"
    if classes.is_file():
        for entry in json.loads(classes.read_text(encoding="utf-8")):
            vtable, cls = entry.get("vtable"), entry.get("class")
            if vtable and cls:
                rows.append(f"vtable\t{vtable.upper()}\t{cls}")
                counts["vtable"] += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text("\n".join(rows) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--xex", default=str(ROOT / ".local" / "game" / "base" / "default.xex"))
    parser.add_argument("--generated", help="generated tree (default .local/generated/default)")
    parser.add_argument("--project", default=str(RE / "ghidra"))
    parser.add_argument("--table-only", action="store_true", help="write the TSV and stop")
    parser.add_argument("--reapply-only", action="store_true",
                        help="skip the import; apply the table to the existing workspace again")
    args = parser.parse_args()

    table = RE / "ghidra-import.tsv"
    counts = write_table(generated_dir(args.generated), table)
    print("table:", table, counts)
    if args.table_only:
        return 0

    ghidra = find_one("ghidra_12.1.3_PUBLIC")
    jdk = find_one("jdk-21*")
    if not ghidra or not jdk:
        sys.exit("expected .local/re/tools/ghidra_12.1.3_PUBLIC and a JDK 21 in .local/re/tools")
    if not (ghidra / "Ghidra" / "Extensions" / "XEXLoaderWV").is_dir():
        sys.exit("the XEXLoaderWV extension is not installed in Ghidra/Extensions")
    project = Path(args.project)
    project.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, JAVA_HOME=str(jdk), PATH=str(jdk / "bin") + os.pathsep + os.environ["PATH"])
    command = [str(ghidra / "support" / "analyzeHeadless.bat"), short_path(project), "fh1",
               "-import", args.xex, "-overwrite",
               "-scriptPath", str(ROOT / "tools" / "re" / "ghidra"),
               "-preScript", "ApplyPinyonKnowledge.java", str(table),
               "-log", str(RE / "ghidra-import.log")]
    if not args.reapply_only:
        result = subprocess.call(command, env=env)
        if result:
            return result
    # Auto-analysis turns some of ShiftGlue's function starts into data (about
    # 11,000 of 77,000 on FH1); apply the table again after it, clearing that
    # data, so every start ShiftGlue recompiled is a function.
    reapply = [str(ghidra / "support" / "analyzeHeadless.bat"), short_path(project), "fh1",
               "-process", Path(args.xex).name, "-noanalysis",
               "-scriptPath", str(ROOT / "tools" / "re" / "ghidra"),
               "-postScript", "ApplyPinyonKnowledge.java", str(table),
               # The save/restore helpers fall through into each other, so
               # analysis marks them non-returning and cuts every caller after
               # its prologue; RepairHelperFlow.java restores that flow.
               "-postScript", "RepairHelperFlow.java",
               "-log", str(RE / "ghidra-reapply.log")]
    return subprocess.call(reapply, env=env)


if __name__ == "__main__":
    sys.exit(main())
