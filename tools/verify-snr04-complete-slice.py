"""Check that six immutable fixtures own one complete Gate A source frame."""

import collections
import json
from pathlib import Path
import runpy
import subprocess
import sys


TOOLS = Path(__file__).resolve().parent
partition_tools = runpy.run_path(str(TOOLS / "partition-snr00-gate-a-slice.py"))
ROLE = partition_tools["role"]
PARTITION = partition_tools["partition"]


def verify(directory: Path, log: Path, ledger_path: Path):
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    partition = PARTITION(ledger_path)
    assert partition["full_owner_census"] and not partition["unattributed_draws"]
    source = ledger["backend_frame"] - 1
    roles = collections.Counter(ROLE(draw) for draw in ledger["draws"])
    fixtures = (
        ("track", "snr02-track", "verify-snr02-track-geometry.py",
         ("selected_shared_track_procedural",), "draws", True),
        ("items", "snr02-items", "verify-snr02-item-scene.py",
         ("selected_procedural_item",), "draws", False),
        ("vegetation", "snr03-scene", "verify-snr03-scene-fixture.py",
         ("selected_vegetation",), "final_variants", False),
        ("characters", "snr03-characters", "verify-snr03-character-fixture.py",
         ("selected_procedural_character",), "draws", False),
        ("manager", "snr03-manager", "verify-snr03-manager-fixture.py",
         ("selected_character",), "draws", False),
        ("remainder", "snr03-remainder", "verify-snr03-remainder-fixture.py",
         ("selected_car_scene_list", "selected_animated",
          "selected_car_presentation"), "draws", False),
    )
    covered = {}
    for name, stem, script, owned_roles, count_key, log_first in fixtures:
        fixture = directory / f"{stem}-{source}.bin"
        args = [str(TOOLS / script)]
        args.extend((str(log), str(ledger_path), str(fixture)) if log_first else
                    (str(fixture), str(log)))
        if script not in ("verify-snr03-scene-fixture.py",
                          "verify-snr02-track-geometry.py"):
            args.append(str(ledger_path))
        result = subprocess.run([sys.executable, *args],
                                capture_output=True, text=True)
        assert result.returncode == 0, f"{name}: {result.stderr.strip()}"
        checked = json.loads(result.stdout)
        count = checked[count_key]
        if isinstance(count, dict):
            count = sum(count.values())
        expected = sum(roles[role] for role in owned_roles)
        assert checked["source_frame"] == source and count == expected, name
        covered[name] = count
    selected = sum(value for key, value in roles.items()
                   if key.startswith("selected_"))
    assert sum(covered.values()) == selected
    prepared = {}
    marker = "FH1 SNR01 prepared draw "
    for line in log.open(encoding="utf-8-sig", errors="replace"):
        if marker not in line:
            continue
        row = json.loads(line.split(marker, 1)[1])
        if row["frame"] == source + 1:
            assert row["ordinal"] not in prepared
            prepared[row["ordinal"]] = row
    assert len(prepared) == len(ledger["draws"])
    assert all(prepared[i]["sequence"] < prepared[i + 1]["sequence"]
               for i in range(1, len(prepared)))
    order = []
    for draw in ledger["draws"]:
        family = ROLE(draw)
        if not family.startswith("selected_"):
            continue
        ordinal = draw["ordinal"]
        row = prepared[ordinal]
        assert row["packet_physical"] == draw["packet_physical"]
        order.append({"ordinal": ordinal, "sequence": row["sequence"],
                      "family": family, "packet": row["packet_physical"]})
    assert len(order) == selected
    return {"source_frame": source, "backend_frame": source + 1,
            "selected_draws": selected, "owned_draws": covered,
            "order": order}


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        raise SystemExit("usage: verify-snr04-complete-slice.py FIXTURE_DIR LOG LEDGER [ORDER_JSON]")
    result = verify(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    if len(sys.argv) == 5:
        Path(sys.argv[4]).write_text(json.dumps(result, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key != "order"}, sort_keys=True))
