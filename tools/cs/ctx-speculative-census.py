"""Issue #1070 item 3: speculative indirect-call contracts for the ctx census.

Analysis only. ctx-exact-census.py keeps the read-everything contract at
every unresolved indirect call, and the continuation demand of those calls
reaches every dispatch-table entry, so every function's return demand is
ALL. A speculative recompiler would instead guard each indirect site with
the targets a probe build observed and send a guard miss (or an unobserved
site) to a conservative clone. This script models that design:

- an observed site calls one of its observed targets (a synthetic dispatch
  function with one branch per target);
- an unobserved site, or a guard miss, calls an opaque fallback that reads
  and writes everything but does not feed return demand into the fast
  bodies (the fallback runs conservative clones);
- functions the probe saw entered with no guest caller (host entries,
  thread starts, native callbacks) keep ALL return demand.

The Odin instruction profile and matched library that Round 3 weighted its
census with are no longer on disk, so this reports a source-level proxy:
ctx slot writes that no later path demands (dead publications), weighted by
the probe's function entry counts, for the conservative and the speculative
contracts. Their ratio scales Round 3's measured 0.903 % net result. Lines
are counted once per entry regardless of branches; both modes share that
error.

    python tools/cs/ctx-speculative-census.py --generated .local/generated/default \\
        --replaced .local/leads/cs/replaced-base.txt \\
        --probe .local/re/probe/race-summary.json --output .local/leads/cs-spec.json
"""
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import re
import sys

spec = importlib.util.spec_from_file_location('ctx_exact', Path(__file__).with_name('ctx-exact-census.py'))
ce = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ce
spec.loader.exec_module(ce)
s = ce.s

CURRENT = [None]
BaseBlock = s.Block


