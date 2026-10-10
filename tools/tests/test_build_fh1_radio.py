import argparse
import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "build-fh1-radio.py"
SPEC = importlib.util.spec_from_file_location("build_fh1_radio", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

# MPEG-1 Layer III, 160 kbps, 48 kHz, joint stereo: one 480-byte frame.
FRAME = bytes([0xFF, 0xFB, 0xA4, 0x40]) + bytes(476)

SYSTEM = """<?xml version="1.0" encoding="utf-8"?>
<RadioSystem>
\t<RadioStation name="Radio1">
\t\t<Playlist noRepeat="15" >
\t\t\t<MusicTrack name="Old" artist="Band" fmodname="R1_Old" likelihoodDaytime="1" />
\t\t</Playlist>
\t</RadioStation>
\t<RadioStation name="Radio2">
\t\t<Playlist noRepeat="15" >
\t\t\t<MusicTrack name="Other" artist="Band" fmodname="R2_Other" likelihoodDaytime="1" />
\t\t</Playlist>
\t</RadioStation>
</RadioSystem>
"""

INFO = ('\r\n<SoundBanks>\r\n  <Bank Name="R1_Old">\r\n    <SoundBankInfo SoundBankIndex="0"/>\r\n'
        '  </Bank>\r\n</SoundBanks>')


def sample(name, frames, channels=2, sync=True):
    length = frames * MODULE.FRAME_SAMPLES
    return MODULE.Sample(name, length, frames * MODULE.FRAME_BYTES, 0, length - 1,
                         MODULE.SAMPLE_MODE, 48000, 255, 128, 128, channels,
                         struct.pack("<ffiHh", 1.0, 10000.0, 868, 0, 0),
                         [(0, "SongStart"), (1152, "EventStart"), (length - 1152, "IdentStart")]
                         if sync else [])


def write_bank(path, samples, payloads):
    bank = MODULE.Bank(0x40000, 0x40, bytes(range(24)), samples, 0)
    with path.open("wb") as stream:
        stream.write(bank.header())
        for data in payloads:
            stream.write(data + bytes(MODULE.aligned(len(data)) - len(data)))


class BankTests(unittest.TestCase):
    def test_header_round_trips_with_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Radio_Music.fsb"
            odd = sample("VO_Line", 1, 1, sync=False)
            odd.length_bytes = 333  # not a multiple of 32, as in the VO banks
            write_bank(path, [sample("R1_Song", 3), odd, sample("R2_Song", 2)],
                       [FRAME * 3, bytes(333), FRAME * 2])
            bank, raw = MODULE.read_bank(path)
            self.assertEqual(bank.header(), raw)
            self.assertEqual(bank.data_start % MODULE.DATA_ALIGN, 0)
            self.assertEqual([s.name for s in bank.samples], ["R1_Song", "VO_Line", "R2_Song"])
            self.assertEqual(bank.samples[2].data_offset - bank.samples[1].data_offset, 352)
            self.assertEqual(bank.samples[0].sync[2], (3 * 1152 - 1152, "IdentStart"))
            self.assertEqual(MODULE.check_bank(path), 0)

    def test_rejects_other_mpeg_formats(self):
        self.assertEqual(len(MODULE.mpeg_frames(FRAME * 4)), 4)
        at_44k = bytes([0xFF, 0xFB, 0xA0, 0x40]) + bytes(476)
        with self.assertRaises(ValueError):
            MODULE.mpeg_frames(at_44k)
        with self.assertRaises(ValueError):
            MODULE.mpeg_frames(FRAME + FRAME[:100])

    def test_long_names_are_refused(self):
        with self.assertRaises(ValueError):
            sample("X" * 30, 1).header()


class TextTests(unittest.TestCase):
    def test_adds_tracks_to_one_station(self):
        text = MODULE.merge_playlist(SYSTEM, "Radio1", [("A & B", 'The "X"', "PS001_A")], False)
        radio1 = text[:text.index('name="Radio2"')]
        self.assertIn('fmodname="R1_Old"', radio1)
        self.assertIn('name="A &amp; B" artist="The &quot;X&quot;" fmodname="PS001_A"', radio1)
        self.assertNotIn("PS001_A", text[text.index('name="Radio2"'):])
        self.assertIn('noRepeat="15"', radio1)

    def test_replace_keeps_a_choice_open(self):
        tracks = [("A", "", "PS001_A"), ("B", "", "PS002_B")]
        text = MODULE.merge_playlist(SYSTEM, "Radio2", tracks, True)
        radio2 = text[text.index('name="Radio2"'):]
        self.assertNotIn("R2_Other", radio2)
        self.assertIn('noRepeat="1"', radio2)
        self.assertIn("R1_Old", text)
        with self.assertRaises(ValueError):
            MODULE.merge_playlist(SYSTEM, "Radio3", tracks, True)

    def test_info_entry_is_in_milliseconds(self):
        s = sample("PS001_A", 100)
        entry = MODULE.info_entry(s, 127, "\r\n")
        self.assertIn('SoundBankIndex="127"', entry)
        self.assertIn('FileLength="2400"', entry)  # 100 frames of 1152 samples at 48 kHz
        self.assertIn('OffsetEventStart="24"', entry)
        self.assertIn('OffsetIdentStart="2376"', entry)
        merged = MODULE.merge_info(INFO, entry)
        self.assertTrue(merged.endswith("  </Bank>\r\n</SoundBanks>"))

    def test_sample_names_are_unique_and_short(self):
        taken = {"ps001_hello"}
        first = MODULE.sample_name(1, "hello", taken)
        self.assertNotEqual(first.lower(), "ps001_hello")
        long = MODULE.sample_name(2, "A very long song title that goes on", taken)
        self.assertLess(len(long), MODULE.NAME_BYTES)
        self.assertEqual(MODULE.sample_name(3, "!!!", taken), "PS003_Track")


class BuildTests(unittest.TestCase):
    def test_builds_a_mod_from_a_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            radio = root / "game" / MODULE.RADIO
            radio.mkdir(parents=True)
            write_bank(radio / "Radio_Music.fsb", [sample("R1_Old", 2)], [FRAME * 2])
            (radio / "RadioSystem.xml").write_text(SYSTEM, encoding="utf-8", newline="\n")
            (radio / "RadioSoundbankInfo_Music.xml").write_bytes(INFO.encode())
            (radio / "Radio_Music.lst").write_bytes(b"R1_Old.wav, quality=0, fsound_loop_off\r\n")
            music = root / "music"
            (music / "sub").mkdir(parents=True)
            (music / "b.mp3").write_bytes(b"x")
            (music / "sub" / "a.wav").write_bytes(b"x")
            (music / "notes.txt").write_bytes(b"x")
            state = root / "state"
            encode, tags = MODULE.encode, MODULE.tags
            MODULE.encode = lambda ffmpeg, source, channels: FRAME * (3 if source.suffix == ".mp3" else 5)
            MODULE.tags = lambda ffprobe, source: {"title": source.stem.upper()}
            try:
                args = argparse.Namespace(music=music, state_root=state, station=["Radio2", "Radio2"],
                                          replace=False, name="my_radio", enable=True,
                                          game_root=root / "game", ffmpeg="ffmpeg", ffprobe="ffprobe")
                self.assertEqual(MODULE.build(args), 0)
                self.assertEqual(MODULE.build(args), 0)  # rebuilding its own mod is allowed
            finally:
                MODULE.encode, MODULE.tags = encode, tags
            out = state / "mods" / "my_radio" / "game" / MODULE.RADIO
            bank, raw = MODULE.read_bank(out / "Radio_Music.fsb")
            self.assertEqual(bank.header(), raw)
            self.assertEqual([s.name for s in bank.samples], ["R1_Old", "PS001_B", "PS002_A"])
            self.assertEqual(bank.samples[2].length_samples, 5 * 1152)
            with (out / "Radio_Music.fsb").open("rb") as stream:
                stream.seek(bank.samples[2].data_offset)
                self.assertEqual(stream.read(5 * 480), FRAME * 5)
            system = (out / "RadioSystem.xml").read_text(encoding="utf-8")
            self.assertEqual(system.count("PS001_B"), 1)
            self.assertIn('fmodname="PS002_A"', system[system.index('name="Radio2"'):])
            info = (out / "RadioSoundbankInfo_Music.xml").read_bytes().decode()
            self.assertIn('<Bank Name="PS002_A">\r\n    <SoundBankInfo SoundBankIndex="2"', info)
            self.assertIn(b"PS002_A.mp3", (out / "Radio_Music.lst").read_bytes())
            toml = (state / "mods" / "my_radio" / "mod.toml").read_text(encoding="utf-8")
            self.assertIn('name = "my_radio"', toml)
            self.assertIn("shares_save = true", toml)
            self.assertIn('enabled_mods = "my_radio"',
                          (state / "config" / "pinyon_shift.toml").read_text(encoding="utf-8"))

    def test_leaves_a_foreign_mod_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            radio = root / "game" / MODULE.RADIO
            radio.mkdir(parents=True)
            write_bank(radio / "Radio_Music.fsb", [sample("R1_Old", 1)], [FRAME])
            (root / "music").mkdir()
            (root / "music" / "a.mp3").write_bytes(b"x")
            mine = root / "state" / "mods" / "custom_radio"
            mine.mkdir(parents=True)
            (mine / "mod.toml").write_text("name = 'custom_radio'\n", encoding="utf-8")
            args = argparse.Namespace(music=root / "music", state_root=root / "state", station=None,
                                      replace=False, name="custom_radio", enable=False,
                                      game_root=root / "game", ffmpeg="ffmpeg", ffprobe=None)
            self.assertEqual(MODULE.build(args), 1)
            self.assertTrue((mine / "mod.toml").exists())


if __name__ == "__main__":
    unittest.main()
