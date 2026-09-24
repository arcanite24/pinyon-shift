#!/usr/bin/env python3
"""Check title vegetation state entries against same-frame BC3 bindings."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


MARKERS = {
    'state': 'FH1 SNR02 vegetation state entry ',
    'item': 'FH1 SNR03 item ',
    'fetch': 'FH1 SNR01 prepared texture fetch ',
    'bound': 'FH1 SNR04 bound pixel ',
    'source': 'FH1 SNR04 BC3 source ',
    'resolved': 'FH1 SNR02 vegetation resource resolved ',
    'resource_bound': 'FH1 SNR02 vegetation resource bound ',
}


def verify(log: Path, frame: int):
    rows = {name: [] for name in MARKERS}
    source_bindings = []
    last_bound = None
    for line in log.open(encoding='utf-8'):
        for name, marker in MARKERS.items():
            if marker not in line:
                continue
            row = json.loads(line.split(marker, 1)[1])
            rows[name].append(row)
            if name == 'bound':
                last_bound = row
            elif name == 'source':
                assert last_bound and last_bound['frame'] == frame + 1
                assert last_bound['fetch'] == row['fetch'] == 0
                assert not last_bound['signed']
                source_bindings.append((last_bound['absolute'], row))
            break
    items = [r for r in rows['item'] if r['frame'] == frame]
    states = [r for r in rows['state'] if r['frame'] == frame]
    assert len(items) == len(states) > 0
    key = lambda r: (r['bucket_entry'], r['owner'], r['record'])
    assert len({key(r) for r in items}) == len(items)
    assert len({key(r) for r in states}) == len(states)
    assert {key(r) for r in items} == {key(r) for r in states}
    assert len({r['index'] for r in states}) == 1
    assert len({(r['entry'], tuple(r['words'])) for r in states}) == 1
    assert all(len(r['words']) == 7 and r['entry'] % 4 == 0 for r in states)

    packets = {r['packet_physical'] for r in items}
    fetches = [r for r in rows['fetch'] if r['frame'] == frame + 1 and
               r['packet_physical'] in packets and r['fetch_constant'] == 0]
    bounds = [r for r in rows['bound'] if r['frame'] == frame + 1 and
              r['packet'] in packets and r['fetch'] == 0 and not r['signed']]
    by_packet_fetch, by_packet_srv = defaultdict(set), defaultdict(set)
    for row in fetches:
        assert row['format'] == 20 and row['width'] == row['height'] == 256
        by_packet_fetch[row['packet_physical']].add(
            (row['base_address'], row['mip_address']))
    for row in bounds:
        by_packet_srv[row['packet']].add(row['absolute'])
    assert set(by_packet_fetch) == set(by_packet_srv) == packets
    assert all(len(values) == 1 for values in by_packet_fetch.values())
    assert all(len(values) == 1 for values in by_packet_srv.values())
    assert len(fetches) == len(bounds)
    texture_to_srv = defaultdict(set)
    counts = Counter()
    packet_texture = {}
    for packet in packets:
        texture = next(iter(by_packet_fetch[packet]))
        srv = next(iter(by_packet_srv[packet]))
        texture_to_srv[texture].add(srv)
        counts[texture] += sum(r['packet_physical'] == packet for r in fetches)
        packet_texture[packet] = texture
    assert len(texture_to_srv) == len(source_bindings) == 5
    assert all(len(srvs) == 1 for srvs in texture_to_srv.values())
    source_srvs = {srv for srv, _ in source_bindings}
    assert source_srvs == {next(iter(srvs)) for srvs in texture_to_srv.values()}
    for srv, source in source_bindings:
        assert source['outdated'] == 0
        assert (source['base'], source['mips']) in texture_to_srv
        assert texture_to_srv[source['base'], source['mips']] == {srv}
    state = states[0]
    report = {'frame': frame, 'items': len(items), 'executions': len(fetches),
            'state_index': state['index'], 'state_entry': state['entry'],
            'state_words': state['words'], 'bc3': [
                {'base': base, 'mips': mips, 'srv': next(iter(texture_to_srv[base, mips])),
                 'executions': count}
                for (base, mips), count in sorted(counts.items())]}
    if all('candidate' in row for row in states):
        by_key = {key(row): row for row in states}
        candidate_textures = defaultdict(set)
        candidate_counts = Counter()
        for item in items:
            row = by_key[key(item)]
            assert row['slot'] < row['limit'] and row['candidate'] > 0
            candidate_textures[row['candidate']].add(
                packet_texture[item['packet_physical']])
            candidate_counts[row['candidate']] += 1
        assert len(candidate_textures) == len(texture_to_srv) == 5
        assert all(len(textures) == 1 for textures in candidate_textures.values())
        assert {next(iter(textures)) for textures in candidate_textures.values()} == set(texture_to_srv)
        report['candidates'] = [
            {'key': candidate, 'base': next(iter(textures))[0],
             'mips': next(iter(textures))[1], 'items': candidate_counts[candidate]}
            for candidate, textures in sorted(candidate_textures.items())]
        resolved = [r for r in rows['resolved'] if r['frame'] == frame]
        resource_bound = [r for r in rows['resource_bound'] if r['frame'] == frame]
        if resolved or resource_bound:
            assert len(resolved) == len(resource_bound) > 0
            state_keys = {(r['bucket_entry'], r['record'], r['candidate'])
                          for r in states}
            resource_key = lambda r: (r['bucket_entry'], r['record'], r['key'])
            resolved_by_key = {resource_key(r): r for r in resolved}
            bound_by_key = {resource_key(r): r for r in resource_bound}
            assert len(resolved_by_key) == len(resolved)
            assert len(bound_by_key) == len(resource_bound)
            assert set(resolved_by_key) == set(bound_by_key) <= state_keys
            objects = defaultdict(set)
            for selected, row in resolved_by_key.items():
                bound = bound_by_key[selected]
                assert row['object'] == bound['object'] != 0
                assert bound['slot'] == 0
                objects[row['key']].add(row['object'])
            assert set(objects) == set(candidate_textures)
            assert all(len(values) == 1 for values in objects.values())
            assert len({next(iter(values)) for values in objects.values()}) == 5
            report['resource_resolutions'] = len(resolved)
            report['resource_objects'] = [
                {'key': candidate, 'object': next(iter(values))}
                for candidate, values in sorted(objects.items())]
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--frame', type=int, required=True)
    args = parser.parse_args()
    report = verify(args.log, args.frame)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'items': report['items'], 'executions': report['executions'],
                      'bc3': len(report['bc3']),
                      'candidates': len(report.get('candidates', [])),
                      'resolved': report.get('resource_resolutions', 0),
                      'state_index': report['state_index']}))
