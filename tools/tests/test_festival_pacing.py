"""The festival_pacing built-in mod (#491): its options and what its scripts
do to the tables they touch, on a small SQLite copy of those tables (no game
files needed)."""
import re
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import mod_options  # noqa: E402

MOD = ROOT / "mods_src" / "builtin" / "festival_pacing"
UPDATE = re.compile(r"^update (\w+) set (\w+) = ", re.MULTILINE)


def scripts():
    return sorted((MOD / "db").glob("*.sql"))


def tables():
    """(table, column) each script changes, in order."""
    found = []
    for script in scripts():
        found += UPDATE.findall(script.read_text(encoding="utf-8"))
    return found


def run(values):
    """The scripts filled with these option values, run on one row per table
    holding 1000; returns {(table, column): value after}."""
    connection = sqlite3.connect(":memory:")
    for table, column in tables():
        connection.execute(f"create table if not exists {table} ({column} integer)")
        connection.execute(f"insert into {table} values (1000)")
    for script in scripts():
        text = mod_options.fill(script.read_text(encoding="utf-8"), values, script.name)
        connection.executescript(text)
    return {(t, c): connection.execute(f"select {c} from {t}").fetchone()[0] for t, c in tables()}


class FestivalPacingTests(unittest.TestCase):
    def setUp(self):
        self.options = {o.key: o for o in mod_options.read_declared(MOD)}

    def test_options_and_defaults(self):
        self.assertEqual(set(self.options), {"prices", "rewards"})
        self.assertEqual(self.options["prices"].default, "0.5")
        self.assertEqual(self.options["rewards"].default, "2")
        for option in self.options.values():
            self.assertIn("1", [c.value for c in option.choices], "each option offers stock (1x)")

    def test_every_key_in_the_scripts_is_declared(self):
        for script in scripts():
            for key in re.findall(r"\{\{(\w+)\}\}", script.read_text(encoding="utf-8")):
                self.assertIn(key, self.options, f"{script.name} uses {key}")

    def test_defaults_halve_prices_and_double_rewards(self):
        after = run({"prices": "0.5", "rewards": "2"})
        for (table, column), value in after.items():
            if table == "PlayerLevelDef":
                expected = 500  # the XP a driver level needs: divided
            elif table in ("EventScoring", "Events", "AffinityLevelDef", "WristbandScoring"):
                expected = 2000  # payouts and wristband points: multiplied
            else:
                expected = 500  # cars, parts and rims
            self.assertEqual(value, expected, f"{table}.{column}")

    def test_stock_changes_nothing(self):
        self.assertTrue(all(v == 1000 for v in run({"prices": "1", "rewards": "1"}).values()))

    def test_covers_cars_parts_rims_payouts_and_levels(self):
        changed = {t for t, _ in tables()}
        for table in ("Data_Car", "List_Wheels", "EventScoring", "Events", "AffinityLevelDef",
                      "PlayerLevelDef", "WristbandScoring"):
            self.assertIn(table, changed)
        self.assertGreater(len([t for t in changed if t.startswith("List_Upgrade")]), 20)


if __name__ == "__main__":
    unittest.main()
