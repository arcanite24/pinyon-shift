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
