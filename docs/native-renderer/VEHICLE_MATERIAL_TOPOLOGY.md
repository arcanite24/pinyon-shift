# Vehicle material topology census

Status: qualified as payload-free metadata in the default-off C4 correlation
mode. The mechanical topology is closed; semantic material labels remain open.

## Boundary

The coherent retained target proves multi-submesh geometry, but its flat
diagnostic output does not identify body paint, glazing, wheels, lights,
livery, or exceptional materials. Before adding semantic material handlers,
the 30 exact vehicle color families need a topology that is independent of
their geometry resources and animated vertex parameters.

Each family now records a material-topology key derived from:

- vertex and pixel shader identity and specialization;
- prepared render state and render-target contract; and
- texture fetch and texture-layout state.

Geometry resources, draw arguments, and raw constant values are excluded from
the topology key. A separate hash tracks pixel-float parameter changes over
time without retaining or exporting their values. The report groups all exact
families by the topology key and counts which families vary their material
parameters.

## Interpretation

The topology answers how many mechanically distinct shader/material contracts
the retained vehicle uses and which exact geometry families share each one. It
does not assign semantic names from hashes. Visual contribution evidence or a
typed title material edge is still required before labeling a group as paint,
glass, wheel, light, livery, or another vehicle material.

The v8 offline qualifier requires the group count to reconcile exactly with
the 30 candidate-family records. Any shader, render-state, texture-layout, or
accounting drift fails the report. The topology cannot enable native
publication or suppression.

## Safety

- The mode remains restart-gated and default-off.
- No constant payload, texture payload, or game asset is written to the log.
- Every original Xenos draw executes unchanged.
- The output is metadata only and cannot establish player identity, complete
  material coverage, or native admission.

## AppData qualification result

The clean combined C4 session reconciled all 30 exact families into one
mechanical material-topology group. All 30 families changed their hashed pixel
parameters over the session, while the shared shader specialization, prepared
render state, and texture layout remained stable. The report passed exact
family/group accounting without exporting material values or assets.

The single group means shader/topology hashes cannot separate body, glass,
wheels, lights, or livery. Those distinctions are parameter- or title-semantic
driven inside the shared mechanical contract. The next material slice should
join the bounded families to the typed title material/upload edge and use
visual contribution evidence for labels; it should not invent semantics from
the common topology key.
