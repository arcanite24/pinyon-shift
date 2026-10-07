import os
import importlib.util
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
import wave
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "run-fh1-render-test.py"
SPEC = importlib.util.spec_from_file_location("run_fh1_render_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class Fh1RenderTestRunnerTests(unittest.TestCase):
    def test_rally_test_ai_requires_native_controller_and_stays_diagnostic(self):
        driver = dict(event="fh1.render_test.rally_ai_driver", route="2", race_serial="49",
                      car="41000000", control_mode="0")
        result = MODULE.rally_test_ai_driver_summary([driver])
        self.assertTrue(result["diagnostic_only"])
        self.assertFalse(result["player_steering_qualified"])
        for invalid in ([], [driver | dict(control_mode="1")], [driver | dict(car="")],
                        [driver | dict(route="22")], [driver | dict(race_serial="0")]):
            with self.assertRaises(RuntimeError): MODULE.rally_test_ai_driver_summary(invalid)

        released = dict(event="fh1.render_test.rally_ai_released", race_serial="49",
                        car="41000000", control_mode="1")
        self.assertEqual(MODULE.rally_test_ai_driver_summary([driver, released], True)["releases"], 1)
        for trace in ([driver], [released, driver], [driver, released, released],
                      [driver, released | dict(car="42000000")],
                      [driver, released | dict(race_serial="50")],
                      [driver, released | dict(control_mode="0")]):
            with self.assertRaises(RuntimeError): MODULE.rally_test_ai_driver_summary(trace, True)

    def test_rally_service_guard_requires_blocked_attempt_and_ready_entry(self):
        context = dict(event="dlc.rally.hub_context", control_owner="2ECD0070",
                       control_available="0", available="0", host_ui="1", loader_idle="1",
                       owner_name="garage")
        free = context | dict(control_owner="00000000", control_available="1", available="1",
                              host_ui="0", owner_name="")
        capture = dict(event="fh1.render_test.capture", game_mode="17")
        events = [context, dict(event="hostui.screen", screen="HORIZON RALLY"),
                  capture | dict(name="garage-rally-disabled"),
                  dict(event="fh1.render_test.hostkey", key="13"),
                  capture | dict(name="garage-rally-blocked"), dict(event="hostui.closed"),
                  free, capture | dict(name="restored-free-roam"),
                  free | dict(control_owner="2EDD0030", owner_name="pause"),
                  dict(event="dlc.rally.hub_selected", source="player")]
        self.assertTrue(MODULE.rally_service_entry_guard_summary(events)["garage_entry_blocked"])
        invalid = [events[:3] + events[4:], events[:-1], events + [events[-1]],
                   events + [dict(event="dlc.rally.hub_error")],
                   [context | dict(available="1")] + events[1:],
                   events[:8] + [free | dict(control_owner="2EDD0030", owner_name="garage")] + events[9:],
                   events[:4] + [dict(event="hostui.closed")] + events[4:],
                   events[:6] + [context] + events[7:]]
        for trace in invalid:
            with self.subTest(trace=trace), self.assertRaises(RuntimeError):
                MODULE.rally_service_entry_guard_summary(trace)

    def test_rally_car_database_requires_native_merge_and_original_entitlements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            original = b'version = 3\n'
            path.write_bytes(original)
            (root / "config").mkdir()
            (root / "config/pinyon_shift.toml").write_text('enabled_mods = ""\n')
            cache = root / "cache/rally_adapter"
            (cache / "reference").mkdir(parents=True)
            (cache / "preparation.json").write_text(json.dumps(dict(recipe=dict(package_id="rally"))))
            (root / "dlc").mkdir()
            (root / "dlc/rally.json").write_text(json.dumps(dict(license_mask="00000001")))
            db = sqlite3.connect(cache / "reference/rally.slt")
            db.executescript('''CREATE TABLE Data_Car(Id,IsInstalled,IsPurchased,IsSelectable,IsDrivable);
                INSERT INTO Data_Car VALUES(346,1,1,1,1),(1272,1,1,1,1);
                CREATE TABLE ContentOffers(OfferId,LicenseMask,Hidden);
                INSERT INTO ContentOffers VALUES(1,1,0),(4,4,1);
                CREATE TABLE ContentOffersMapping(OfferId,ContentType,ContentId);
                INSERT INTO ContentOffersMapping VALUES(1,1,1272),(4,1,346),(1,3,111);''')
            for table in ("List_UpgradeTireCompound", "List_UpgradeSpringDamper", "List_UpgradeEngine"):
                db.execute(f"CREATE TABLE {table}(Ordinal)")
                db.executemany(f"INSERT INTO {table} VALUES(?)", [(346,), (1272,)])
            db.commit(); db.close()
            events = [dict(event="paths.configured", user=str(root / "user")),
                      dict(event="dlc.rally.overlay_mounted"), dict(event="dlc.rally.progress_loaded", path=str(path)),
                      dict(event="dlc.rally.prepared_entry", verification="launch_preflight"),
                      dict(event="dlc.rally.series_loader_installed", series_id="0", stage_count="28")]
            fields = dict(installed="1", purchased="1", selectable="1", drivable="1",
                          tire_options="1", suspension_options="1", engine_options="1")
            cars = [dict(event="dlc.car_database", car_id=str(id), **fields) for id in (346, 1272)]
            entitlements = [dict(event="dlc.content_entitlement", content_type=str(type), content_id=str(id),
                                 installed="1", purchased=str(bought), base="0", visible=str(bought))
                            for type, id, bought in ((1,346,0),(1,1272,1),(3,111,1))]
            trace = cars + entitlements + [dict(event="dlc.car_trace_complete", rows="2")]
            summary = MODULE.rally_car_database_summary(events + trace, root, [original])
            self.assertEqual(summary["selectable_owned_cars"], [1272])
            self.assertFalse(summary["purchase_driving_and_upgrade_ui_qualified"])
            for invalid in (trace[:-1], trace + [cars[0]], trace[1:], trace + [dict(event="dlc.car_trace_error")],
                            [e | dict(purchased="1") if e.get("content_id") == "346" else e for e in trace],
                            [e | dict(tire_options="0") if e.get("car_id") == "1272" else e for e in trace],
                            [e | dict(selectable="0") if e.get("car_id") == "1272" else e for e in trace]):
                with self.assertRaises(RuntimeError): MODULE.rally_car_database_summary(events + invalid, root, [original])
            path.write_bytes(original + b'# changed\n')
            with self.assertRaises(RuntimeError): MODULE.rally_car_database_summary(events + trace, root, [original])

    def test_rally_native_entry_positions_require_all_owned_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owned = root / "cache/rally_adapter/game/media/gamemodes/ColoradoDirt/rally_event_activations.xml"
            owned.parent.mkdir(parents=True)
            owned.write_text('<ActivityManager>' + ''.join(
                f'<Activity name="MS_RALLY_{id:02}"><TriggerZone position.x="{id}" position.z="{-id}"/></Activity>'
                for id in range(1, 8)) + '</ActivityManager>')
            events = [dict(event="dlc.rally.entry_position_loaded", name=f"horizon_rally_{id:02}", x=str(id), z=str(-id))
                      for id in range(1, 8)]
            self.assertTrue(MODULE.rally_entry_positions_summary(events, root)["owned_coordinates"])
            for invalid in (events[:-1], events + [events[0]], events[:-1] + [events[0]],
                            events[:-1] + [events[-1] | dict(x="nan")],
                            events[:-1] + [events[-1] | dict(z="0")],
                            events[:-1] + [events[-1] | dict(name="horizon_rally_08")]):
                with self.assertRaises(RuntimeError): MODULE.rally_entry_positions_summary(invalid, root)
            owned.write_text(owned.read_text().replace('position.x="7"', 'position.x="nan"'))
            with self.assertRaises(RuntimeError): MODULE.rally_entry_positions_summary(events, root)

    def test_default_pace_rejects_probe_source_wrong_locale_and_mod_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            path.write_text('version = 3\n')
            (root / "config").mkdir()
            (root / "config/pinyon_shift.toml").write_text('enabled_mods = ""\n')
            events = [dict(event="paths.configured", user=str(root / "user")),
                      dict(event="dlc.rally.overlay_mounted"), dict(event="dlc.rally.progress_loaded", path=str(path)),
                      dict(event="dlc.rally.pace_update_installed", method="82BB5918", owner="native_audio_update"),
                      dict(event="dlc.rally.pace_update", method="82BB5918", manager="409C4460", tid="audio"),
                      dict(event="dlc.rally.pace_loaded", language="MX", source="owned_content", tid="audio")]
            self.assertTrue(MODULE.rally_default_pace_summary(events, root, "MX")["default_enabled"])
            for invalid in (events[:-1], events + [events[-1]], events[:-1] + [events[-1] | dict(source="private_probe")],
                            events[:-1] + [events[-1] | dict(language="EN")], events + [dict(event="dlc.rally.audio_probe_play")],
                            events + [dict(event="mod.loaded")], events[:1] + events[2:]):
                with self.assertRaises(RuntimeError): MODULE.rally_default_pace_summary(invalid, root, "MX")

    def test_rally_cue_lifetimes_require_the_native_audio_thread(self):
        events = [dict(event="dlc.rally.pace_update_installed", method="82BB5918", owner="native_audio_update"),
                  dict(event="dlc.rally.pace_update", method="82BB5918", manager="409C4460", tid="audio"),
                  dict(event="dlc.rally.pace_play", tid="audio"),
                  dict(event="dlc.rally.audio_cue_cleanup", tid="audio")]
        self.assertEqual(MODULE.rally_audio_owner_summary(events)["audio_thread"], "audio")
        for invalid in (events[1:], events[:1] + events[2:],
                        events[:1] + [events[1] | dict(manager="0")] + events[2:],
                        events[:-1] + [events[-1] | dict(tid="frame")],
                        events + [dict(event="dlc.rally.pace_finished")]):
            with self.assertRaises(RuntimeError): MODULE.rally_audio_owner_summary(invalid)

    def test_normal_rally_entry_requires_advancing_first_stage_and_fresh_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            data = 'version = 3\n' + ''.join(f'[[stages]]\nroute = {r}\ncompletions = 0\nbest_seconds = 0.0\n'
                for r in MODULE.RALLY_STAGE_ROUTES) + ''.join(f'[[series]]\nid = {id}\ncompletions = 0\nbest_seconds = 0.0\n'
                for id in range(1,8)) + '[attempt]\nseries_id = 3\nactive = true\ncompleted = 0\nseconds = [0,0,0,0]\ntotal_seconds = 0.0\n'
            path.write_text(data)
            (root / "config").mkdir()
            (root / "config/pinyon_shift.toml").write_text('enabled_mods = ""\n')
            trace = dict(event="dlc.rally.race_trace",route="4",mode="3",started="1",ended="0",end_reason="0",
                car="41000000",event_id="250",race_serial="12",time_72="1.0")
            events = [dict(event="paths.configured",user=str(root / "user")),dict(event="dlc.rally.overlay_mounted"),
                dict(event="dlc.rally.progress_loaded",path=str(path)),dict(event="dlc.rally.prepared_entry",verification="launch_preflight"),
                dict(event="dlc.rally.series_loader_installed",series_id="0",stage_count="28"), trace, trace | dict(time_72="2.0")]
            self.assertEqual(MODULE.rally_entry_summary(events, root, 3)["route"],4)
            hub = dict(event="dlc.rally.hub_selected", series_id="3", source="private_probe")
            self.assertEqual(MODULE.rally_entry_summary(events + [hub], root, 3)["entry_source"], "private_probe")
            menu = [dict(event="hostui.open",screen="SETTINGS"),
                    dict(event="hostui.layout",screen="SETTINGS",inside="1"),
                    dict(event="hostui.screen",screen="HORIZON RALLY"),
                    dict(event="hostui.layout",screen="HORIZON RALLY",inside="1"),
                    dict(event="hostui.closed"), hub | dict(source="player")]
            self.assertTrue(MODULE.rally_hub_ui_summary(events + menu, root, 3)["hub_keyboard_entry"])
            for invalid in (menu[:-1] + [hub], menu[1:], menu[:4] + menu[5:],
                            [e | dict(inside="0") if e.get("event") == "hostui.layout" else e for e in menu]):
                with self.assertRaises(RuntimeError): MODULE.rally_hub_ui_summary(events + invalid, root, 3)
            for extra in ([hub, hub], [hub | dict(series_id="7")], [hub | dict(source="unknown")],
                          [dict(event="dlc.rally.hub_error")]):
                with self.assertRaises(RuntimeError): MODULE.rally_entry_summary(events + extra, root, 3)
            for change in (dict(route="5"),dict(mode="17"),dict(started="0"),dict(ended="1"),dict(end_reason="2"),
                           dict(race_serial="0"),dict(car=""),dict(time_72="nan")):
                with self.subTest(change=change), self.assertRaises(RuntimeError):
                    MODULE.rally_entry_summary(events[:-2] + [e | change for e in events[-2:]], root, 3)
            for invalid in (events[:-1], events[:-1] + [trace], events + [dict(event="dlc.rally.stage_completed")]):
                with self.assertRaises(RuntimeError): MODULE.rally_entry_summary(invalid, root, 3)
            for bad in (data.replace('series_id = 3','series_id = 7'),data.replace('completed = 0','completed = 1'),
                        data.replace('completions = 0','completions = 1'), data.replace('id = 2', 'id = 1')):
                path.write_text(bad)
                with self.assertRaises(RuntimeError): MODULE.rally_entry_summary(events, root, 3)

    def test_normal_rally_requires_owned_preflight_and_all_stage_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            path.write_bytes(b'version = 3\n')
            (root / "config").mkdir()
            (root / "config/pinyon_shift.toml").write_bytes(b'enabled_mods = ""\n')
            events = [dict(event="paths.configured", user=str(root / "user")),
                dict(event="dlc.rally.overlay_mounted"), dict(event="dlc.rally.progress_loaded", path=str(path)),
                dict(event="dlc.rally.prepared_entry", verification="launch_preflight"),
                dict(event="dlc.rally.series_loader_installed", series_id="0", stage_count="28")]
            self.assertTrue(MODULE.rally_normal_entry_summary(events, root)["launch_preflight"])
            for invalid in (events[:-1], events[:3], events + [events[3]],
                            events[:-1] + [dict(event="dlc.rally.series_loader_installed", series_id="7", stage_count="4")]):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_normal_entry_summary(invalid, root)

    def test_builtin_rally_rejects_redirected_profile_mods_and_failed_mounts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            path.write_bytes(b'version = 3\n')
            (root / "config").mkdir()
            config = root / "config/pinyon_shift.toml"
            config.write_bytes(b'enabled_mods = ""\n')
            events = [dict(event="paths.configured", user=str(root / "user")),
                      dict(event="dlc.rally.overlay_mounted"),
                      dict(event="dlc.rally.progress_loaded", path=str(path))]
            self.assertEqual(MODULE.rally_builtin_summary(events, root)["progress_path"], str(path))
            for invalid in (events[1:], events + [events[1]],
                            [events[0] | dict(user=str(root / "user-modded")), *events[1:]],
                            [*events[:-1], events[-1] | dict(path=str(root.parent / "outside.toml"))]):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_builtin_summary(invalid, root)
            for name in ("mod.loaded", "mod.profile.created", "dlc.rally.adapter_error"):
                with self.subTest(name=name), self.assertRaises(RuntimeError):
                    MODULE.rally_builtin_summary(events + [dict(event=name)], root)
            config.write_bytes(b'enabled_mods = "rally_stage_probe"\n')
            with self.assertRaisesRegex(RuntimeError, "enabled mods"):
                MODULE.rally_builtin_summary(events, root)
            config.write_bytes(b'enabled_mods = ""\n')
            (root / "user-modded").mkdir()
            with self.assertRaises(RuntimeError):
                MODULE.rally_builtin_summary(events, root)

    def stage_reload_fixture(self, root):
        path = root / "user-modded/account/title/00000001/ForzaProfile/rally-progress.toml"
        path.parent.mkdir(parents=True)
        data = "version = 2\n" + "".join(
            f'\n[[stages]]\nroute = {route}\ncompletions = {2 if route == 1 else 0}\n'
            f'best_seconds = {171.5 if route == 1 else 0.0}\n' for route in MODULE.RALLY_STAGE_ROUTES)
        path.write_text(data)
        loaded = dict(event="dlc.rally.progress_loaded", path=str(path), route="1",
                      completions="2", best_seconds="171.5", completed_stages="1")
        running = dict(event="dlc.rally.race_trace", route="1", mode="3", started="1", ended="0",
                       end_reason="0", event_id="247", car="ABCD", race_serial="16", time_72="8")
        return path, path.read_bytes(), [loaded, running, running | dict(time_72="9")]

    def test_stage_reload_matches_native_record_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, data, events = self.stage_reload_fixture(root)
            result = MODULE.rally_stage_reload_summary(events, root, 1, [data])
            self.assertEqual((result["route"], result["completions"], result["best_seconds"]), (1, 2, 171.5))
            self.assertTrue(result["earned_records_preserved"])
            path.write_bytes(data + b'# changed\n')
            with self.assertRaisesRegex(RuntimeError, "changed its earned records"):
                MODULE.rally_stage_reload_summary(events, root, 1, [data])

    def test_private_state_copies_builtin_rally_assets_without_shader_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "seed", root / "run"
            (source / "cache/rally_adapter/game/media").mkdir(parents=True)
            (source / "cache/rally_adapter/rally-stage.toml").write_bytes(b'version = 1\n')
            (source / "cache/rally_adapter/game/media/owned.zip").write_bytes(b'owned')
            (source / "cache/ignored.bin").write_bytes(b'cache')
            (source / "dlc").mkdir()
            (source / "dlc/owned.json").write_bytes(b'accepted import metadata')
            MODULE.prepare_isolated_state(source, destination)
            self.assertEqual((destination / "dlc/owned.json").read_bytes(), b'accepted import metadata')
            self.assertEqual((destination / "cache/rally_adapter/game/media/owned.zip").read_bytes(), b'owned')
            self.assertFalse((destination / "cache/ignored.bin").exists())
            self.assertFalse((destination / "mods").exists())

    def test_private_state_links_marketplace_content_and_copies_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "seed", root / "run"
            package = source / "user/0000000000000000/4D5309C9/00000002/PKG/Media"
            package.mkdir(parents=True)
            (package / "1100.puboffer").write_bytes(b'offer')
            profile = source / "user/B13EBABEBABEBABE/4D5309C9/00000001/ForzaProfile"
            profile.mkdir(parents=True)
            (profile / "ForzaProfile").write_bytes(b'save')
            (source / "dlc/staging-abc").mkdir(parents=True)
            (source / "dlc/staging-abc/input-0.stfs").write_bytes(b'scratch')
            (source / "dlc/PKG.json").write_bytes(b'record')
            MODULE.prepare_isolated_state(source, destination)
            linked = destination / "user/0000000000000000/4D5309C9/00000002/PKG/Media/1100.puboffer"
            self.assertEqual(linked.read_bytes(), b'offer')
            self.assertTrue(os.path.samefile(linked, package / "1100.puboffer"))
            copied = destination / "user/B13EBABEBABEBABE/4D5309C9/00000001/ForzaProfile/ForzaProfile"
            self.assertEqual(copied.read_bytes(), b'save')
            self.assertFalse(os.path.samefile(copied, profile / "ForzaProfile"))
            self.assertTrue((destination / "dlc/PKG.json").is_file())
            self.assertFalse((destination / "dlc/staging-abc").exists())

    def test_cpu_lists_for_low_spec_simulation(self):
        self.assertEqual(MODULE.parse_cpu_list("0,2,4,6"), [0, 2, 4, 6])
        self.assertEqual(MODULE.parse_cpu_list("0-3,8"), [0, 1, 2, 3, 8])
        for invalid in ("3-1", "64", "a", ""):
            with self.assertRaises(ValueError):
                MODULE.parse_cpu_list(invalid)

    def test_low_spec_simulation_reports_only_when_requested(self):
        import argparse

        plain = argparse.Namespace(host_cpus=None, sibling_load=None, vram_balloon_gb=None,
                                   build_directory=None)
        with MODULE.LowSpecSimulation(plain) as simulation:
            self.assertIsNone(simulation.summary())
        cpus = argparse.Namespace(host_cpus="0-7", sibling_load=None, vram_balloon_gb=None,
                                  build_directory=None)
        with MODULE.LowSpecSimulation(cpus) as simulation:
            self.assertEqual(simulation.summary()["kind"], "sensitivity")
            self.assertEqual(simulation.summary()["host_cpus"], "0-7")
        missing = argparse.Namespace(host_cpus=None, sibling_load=None, vram_balloon_gb=1.0,
                                     build_directory=Path(tempfile.gettempdir()) / "no-build")
        with self.assertRaises(ValueError):
            with MODULE.LowSpecSimulation(missing):
                pass

    def test_stage_reload_rejects_metadata_mismatch_and_awards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, data, events = self.stage_reload_fixture(root)
            for change in (dict(route="2"), dict(completions="1"), dict(completions="0"),
                           dict(best_seconds="170"), dict(best_seconds="nan"), dict(completed_stages="2"),
                           dict(path=str(root.parent / "other.toml"))):
                with self.subTest(change=change), self.assertRaises(RuntimeError):
                    MODULE.rally_stage_reload_summary([events[0] | change, *events[1:]], root, 1, [data])
            for event in ("dlc.rally.stage_completed", "dlc.rally.progress_error", "dlc.rally.series_error"):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_stage_reload_summary(events + [dict(event=event)], root, 1, [data])
            for invalid in ([], events + [events[0]]):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_stage_reload_summary(invalid, root, 1, [data])
            invalid = data.replace(b'171.5', b'nan')
            path.write_bytes(invalid)
            with self.assertRaises(RuntimeError):
                MODULE.rally_stage_reload_summary(events, root, 1, [invalid])

    def test_stage_reload_requires_advancing_native_race(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, data, events = self.stage_reload_fixture(root)
            for change in (dict(route="2"), dict(mode="17"), dict(started="0"), dict(ended="1"),
                           dict(end_reason="2"), dict(car=""), dict(event_id="0"), dict(race_serial="0"),
                           dict(time_72="nan"), dict(time_72="0")):
                with self.subTest(change=change), self.assertRaises(RuntimeError):
                    MODULE.rally_stage_reload_summary([events[0], *[e | change for e in events[1:]]], root, 1, [data])
            for invalid in (events[:-1], [*events[:-1], events[1]],
                            [*events[:-1], events[-1] | dict(race_serial="17")]):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_stage_reload_summary(invalid, root, 1, [data])

    def retry_events(self):
        first = dict(event="dlc.rally.pace_play", route="1", race_serial="16", call_index="0",
                     sample_index="0", group="CoDriver_EN/CoDriver/Distance", cue="50Distance", icon="None")
        return [first,
                dict(event="dlc.rally.pace_cancelled", reason="race_reset", route="1",
                     race_serial="16", seconds="0.000000"),
                dict(event="dlc.rally.race_trace", route="1", race_serial="16", started="0", ended="0", time_72="0"),
                dict(event="dlc.rally.race_trace", route="1", race_serial="16", started="0", ended="0", time_72="0"),
                dict(first), dict(first, call_index="1")]

    def test_rally_retry_accepts_reused_native_serial_and_rearmed_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            result = MODULE.rally_pace_retry_summary(self.retry_events(), state, [])
            self.assertTrue(result["serial_reused"])
            self.assertFalse(result["completed_retry_qualified"])
            events = self.retry_events()
            for event in events[1:]: event["race_serial"] = "17"
            self.assertFalse(MODULE.rally_pace_retry_summary(events, state, [])["serial_reused"])

    def test_rally_retry_rejects_missing_preparation_phrase_or_later_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for index, changes in ((1, {"seconds": "1"}), (1, {"reason": "pose_suspended"}),
                                   (2, {"started": "1"}), (2, {"time_72": "nan"}),
                                   (4, {"route": "2"}), (4, {"cue": "Wrong"}),
                                   (4, {"sample_index": "1"}), (5, {"call_index": "0"})):
                events = self.retry_events(); events[index].update(changes)
                with self.subTest(index=index, changes=changes), self.assertRaises(RuntimeError):
                    MODULE.rally_pace_retry_summary(events, state, [])
            for name in ("dlc.rally.stage_completed", "dlc.rally.progress_error"):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_pace_retry_summary(self.retry_events() + [dict(event=name)], state, [])

    def test_rally_retry_preserves_earned_record_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            path = state / "user-modded/profile/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            earned = b"version = 1\n[[stages]]\nroute = 1\ncompletions = 1\nbest_seconds = 140.0\n"
            path.write_bytes(earned)
            self.assertTrue(MODULE.rally_pace_retry_summary(self.retry_events(), state, [earned])["earned_records_preserved"])
            with self.assertRaisesRegex(RuntimeError, "changed earned"):
                MODULE.rally_pace_retry_summary(self.retry_events(), state, [])
            path.write_bytes(earned.replace(b"140.0", b"130.0"))
            with self.assertRaisesRegex(RuntimeError, "changed earned"):
                MODULE.rally_pace_retry_summary(self.retry_events(), state, [earned])

    def suspend_events(self):
        return [dict(event="dlc.rally.pace_play", route="1", race_serial="16", call_index="0"),
                dict(event="dlc.rally.pace_cancelled", route="1", race_serial="16",
                     seconds="4", reason="pose_suspended", had_voice="1"),
                dict(event="dlc.rally.pace_hud", visible="0")] + [
                dict(event="dlc.rally.race_trace", race_serial="16", route="1", time_72="4")
                for _ in range(3)] + [
                dict(event="dlc.rally.pace_resumed", route="1", race_serial="16", seconds="4.1"),
                dict(event="dlc.rally.pace_play", route="1", race_serial="16", call_index="1")]

    def test_rally_pace_requires_active_phrase_pause_and_clean_resume(self):
        result = MODULE.rally_pace_suspend_summary(self.suspend_events())
        self.assertEqual(result["interrupted_call"], 0)
        self.assertEqual(result["frozen_observations"], 3)
        self.assertFalse(result["visual_hud_qualified"])
        with self.assertRaisesRegex(RuntimeError, "active native phrase"):
            MODULE.rally_pace_suspend_summary([])

    def test_rally_pace_pause_rejects_stale_speech_hud_clock_and_gate_replays(self):
        for index, fields in ((1, {"had_voice": "0"}), (1, {"seconds": "nan"}),
                              (2, {"visible": "1"}), (3, {"time_72": "4.5"}),
                              (3, {"time_72": "nan"}), (3, {"race_serial": "17"}),
                              (6, {"seconds": "5"}), (6, {"seconds": "nan"}),
                              (6, {"route": "2"}), (7, {"call_index": "0"})):
            events = self.suspend_events(); events[index].update(fields)
            with self.subTest(index=index, fields=fields), self.assertRaises(RuntimeError):
                MODULE.rally_pace_suspend_summary(events)
        with self.assertRaisesRegex(RuntimeError, "speech or icons"):
            events = self.suspend_events(); events.insert(4, dict(event="dlc.rally.pace_play"))
            MODULE.rally_pace_suspend_summary(events)
        with self.assertRaisesRegex(RuntimeError, "did not resume"):
            MODULE.rally_pace_suspend_summary(self.suspend_events()[:6])
        with self.assertRaisesRegex(RuntimeError, "did not clear"):
            events = self.suspend_events(); events.pop(2)
            MODULE.rally_pace_suspend_summary(events)

    def pace_events(self, state):
        metadata = state / "mods/rally_stage_probe/rally-pace.toml"
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text("version = 1\n" + "".join(
            f"[[calls]]\nroute = 1\n[[calls.samples]]\ngroup = 'CoDriver/Distance'\n"
            f"cue = '{cue}'\nicon = 'None'\n" for cue in ("50Distance", "90Distance")))
        events = [dict(event="dlc.rally.pace_loaded", language="EN")]
        for i, cue in enumerate(("50Distance", "90Distance")):
            events += [dict(event="dlc.rally.pace_play", language="EN", route="1", race_serial="16",
                            seconds=str(i + 1), call_index=str(i), sample_index="0", handle="1234",
                            voice="5678", group="CoDriver_EN/CoDriver/Distance", cue=cue, icon="None"),
                       dict(event="dlc.rally.pace_finished", call_index=str(i), sample_index="0")]
        events.append(self.audio_events(state)[-1])
        return events

    def test_builtin_rally_pace_uses_mounted_owned_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            events = self.pace_events(state)
            builtin = state / "cache/rally_adapter"
            builtin.mkdir(parents=True)
            (state / "mods/rally_stage_probe/rally-pace.toml").rename(builtin / "rally-pace.toml")
            with self.assertRaises(FileNotFoundError):
                MODULE.rally_pace_summary(events, state, "EN", state)
            result = MODULE.rally_pace_summary([dict(event="dlc.rally.overlay_mounted"), *events], state, "EN", state)
            self.assertEqual(result["native_plays"], 2)

    def test_rally_pace_requires_complete_native_phrases(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            events = self.pace_events(state)
            result = MODULE.rally_pace_summary(events, state, "EN", state)
            self.assertEqual(result["completed_phrases"], 2)
            self.assertFalse(result["rewind_qualified"])
            with self.assertRaisesRegex(RuntimeError, "two complete"):
                MODULE.rally_pace_summary(events[:4], state, "EN", state)
            with self.assertRaisesRegex(RuntimeError, "finish without"):
                MODULE.rally_pace_summary([events[0], events[2]], state, "EN", state)

    def test_rally_pace_rejects_wrong_voice_mapping_overlap_and_repeats(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            events = self.pace_events(state)
            for key, value in (("voice", "0"), ("group", "CoDriver_MX/CoDriver/Distance"),
                               ("cue", "other"), ("route", "2"), ("seconds", "nan"), ("icon", "Wrong")):
                bad = [dict(event) for event in events]
                bad[1][key] = value
                with self.assertRaisesRegex(RuntimeError, "voice, mapping or phrase"):
                    MODULE.rally_pace_summary(bad, state, "EN", state)
            with self.assertRaisesRegex(RuntimeError, "voice, mapping or phrase"):
                MODULE.rally_pace_summary([events[0], events[1], events[3], events[2], events[4]], state, "EN", state)
            with self.assertRaisesRegex(RuntimeError, "repeated"):
                MODULE.rally_pace_summary(events + events[1:3], state, "EN", state)
            with self.assertRaisesRegex(RuntimeError, "pace error"):
                MODULE.rally_pace_summary(events + [dict(event="dlc.rally.pace_error", error="load failed")], state, "EN", state)

    def test_rally_pace_requires_ordered_metadata_and_nonsilent_pcm(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            events = self.pace_events(state)
            with self.assertRaisesRegex(RuntimeError, "before metadata"):
                MODULE.rally_pace_summary(events[1:3] + events[:1] + events[3:], state, "EN", state)
            with self.assertRaisesRegex(RuntimeError, "PCM capture missing"):
                MODULE.rally_pace_summary(events[:-1], state, "EN", state)
            with self.assertRaisesRegex(RuntimeError, "PCM capture missing"):
                MODULE.rally_pace_summary([events[-1]] + events[:-1], state, "EN", state)
            events[-1] = self.audio_events(state, 0)[-1]
            with self.assertRaisesRegex(RuntimeError, "silence"):
                MODULE.rally_pace_summary(events, state, "EN", state)

    def audio_events(self, output, value=1000):
        path = output / "rally-audio-probe.wav"
        with wave.open(str(path), "wb") as recording:
            recording.setparams((6, 2, 48000, 384000, "NONE", "not compressed"))
            recording.writeframes(value.to_bytes(2, "little", signed=True) * 2304000)
        bank = "Game:\\Media\\Audio\\VO\\CoDriver_MX.fev"
        return [dict(event="dlc.rally.audio_probe_bank_loaded", language="MX", bank=bank, project="1000"),
                dict(event="dlc.rally.audio_probe_cue_created", language="MX", handle="2000"),
                dict(event="dlc.rally.audio_probe_play", language="MX", bank=bank,
                     group="CoDriver_MX/CoDriver/Turns/Right", cue="MedRight", project="1000", handle="2000", voice="3000"),
                dict(event="dlc.rally.audio_capture_saved", path=str(path), source="native_pre_device_pcm",
                     rms=str(value / 32767), peak=str(value / 32767))]

    def test_rally_audio_requires_native_voice_and_non_silent_pcm(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            events = self.audio_events(output)
            result = MODULE.rally_audio_summary(events, output, "MX")
            self.assertEqual(result["duration_seconds"], 8)
            self.assertEqual(result["scope"], "single_cue_and_mix")
            events[2]["voice"] = "0"
            with self.assertRaisesRegex(RuntimeError, "did not start"):
                MODULE.rally_audio_summary(events, output, "MX")
            events = self.audio_events(output, 0)
            with self.assertRaisesRegex(RuntimeError, "silence"):
                MODULE.rally_audio_summary(events, output, "MX")

    def test_rally_audio_rejects_wrong_language_order_and_capture_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            events = self.audio_events(output)
            with self.assertRaisesRegex(RuntimeError, "wrong language"):
                MODULE.rally_audio_summary(events, output, "EN")
            with self.assertRaisesRegex(RuntimeError, "out of order"):
                MODULE.rally_audio_summary(list(reversed(events)), output, "MX")
            events[-1]["path"] = str(output.parent / "other.wav")
            with self.assertRaisesRegex(RuntimeError, "path or source"):
                MODULE.rally_audio_summary(events, output, "MX")

    def test_rally_audio_rejects_truncated_or_mismatched_pcm(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            events = self.audio_events(output)
            events[-1]["rms"] = "nan"
            with self.assertRaisesRegex(RuntimeError, "rms mismatch"):
                MODULE.rally_audio_summary(events, output, "MX")
            path = output / "rally-audio-probe.wav"
            path.write_bytes(path.read_bytes()[:-8])
            with self.assertRaisesRegex(RuntimeError, "truncated"):
                MODULE.rally_audio_summary(events, output, "MX")

    def test_rally_return_requires_live_worlds_unchanged_anchor_and_entry_pose(self):
        anchor = dict(event="dlc.rally.return_anchor", mode="17", event_id="4294967295", valid="1",
                      x="2000", y="140", z="960", forward_x="1", forward_y="0", forward_z="0")
        world = dict(event="dlc.rally.world_loaded", mode="17", track_id="317", media_name="Colorado")
        capture = dict(event="fh1.render_test.capture", game_mode="17", vehicle_pose_valid="1",
                       vehicle_x="2000", vehicle_y="140", vehicle_z="960")
        events = [world, anchor, capture | dict(name="event-ready")]
        for i, route in enumerate((1, 2, 3, 41)):
            events.extend([world | dict(mode="3", track_id=str(1148 + i), media_name="ColoradoDirt"),
                           anchor | dict(mode="3", event_id=str(247 + i)),
                           dict(event="dlc.rally.stage_completed", route=str(route), event_id=str(247 + i))])
        events.extend([dict(event="dlc.rally.series_return", event_id="250"), world, anchor,
                       capture | dict(name="series-return", vehicle_x="2050")])
        result = MODULE.rally_return_entry_summary(events)
        self.assertEqual((result["track_id"], result["return_distance"]), (317, 50))
        mutations = ((0, dict(track_id="1148", media_name="ColoradoDirt")),
                     (3, dict(media_name="Colorado")), (6, dict(track_id="1148")),
                     (7, dict(x="2001")), (7, dict(forward_x="nan")), (7, dict(valid="0")),
                     (16, dict(track_id="1148")), (17, dict(z="961")),
                     (18, dict(vehicle_x="10000")), (18, dict(vehicle_pose_valid="0")),
                     (18, dict(game_mode="3")), (2, dict(vehicle_x="3000")))
        for index, changes in mutations:
            with self.subTest(index=index, changes=changes):
                invalid = list(events)
                invalid[index] = invalid[index] | changes
                with self.assertRaises(RuntimeError):
                    MODULE.rally_return_entry_summary(invalid)
        for index in (0, 1, 7, 16, 17):
            with self.subTest(missing=index), self.assertRaises(RuntimeError):
                MODULE.rally_return_entry_summary(events[:index] + events[index + 1:])

    def test_completed_series_reload_preserves_count_best_total_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user-modded/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            data = "version = 3\n" + "".join(
                f'\n[[series]]\nid = {i}\ncompletions = {int(i == 7)}\n'
                f'best_seconds = {460.0 if i == 7 else 0.0}\n' for i in range(1, 8))
            data += '\n[attempt]\nseries_id = 7\ncompleted = 4\nactive = false\nseconds = [100.0,110.0,120.0,130.0]\ntotal_seconds = 460.0\n'
            original = data.encode()
            path.write_bytes(original)
            loaded = dict(event="dlc.rally.series_loaded", series_id="7", active="0", completed="4",
                          next_route="0", total_seconds="460", series_completions="1", best_seconds="460")
            events = [dict(event="dlc.rally.progress_loaded", path=str(path)), loaded]
            result = MODULE.rally_series_reload_summary(events, root, 7, [original])
            self.assertEqual((result["completions"], result["best_seconds"], result["total_seconds"]), (1, 460, 460))
            for changes in (dict(active="1"), dict(completed="3"), dict(next_route="2"),
                            dict(series_completions="2"), dict(best_seconds="459"),
                            dict(total_seconds="461")):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_series_reload_summary([events[0], loaded | changes], root, 7, [original])
            for event in ("dlc.rally.stage_completed", "dlc.rally.series_error", "dlc.rally.series_retired"):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_series_reload_summary(events + [dict(event=event)], root, 7, [original])
            path.write_bytes(original + b'# changed\n')
            with self.assertRaisesRegex(RuntimeError, "changed its progress record"):
                MODULE.rally_series_reload_summary(events, root, 7, [original])

    def test_resume_requires_loaded_attempt_new_stage_and_unchanged_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            data = b'version = 3\n[attempt]\nseries_id = 7\ncompleted = 1\nactive = true\ntotal_seconds = 100.0\n'
            path.write_bytes(data)
            loaded = dict(event="dlc.rally.series_loaded", series_id="7", active="1", completed="1",
                          next_route="2", total_seconds="100")
            resumed = dict(event="dlc.rally.series_load", route="2", event_id="248", resume="1")
            trace = dict(event="dlc.rally.race_trace", route="2", event_id="248", mode="3", started="1",
                         ended="0", end_reason="0", car="ABCD", race_serial="17", time_72="1")
            events = [dict(event="dlc.rally.progress_loaded", path=str(path)), loaded, resumed,
                      trace, trace | dict(time_72="2")]
            self.assertEqual(MODULE.rally_resume_summary(events, root, 7, 2, [data])["total_seconds"], 100)
            (root / "config").mkdir()
            (root / "config/pinyon_shift.toml").write_text('enabled_mods = ""\n')
            normal = [dict(event="paths.configured", user=str(root / "user")),
                      dict(event="dlc.rally.overlay_mounted"),
                      dict(event="dlc.rally.prepared_entry", verification="launch_preflight"),
                      dict(event="dlc.rally.series_loader_installed", series_id="0", stage_count="28")]
            menu = [dict(event="hostui.open", screen="SETTINGS"),
                    dict(event="hostui.layout", screen="SETTINGS", inside="1"),
                    dict(event="hostui.screen", screen="HORIZON RALLY"),
                    dict(event="hostui.layout", screen="HORIZON RALLY", inside="1"),
                    dict(event="hostui.closed"),
                    dict(event="dlc.rally.hub_selected", source="player", series_id="7")]
            ui = events[:2] + normal + menu + events[2:]
            self.assertTrue(MODULE.rally_hub_resume_summary(ui, root, 7, 2, [data])["hub_keyboard_resume"])
            for invalid in (ui + [menu[-1]], ui + [dict(event="dlc.rally.hub_error")],
                            events + normal + menu,
                            [e | dict(source="private_probe") if e.get("event") == "dlc.rally.hub_selected" else e for e in ui]):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_hub_resume_summary(invalid, root, 7, 2, [data])
            first = data.replace(b'completed = 1', b'completed = 0').replace(b'total_seconds = 100.0', b'total_seconds = 0.0')
            path.write_bytes(first)
            first_events = [e | dict(completed="0", next_route="1", total_seconds="0")
                            if e.get("event") == "dlc.rally.series_loaded" else
                            e | dict(route="1", event_id="247") if "route" in e else e for e in ui]
            self.assertEqual(MODULE.rally_hub_resume_summary(first_events, root, 7, 1, [first])["completed"], 0)
            invalid = [e | dict(total_seconds="1") if e.get("event") == "dlc.rally.series_loaded" else e for e in first_events]
            with self.assertRaises(RuntimeError): MODULE.rally_hub_resume_summary(invalid, root, 7, 1, [first])
            path.write_bytes(data)
            for invalid in (events[:-1], [e for e in events if e is not loaded],
                            [events[0], loaded | dict(active="0"), *events[2:]],
                            [events[0], loaded, resumed | dict(resume="0"), *events[3:]],
                            events + [dict(event="dlc.rally.stage_completed")]):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_resume_summary(invalid, root, 7, 2, [data])
            path.write_bytes(data + b'# changed\n')
            with self.assertRaisesRegex(RuntimeError, "changed the saved attempt"):
                MODULE.rally_resume_summary(events, root, 7, 2, [data])

    def test_hub_retirement_requires_confirmation_and_preserves_earned_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            records = 'version = 3\n[[stages]]\nroute = 1\ncompletions = 1\nbest_seconds = 100.0\n[[series]]\nid = 7\ncompletions = 0\nbest_seconds = 0.0\n'
            original = (records + '[attempt]\nseries_id = 7\nactive = true\ncompleted = 1\nseconds = [100,0,0,0]\ntotal_seconds = 100.0\n').encode()
            final = records + '[attempt]\nseries_id = 0\nactive = false\ncompleted = 0\nseconds = [0,0,0,0]\ntotal_seconds = 0.0\n'
            path.write_text(final)
            (root / "config").mkdir()
            (root / "config/pinyon_shift.toml").write_text('enabled_mods = ""\n')
            events = [dict(event="paths.configured", user=str(root / "user")),
                      dict(event="dlc.rally.overlay_mounted"), dict(event="dlc.rally.progress_loaded", path=str(path)),
                      dict(event="dlc.rally.prepared_entry", verification="launch_preflight"),
                      dict(event="dlc.rally.series_loader_installed", series_id="0", stage_count="28"),
                      dict(event="dlc.rally.series_loaded", series_id="7", active="1"),
                      dict(event="fh1.render_test.capture", vehicle_pose_valid="1", vehicle_x="0", vehicle_y="0", vehicle_z="0"),
                      dict(event="hostui.open", screen="SETTINGS"),
                      dict(event="hostui.screen", screen="HORIZON RALLY")]
            events += [dict(event="hostui.layout", screen=s, inside="1")
                       for s in ("SETTINGS", "HORIZON RALLY", "RETIRE CHAMPIONSHIP?")]
            confirmation = dict(event="hostui.screen", screen="RETIRE CHAMPIONSHIP?")
            events += [confirmation, confirmation, dict(event="dlc.rally.series_retired", source="player")]
            action_events = list(events)
            capture = dict(event="fh1.render_test.capture", game_mode="17", vehicle_pose_valid="1",
                           vehicle_x="40", vehicle_y="0", vehicle_z="0")
            events += [dict(event="hostui.closed"), capture, capture | dict(vehicle_x="60")]
            self.assertTrue(MODULE.rally_hub_retirement_summary(events, root, 7, [original])["earned_records_preserved"])
            for invalid in (events[:-1], action_events, events + [action_events[-1]],
                            [e for e in events if e is not confirmation],
                            [e | dict(source="private_probe") if e.get("event") == "dlc.rally.series_retired" else e for e in events],
                            events + [dict(event="dlc.rally.stage_completed")],
                            [e | dict(vehicle_x="0") if e.get("event") == "fh1.render_test.capture" else e for e in events],
                            [e | dict(inside="0") if e.get("event") == "hostui.layout" else e for e in events]):
                with self.assertRaises(RuntimeError): MODULE.rally_hub_retirement_summary(invalid, root, 7, [original])
            for bad in (final.replace('active = false', 'active = true'),
                        final.replace('best_seconds = 100.0', 'best_seconds = 99.0')):
                path.write_text(bad)
                with self.assertRaises(RuntimeError): MODULE.rally_hub_retirement_summary(events, root, 7, [original])

    def test_series_requires_four_native_finishes_saved_total_and_final_return(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user-modded/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            routes, times = (1, 2, 3, 41), (100.0, 110.0, 120.0, 130.0)
            data = "version = 3\n" + "".join(
                f'\n[[stages]]\nroute = {route}\ncompletions = {int(route in routes)}\n'
                f'best_seconds = {times[routes.index(route)] if route in routes else 0.0}\n'
                for route in MODULE.RALLY_STAGE_ROUTES)
            data += "".join(f'\n[[series]]\nid = {i}\ncompletions = {int(i == 7)}\n'
                            f'best_seconds = {460.0 if i == 7 else 0.0}\n' for i in range(1, 8))
            data += '\n[attempt]\nseries_id = 7\ncompleted = 4\nactive = false\nseconds = [100.0,110.0,120.0,130.0]\ntotal_seconds = 460.0\n'
            path.write_text(data)
            events = [dict(event="dlc.rally.progress_loaded", path=str(path))]
            awards = []
            for i, (route, seconds) in enumerate(zip(routes, times)):
                finish = dict(event="dlc.rally.race_trace", route=str(route), event_id=str(247+i),
                              race_serial=str(14+i), car="4065FE50", started="1", ended="1", end_reason="1",
                              time_72=str(seconds), time_88=str(seconds))
                award = dict(event="dlc.rally.stage_completed", route=str(route), event_id=str(247+i),
                             race_serial=str(14+i), completions="1", seconds=str(seconds), best_seconds=str(seconds))
                saved = dict(event="dlc.rally.series_stage_saved", series_id="7", route=str(route),
                             completed=str(i+1), next_route=str(routes[i+1] if i < 3 else 0),
                             total_seconds=str(sum(times[:i+1])), series_completions="1" if i==3 else "0")
                awards.append(award)
                events.extend([finish, award, saved, finish])
            returned = dict(event="dlc.rally.series_return", event_id="250")
            capture = dict(event="fh1.render_test.capture", game_mode="17")
            events.extend([returned, capture])
            result = MODULE.rally_series_summary(events, root, 7)
            self.assertEqual(result["total_seconds"], 460.0)
            self.assertEqual(result["completions"], 1)
            for invalid in (events[:-2], events[:-1] + [capture | dict(game_mode="3")],
                            events + [awards[0]], [e for e in events if e is not awards[2]],
                            events + [dict(event="dlc.rally.series_error")]):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_series_summary(invalid, root, 7)
            for old, new in (("total_seconds = 460.0", "total_seconds = 999.0"),
                             ("completed = 4", "completed = 3"), ("active = false", "active = true"),
                             ("version = 3", "version = 2")):
                path.write_text(data.replace(old, new))
                with self.assertRaises(RuntimeError):
                    MODULE.rally_series_summary(events, root, 7)

    def test_retirement_requires_running_stage_return_and_no_awards(self):
        running = dict(event="dlc.rally.race_trace", route="1", event_id="247", race_serial="14",
                       mode="3", started="1", ended="0", end_reason="0", time_72="20")
        returned = running | dict(route="0", mode="17")
        self.assertEqual(MODULE.rally_retirement_summary([running, returned], 1)["route"], 1)
        capture = dict(event="fh1.render_test.capture", name="retirement-return", game_mode="17")
        self.assertEqual(MODULE.rally_retirement_summary([running, capture], 1)["route"], 1)
        for events in ([], [running], [returned, running], [running | dict(time_72="nan"), returned],
                       [running, running | dict(ended="1", end_reason="1"), returned],
                       [running, returned, dict(event="dlc.rally.stage_completed")],
                       [running, returned, dict(event="dlc.rally.progress_error")]):
            with self.assertRaises(RuntimeError):
                MODULE.rally_retirement_summary(events, 1)

    def test_series_retirement_requires_saved_cancellation_and_unchanged_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user-modded/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            data = 'version = 3\n' + ''.join(
                f'\n[[series]]\nid = {i}\ncompletions = {int(i == 7)}\nbest_seconds = {460.0 if i == 7 else 0.0}\n'
                for i in range(1, 8))
            data += '\n[[stages]]\nroute = 1\ncompletions = 1\nbest_seconds = 100.0\n'
            data += '\n[attempt]\nseries_id = 0\ncompleted = 0\nactive = false\nseconds = [0.0,0.0,0.0,0.0]\ntotal_seconds = 0.0\n'
            path.write_text(data)
            running = dict(event="dlc.rally.race_trace", route="1", event_id="247", race_serial="14",
                           mode="3", started="1", ended="0", end_reason="0", time_72="20")
            loaded = dict(event="dlc.rally.series_loaded", series_id="7", series_completions="1", best_seconds="460")
            events = [dict(event="dlc.rally.progress_loaded", path=str(path)), loaded, running,
                      dict(event="dlc.rally.series_retired"), dict(event="fh1.render_test.capture", game_mode="17")]
            self.assertEqual(MODULE.rally_retirement_summary(events, 1, root)["series_id"], 7)
            self.assertEqual(MODULE.rally_retirement_summary(events, 1, root, [data.encode()])["series_id"], 7)
            with self.assertRaisesRegex(RuntimeError, "did not cancel"):
                MODULE.rally_retirement_summary([e for e in events if e.get("event") != "dlc.rally.series_retired"], 1, root)
            for old, new in (("active = false", "active = true"), ("completed = 0", "completed = 1"),
                             ("best_seconds = 460.0", "best_seconds = 459.0"), ("completions = 1", "completions = 2")):
                path.write_text(data.replace(old, new))
                with self.assertRaises(RuntimeError):
                    MODULE.rally_retirement_summary(events, 1, root)
            path.write_text(data.replace("best_seconds = 100.0", "best_seconds = 99.0"))
            with self.assertRaisesRegex(RuntimeError, "changed previously saved"):
                MODULE.rally_retirement_summary(events, 1, root, [data.encode()])

    def test_rally_transition_requires_saved_stage_and_advancing_new_race(self):
        award = dict(event="dlc.rally.stage_completed", route="1", event_id="247", race_serial="14")
        running = dict(event="dlc.rally.race_trace", route="2", event_id="248", race_serial="15",
                       car="4065FE50", mode="3", started="1", ended="0", end_reason="0", time_72="2.0")
        later = running | dict(time_72="3.0")
        self.assertEqual(MODULE.rally_transition_summary([award, running, later], 1, 2)["event_id"], "248")
        for events in ([running, later], [running, later, award], [award, running, running],
                       [award, later, running], [award | dict(event_id="0"), running, later],
                       [award | dict(race_serial="0"), running, later]):
            with self.assertRaisesRegex(RuntimeError, "next running native race"):
                MODULE.rally_transition_summary(events, 1, 2)
        for changes in (dict(route="1"), dict(event_id="247"), dict(race_serial="14"),
                        dict(mode="17"), dict(started="0"), dict(ended="1"),
                        dict(end_reason="2"), dict(time_72="nan"), dict(car="")):
            with self.assertRaises(RuntimeError):
                MODULE.rally_transition_summary([award, running | changes, later | changes], 1, 2)

    def test_free_roam_return_rejects_results_screen_and_missing_capture(self):
        capture = dict(event="fh1.render_test.capture", name="stage-return", game_mode="17")
        MODULE.require_free_roam_capture([capture], "stage-return")
        for events in ([], [capture | dict(game_mode="3")], [capture | dict(game_mode="0")],
                       [capture | dict(name="other")], [capture, capture]):
            with self.assertRaisesRegex(RuntimeError, "native free roam"):
                MODULE.require_free_roam_capture(events, "stage-return")

    def test_rally_completion_requires_persisted_result_in_active_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user-modded/account/title/00000001/ForzaProfile/rally-progress.toml"
            path.parent.mkdir(parents=True)
            data = "version = 1\n" + "".join(
                f"\n[[stages]]\nroute = {route}\ncompletions = {int(route == 1)}\nbest_seconds = {171.5 if route == 1 else 0.0}\n"
                for route in range(1, 22))
            path.write_text(data, encoding="utf-8")
            loaded = dict(event="dlc.rally.progress_loaded", path=str(path))
            award = dict(event="dlc.rally.stage_completed", route="1", race_serial="14",
                         completions="1", seconds="171.5", best_seconds="171.5")
            finish = dict(race_serial="14", seconds=171.5)
            events = [loaded, award]
            self.assertEqual(MODULE.rally_progress_summary(events, root, finish)["completions"], 1)
            expanded = "version = 2\n" + "".join(
                f"\n[[stages]]\nroute = {route}\ncompletions = {int(route == 41)}\nbest_seconds = {171.5 if route == 41 else 0.0}\n"
                for route in MODULE.RALLY_STAGE_ROUTES)
            path.write_text(expanded, encoding="utf-8")
            fourth_events = [loaded, award | dict(route="41")]
            self.assertEqual(MODULE.rally_progress_summary(fourth_events, root, finish)["route"], 41)
            with self.assertRaises(RuntimeError):
                MODULE.rally_progress_summary([loaded, award | dict(route="24")], root, finish)
            path.write_text(data, encoding="utf-8")
            for invalid in ([loaded], events + [award], events + [dict(event="dlc.rally.progress_error")],
                            [loaded | dict(path=str(root.parent / "other.toml")), award],
                            [loaded, award | dict(race_serial="15")],
                            [loaded, award | dict(best_seconds="nan")]):
                with self.assertRaises(RuntimeError):
                    MODULE.rally_progress_summary(invalid, root, finish)
            path.write_text(data.replace("completions = 1", "completions = 0"), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "did not persist"):
                MODULE.rally_progress_summary(events, root, finish)
            path.unlink()
            with self.assertRaisesRegex(RuntimeError, "active isolated profile"):
                MODULE.rally_progress_summary(events, root, finish)

    def test_native_finish_requires_success_and_stable_finite_time(self):
        finish = dict(event="dlc.rally.race_trace", car="4065FE50", race_serial="14",
                      started="1", ended="1", end_reason="1", time_72="171.188133", time_88="171.188133")
        self.assertAlmostEqual(MODULE.race_finish_summary([finish, finish])["seconds"], 171.188133)
        for changes in (dict(ended="0"), dict(end_reason="2"), dict(time_72="nan"),
                        dict(time_72="0", time_88="0"), dict(time_88="0"), dict(time_88="nan")):
            event = finish | changes
            with self.assertRaisesRegex(RuntimeError, "native player race finish"):
                MODULE.race_finish_summary([event, event])
        with self.assertRaises(RuntimeError):
            MODULE.race_finish_summary([finish, finish | dict(race_serial="15")])

    def test_accepts_state_waits_and_rejects_malformed_ones(self):
        header = MODULE.HEADER + "\ninput 0 0000 0 0 0 0 0 0\n"
        tail = "capture 20 shot\nstop 30\n"
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "route.fh1test"
            for wait in ("wait 10 600 vehicle", "wait 10 600 rally-stage-saved", "wait 10 600 freeroam", "wait 10 600 vehicle-moved 30",
                         "wait 10 600 movie pressstart", "wait 10 600 file carselect"):
                script.write_text(header + wait + "\n" + tail, encoding="utf-8")
                self.assertEqual([(20, "shot")], MODULE.parse_scenario(script)[0])
            script.write_text(header + "wait 10 600 vehicle\nwait 10 600 vehicle\n" + tail,
                              encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.parse_scenario(script)
            for wait in ("wait 10 600 vehicle-moved", "wait 10 0 vehicle",
                         "wait 10 600 teleport", "wait 10 600 vehicle-moved 0"):
                script.write_text(header + wait + "\n" + tail, encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.parse_scenario(script)

    def test_accepts_host_keys_in_order(self):
        header = MODULE.HEADER + "\ninput 0 0000 0 0 0 0 0 0\n"
        tail = "capture 20 shot\nstop 30\n"
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "route.fh1test"
            script.write_text(header + "hostkey 5 F6\nhostkey 6 down\n" + tail, encoding="utf-8")
            self.assertEqual([(20, "shot")], MODULE.parse_scenario(script)[0])
            script.write_text(header + "hostkey 5 f6\nhostclick 6 left 300 277\n" + tail,
                              encoding="utf-8")
            self.assertEqual([(20, "shot")], MODULE.parse_scenario(script)[0])
            for keys in ("hostkey 5 f6\nhostkey 5 enter\n", "hostkey 5 tab\n", "hostkey 5\n",
                         "hostclick 5 middle 1 1\n", "hostclick 5 left 1280 1\n"):
                script.write_text(header + keys + tail, encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.parse_scenario(script)

    def test_accepts_memory_snapshots_and_pokes(self):
        header = MODULE.HEADER + "\ninput 0 0000 0 0 0 0 0 0\n"
        tail = "capture 20 shot\nstop 30\n"
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "route.fh1test"
            script.write_text(header + "snapshot 5 s0\npoke 6 0C19DCAC 0.5\nsnapshot 7 s1\n"
                              + tail, encoding="utf-8")
            self.assertEqual([(20, "shot")], MODULE.parse_scenario(script)[0])
            for lines in ("snapshot 5 ../s0\n", "poke 5 20000000 1\n", "poke 5 0C19DCAC x\n",
                          "snapshot 6 a\nsnapshot 5 b\n", "poke 5 0C19DCAC\n"):
                script.write_text(header + lines + tail, encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.parse_scenario(script)

    def test_race_start_wait_route_parses(self):
        scenarios = Path(__file__).parents[2] / "config" / "render-tests"
        captures = MODULE.parse_scenario(scenarios / "fh1-race-start-wait.fh1test")[0]
        self.assertIn((4330, "race-moving"), captures)

    def test_synchronized_routes_parse(self):
        scenarios = Path(__file__).parents[2] / "config" / "render-tests"
        for name in (
            "fh1-race-sync", "fh1-modes-sync", "fh1-opening-sync", "fh1-long-drive", "fh1-buy-car",
            "fh1-rewind-sync", "fh1-settings-gate", "fh1-xam-dialogs",
            "fh1-rally-stage-start", "fh1-rally-stage-ai",
            "fh1-rally-stage-retire", "fh1-rally-transition", "fh1-rally-series-07",
            "fh1-rally-series-resume", "fh1-rally-series-reload",
            "fh1-rally-pace-probe", "fh1-rally-pace-pause",
            "fh1-rally-pace-retry",
            "fh1-rally-stage-reload",
            "fh1-rally-builtin-first-stage",
            "fh1-rally-builtin-resume",
            "fh1-rally-hub-entry", "fh1-rally-hub-resume", "fh1-rally-hub-retire",
            "fh1-rally-hub-resume-first",
            "fh1-rally-car-database",
        ):
            self.assertTrue(MODULE.parse_scenario(scenarios / f"{name}.fh1test")[0])

    def test_resolves_disc_corpus_ucode_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ucode").mkdir()
            (root / "ucode" / "pixel-i01-test.bin").write_bytes(b"shader")
            self.assertEqual(
                (root / "ucode").resolve(),
                MODULE.resolve_disc_shader_corpus(root),
            )
            with self.assertRaisesRegex(ValueError, "contains no corpus.blob or .bin shaders"):
                MODULE.resolve_disc_shader_corpus(root / "missing")

    def test_resolves_packed_disc_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                MODULE.resolve_disc_shader_corpus(root)
            # Contents are validated by the producer; discovery accepts its
            # current packed filename as well as the legacy loose programs.
            (root / "corpus.blob").write_bytes(b"FH1C" + bytes((1, 0, 0, 0)) + bytes(4))
            self.assertEqual(root.resolve(), MODULE.resolve_disc_shader_corpus(root))

    def test_shader_capture_summary_can_gate_runtime_misses(self):
        events = [{
            "event": "native_renderer.shader_capture.summary",
            "entries": "2",
            "bytes": "1024",
            "duplicate_callbacks": "3",
            "rejected_callbacks": "0",
        }]
        self.assertEqual(2, MODULE.shader_capture_summary(events, False)["entries"])
        with self.assertRaisesRegex(RuntimeError, "2 runtime translation misses"):
            MODULE.shader_capture_summary(events, True)

    def test_requires_explicit_image_baseline_mode(self):
        with self.assertRaisesRegex(ValueError, "--record-baseline"):
            MODULE.require_image_reference({"scene": (1, 2, 0.1)}, None, False)
        MODULE.require_image_reference({"scene": (1, 2, 0.1)}, None, True)
        MODULE.require_image_reference(
            {"scene": (1, 2, 0.1)}, Path("baseline"), False
        )

    def test_prepares_private_state_without_copying_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "user").mkdir(parents=True)
            (source / "config").mkdir()
            (source / "cache").mkdir()
            (source / "user" / "profile").write_text("save", encoding="utf-8")
            (source / "config" / "settings.toml").write_text(
                "setting = true", encoding="utf-8"
            )
            (source / "cache" / "shader.bin").write_bytes(b"cache")

            destination = root / "run" / "state"
            MODULE.prepare_isolated_state(source, destination)

            self.assertEqual(
                "save",
                (destination / "user" / "profile").read_text(encoding="utf-8"),
            )
            self.assertTrue((destination / "config" / "settings.toml").is_file())
            self.assertFalse((destination / "cache").exists())

    @unittest.skipUnless(sys.platform == "win32", "Windows Marketplace paths")
    def test_private_state_copies_deep_dlc_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = Path("user/0000000000000000/4D5309C9/00000002") / ("A" * 42)
            relative /= Path("Media/DLCZips/1600_pri_65/Media/UI/Textures") / ("localized-" * 8)
            source = root / "source"
            destination = root / "private-run-state"
            try:
                member = Path("\\\\?\\" + str(source / relative / "icon.bin"))
                member.parent.mkdir(parents=True)
                member.write_bytes(b"rally asset")
                MODULE.prepare_isolated_state(source, destination)
                copied = Path("\\\\?\\" + str(destination / relative / "icon.bin"))
                self.assertGreater(len(str(copied)), 260)
                self.assertEqual(b"rally asset", copied.read_bytes())
                self.assertEqual(b"rally asset", member.read_bytes())
            finally:
                # This test owns these two trees; use extended paths for cleanup too.
                for tree in (source, destination):
                    extended = Path("\\\\?\\" + str(tree))
                    if extended.exists():
                        shutil.rmtree(extended)

    def test_seeds_only_fh1_native_shader_and_pipeline_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            storage = source / "cache"
            storage.mkdir(parents=True)
            (storage / "fh1-native-shaders-v2.bin").write_bytes(b"shaders")
            (storage / "fh1-native-pipelines-v1.bin").write_bytes(b"pipelines")
            (storage / "unrelated.pnsp").write_bytes(b"pack")
            destination = root / "destination"

            self.assertEqual(
                ["fh1-native-shaders-v2.bin", "fh1-native-pipelines-v1.bin"],
                MODULE.seed_fh1_shader_storage(source, destination),
            )
            copied = destination / "cache"
            self.assertEqual(b"shaders", (copied / "fh1-native-shaders-v2.bin").read_bytes())
            self.assertEqual(b"pipelines", (copied / "fh1-native-pipelines-v1.bin").read_bytes())
            self.assertFalse((copied / "unrelated.pnsp").exists())

    def test_seeds_vulkan_shader_and_pipeline_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            storage = source / "cache" / "shaders" / "shareable"
            storage.mkdir(parents=True)
            (storage / "4D5309C9.xsh").write_bytes(b"ucode")
            (storage / "4D5309C9.fbo.vk.xpso").write_bytes(b"pipelines")
            (storage / "4D5309C9.rtv.d3d12.xpso").write_bytes(b"d3d12")
            (storage / "pack.pnsp").write_bytes(b"pack")
            destination = root / "destination"

            self.assertEqual(
                ["4D5309C9.fbo.vk.xpso", "4D5309C9.xsh"],
                MODULE.seed_vulkan_shader_storage(source, destination),
            )
            copied = destination / "cache" / "shaders" / "shareable"
            self.assertEqual(b"ucode", (copied / "4D5309C9.xsh").read_bytes())
            self.assertEqual(b"pipelines", (copied / "4D5309C9.fbo.vk.xpso").read_bytes())
            self.assertFalse((copied / "4D5309C9.rtv.d3d12.xpso").exists())
            self.assertFalse((copied / "pack.pnsp").exists())
            with self.assertRaises(ValueError):
                MODULE.seed_vulkan_shader_storage(root / "empty", destination)

    def test_seeds_only_fh1_pipeline_prewarm_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "cache").mkdir(parents=True)
            (source / "cache/fh1-gpu-prewarm-v3.txt").write_text(
                "pinyon-shift.fh1-gpu-prewarm.v3\n", encoding="utf-8"
            )
            destination = root / "destination"

            self.assertEqual(
                "fh1-gpu-prewarm-v3.txt",
                MODULE.seed_fh1_pipeline_prewarm(source, destination),
            )
            self.assertTrue(
                (destination / "cache/fh1-gpu-prewarm-v3.txt").is_file()
            )

    def test_parses_v5_pass_family_cost(self):
        line = (
            "FH1 V5 pass family FA79E5778D949D02: attachment 4A23C979E555853F, "
            "first family B45B38234A27121C, first draw 39E7407EABA44369, "
            "copy 0000000000000000, samples 12, draws 87-121 (average 103), "
            "total 20280000 ns, average 1690000 ns, maximum 2000000 ns"
        )
        match = MODULE.PASS_FAMILY.search(line)
        self.assertIsNotNone(match)
        self.assertEqual("FA79E5778D949D02", match.group("family"))
        self.assertEqual("1690000", match.group("average_ns"))

    def test_parses_strict_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.fh1test"
            path.write_text(
                "pinyon-shift-fh1-render-test-v1\n"
                "# clock-hz 30\n"
                "# expect-image scene 3 8 0.1\n"
                "# expect-performance 50000 55 27 31\n"
                "# expect-distinct-presentation 55\n"
                "# expect-simulation-time 0.9 1.1 0\n"
                "# expect-capture-mae scene scene 0\n"
                "# expect-race-hud scene\n"
                "# expect-race-hud-any scene later\n"
                "input 0 0000 0 0 0 0 0 0\n"
                "input 10 1000 0 0 0 0 0 0\n"
                "capture 20 scene\n"
                "capture 25 later\n"
                "stop 30\n",
                encoding="utf-8",
            )
            (
                captures, stop, images, performance, distinct,
                simulation_time, capture_mae, race_hud, race_hud_any,
            ) = MODULE.parse_scenario(path)
            self.assertEqual([(20, "scene"), (25, "later")], captures)
            self.assertEqual(30, stop)
            self.assertEqual({"scene": (3.0, 8.0, 0.1)}, images)
            self.assertEqual((50000.0, 55.0, 27.0, 31.0), performance)
            self.assertEqual(55.0, distinct)
            self.assertEqual((0.9, 1.1, 0), simulation_time)
            self.assertEqual([("scene", "scene", 0.0)], capture_mae)
            self.assertEqual({"scene"}, race_hud)
            self.assertEqual([{"scene", "later"}], race_hud_any)

    def test_recognizes_fh1_race_hud_regions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "race.ppm"
            width = height = 100
            pixels = bytearray(width * height * 3)

            def fill(x0, x1, y0, y1, color):
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        offset = (y * width + x) * 3
                        pixels[offset : offset + 3] = bytes(color)

            fill(3, 23, 2, 14, (255, 255, 255))
            fill(78, 97, 2, 14, (255, 255, 255))
            fill(78, 97, 24, 40, (255, 20, 120))
            path.write_bytes(b"P6\n100 100\n255\n" + pixels)
            self.assertGreater(
                MODULE.race_hud_summary(path)["standings_pink_fraction"], 0.01
            )

            fill(78, 97, 24, 40, (255, 255, 255))
            path.write_bytes(b"P6\n100 100\n255\n" + pixels)
            self.assertGreater(
                MODULE.race_hud_summary(path)["standings_white_fraction"], 0.01
            )

            fill(78, 97, 15, 40, (0, 0, 0))
            fill(78, 97, 15, 19, (255, 20, 120))
            path.write_bytes(b"P6\n100 100\n255\n" + pixels)
            self.assertGreater(
                MODULE.race_hud_summary(path)["standings_pink_fraction"], 0.01
            )

            path.write_bytes(b"P6\n100 100\n255\n" + bytes(len(pixels)))
            with self.assertRaisesRegex(RuntimeError, "missing FH1 race HUD"):
                MODULE.race_hud_summary(path)

    def test_capture_mae_detects_missing_mode_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            header = b"P6\n1 1\n255\n"
            (output / "before.ppm").write_bytes(header + bytes((10, 20, 30)))
            (output / "after.ppm").write_bytes(header + bytes((40, 50, 60)))
            self.assertEqual(
                30.0, MODULE.compare_capture_mae(output, "before", "after")
            )

    def test_rejects_nonzero_initial_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.fh1test"
            path.write_text(
                "pinyon-shift-fh1-render-test-v1\n"
                "input 1 0000 0 0 0 0 0 0\n"
                "capture 20 scene\n"
                "stop 30\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "frame 0"):
                MODULE.parse_scenario(path)

    def test_rejects_output_waits_on_wall_time_clock_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.fh1test"
            script = ("pinyon-shift-fh1-render-test-v1\n"
                      "input 0 0000 0 0 0 0 0 0\n"
                      "capture 20 scene\nstop 30\n")
            for directive in ("# clock-hz 120\n", "wait 10 100 vehicle\n"):
                path.write_text(script.replace("input 0", directive + "input 0"))
                self.assertEqual([(20, "scene")], MODULE.parse_scenario(path)[0])
            path.write_text(script.replace("input 0", "# clock-hz 120\nwait 10 100 vehicle\ninput 0"))
            with self.assertRaisesRegex(ValueError, "output-frame waits"):
                MODULE.parse_scenario(path)

    def test_capture_pose_fields_are_numeric(self):
        event = {
            "vehicle_pose_valid": "1",
            "vehicle_x": "1.25",
            "vehicle_y": "-2.5",
            "vehicle_z": "3.75",
        }
        pose = {
            axis: float(event[f"vehicle_{axis}"]) for axis in ("x", "y", "z")
        }
        self.assertEqual(pose, {"x": 1.25, "y": -2.5, "z": 3.75})

    def test_compares_vehicle_pose_by_wall_time_frame(self):
        baseline = [
            {"frame": 60, "vehicle_pose": {"x": 1.0, "y": 2.0, "z": 3.0}}
        ]
        candidate = [
            {"frame": 60, "vehicle_pose": {"x": 1.3, "y": 2.4, "z": 3.0}}
        ]
        comparison = MODULE.compare_vehicle_poses(candidate, baseline, 0.51)
        self.assertEqual(comparison, [{"frame": 60, "distance": 0.5}])
        with self.assertRaisesRegex(RuntimeError, "differs by"):
            MODULE.compare_vehicle_poses(candidate, baseline, 0.49)

if __name__ == "__main__":
    unittest.main()
