import importlib.util
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "build-mod-archives.py"
SPEC = importlib.util.spec_from_file_location("build_mod_archives", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def manifest_line(archive: Path, guest: str) -> str:
    data = archive.read_bytes()
    at = data.rfind(b"PK\x05\x06")
    _, _, _, _, count, size, offset, _ = MODULE.END.unpack_from(data, at)
    return (f'<Zip version="1" path="{guest}" priority="80" dirstart="{offset}" '
            f'dirsize="{size + 22}" direntries="{count}" />')


class BuildModArchivesTests(unittest.TestCase):
    def make(self, directory: Path):
        game = directory / "game"
        tables = game / "media" / "StringTables"
        tables.mkdir(parents=True)
        archive = tables / "EN.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            for name, data in (("Activities.str", b"activities" * 50),
                               ("PauseMenu.str", b"pause menu"), ("Sub/Other.str", b"other")):
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                # The title's data-offset field; the builder must rewrite it.
                info.extra = struct.pack("<HHI", MODULE.DATA_OFFSET_EXTRA, 4, 0xDEADBEEF)
                zipped.writestr(info, data)
        lines = [manifest_line(archive, "game:\\media\\stringtables\\en.zip"),
                 '<Zip version="1" path="game:\\media\\ui.zip" priority="95" dirstart="1" '
                 'dirsize="2" direntries="3" />']
        (game / "media" / "zipmanifest.xml").write_bytes(
            b"\xef\xbb\xbf<ZipFiles>\r\n" + "\r\n".join(lines).encode() + b"\r\n</ZipFiles>\r\n")
        state = directory / "state"
        (state / "config").mkdir(parents=True)
        (state / "config" / "pinyon_shift.toml").write_text(
            'enabled_mods = "first,second"\n', encoding="utf-8")
        for mod, text in (("first", b"FIRST"), ("second", b"SECOND")):
            members = state / "mods" / mod / "members" / "media" / "StringTables" / "EN.zip"
            members.mkdir(parents=True)
            (members / "PauseMenu.str").write_bytes(text)
        (state / "mods" / "second" / "members" / "media" / "StringTables" / "EN.zip" / "Sub").mkdir()
        (state / "mods" / "second" / "members" / "media" / "StringTables" / "EN.zip" / "Sub"
         / "Other.str").write_bytes(b"replaced other")
        return game, state

    def test_replaces_members_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state = self.make(Path(directory))
            result = MODULE.build(state, game)
            self.assertTrue(result["patched"])
            generated = state / "mods" / MODULE.GENERATED / "game"
            rebuilt = generated / "media" / "StringTables" / "EN.zip"
            with zipfile.ZipFile(rebuilt) as zipped:
                self.assertEqual(b"FIRST", zipped.read("PauseMenu.str"))
                self.assertEqual(b"replaced other", zipped.read("Sub/Other.str"))
                self.assertEqual(b"activities" * 50, zipped.read("Activities.str"))
                self.assertEqual(zipfile.ZIP_DEFLATED, zipped.getinfo("Activities.str").compress_type)
                self.assertEqual(zipfile.ZIP_STORED, zipped.getinfo("PauseMenu.str").compress_type)
            data = rebuilt.read_bytes()
            records, _ = MODULE.read_central(data)
            for raw, info in records:
                local = MODULE.LOCAL.unpack_from(data, info["offset"])
                self.assertEqual(info["method"], local[3])
                body = info["offset"] + MODULE.LOCAL.size + local[9] + local[10]
                name_size = MODULE.CENTRAL.unpack_from(raw)[10]
                key, size, offset = struct.unpack_from("<HHI", raw, MODULE.CENTRAL.size + name_size)
                self.assertEqual((MODULE.DATA_OFFSET_EXTRA, 4, body), (key, size, offset))
            manifest = (generated / "media" / "zipmanifest.xml").read_bytes().decode("utf-8-sig")
            self.assertIn(manifest_line(rebuilt, "game:\\media\\stringtables\\en.zip"), manifest)
            self.assertIn('path="game:\\media\\ui.zip" priority="95" dirstart="1"', manifest)
            self.assertIn(f'enabled_mods = "{MODULE.GENERATED},first,second"',
                          (state / "config" / "pinyon_shift.toml").read_text(encoding="utf-8"))
            # The player's archive is untouched.
            with zipfile.ZipFile(game / "media" / "StringTables" / "EN.zip") as zipped:
                self.assertEqual(b"pause menu", zipped.read("PauseMenu.str"))

    def test_patches_the_manifest_and_archive_a_mod_replaces(self):
        # A total conversion (the XE mod) ships its own zipmanifest.xml, with
        # lines for its new archives, and replaced archives; member mods must
        # build on those, or the generated manifest drops its archives.
        with tempfile.TemporaryDirectory() as directory:
            game, state = self.make(Path(directory))
            conversion = state / "mods" / "conversion" / "game" / "media"
            (conversion / "StringTables").mkdir(parents=True)
            archive = conversion / "StringTables" / "EN.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("PauseMenu.str", b"conversion pause")
                zipped.writestr("Sub/Other.str", b"conversion other")
            text = (game / "media" / "zipmanifest.xml").read_bytes().decode("utf-8-sig")
            text = text.replace(manifest_line(game / "media" / "StringTables" / "EN.zip",
                                              "game:\\media\\stringtables\\en.zip"),
                                manifest_line(archive, "game:\\media\\stringtables\\en.zip"))
            text = text.replace("</ZipFiles>", '<Zip version="1" path="game:\\media\\cars\\'
                                'new_car.zip" priority="80" dirstart="4" dirsize="5" '
                                'direntries="6" />\r\n</ZipFiles>')
            (conversion / "zipmanifest.xml").write_bytes(b"\xef\xbb\xbf" + text.encode())
            (state / "config" / "pinyon_shift.toml").write_text(
                'enabled_mods = "first,conversion"\n', encoding="utf-8")
            MODULE.build(state, game)
            generated = state / "mods" / MODULE.GENERATED / "game" / "media"
            with zipfile.ZipFile(generated / "StringTables" / "EN.zip") as zipped:
                self.assertEqual(b"FIRST", zipped.read("PauseMenu.str"))
                self.assertEqual(b"conversion other", zipped.read("Sub/Other.str"))
            self.assertIn("new_car.zip", (generated / "zipmanifest.xml").read_text(
                encoding="utf-8-sig"))

    def test_removes_the_generated_mod_without_members(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state = self.make(Path(directory))
            MODULE.build(state, game)
            for mod in ("first", "second"):
                import shutil
                shutil.rmtree(state / "mods" / mod / "members")
            self.assertFalse(MODULE.build(state, game)["patched"])
            self.assertFalse((state / "mods" / MODULE.GENERATED).exists())

    def test_refuses_a_member_the_archive_lacks_and_a_mismatched_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state = self.make(Path(directory))
            extra = state / "mods" / "first" / "members" / "media" / "StringTables" / "EN.zip"
            (extra / "New.str").write_bytes(b"new")
            with self.assertRaises(MODULE.ArchiveError):
                MODULE.build(state, game)
            (extra / "New.str").unlink()
            manifest = game / "media" / "zipmanifest.xml"
            manifest.write_bytes(manifest.read_bytes().replace(b'direntries="3"', b'direntries="9"', 1))
            with self.assertRaises(MODULE.ArchiveError):
                MODULE.build(state, game)

    def test_merges_ini_keys_with_the_earlier_mod_winning(self):
        base = (b"Collision\\PlayerTorqueScale 0.0\r\n"
                b"Collision\\RaceCarTorqueScaleInRace = 0.2\r\n"
                b"Replay\\ReplayPosSpringK 30\r\n")
        merged = MODULE.merge_ini(base, b"collision\\playertorquescale 0.5\nNew\\Key 7\n")
        merged = MODULE.merge_ini(merged, b"Collision\\RaceCarTorqueScaleInRace 0.4\n")
        self.assertEqual(b"Collision\\PlayerTorqueScale 0.5\r\n"
                         b"Collision\\RaceCarTorqueScaleInRace = 0.4\r\n"
                         b"Replay\\ReplayPosSpringK 30\r\n"
                         b"New\\Key 7\r\n", merged)

    def test_merges_xml_elements_by_key_attribute_and_position(self):
        base = (b'<?xml version="1.0"?>\r\n<AIOpenWorld>\r\n'
                b'    <Settings name="freeroam">\r\n'
                b'        <CarList numInitialTrafficCars="4">\r\n'
                b'            <Car model="282"/>  <!-- VW Beetle -->\r\n'
                b'            <Car model="1241"/>\r\n'
                b'        </CarList>\r\n'
                b'        <Density>0.5</Density>\r\n'
                b'    </Settings>\r\n'
                b'    <Settings name="race"><Density>1</Density></Settings>\r\n'
                b'</AIOpenWorld>\r\n')
        patch = (b'<AIOpenWorld><Settings name="freeroam">'
                 b'<CarList numInitialTrafficCars="8"><Car model="1241" pinyon-remove="true"/>'
                 b'<Car model="1529" maxactive="1"/></CarList>'
                 b'<Density>0.9</Density></Settings></AIOpenWorld>')
        merged = MODULE.merge_xml(base, patch)
        text = merged.decode("utf-8")
        self.assertTrue(text.startswith('<?xml version="1.0"?>\r\n<AIOpenWorld>'))
        self.assertNotIn("\n", text.replace("\r\n", ""))
        self.assertIn('numInitialTrafficCars="8"', text)
        self.assertIn("<!-- VW Beetle -->", text)
        self.assertNotIn('model="1241"', text)
        self.assertIn('<Car model="1529" maxactive="1" />', text)
        self.assertIn("<Density>0.9</Density>", text)
        self.assertIn('<Settings name="race"><Density>1</Density></Settings>', text)
        with self.assertRaises(MODULE.ArchiveError):
            MODULE.merge_xml(base, b"<Other/>")

    def test_appends_unkeyed_elements_marked_to_add(self):
        base = (b'<CameraPhysics>\r\n  <DriverCam NumLayers="2">\r\n'
                b'    <Layer InputType="SpeedMPH"/>\r\n    <Layer InputType="Slip"/>\r\n'
                b'  </DriverCam>\r\n</CameraPhysics>\r\n')
        patch = (b'<CameraPhysics><DriverCam NumLayers="3">'
                 b'<Layer pinyon-add="true" InputType="ConstantOne"/></DriverCam></CameraPhysics>')
        text = MODULE.merge_xml(base, patch).decode("utf-8")
        self.assertIn('NumLayers="3"', text)
        self.assertIn('<Layer InputType="SpeedMPH" />', text)
        self.assertIn('<Layer InputType="Slip" />', text)
        self.assertIn('<Layer InputType="ConstantOne" />', text)
        self.assertNotIn("pinyon-add", text)
        self.assertLess(text.index("Slip"), text.index("ConstantOne"))

    def test_builds_merged_members_over_the_players_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state = self.make(Path(directory))
            for mod in ("first", "second"):
                shutil.rmtree(state / "mods" / mod / "members")
            archive = game / "media" / "StringTables" / "EN.zip"
            with zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as zipped:
                info = zipfile.ZipInfo("Settings.ini")
                info.compress_type = zipfile.ZIP_DEFLATED
                info.extra = struct.pack("<HHI", MODULE.DATA_OFFSET_EXTRA, 4, 0)
                zipped.writestr(info, b"A\\One 1\r\nA\\Two 2\r\n")
            manifest = game / "media" / "zipmanifest.xml"
            text = manifest.read_bytes().decode("utf-8-sig")
            text = text[:text.index("<Zip")] + manifest_line(
                archive, "game:\\media\\stringtables\\en.zip") + text[text.index("\r\n<Zip"):]
            manifest.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
            for mod, lines in (("first", b"A\\Two 20\n"), ("second", b"A\\One 10\nA\\Two 99\n")):
                merge = state / "mods" / mod / "merge" / "media" / "StringTables" / "EN.zip"
                merge.mkdir(parents=True)
                (merge / "Settings.ini").write_bytes(lines)
            result = MODULE.build(state, game)
            self.assertEqual({"settings.ini": ["first", "second"]},
                             result["archives"][0]["merged"])
            rebuilt = state / "mods" / MODULE.GENERATED / "game" / "media" / "StringTables" / "EN.zip"
            with zipfile.ZipFile(rebuilt) as zipped:
                self.assertEqual(b"A\\One 10\r\nA\\Two 20\r\n", zipped.read("Settings.ini"))
                self.assertEqual(b"pause menu", zipped.read("PauseMenu.str"))
            generated = state / "mods" / MODULE.GENERATED / "mod.toml"
            self.assertNotIn("shares_save", generated.read_text(encoding="utf-8"))
            # Built only from mods that keep the player's save, it keeps it.
            for mod in ("first", "second"):
                (state / "mods" / mod / "mod.toml").write_text(
                    f'name = "{mod}"\nshares_save = true\n', encoding="utf-8")
            MODULE.build(state, game)
            self.assertIn("shares_save = true", generated.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
