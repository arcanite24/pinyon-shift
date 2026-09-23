# Gate A combined same-frame capture — 2026-09-23

An AppData-backed sustained-race replay published the selected shared-track,
procedural-item and procedural-vegetation geometry from title source frame
5000 and consumed all three at output frame 5001. It exited normally with
eight 1280×720 compatibility screenshots. The strict frame-wide census passed
for all 2,979 backend draws, and the fail-closed Gate A partition assigned
1,670 to the required diagnostic slice, 67 to retained effects and 1,242 to
other targets. There were no unattributed draws. The three owned fixtures
cover **1,229/1,670** selected draws by exact packet and final draw sequence:

| Required family | Selected draws | Same-frame owned fixture |
| --- | ---: | --- |
| Shared track/procedural scene lists | 782 | 782/782; 91 title targets, 94 vertex ranges, 236 index ranges |
| Procedural item/node packets | 312 | 312/312; 174 title calls, 518,400 unique vertex bytes |
| Procedural vegetation | 135 | 135/135; 67 title items, 376,272 unique vertex bytes |
| Car scene lists | 292 | None |
| Character-manager direct records | 102 | None |
| Procedural characters | 18 | None |
| Animated-scene scalar packets | 20 | None |
| Car-presentation scalar packets | 9 | None |

The partition now identifies procedural characters by the title draw target
`0x8245AB88` and vegetation by `0x824136F0`, both within the same second-path
caller. An earlier bound-record-only rule mislabeled procedural characters
as vegetation. Five strict ledgers pass the corrected rule without changing
their total selected/retained/outside counts. In this replay, all 135 true
vegetation draws have successful vertex snapshots and match the vegetation
fixture's 135 ordered final variants.

The first combined attempt had 70 vegetation items and 155 matching prepared
draws, but rejected the owned vegetation scene after 52 later stride-4 fetches
hit snapshot status 4 (budget exceeded). The SDK used one byte counter for
both item and vegetation snapshots, yet applied vegetation's 2 MiB ceiling
to their combined copies. Item and vegetation now have independent per-frame
counters, preserving their existing 8 MiB and 2 MiB ceilings. The second
combined attempt had zero status-4 stride-4 fetches, published its `SNR03F3`
fixture, and passed the independent fixture verifier. Three unrelated
oversized stride-4 fetches still have status 3 and are outside the selected
vegetation family.

Each fixture also rendered through its existing private 1280×720 diagnostic:
track 880,042 covered pixels from 782 draws, procedural items 63,380 pixels
from 312 draws, and vegetation 395,009 pixels from 135 draws. A second run of
each produced byte-identical identity and depth files. These are **three
separate depth targets**, not a composed scene or three disjoint pixel sets;
the pixel counts must not be added. Track still uses an identity pixel shader
and omits stencil/material alpha; procedural items omit material alpha; the
vegetation diagnostic is unmasked and one-sample. There is no full-slice
coverage, exact material/lifetime admission, or compatibility parity yet.

Reproduce the independent checks from the local capture:

```powershell
$base = '.local/native-renderer/snr04'
python tools/summarize-snr01-frame-wide-census.py "$base/combined-scene-live-b-filtered.log" --source-frame 5000 --require-candidate-boundary --output "$base/combined-scene-live-b-ledger.json"
python tools/partition-snr00-gate-a-slice.py "$base/combined-scene-live-b-ledger.json"
python tools/verify-snr02-track-geometry.py "$base/combined-scene-live-b-filtered.log" "$base/combined-scene-live-b-ledger.json" "$base/combined-scene-live-b/snr02-track-5000.bin"
python tools/verify-snr02-item-scene.py "$base/combined-scene-live-b/snr02-items-5000.bin" "$base/combined-scene-live-b-filtered.log" "$base/combined-scene-live-b-ledger.json"
python tools/verify-snr03-vegetation-publication.py "$base/combined-scene-live-b-filtered.log" "$base/combined-scene-live-b-ledger.json" --source-frame 5000
python tools/verify-snr03-scene-fixture.py "$base/combined-scene-live-b/snr03-scene-5000.bin" "$base/combined-scene-live-b-full-evidence.log"
```

The full-evidence log includes `FH1 scene binding` rows required by the
vegetation fixture verifier; the smaller filtered log contains the title,
GPU and clear-producer rows required by the census and other verifiers.

