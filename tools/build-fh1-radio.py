#!/usr/bin/env python3
"""Build a custom FH1 radio station from a folder of music (FB-1.4, #420).

FH1's radio is one FMOD Ex bank, media/audio/radio/Radio_Music.fsb: an FSB4
file whose 127 samples are plain MPEG-1 Layer III, 48 kHz, 160 kbps CBR
(480-byte frames), mono for the 3D stations and stereo for Radio1-3. Each
sample carries three named sync points, in samples: SongStart, EventStart
and IdentStart. RadioSoundbankInfo_Music.xml repeats them in milliseconds
(rounded down) with the sample's index and length, and RadioSystem.xml's
station playlists name samples by their FMOD name.

This tool encodes the folder's files with FFmpeg to the bank's format,
appends them to a copy of the player's own bank (the stock samples keep
their indexes), and writes the bank, the info file and RadioSystem.xml with
the station's playlist extended or replaced, as an asset mod:

  <state>/mods/<name>/game/media/audio/radio/...

  build-fh1-radio.py <music-folder> --state-root <state> [--station Radio1 ...]
                     [--replace] [--name custom_radio] [--enable]
  build-fh1-radio.py --check-bank [Radio_Music.fsb]

--check-bank parses a bank and rebuilds its header from the parsed fields,
proving the reader and writer agree byte for byte with the shipped file.
Nothing from the disc is ever written outside the mod directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
RADIO = Path("media") / "audio" / "radio"
RATE = 48000
BITRATE = 160
FRAME_BYTES = 144000 * BITRATE // RATE  # 480, no padding slot at 48 kHz
FRAME_SAMPLES = 1152
DATA_ALIGN = 32  # each sample's data starts on this boundary, zero padded
SAMPLE_MODE = 0x90000200  # FMOD MPEG plus two flags every stock sample has
NAME_BYTES = 30
SYNC_NAME_BYTES = 256
SYNC_NAMES = ("SongStart", "EventStart", "IdentStart")
STATIONS = ("Radio1", "Radio2", "Radio3")
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".wma"}
IDENT_BEFORE_END_S = 4.0
MARKER = ".pinyon-radio"


def aligned(size: int) -> int:
    return size + (-size % DATA_ALIGN)


@dataclass
class Sample:
    name: str
    length_samples: int
    length_bytes: int
    loop_start: int
    loop_end: int
    mode: int
    frequency: int
    volume: int
    pan: int
    priority: int
    channels: int
    tail: bytes  # min/max distance, frequency/volume/pan variation
    sync: list[tuple[int, str]] = field(default_factory=list)
    data_offset: int = 0

    def header(self) -> bytes:
        name = self.name.encode("ascii")
        if len(name) >= NAME_BYTES:
            raise ValueError(f"sample name {self.name!r} is longer than {NAME_BYTES - 1} bytes")
        extra = b""
        if self.sync:
            extra = b"SYNC" + struct.pack("<I", len(self.sync))
            for offset, label in self.sync:
                extra += struct.pack("<I", offset) + label.encode("ascii").ljust(SYNC_NAME_BYTES, b"\0")
        size = 80 + len(extra)
        return (struct.pack("<H", size) + name.ljust(NAME_BYTES, b"\0")
                + struct.pack("<IIIIIiHhHH", self.length_samples, self.length_bytes,
                              self.loop_start, self.loop_end, self.mode, self.frequency,
                              self.volume, self.pan, self.priority, self.channels)
                + self.tail + extra)


@dataclass
class Bank:
    version: int
    mode: int
    reserved: bytes  # 24 bytes after the mode: FMOD's zero field and hash
    samples: list[Sample]
    data_start: int

    def header(self) -> bytes:
        headers = b"".join(s.header() for s in self.samples)
        headers += b"\0" * (-(48 + len(headers)) % DATA_ALIGN)
        data = sum(aligned(s.length_bytes) for s in self.samples)
        return (struct.pack("<4sIIIII", b"FSB4", len(self.samples), len(headers), data,
                            self.version, self.mode) + self.reserved + headers)


def read_bank(path: Path) -> tuple[Bank, bytes]:
    """Parse an FSB4 bank; also return its raw header for comparison."""
    with path.open("rb") as stream:
        head = stream.read(48)
        magic, count, header_size, data_size, version, mode = struct.unpack("<4sIIIII", head[:24])
        if magic != b"FSB4":
            raise ValueError(f"{path} is not an FSB4 bank")
        raw = stream.read(header_size)
    samples, offset, position = [], 0, 48 + header_size
    for _ in range(count):
        size, = struct.unpack("<H", raw[offset:offset + 2])
        fields = struct.unpack("<IIIIIiHhHH", raw[offset + 32:offset + 64])
        sample = Sample(raw[offset + 2:offset + 32].split(b"\0")[0].decode("ascii"), *fields,
                        tail=raw[offset + 64:offset + 80], data_offset=position)
        extra = raw[offset + 80:offset + size]
        if extra[:4] == b"SYNC":
            n, = struct.unpack("<I", extra[4:8])
            for k in range(n):
                entry = extra[8 + k * 260:8 + (k + 1) * 260]
                sample.sync.append((struct.unpack("<I", entry[:4])[0],
                                    entry[4:].split(b"\0")[0].decode("ascii")))
        elif extra:
            raise ValueError(f"{sample.name}: unknown extra header {extra[:4]!r}")
        samples.append(sample)
        position += aligned(sample.length_bytes)
        offset += size
    if raw[offset:].strip(b"\0"):
        raise ValueError(f"{path}: unknown data after the sample headers")
    if position != 48 + header_size + data_size:
        raise ValueError(f"{path}: sample data does not add up to the header's size")
    return Bank(version, mode, head[24:48], samples, 48 + header_size), head + raw


def mpeg_frames(data: bytes) -> list[bytes]:
    """Split an encoder's output into frames of the bank's one format."""
    frames, i = [], 0
    while i + 4 <= len(data):
        if data[i] != 0xFF or data[i + 1] & 0xE0 != 0xE0:
            raise ValueError(f"no MPEG frame at byte {i}")
        b1, b2 = data[i + 1], data[i + 2]
        if (b1 >> 3) & 3 != 3 or (b1 >> 1) & 3 != 1 or b2 >> 4 != 10 or (b2 >> 2) & 3 != 1:
            raise ValueError(f"frame at byte {i} is not MPEG-1 Layer III, 160 kbps, 48 kHz")
        frames.append(data[i:i + FRAME_BYTES])
        i += FRAME_BYTES
    if i != len(data) or not frames:
        raise ValueError("MPEG data ends inside a frame")
    return frames


def encode(ffmpeg: str, source: Path, channels: int) -> bytes:
    command = [ffmpeg, "-v", "error", "-nostdin", "-i", str(source), "-vn", "-map_metadata", "-1",
               "-ar", str(RATE), "-ac", str(channels), "-c:a", "libmp3lame",
               "-b:a", f"{BITRATE}k", "-write_xing", "0", "-id3v2_version", "0",
               "-write_id3v1", "0", "-f", "mp3", "-"]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg could not encode {source}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def tags(ffprobe: str, source: Path) -> dict[str, str]:
    result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format_tags=title,artist",
                             "-of", "json", str(source)], capture_output=True)
    if result.returncode != 0:
        return {}
    found = json.loads(result.stdout or b"{}").get("format", {}).get("tags", {})
    return {k.lower(): v.strip() for k, v in found.items() if v.strip()}


def find_music(folder: Path) -> list[Path]:
    return sorted((p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES),
                  key=lambda p: str(p.relative_to(folder)).lower())


def sample_name(index: int, title: str, taken: set[str]) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "", title.title())[:20] or "Track"
    name = f"PS{index:03d}_{slug}"[:NAME_BYTES - 1]
    while name.lower() in taken:
        name = f"PS{index:03d}_{hashlib.sha1(name.encode()).hexdigest()[:8]}"
    taken.add(name.lower())
    return name


def new_sample(name: str, frames: int, channels: int, template: Sample) -> Sample:
    samples = frames * FRAME_SAMPLES
    ident = max(0, samples - int(IDENT_BEFORE_END_S * RATE))
    return Sample(name, samples, frames * FRAME_BYTES, 0, samples - 1, SAMPLE_MODE, RATE,
                  template.volume, template.pan, template.priority, channels, template.tail,
                  [(0, "SongStart"), (0, "EventStart"), (ident, "IdentStart")])


def info_entry(sample: Sample, index: int, newline: str) -> str:
    sync = dict((label, offset) for offset, label in sample.sync)
    ms = lambda samples: samples * 1000 // sample.frequency
    return (f'  <Bank Name="{sample.name}">{newline}'
            f'    <SoundBankInfo SoundBankIndex="{index}" OffsetEventStart="{ms(sync["EventStart"])}" '
            f'OffsetIdentStart="{ms(sync["IdentStart"])}" OffsetSongStart="{ms(sync["SongStart"])}" '
            f'OffsetStartNextTrack="0" FileLength="{ms(sample.length_samples)}" '
            f'SyncpointIndexIdentStart="{SYNC_NAMES.index("IdentStart")}" '
            f'SyncpointStartNextTrack="-1"/>{newline}  </Bank>{newline}')


def merge_info(text: str, entries: str) -> str:
    end = text.rfind("</SoundBanks>")
    if end < 0:
        raise ValueError("RadioSoundbankInfo_Music.xml has no </SoundBanks>")
    return text[:end] + entries + text[end:]


def merge_playlist(text: str, station: str, tracks: list[tuple[str, str, str]], replace: bool) -> str:
    """Add MusicTrack lines to a station's playlist, or replace its tracks."""
    start = re.search(rf'<RadioStation\s+name="{re.escape(station)}"', text)
    if not start:
        raise ValueError(f"RadioSystem.xml has no station {station}")
    playlist = re.compile(r'(<Playlist\b[^>]*>)(.*?)(\n[ \t]*</Playlist>)', re.S).search(text, start.end())
    if not playlist or playlist.start() > text.find("</RadioStation>", start.end()):
        raise ValueError(f"{station} has no playlist")
    lines = "".join(
        f'\n\t\t\t<MusicTrack name="{escape(title, {chr(34): "&quot;"})}" '
        f'artist="{escape(artist, {chr(34): "&quot;"})}" fmodname="{name}" '
        'likelihoodDaytime="1" likelihoodMorning="1" likelihoodEvening="1"  likelihoodNight="1" />'
        for title, artist, name in tracks)
    opening, body = playlist.group(1), playlist.group(2)
    if replace:
        body = ""
        # The picker skips the last noRepeat tracks; keep one choice open.
        opening = re.sub(r'noRepeat="\d+"', f'noRepeat="{max(0, min(15, len(tracks) - 1))}"', opening)
    else:
        body = body.rstrip()
    return text[:playlist.start()] + opening + body + lines + playlist.group(3) + text[playlist.end():]


