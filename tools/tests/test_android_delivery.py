"""Android without adb or hand-installed tools (ONE_CLICK_SETUP_BACKLOG A-1 to A-5).

The launcher builds the package with the pinned toolchain, shows where it is,
and serves it and the game files to the player's device on the local network
while its Android panel shares. These pin the safety rules of that share and
the build script's checks.
"""

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "launcher" / "PinyonShift.Launcher"


def read(path):
    return path.read_text(encoding="utf-8")


class ShareTests(unittest.TestCase):
    def setUp(self):
        self.share = read(LAUNCHER / "AndroidShare.cs")
        self.window = read(LAUNCHER / "MainWindow.xaml.cs")

    def test_only_private_addresses_are_answered(self):
        serve = self.share[self.share.index("private async Task ServeAsync"):]
        self.assertLess(serve.index("IsPrivate(remote)"), serve.index("ReadRequestAsync"))
        self.assertIn("b[0] == 192 && b[1] == 168", self.share)
        self.assertIn("!IsPrivate(request.RemoteEndPoint.Address)", self.share)

    def test_files_need_the_pairing_code_and_wrong_codes_lock_the_share(self):
        route = self.share[self.share.index("private async Task RouteAsync"):]
        self.assertLess(route.index("X-Pinyon-Code"), route.index('"/pinyon/v1/manifest"'))
        self.assertIn("CryptographicOperations.FixedTimeEquals", route)
        self.assertIn("MaxWrongCodes = 10", self.share)
        self.assertIn("RandomNumberGenerator.GetInt32(0, 1_000_000)", self.share)

    def test_files_are_served_by_index_from_the_listed_groups_only(self):
        # A request never names a path on the PC.
        route = self.share[self.share.index("private async Task RouteAsync"):]
        self.assertIn("_files[fileIndex].Source", route)
        self.assertNotRegex(route, r"Path\.Combine\(")
        self.assertIn('request.Method is not ("GET" or "HEAD")', route)

    def test_the_share_serves_only_while_the_panel_is_open(self):
        show = self.window[self.window.index("private void ShowPanel"):]
        show = show[:show.index("\n    }\n")]
        self.assertIn("StopAndroidShare()", show)
        self.assertIn("_androidShare?.Dispose();", self.window)

    def test_the_save_is_offered_but_not_preselected(self):
        groups = self.window[self.window.index("private IReadOnlyList<ShareGroup> AndroidShareGroups"):]
        self.assertIn('new ShareGroup("save", "this PC\'s save", false, save)', groups)
        self.assertIn('"user-modded"', groups)

    def test_the_apk_is_easy_to_find(self):
        xaml = read(LAUNCHER / "MainWindow.xaml")
        for name in ("AndroidApkText", "AndroidShowButton", "AndroidSaveButton", "AndroidShareButton",
                     "AndroidQrImage", "AndroidUsbButton"):
            self.assertIn(f'x:Name="{name}"', xaml)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.build = read(ROOT / "tools" / "build-android.ps1")

    def test_v4_is_built_when_the_player_plays_v4(self):
        self.assertIn("[switch]$TitleUpdateV4", self.build)
        self.assertIn("'--title-update-v4'", self.build)
        self.assertIn(".local/generated-v4", self.build)
        window = read(LAUNCHER / "MainWindow.xaml.cs")
        self.assertIn('arguments.Add("-TitleUpdateV4")', window)

    def test_space_and_download_sites_are_checked_first(self):
        self.assertLess(self.build.index("Assert-PinyonFreeSpace -Root $root -Android"),
                        self.build.index("'android', 'build'"))
        self.assertLess(self.build.index("Assert-PinyonDownloadHosts"),
                        self.build.index("Invoke-PinyonDownload"))
        config = json.loads(read(ROOT / "config" / "release-toolchain.json"))
        self.assertGreater(config["disk_space_gb"]["android"], 0)

    def test_the_package_records_what_it_holds(self):
        self.assertIn("pinyon-shift.json", self.build)
        self.assertRegex(self.build, r"title_update_v4 = \[bool\]\$TitleUpdateV4")

    def test_usb_install_is_for_developers_and_resumes(self):
        usb = read(ROOT / "tools" / "install-android-usb.ps1")
        self.assertLess(usb.index("'android', 'install'"), usb.index("'android', 'push-data'"))
        self.assertIn("push-title-update", usb)
        self.assertTrue(re.search(r"android-error\.json", usb))


if __name__ == "__main__":
    unittest.main()
