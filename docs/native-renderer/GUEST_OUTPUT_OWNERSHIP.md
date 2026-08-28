# Native guest-output ownership

NR-01A introduces the registration contract only. It does not invoke a native
renderer, expose D3D12 objects, transition resources, or alter presentation.
Xenos therefore remains the sole producer and authority for every frame.

The backend-neutral context records output/display dimensions, an opaque output
format, a submission sequence, and opaque device, command-context, and output
handles. Backend-specific code will populate those fields in NR-01B while the
public interface remains independent of D3D12 headers.

Registration is atomic. With no callback registered, invocation returns
`false`, meaning yield. A registered callback must return `false` without
recording any output command. Once it records a command that can modify output,
it must return `true`; later integration will latch failures rather than yield
after partial modification.

Patch `0046-native-guest-output-callback-contract.patch` includes native unit
tests for default inert state, claim propagation, yield propagation, and
unregistration. There is deliberately no swap-path call site in that patch.

## D3D12 ownership

Patch `0047-d3d12-native-guest-output-context.patch` invokes a registered
callback after Xenos gamma and optional FXAA have completed, while the existing
command-processor submission is still open. The guest-output texture is in the
presenter's internal state at entry. Backend operations queue transitions and
commands into that same deferred list and restore the internal state before the
presenter receives the image.

The first operation is a full-output floating-point clear. Descriptor
allocation occurs before any barrier or clear is recorded; allocation failure
therefore yields safely with Xenos still authoritative. Once the operation
records a transition, it returns success and the title callback must claim the
frame.

Pinyon's `pinyon_shift_native_renderer_diagnostic_clear` experiment defaults to
off and requires restart. When enabled it alternates two unmistakable clear
colors, records bounded frame diagnostics, and latches any unsupported context
or clear failure back to Xenos. The experiment does not skip or suppress any
guest draw or resolve—the diagnostic clear occurs after the complete Xenos
frame solely to qualify output ownership.

## NR-01B qualification

The clean `884b554` build applied all 47 ReXGlue patches and produced executable
SHA-256 `3786D55CEE60E9F5B087B58A86DA07A61975C19F1157F6EB4EEB3DB82AF953E2`.
The ReXGlue unit suite passed 2,282 assertions across 247 test cases, with the
four documented upstream `BitStream::Write` cases skipped.

AppData-backed control session `20260828T011525Z-p33512` ran with the experiment
disabled, remained responsive, emitted no native-output or error events, and
exited normally. Enabled session `20260828T011624Z-p41092` then claimed 4,500 of
4,500 observed callbacks. The bounded markers reported a 2560 by 1440 guest
output, a 1280 by 720 display, and format identifier 24. Visual inspection
confirmed alternating full-frame orange/red and blue phases. The session
recorded no callback failure, device removal, TDR, validation error, or
resource-state warning and exited normally. Presentation cadence remained
60.003 Hz and simulation cadence 29.793 Hz; the two sessions exercised
different scene durations and therefore are not treated as a performance A/B.

## Diagnostic triangle and recovery

Patch `0049-native-guest-output-diagnostic-triangle.patch` adds one more
backend-neutral context operation. Its D3D12 implementation lazily creates a
small compute pipeline, obtains the output UAV descriptor before recording any
barrier, dispatches into the command processor's deferred list, and restores
the presenter-owned internal state. Pipeline or descriptor failure therefore
yields before output is touched; a failure after registration is latched and
all later frames yield to Xenos.

The `pinyon_shift_native_renderer` setting accepts `xenos`,
`diagnostic_clear`, or `diagnostic_triangle`; only the safe `xenos` default and
the triangle qualification mode are exposed in the launcher. The graphics
panel backs up every change and provides a dedicated **Reset to Xenos** action
that changes no unrelated setting. Sanitized crash reports record the
configured mode, last effective mode, bounded claimed-frame count, and any
fallback reason.

## NR-01C/D qualification

The clean post-rebase build applied all 49 ReXGlue patches and produced
executable SHA-256
`5FD5D2511075B3FF4200F82A99B1A62069F7E08523F374D5159183D5A2D34DD7`.
All 61 repository tests passed, tracked Markdown links were valid, and the
ReXGlue unit suite passed 2,282 assertions across 247 test cases with the four
documented upstream `BitStream::Write` cases skipped.

AppData-backed control session `20260828T015455Z-p33796` ran with `xenos`
selected. It recorded Xenos as the sole output authority, registered no native
callback, claimed no frame, emitted no renderer failure, and exited normally.

Diagnostic session `20260828T015607Z-p29900` claimed 2,100 of 2,100 observed
callbacks. Its final marker reported a 2560 by 1440 guest output, a 1280 by 720
display, and format identifier 24. Visual inspection confirmed a centered
full-frame color triangle whose phase changed during sustained presentation.
The session recorded no callback failure, device removal, TDR, validation
error, resource-state warning, or presentation deadline miss and exited
normally. Presentation cadence was 60.002 Hz and simulation cadence was
29.409 Hz.

Unsupported-mode recovery session `20260828T015729Z-p11548` emitted exactly
one `unsupported_mode` failure with `fallback=xenos`, registered no native
callback, claimed no frame, visibly continued through the normal Xenos-rendered
Microsoft Studios sequence, and exited normally. The launcher recovery command
also created a timestamped configuration backup and reset only
`pinyon_shift_native_renderer` to `xenos`; all unrelated graphics settings and
the AppData save remained unchanged.

## Retained authentic-pass preview

Patch `0065-d3d12-retained-pass-preview.patch` adds the first display path for
authentic native replay pixels. The explicit `diagnostic_retained_pass` mode
samples the already-qualified top-left 512 by 512 crop of the retained NR-02F
RGBA16F target and scales it into the guest-output texture with an amber border.
This is the same private target produced by the indexed anchor and AutoIndex
follower, not a synthetic triangle or CPU-uploaded screenshot.

The backend accepts only the measured multisampled
`DXGI_FORMAT_R16G16B16A16_FLOAT` target. It resolves that private target into a
persistent single-sample texture, transitions the resolved texture to a compute
SRV, dispatches in the command processor's open submission, and restores the
source, resolved target, and presenter-owned guest-output states. Until an exact
retained target exists, the callback returns `false`, records paced waiting
diagnostics, and leaves the complete Xenos frame visible. The mode is
default-off, restart-required, and exposed as a developer preview in the
launcher. It does not suppress any original draw, resolve, query, or
guest-visible side effect.

## Retained-pass preview qualification

Clean-build AppData-backed session `20260828T205347Z-p35488` first displayed
the complete Xenos frame while waiting for the qualified anchor/follower pair,
then switched to the amber-framed native crop after frame 2,656. Visual
inspection confirmed authentic scene sky, clouds, barriers, Horizon banners,
and ground geometry in the retained target. A second capture ten seconds later
remained stable and showed the continuously refreshed pass rather than a
synthetic or CPU-uploaded image.

The session recorded the isolated two-draw pass, seven paced native-output
markers, zero native-output failures, zero device-loss/fatal/error markers, and
a normal shutdown. Its 4,689 measured frames had 31.033 median FPS, 19.161
one-percent-low FPS, 59.991 Hz host presentation cadence, and zero presentation
deadline misses. Every original Xenos draw remained enabled and suppression
remained disabled for the entire qualification.

NR-04A subsequently tightens this preview with the exact-frame publication
contract documented in `FRAME_PUBLICATION.md`. A retained pass may now reach
guest output only when it was reproduced in the same guest frame as the active
swap; stale targets yield immediately to Xenos.