def enable(config: Path, name: str) -> None:
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    match = re.search(r'^enabled_mods[ \t]*=[ \t]*"([^"]*)"[ \t]*$', text, re.MULTILINE)
    mods = [m for m in (match.group(1).split(",") if match else []) if m.strip()]
    if name not in mods:
        mods.append(name)
    line = f'enabled_mods = "{",".join(mods)}"'
    if match:
        text = text[:match.start()] + line + text[match.end():]
    else:
        text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8", newline="\n")


def check_bank(path: Path) -> int:
    bank, raw = read_bank(path)
    rebuilt = bank.header()
    same = rebuilt == raw
    syncs = sum(1 for s in bank.samples if [label for _, label in s.sync] == list(SYNC_NAMES))
    native, padding = 0, True
    with path.open("rb") as stream:
        for sample in bank.samples:
            stream.seek(sample.data_offset)
            data = stream.read(aligned(sample.length_bytes))
            padding &= not data[sample.length_bytes:].strip(b"\0")
            try:
                frames = mpeg_frames(data[:sample.length_bytes])
                native += len(frames) * FRAME_SAMPLES == sample.length_samples
            except ValueError:
                pass
    same &= padding
    print(f"{path.name}: {len(bank.samples)} samples, {syncs} with SongStart/EventStart/IdentStart, "
          f"{native} of {FRAME_BYTES}-byte {BITRATE} kbps frames, "
          f"{'rebuilt byte for byte' if same else 'differs'} ({len(raw)} header bytes)")
    return 0 if same else 1


