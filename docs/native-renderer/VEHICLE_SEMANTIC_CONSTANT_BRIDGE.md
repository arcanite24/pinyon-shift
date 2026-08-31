# Vehicle semantic constant bridge

Status: private draw-atomic bridge qualified; native publication remains off.

## Purpose

The retained 30-family vehicle pass already proves stable animated geometry
and replay. This bridge gives each correlated color draw a current-draw vertex
constant snapshot without guessing a title-side constant-buffer owner. It is
an implementation boundary for later player identity, transform, wheel, and
material work, not a claim that every register has semantic provenance.

## Runtime contract

- ReXGlue records compact final-write state for the 512 float-constant
  registers inside the command processor.
- Draw preparation compares that state with the exact shader-used register
  values and records validity, split provenance, maximum age, and a component
  mismatch mask.
- A matched vehicle family copies its bounded prepared constant observation to
  one private in-memory bridge slot for the current frame and draw.
- The slot records register-layout and value hashes plus exact/unresolved
  vector counts. Constant payloads never enter the public log or report.
- Missing, overflowing, or uncorrelated draws are rejected. Xenos remains the
  only output authority; no native draw, publication, or suppression follows
  from this bridge.

## Qualification

The saved-profile run `20260831T203519Z-p39592` exited normally and produced:

- 484 committed shadow epochs and 14,505 exact vehicle color correlations;
- all 30 bounded vehicle families and 68 unique geometry seeds;
- 14,505 bridge publications and zero bridge rejections;
- a stable 16-register layout in every family with zero layout variations;
- 217,575 exact vectors, zero missing vectors, zero split vectors, and a
  maximum final-write age of zero frames; and
- one unresolved vector per draw, always register 254 with mismatch mask `F`
  and zero mask variations.

Register 254 is therefore isolated as a special-register update outside the
ordinary command-processor write route. It remains available as an opaque
current-draw value in the private snapshot, but it is not packet-proven and
must not receive transform or player semantics without independent evidence.

## Next admission boundary

The bridge may feed only private retained-vehicle work until exact player
identity and mesh/material role joins are established. A later visible path
must retain per-item Xenos fallback, reject stale or incomplete snapshots, and
keep register 254 outside any provenance-dependent decision.
