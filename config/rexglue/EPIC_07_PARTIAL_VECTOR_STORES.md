# PPC partial vector-store semantic qualification

EPIC-07 adds generated-native-code regression coverage for `stvlx` and
`stvrx` in `0042-ppc-partial-vector-store-regression-tests.patch`. It verifies
the existing ReXGlue lowering; it does not import or change Xenia's x64 JIT
implementation.

## Evidence and scope

Xenia Canary commit `30ac9d7be69bf7d9e9cc5d92d126cc62c58b8f48`
replaced an incorrect shuffle/blend lowering after partial vector stores were
observed corrupting optimized guest memcpy heads and tails. Its semantic cases
are applicable to ReXGlue even though its emitter implementation is not.

Source: <https://github.com/xenia-canary/xenia-canary/commit/30ac9d7be69bf7d9e9cc5d92d126cc62c58b8f48>

## Coverage

The patch adds one PPC assembly fixture that ReXGlue recompiles to host C++ and
executes through `ppc_tests`:

- deterministic `stvlx` and `stvrx` offsets `0`, `1`, `4`, `8`, `12`, and
  `15`;
- byte-distinct source vectors and destination sentinels, checking every byte;
- preserved bytes outside each partial write range;
- `RA == RB` effective-address alias cases;
- unaligned-source memcpy head and tail sequences using `lvsl`, two `lvx`
  instructions, `vperm`, and the relevant partial store;
- two reference-model differential tests, each with 256 deterministic random
  source vectors, destination sentinels, and offsets.

The differential harness initializes the vector in guest byte order, computes
the expected 16-byte destination independently, executes the generated host
function, and compares the full destination block byte-for-byte. The fixed
seed `0x5EED07A1` makes every failure reproducible.

Run the focused suite and write a provenance-complete JSON report with:

```powershell
.\tools\qualify-partial-vector-store.ps1
```

The report records the project and ReXGlue revisions, ordered patch set,
generated source and executable fingerprints, compiler, configuration scope,
test counts, seed, and exact test output. Renderer and GPU fields are recorded
as not applicable because this qualification executes CPU-generated code only.

## Qualification result

The 2026-08-27 clean-stack qualification passed 20 focused generated-code
cases with 800 assertions. This comprises 18 deterministic, alias, and memcpy
fixtures plus 256 reference comparisons for each instruction. The complete PPC
suite passed 1,480 test cases and 6,549 assertions; the complete ReXGlue unit
suite passed 242 test cases and 2,262 assertions with four pre-existing
BitStream write cases skipped.

The generated function source fingerprint was
`A5E28D4699F1345374A613C6DE6C0EDB4231A5C920524F3B6277057FEF584F8C` and
the focused test executable fingerprint was
`DB3AE056533C1047F5B08EA7A035A2D8A96FAFFDAD12BFD850EEFCA8C5A1B891`.

## Mutation sensitivity

Qualification must also be repeated locally with two temporary mutations:

1. reverse the source-vector byte index in one partial-store lowering;
2. shift a destination range by one byte so a preserved sentinel is overwritten.

The focused suite must fail for both mutations. Neither mutation belongs in
the project patch. Both controls failed 10 of 20 focused cases before the
clean patch stack was rematerialized and requalified.

## Rollback

Removing patch `0042` and this qualification wrapper removes only regression
coverage and reporting. Runtime code and shipping defaults are unchanged.