def build(args: argparse.Namespace) -> int:
    stations = list(dict.fromkeys(args.station or ["Radio1"]))
    game = args.game_root / RADIO
    music = find_music(args.music)
    if not music:
        print(f"no audio files in {args.music}")
        return 1
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    ffprobe = args.ffprobe or shutil.which("ffprobe")
    if not ffmpeg:
        print("FFmpeg is needed to encode the music; install it or pass --ffmpeg")
        return 1
    bank, _ = read_bank(game / "Radio_Music.fsb")
    stereo = [s for s in bank.samples if s.channels == 2]
    template = stereo[0] if stereo else bank.samples[0]
    taken = {s.name.lower() for s in bank.samples}
    mod = args.state_root / "mods" / args.name
    radio = mod / "game" / RADIO
    if mod.exists():
        if not (mod / MARKER).exists():
            print(f"{mod} exists and was not made by this tool; choose another --name")
            return 1
        shutil.rmtree(mod)
    radio.mkdir(parents=True)
    (mod / MARKER).write_text("built by tools/build-fh1-radio.py\n", encoding="utf-8")

    added, tracks, temporary = [], [], Path(tempfile.mkdtemp(prefix="fh1-radio-", dir=mod))
    try:
        for number, source in enumerate(music, 1):
            found = tags(ffprobe, source) if ffprobe else {}
            title = found.get("title") or source.stem
            artist = found.get("artist") or ""
            data = encode(ffmpeg, source, 2)
            frames = mpeg_frames(data)
            name = sample_name(number, title, taken)
            sample = new_sample(name, len(frames), 2, template)
            (temporary / name).write_bytes(data)
            added.append(sample)
            tracks.append((title, artist, name))
            print(f"{name}: {title}{' - ' + artist if artist else ''}, "
                  f"{sample.length_samples / RATE:.0f} s")

        out = Bank(bank.version, bank.mode, bank.reserved, bank.samples + added, 0)
        with (radio / "Radio_Music.fsb").open("wb") as target:
            target.write(out.header())
            with (game / "Radio_Music.fsb").open("rb") as stock:
                stock.seek(bank.data_start)
                shutil.copyfileobj(stock, target, 1 << 22)
            for sample in added:
                data = (temporary / sample.name).read_bytes()
                target.write(data + b"\0" * (aligned(len(data)) - len(data)))
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    info = (game / "RadioSoundbankInfo_Music.xml").read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in info else "\n"
    entries = "".join(info_entry(s, len(bank.samples) + i, newline) for i, s in enumerate(added))
    (radio / "RadioSoundbankInfo_Music.xml").write_bytes(merge_info(info, entries).encode("utf-8"))
    system = (game / "RadioSystem.xml").read_bytes().decode("utf-8")
    for station in stations:
        system = merge_playlist(system, station, tracks, args.replace)
    (radio / "RadioSystem.xml").write_bytes(system.encode("utf-8"))
    listing = (game / "Radio_Music.lst").read_bytes().decode("utf-8", errors="replace")
    lst_newline = "\r\n" if "\r\n" in listing else "\n"
    listing = listing.rstrip("\r\n") + lst_newline + "".join(
        f"{s.name}.mp3, quality=0, fsound_loop_off{lst_newline}" for s in added)
    (radio / "Radio_Music.lst").write_bytes(listing.encode("utf-8"))
    (mod / "mod.toml").write_text(
        f'name = "{args.name}"\nversion = "1.0.0"\nabi = 1\n'
        f'# {len(added)} tracks {"replacing" if args.replace else "added to"} {", ".join(stations)}\n'
        'shares_save = true\n', encoding="utf-8", newline="\n")
    print(f"{len(added)} tracks {'replace' if args.replace else 'join'} the playlist of {", ".join(stations)} "
          f"in {mod}")
    if args.enable:
        enable(args.state_root / "config" / "pinyon_shift.toml", args.name)
        print(f"enabled {args.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("music", type=Path, nargs="?", help="folder of music files")
    parser.add_argument("--state-root", type=Path, help="the state directory the mod is written to")
    parser.add_argument("--station", choices=STATIONS, action="append",
                        help="station to change, repeatable (default Radio1)")
    parser.add_argument("--replace", action="store_true",
                        help="play only the folder's tracks on the station")
    parser.add_argument("--name", default="custom_radio", help="mod name (default custom_radio)")
    parser.add_argument("--enable", action="store_true", help="add the mod to enabled_mods")
    parser.add_argument("--game-root", type=Path, default=ROOT / ".local" / "game" / "base")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--check-bank", nargs="?", type=Path, const=Path(), metavar="FSB",
                        help="check that a bank's header rebuilds byte for byte")
    args = parser.parse_args()
    if args.check_bank is not None:
        return check_bank(args.check_bank if args.check_bank != Path() else
                          args.game_root / RADIO / "Radio_Music.fsb")
    if not args.music or not args.state_root:
        parser.error("a music folder and --state-root are needed")
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", args.name):
        parser.error("--name may use letters, digits, _ and -")
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
