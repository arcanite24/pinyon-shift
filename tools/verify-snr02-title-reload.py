#!/usr/bin/env python3
"""Verify one-process selected foliage teardown and current BC3 rebind."""

import argparse
import hashlib
import json
from pathlib import Path


def verify(root: Path, first: int, second: int) -> dict:
    assert 0 < first < second
    states = [json.loads((root / f'state-join-{frame}.json').read_text())
              for frame in (first, second)]
    sources = [json.loads((root / f'source-join-{frame + 1}.json').read_text())
               for frame in (first, second)]
    assert [state['frame'] for state in states] == [first, second]
    assert [source['frame'] for source in sources] == [first + 1, second + 1]

    snapshots = []
    for frame, state, source in zip((first, second), states, sources):
        candidates = {row['key']: row for row in state['candidates']}
        resources = {row['key']: row for row in state['provider_resources']}
        generations = {row['key']: row for row in state['provider_resource_generations']}
        payloads = {(int(row['base'], 16), int(row['mips'], 16)): row
                    for row in source['sources']}
        assert len(candidates) == len(resources) == len(generations) == len(payloads) == 5
        assert set(candidates) == set(resources) == set(generations)
        snapshot = {}
        for key, candidate in candidates.items():
            pair = candidate['base'], candidate['mips']
            assert pair in payloads
            payload = payloads[pair]
            assert payload['outdated'] == 0 and payload['payload_generation'] > 0
            assert payload['allocation_id'] > 0
            path = root / (f"snr04-bc3-frame{frame + 1}-submission{frame + 1}"
                           f"-srv{payload['srv']}.bc3mips")
            mip_bytes = path.read_bytes()
            assert len(mip_bytes) == 87408
            assert hashlib.sha256(mip_bytes).hexdigest() == payload['payload_sha256']
            snapshot[key] = {'candidate': candidate, 'resource': resources[key],
                             'generation': generations[key], 'payload': payload}
        snapshots.append(snapshot)

    before, after = snapshots
    assert set(before) == set(after)
    destroyed = []
    for line in (root / 'evidence.log').open(encoding='utf-8'):
        marker = 'FH1 SNR02 selected resource destroyed '
        if marker in line:
            row = json.loads(line.split(marker, 1)[1])
            if first < row['frame'] < second:
                destroyed.append((row['address'], row['vtable'], row['generation']))
    expected = {(entry['resource'][field], vtable, entry['generation'][kind])
                for entry in before.values()
                for field, kind, vtable in (('resource36', 'chain', 0x8224368C),
                                            ('resource40', 'base', 0x822436F4))}
    assert len(expected) == 10 and len(destroyed) == len(set(destroyed))
    assert expected == set(destroyed)

    rows = []
    for key in sorted(before):
        old, new = before[key], after[key]
        assert (old['candidate']['base'], old['candidate']['mips']) == (
            new['candidate']['base'], new['candidate']['mips'])
        for kind, field in (('chain', 'resource36'), ('base', 'resource40')):
            assert new['generation'][kind] > old['generation'][kind]
            assert (new['resource'][field], new['generation'][kind]) != (
                old['resource'][field], old['generation'][kind])
        a, b = old['payload'], new['payload']
        assert b['payload_sha256'] == a['payload_sha256']
        assert (b['allocation_id'] != a['allocation_id'] or
                b['payload_generation'] > a['payload_generation'])
        rows.append({'key': key, 'chain_generation': [old['generation']['chain'],
                                                      new['generation']['chain']],
                     'base_generation': [old['generation']['base'],
                                         new['generation']['base']],
                     'cache_allocation_id': [a['allocation_id'], b['allocation_id']],
                     'payload_generation': [a['payload_generation'],
                                            b['payload_generation']],
                     'payload_sha256': b['payload_sha256']})
    return {'first_frame': first, 'rebind_frame': second,
            'selected_destructors': len(expected), 'keys': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--first', type=int, required=True)
    parser.add_argument('--second', type=int, required=True)
    args = parser.parse_args()
    report = verify(args.root, args.first, args.second)
    (args.root / 'title-reload-join.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'keys': len(report['keys']),
                      'selected_destructors': report['selected_destructors']}))