| Evidence | SHA-256 |
| --- | --- |
| `combined-scene-live-b-filtered.log` | `8052151180FA02862D083935C2AD0998BF9BB6F9B74F44C02FD087EC08D8B0D0` |
| `combined-scene-live-b-ledger.json` | `88439C3680AEC3437140DED2E60B4C96AF36253FEEBBC566CAA0A0B306F2F474` |
| `combined-scene-live-b/snr02-track-5000.bin` | `0C644C113A41648AF2BCF9B644CE077F9C22EE34AEDD2EB6E6623890096BE1A9` |
| `combined-scene-live-b/snr02-items-5000.bin` | `9B6C3BA04A379CFF8C7BC384882FB651BBD748F833B9082B7FCCA0BEBCAF6210` |
| `combined-scene-live-b/snr03-scene-5000.bin` | `47D9A40C61E7027D4B358B51E4CF31ECB0E2A390852B5EA7248ADD16DAAF2ADC` |
| `combined-scene-live-b/track-source-5000.ppm` | `A5E1F63FB33F8CC970B1A4C5CEB15AD5E3F6E0842A624F85CE1F07013F20A3E4` |
| Track private identity/depth | `89D941504B5078E790657A197B5663BB75D0DFF6A96D3EC61FCD05D8CF07B38E` / `FE9F82E803D1B6919F153D4808E80AE1ACCC95B6BED4F7ECC19829B7D6646C94` |
| Item private identity/depth | `DD44EC5694934EFAAC281D4F8F9684594A8B318B3A170E5385F274CD478BA73A` / `3709D221F25F1D1DF47B28839346C65C43956F90E1CFD2D52C4C0A0C6399F9C6` |
| Vegetation private identity/depth | `E4372985A1C0EE4F6947567619B7C59F80F6AA4C80FBBD174DEE798A8C209896` / `44A99B3EB03241AD171BAD0E36947175E7B961173525398F7C890DB2DEEA52BB` |

The next capture format must support the uncovered selected families,
especially car scene lists: this frame has 292 such draws, and another strict
frame had 702 across 63 vertex shader hashes, with one or three vertex streams
and 16- or 32-bit indices. The track fixture's single-stream, 16-bit-strip
assumptions cannot be reused unchanged. Gate A remains open.

## Complete same-frame fixture coverage

A later source-frame-5000/output-frame-5001 replay published all six fixture
families in one run. Its strict frame-wide census attributed all 3,888 draws
with zero unknown owners. `verify-snr04-complete-slice.py` reruns each family's
independent fixture/log/ledger verifier and checks that their role counts
partition all **2,192/2,192** selected draws:

| Owned fixture family | Draws | Separate private identity pixels |
| --- | ---: | ---: |
| Shared track | 699 | 659,995 |
| Procedural items | 171 | 35,879 |
| Vegetation | 125 | 59,781 |
| Procedural characters | 11 | 24,884 |
| Character manager | 306 | 14,957 |
| Car scene-list, animated and presentation remainder | 880 | 136,308 |

All six private diagnostics consumed their fixtures from that same source
frame. These are six separate depth targets. The pixel counts overlap and
cannot be summed into a scene image or used to claim exact occlusion. A
[later staged diagnostic](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md)
executes all 2,192 draws in global sequence with logically carried private
color/depth. Exact material roles and resource generations remain separate
SNR-02 work.

```powershell
$base = '.local/native-renderer/snr04'
python tools/verify-snr04-complete-slice.py "$base/remainder-index-live-b" "$base/remainder-index-live-b-evidence.log" "$base/remainder-index-live-b-ledger.json"
```

| Same-frame evidence | SHA-256 |
| --- | --- |
| `remainder-index-live-b-evidence.log` | `5A690FD3F582B85F3FB8947C2BE4399730DCDA7934461D03D597E59296309054` |
| `remainder-index-live-b-ledger.json` | `7538696389C2E4A4696370FD7515EFA141506BA0B142A9A9F2C1BC5CFD878D5E` |
| Track / items / vegetation fixtures | `68BCBE03CD49875AE842217969A0D4BFA0D1993EE649F936E39E05B671DA6A23` / `045485A19258A0CACDA4CE3C5C8BC126A89E06798AD44104DA5CD9921AEE7125` / `D1C3D98D3DD037CC1970101A861D22D2F161383688373ACF53B1AF553985FCFD` |
| Procedural characters / manager / remainder fixtures | `67B31765B68D6A7F58AE44F2240EA64F5F9A894C4D6F0075A024AA7E6335C18A` / `A62CE36CC359E120AC4A96BBC19A2599E7164B72F8641967C21509E968104854` / `21896007841BEB6B028A7134D681ACDA13BE7122B9CF2374077F60B76795F8DA` |
