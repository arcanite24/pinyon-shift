---
title: Audio and radio
section: Reverse engineering
order: 12
description: Forza Horizon's FMOD Ex audio: the audio manager and its cues, the 5.1 mixer, its codecs and its output path, speech and ambience banks, the radio's single MP3 music bank, its station list and playlists, and why the selectable stations are fixed in code.
---

# Audio and radio

All of the game's sound goes through **FMOD Ex**: event projects (`.fev`) name cues, and 984 sound banks (`.fsb`) under `media/audio` hold the samples. One audio manager object owns the FMOD system, and simulation code reaches it through `CAudioManagerDeferred` commands ([The executable](game-executable.md#classes)). FMOD mixes in 5.1 on its own mixer thread and hands float blocks to XAudio2, which passes them to the console's audio output. XMA is the compressed format of 975 of the 984 banks, decoded on the way in through the console's XMA hardware.

The radio is simpler than it looks. All its music is one 680 MB bank of plain MP3 samples, `Radio_Music.fsb`, and an XML file lists the stations and which samples each may play. That is why custom stations are possible as data mods ([Modding](modding.md#custom-radio-stations)), while adding a fourth selectable station is not: the station names and their icons are in the executable.

An FSB4 bank's header lists its samples, and each radio sample carries three named sync points. This reads them without decoding any audio:

```python
import struct


def fsb4_samples(path):
    """(name, length in samples, frequency, sync points) for each sample of an FSB4 bank."""
    with open(path, "rb") as bank:
        magic, count, header_size = struct.unpack("<4sII", bank.read(48)[:12])
        assert magic == b"FSB4"
        headers = bank.read(header_size)  # sample headers; the audio data follows
    offset = 0
    for _ in range(count):
        size = struct.unpack_from("<H", headers, offset)[0]
        name = headers[offset + 2:offset + 32].split(b"\0")[0].decode("ascii")
        length, _, _, _, _, frequency = struct.unpack_from("<IIIIIi", headers, offset + 32)
        sync = []
        if headers[offset + 80:offset + 84] == b"SYNC":   # named markers, 260 bytes each
            for k in range(struct.unpack_from("<I", headers, offset + 84)[0]):
                entry = offset + 88 + 260 * k
                label = headers[entry + 4:entry + 260].split(b"\0")[0].decode("ascii")
                sync.append((label, struct.unpack_from("<I", headers, entry)[0]))
        yield name, length, frequency, sync
        offset += size
```

On `Radio_Music.fsb` it yields 127 samples, each with `SongStart`, `EventStart` and `IdentStart` markers. Unlike the game's archives, FSB4 headers are little-endian. `tools/build-fh1-radio.py --check-bank` parses the whole bank and rebuilds its header byte for byte.

## Audio engine

Most banks are XMA, which FMOD's XMA codec decodes through the console's XMA registers by way of nine small XDK helper routines. In the recompiled game those register writes never fault: the generator recognises the register window when the address is built and emits each store as a direct call into the runtime's decoder, about 115 calls a frame. The decoder's register handler used to decode each kicked context on the FMOD mixer thread itself; the SDK cvar `xma_decode_kicks_inline=false` leaves that to the decoder thread, which measured 15 % fewer mixer-thread cycles on the desktop and 21 % fewer instructions on the Odin with no stall or queue change ([research record](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/NEXT_LEVEL_RESEARCH.md), NL-4.1). A 40 s capture of the Odin race in each mode, with every frame's submit time, found no dropout in either (no gap between frames over 17 ms, no sudden level drop, no XMA stall), but the decoder thread takes back most of the saving: about 0.1 ms a frame net. Played on the Odin in worker mode it sounded right, so worker decoding has been the default since 2026-10-13 ([near-native record](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/NEAR_NATIVE_RESEARCH.md#progress), NL-4.1).

{{findings:audio/Audio engine}}

## Mixer and output

FMOD mixes on its own thread, one 256-sample block every 5.33 ms, and it mixes in 5.1: the title never changes FMOD's default speaker mode. Every sample in the banks is mono or stereo, so the six channels come only from the mix buses, and the effect units spend nearly all their time in their six-channel loops before the host folds the result to stereo. On Android and Linux (the Steam Deck) Pinyon Shift now sets FMOD to stereo before it starts (`pinyon_shift_fmod_stereo`), which cut the mixer's instructions by 45 % and its CPU by about 1 ms a frame on the Odin; Windows and macOS keep the 5.1 mix for surround speakers. Each block takes this path (threads on the left, CPU a frame on the Odin at 60 fps from the [research record](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/NEAR_NATIVE_RESEARCH.md#where-the-overhead-is)):

```text
CAudioThread, once a frame (2.39 ms*)   game sound logic, FMOD Event System
FMOD mixer thread (4.46 ms)             XMA or MPEG codec > resampler > 5.1 DSP graph > float source voice
XAudio2 pass thread (0.59 ms)           source voice > six-channel master
host Audio Worker (0.32 ms)             render-driver callback > XAudioSubmitRenderDriverFrame
host SDL output                         1,536 floats a block, folded to stereo on Android
```

\* Before the audio update gate: at 60 fps the game's audio updates now run at the console's 30 Hz, which takes 0.44-0.63 ms off this thread on the Odin ([Runtime](runtime.md)).

{{findings:audio/Mixer and output}}

## Speech and ambience banks

{{findings:audio/Speech and ambience banks}}

## Radio banks and playlists

{{findings:audio/Radio banks and playlists}}

## Radio presentation

{{findings:audio/Radio presentation}}
