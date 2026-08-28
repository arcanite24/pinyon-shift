# Native resource cache budgets

NR-03I adds finite admission and maintenance policies to the backend-neutral
buffer and texture caches. The policy is independent of D3D12 and Vulkan and
does not render, suppress, or replace any Xenos work.

## Contract

Every cache policy defines:

- a maximum live byte count;
- a maximum live resource count;
- a maximum remembered-state count;
- a maximum eviction batch;
- a long normal-operation idle guard; and
- a shorter explicit-pressure idle guard.

An admission that would exceed the byte or count limit first retires the
least-recently-used eligible resources, up to one eviction batch. If recent
resources still occupy the budget, the new resource is refused. Texture
refusal keeps the previous complete generation or the neutral fallback and
becomes retryable after the pressure guard; it never silently installs an
over-budget allocation.

Retirement and destruction remain separate. Evicted resources leave lookup
immediately, but their opaque backend handles are returned by `Collect` only
after the final recorded submission completes. Live and retired bytes are
reported separately so fence lag remains visible.

Idle maintenance is also bounded to one batch. Normal maintenance uses the
long guard, while an explicit memory-pressure call uses the shorter guard.
Empty texture decode states are pruned with the same bounded policy, preventing
streaming churn and permanent failures from growing remembered state without
limit.

## Current diagnostic integration

The default-off D3D12 texture bridge configures a 128 MiB live texture budget,
2,048 live resources, 4,096 remembered states, and 16 evictions per pass. It
performs normal maintenance with a 1,200-submission idle guard and uses a
120-submission guard when admission is under pressure. Runtime cache age is
measured from the command processor's submission sequence rather than the much
faster texture-observer call count.

Periodic and shutdown diagnostics report live and retired bytes, budget
evictions and refusals, remembered-state count, and state evictions. Xenos
continues to own every draw, resolve, and presented frame.

## Validation

Native semantic tests cover:

- strict byte and count admission;
- deterministic least-recently-used selection;
- one-batch amortized eviction;
- distinct normal and pressure idle guards;
- retryable texture budget refusal;
- remembered-state pruning; and
- fence-safe collection after budget retirement.

Runtime qualification must confirm bounded live/state telemetry, zero retained
references at shutdown, no device loss or renderer failure, and unchanged
Xenos presentation.

The AppData-backed qualification session `20260828T230532Z-p40180` ran for
179.274 seconds with 5,681 samples. It held two live texture resources at
131,072 bytes, recorded 32,148 cache hits and two misses, and reported zero
cache-budget evictions, refusals, state evictions, and retired bytes. Shutdown
released every live resource and retained reference with no renderer failure,
fatal event, crash, or device loss. Median performance was 30.211 FPS, host
presentation remained at 59.986 Hz, and no present deadline was missed.
