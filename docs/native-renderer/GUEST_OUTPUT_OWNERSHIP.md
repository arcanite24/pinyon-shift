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
unregistration. There is deliberately no swap-path call site in this patch.
