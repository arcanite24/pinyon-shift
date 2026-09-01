# Static-world prepared layout boundary

Status: complete bounded vertex/material snapshot implementation; batched
runtime qualification remains pending

## Purpose

The title's `CSimpleMesh` object proves primitive, index-buffer, and selected
material ownership, but the complete vertex layout is shader-derived and only
exists after Xenos decodes the draw state. This checkpoint joins those two
surfaces without guessing a second title-side layout.

## Exact boundary

The static SimpleModel path binds the mesh index buffer, flushes draw state
through `8240BB40`, and then calls indexed-draw emitter `82416380`. The existing
physical-PM4 provenance join identifies the exact prepared draw produced by
that mesh. At that point the observer has bounded metadata for:

- up to 8 vertex bindings, including fetch constant, address, size, stride,
  and endianness;
- up to 32 shader-derived vertex attributes with complete fetch and result
  descriptors;
- up to 64 float constants per shader stage, plus bool and loop constants;
- up to 16 decoded texture states; and
- shader, pipeline, geometry-layout, texture-layout, and render-state hashes.

The implementation retains at most 512 distinct static-world layout families.
Each family records one complete bounded metadata sample, call/frame coverage,
and dynamic parameter-hash variation. Resource payload bytes are never copied
or exported.

## Fail-closed runtime gate

Every prepared static-world match must classify as exactly one of bounded,
unbounded geometry, or parameter overflow. Qualification requires all matches
to be bounded, at least one retained layout family, and zero table overflow.
Independent counters are emitted in the static-world runtime summary.

This is observation only. Xenos remains authoritative; native admission and
draw suppression remain disabled until the combined C1/C2 AppData run proves
the boundary in representative gameplay.
