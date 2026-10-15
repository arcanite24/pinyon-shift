import importlib.util
import re
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "generate-fh1-symbols.py"
SPEC = importlib.util.spec_from_file_location("generate_fh1_symbols", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class Fh1SymbolTableTests(unittest.TestCase):
    def test_checked_in_table_matches_its_sources(self):
        self.assertEqual(MODULE.OUTPUT.read_text(encoding="utf-8"), MODULE.generate())

    def test_v4_offsets_name_every_offset(self):
        # generate-fh1-symbols.py --v4 refuses to write the v4 table unless
        # fh1-offsets-v4.toml lists exactly the offsets of fh1-symbols.toml,
        # but only a machine with the v4 images runs it: check the names here.
        import tomllib
        base = tomllib.loads(MODULE.SYMBOLS.read_text(encoding="utf-8"))["offsets"]
        v4 = tomllib.loads(MODULE.V4_OFFSETS.read_text(encoding="utf-8"))["offsets"]
        self.assertEqual(sorted(set(base) - set(v4)), [], "offsets without a verified v4 value")
        self.assertEqual(sorted(set(v4) - set(base)), [], "v4 offsets without a base offset")

    def test_every_hook_site_is_a_symbol(self):
        text = MODULE.generate()
        hooks = re.findall(r'name = "(\w+)"', MODULE.HOOKS.read_text(encoding="utf-8"))
        for hook in hooks:
            self.assertIn(f'"hook.{hook}"', text)

    def test_semantic_symbols_point_at_hook_sites_or_functions(self):
        # A semantic name must name an address the generated code knows: a
        # hook site, or a function start (sub_XXXXXXXX).
        generated = MODULE.ROOT / ".local" / "generated" / "default" / "pinyon_shift_init.cpp"
        hook_addresses = {int(address, 16) for address in
                          re.findall(r"address = 0x([0-9A-Fa-f]+)",
                                     MODULE.HOOKS.read_text(encoding="utf-8"))}
        import tomllib
        symbols = tomllib.loads(MODULE.SYMBOLS.read_text(encoding="utf-8"))["symbols"]
        functions = (generated.read_text(encoding="utf-8") if generated.exists() else None)
        for name, address in symbols.items():
            if address in hook_addresses:
                continue
            if functions is None:
                self.skipTest("generated code is not present")
            self.assertRegex(functions, rf"\{{ 0x{address:08X}, (sub_{address:08X}|__imp__\w+) \}}",
                             name)


if __name__ == "__main__":
    unittest.main()