class LineBlock(BaseBlock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lines = []
        CURRENT[0] = self


s.Block = LineBlock
base_effects = ce.effects


def recording_effects(line):
    result = base_effects(line)
    if CURRENT[0] is not None:
        CURRENT[0].lines.append(result)
    return result


ce.effects = recording_effects


def parse_functions(generated, replaced, mappings, observed):
    """Parse every body; rewrite indirect calls by their probe site."""
    fs = {}; sites = Counter(); dispatch = {}
    for p in sorted(generated.glob('*_recomp.*.cpp')):
        for m in re.finditer(r'^DEFINE_REX_FUNC\((\w+)\) \{\n(.*?)^\}', p.read_text(), re.M | re.S):
            if m[1].startswith('ref_'):
                continue
            body = m[2]
            # Tag each unresolved indirect call with its call-site address
            # (lr - 4), so the parsed block's '?indirect' can be replaced.
            order = []
            lr = None
            for line in body.splitlines():
                hit = re.search(r'ctx\.lr = 0x([\dA-Fa-f]+);', line)
                if hit:
                    lr = int(hit[1], 16)
                if 'REX_CALL_INDIRECT_FUNC(' in line:
                    order.append(lr - 4 if lr else None); lr = None
            f = ce.parse(body, mappings, sites)
            it = iter(order)
            for b in f.blocks:
                calls = []
                for c in b.calls:
                    if c == '?indirect':
                        site = next(it, None)
                        targets = observed.get(site) if site is not None else None
                        names = sorted({mappings[t] for t in targets or () if t in mappings})
                        if names:
                            key = f'?spec_{site:08X}'
                            dispatch[key] = names
                            calls.append(key); sites['spec_observed'] += 1
                        else:
                            calls.append('?fallback'); sites['spec_fallback'] += 1
                    else:
                        calls.append(c)
                b.calls = [ce.canonical(c, replaced) for c in calls]
            if m[1] in replaced:
                fs['__imp__' + m[1]] = f
                fs[m[1]] = s.Function([s.Block(read=s.ALL, write=s.ALL)], 0, 0, 0, 0)
            else:
                fs[m[1]] = f
    for key, names in dispatch.items():
        blocks = [s.Block()]
        blocks[0].successors = list(range(1, len(names) + 1))
        for n in names:
            b = s.Block(); b.calls = [ce.canonical(n, replaced)]; b.successors = []
            blocks.append(b)
        fs[key] = s.Function(blocks, 0, 0, 0, 0)
    return fs, sites


def dead_writes(fs, summaries, weights):
    """Entry-weighted count of slot writes no later path demands."""
    dead = total = lines = 0
    for name, f in fs.items():
        w = weights.get(name, 0)
        if not w or not hasattr(f.blocks[0], 'lines'):
            continue
        live = ce.liveness(f, summaries, summaries[name]['returned'])
        for i, b in enumerate(f.blocks):
            tail = summaries[name]['returned'] if not b.successors else 0
            for j in b.successors:
                tail |= live[j]
            for target in reversed(b.calls):
                c = summaries.get(target, ce.UNKNOWN)
                tail = c['reads'] | (tail & ~c['must'])
            if b.read == s.ALL and b.write == s.ALL:
                tail = s.ALL
            for read, write, kill in reversed(getattr(b, 'lines', [])):
                lines += w
                if write:
                    total += w
                    if not (write & tail):
                        dead += w
                tail = read | (tail & ~kill)
    return dict(dead_writes=dead, slot_writes=total, lines=lines,
                **redundant_reads(fs, summaries, weights))


def redundant_reads(fs, summaries, weights):
    """Entry-weighted slot reads whose value every path already holds.

    Forward must-availability: a read or write makes a slot available, a
    call drops what the callee may write, joins intersect. Only these reads
    can come from a host register instead of ctx.
    """
    redundant = reads = 0
    for name, f in fs.items():
        w = weights.get(name, 0)
        if not w or not hasattr(f.blocks[0], 'lines'):
            continue
        n = len(f.blocks)
        preds = [[] for _ in range(n)]
        for i, b in enumerate(f.blocks):
            for j in b.successors:
                preds[j].append(i)
        out = [s.ALL] * n

        def transfer(i, avail, count=False):
            nonlocal redundant, reads
            b = f.blocks[i]
            if b.read == s.ALL and b.write == s.ALL:
                return 0
            for read, write, kill in getattr(b, 'lines', []):
                if count and read:
                    reads += w
                    if read & avail == read:
                        redundant += w
                avail |= read | kill
            for target in b.calls:
                avail &= ~summaries.get(target, ce.UNKNOWN)['writes']
            return avail

        changed = True
        while changed:
            changed = False
            for i in range(n):
                avail = 0 if i == 0 or not preds[i] else s.ALL
                for p in preds[i]:
                    avail &= out[p]
                new = transfer(i, avail)
                if new != out[i]:
                    out[i] = new; changed = True
        for i in range(n):
            avail = 0 if i == 0 or not preds[i] else s.ALL
            for p in preds[i]:
                avail &= out[p]
            transfer(i, avail, True)
    return dict(redundant_reads=redundant, slot_reads=reads)


def run(a):
    init = (a.generated / 'pinyon_shift_init.cpp').read_text()
    mappings = {int(x, 16): n for x, n in re.findall(r'\{ 0x([\dA-Fa-f]+), (\w+) \}', init)}
    if a.replaced:
        replaced = set(a.replaced.read_text().split())
    else:
        syms = ce.symbols(a.binary)
        replaced = {n for n in syms if not n.startswith('__imp__') and
                    '__imp__' + n in syms and syms[n][0] != syms['__imp__' + n][0]}
    probe = json.loads(a.probe.read_text())
    observed = {int(site, 16): {int(t, 16) for t in targets}
                for site, targets in probe['indirect'].items()}
    calls = {int(x, 16): n for x, n in probe['calls'].items()}
    weights = {}
    for address, name in mappings.items():
        n = calls.get(address, 0)
        weights[name] = n; weights['__imp__' + name] = n
    contracts = ce.native_contracts()

    def add_native(fs):
        for name, c in contracts.items():
            if name not in fs:
                fs[name] = s.Function([s.Block(read=c['reads'], write=c['writes'], kill=c['must'])], 0, 0, 0, 0)

    results = {}
    # Conservative: Round 3's contracts (every indirect call reads all,
    # its continuation reaches every dispatch entry).
    fs, sites = ce_parse_conservative(a.generated, replaced, mappings)
    add_native(fs)
    callbacks = {'__imp__' + n for n in replaced if '__imp__' + n in fs}
    summaries, meta = ce.solve(fs, set(mappings.values()), callbacks)
    results['conservative'] = dict(dead_writes(fs, summaries, weights), **meta,
                                   returned_all=sum(v['returned'] == s.ALL for v in summaries.values()))
    # Speculative: observed targets, fallback without broad return demand.
    fs, sites = parse_functions(a.generated, replaced, mappings, observed)
    add_native(fs)
    guest_callers = defaultdict(int)
    for name, f in fs.items():
        for b in f.blocks:
            for c in b.calls:
                guest_callers[c] += 1
    host_entries = {n for n in fs if weights.get(n) and not guest_callers.get(n)}
    summaries, meta = ce.solve(fs, set(), callbacks | host_entries)
    results['speculative'] = dict(dead_writes(fs, summaries, weights), **meta,
                                  host_entries=len(host_entries),
                                  returned_all=sum(v['returned'] == s.ALL for k, v in summaries.items()
                                                   if not k.startswith('?')),
                                  sites={k: v for k, v in sites.items() if k.startswith(('spec', 'indirect'))})
    c, p = results['conservative'], results['speculative']
    ratio = p['dead_writes'] / c['dead_writes'] if c['dead_writes'] else None
    results['dead_write_ratio'] = ratio
    results['round3_net_percent'] = 0.903
    results['scaled_estimate_percent'] = 0.903 * ratio if ratio else None
    for mode in ('conservative', 'speculative'):
        r = results[mode]
        r['dead_share_of_lines_percent'] = 100 * r['dead_writes'] / r['lines'] if r['lines'] else None
        r['removable_share_of_lines_percent'] = (100 * (r['dead_writes'] + r['redundant_reads']) /
                                                 r['lines'] if r['lines'] else None)
    c, p = results['conservative'], results['speculative']
    results['removable_ratio'] = ((p['dead_writes'] + p['redundant_reads']) /
                                  (c['dead_writes'] + c['redundant_reads']))
    results['scaled_removable_estimate_percent'] = 0.903 * results['removable_ratio']
    return results


def ce_parse_conservative(generated, replaced, mappings):
    fs = {}; sites = Counter()
    for p in sorted(generated.glob('*_recomp.*.cpp')):
        for m in re.finditer(r'^DEFINE_REX_FUNC\((\w+)\) \{\n(.*?)^\}', p.read_text(), re.M | re.S):
            if m[1].startswith('ref_'):
                continue
            f = ce.parse(m[2], mappings, sites)
            for b in f.blocks:
                b.calls = [ce.canonical(c, replaced) for c in b.calls]
            if m[1] in replaced:
                fs['__imp__' + m[1]] = f
                fs[m[1]] = s.Function([s.Block(read=s.ALL, write=s.ALL)], 0, 0, 0, 0)
            else:
                fs[m[1]] = f
    return fs, sites


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--generated', type=Path, required=True)
    ap.add_argument('--binary', type=Path, help='matched ELF; its strong sub_X overrides')
    ap.add_argument('--replaced', type=Path,
                    help='alternative: file listing the sub_X names with native overrides')
    ap.add_argument('--probe', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    result = run(a)
    a.output.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=1))
