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
    'second_draw': 'FH1 SNR01 second draw call ',
    'semantic': 'FH1 SNR01 semantic packet ',
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
                assert last_bound
                assert last_bound['fetch'] == row['fetch'] == 0
                assert not last_bound['signed']
                if last_bound['frame'] == frame + 1:
                    source_bindings.append((last_bound['absolute'], row))
            break
    items = [r for r in rows['item'] if r['frame'] == frame]
    states = [r for r in rows['state'] if r['frame'] == frame]
    if not items:
        semantic = {r['ordinal']: r for r in rows['semantic'] if r['frame'] == frame}
        state_keys = {(r['bucket_entry'], r['owner'], r['record']) for r in states}
        for call in rows['second_draw']:
            if call['frame'] != frame or (call['bucket_entry'],
                    call['vegetation_owner'], call['vegetation_selected_record']) not in state_keys:
                continue
            assert call['first_semantic'] == call['last_semantic'] in semantic
            packet = semantic[call['first_semantic']]
            items.append({'bucket_entry': call['bucket_entry'],
                          'owner': call['vegetation_owner'],
                          'record': call['vegetation_selected_record'],
                          'packet_physical': packet['header_physical']})
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
    fetch_source = 'prepared'
    if not fetches:
        sources_by_srv = {srv: source for srv, source in source_bindings}
        assert len(sources_by_srv) == 5
        assert all(r['absolute'] in sources_by_srv for r in bounds)
        fetches = [{'packet_physical': r['packet'], 'fetch_constant': 0,
                    'format': 20, 'width': 256, 'height': 256,
                    'base_address': sources_by_srv[r['absolute']]['base'],
                    'mip_address': sources_by_srv[r['absolute']]['mips']}
                   for r in bounds]
        fetch_source = 'fenced_bc3'
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
            'fetch_source': fetch_source,
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
            if any('manager_context' in row for row in resolved):
                assert all('manager_context' in row for row in resolved)
                contexts = {row['manager_context'] for row in resolved}
                tables = {row['manager_table'] for row in resolved}
                vtables = {row['manager_vtable'] for row in resolved}
                assert len(contexts) == len(tables) == len(vtables) == 1
                assert 0 not in contexts | tables | vtables
                managers = defaultdict(set)
                for row in resolved:
                    assert row['manager_object'] != 0
                    assert row['object'] - row['manager_object'] == 44
                    managers[row['key']].add(row['manager_object'])
                assert set(managers) == set(objects)
                assert all(len(values) == 1 for values in managers.values())
                assert len({next(iter(values)) for values in managers.values()}) == 5
                assert len({next(iter(values)) - candidate * 96
                            for candidate, values in managers.items()}) == 1
                report['manager_context'] = next(iter(contexts))
                report['manager_table'] = next(iter(tables))
                report['manager_vtable'] = next(iter(vtables))
                report['manager_stride'] = 96
                report['manager_objects'] = [
                    {'key': candidate, 'object': next(iter(values))}
                    for candidate, values in sorted(managers.items())]
                if any('resource36' in row for row in resolved):
                    assert all('resource36' in row for row in resolved)
                    resources = defaultdict(set)
                    for row in resolved:
                        assert row['manager_flags'] >> 13 == row['key']
                        assert row['resource32'] == 0
                        assert row['resource36'] and row['resource40']
                        resources[row['key']].add(
                            (row['resource36'], row['resource40']))
                    assert set(resources) == set(objects)
                    assert all(len(values) == 1 for values in resources.values())
                    assert len({pointer for values in resources.values()
                                for pair in values for pointer in pair}) == 10
                    report['provider_resources'] = [
                        {'key': candidate, 'resource36': next(iter(values))[0],
                         'resource40': next(iter(values))[1]}
                        for candidate, values in sorted(resources.items())]
                    if any('resource36_vtable' in row for row in resolved):
                        assert all(row.get('resource36_vtable') == 0x8224368C and
                                   row.get('resource40_vtable') == 0x822436F4
                                   for row in resolved)
                        report['provider_resource_vtables'] = {
                            'chain': '8224368C', 'base': '822436F4'}
                    if any('resource36_generation' in row for row in resolved):
                        assert all(not row['generation_overflow'] and
                                   row['resource36_generation'] > 0 and
                                   row['resource40_generation'] > 0
                                   for row in resolved)
                        generations = defaultdict(set)
                        for row in resolved:
                            generations[row['key']].add((row['resource36_generation'],
                                                         row['resource40_generation']))
                        assert all(len(values) == 1 for values in generations.values())
                        assert len({generation for values in generations.values()
                                    for pair in values for generation in pair}) == 10
                        report['provider_resource_generations'] = [
                            {'key': candidate, 'chain': next(iter(values))[0],
                             'base': next(iter(values))[1]}
                            for candidate, values in sorted(generations.items())]
                        if any('generation_reuses' in row for row in resolved):
                            assert all('generation_reuses' in row and
                                       'generation_destructions' in row and
                                       'resource36_previous_generation' in row and
                                       'resource40_previous_generation' in row
                                       for row in resolved)
                            report['resource_lifecycle'] = {
                                'reuses': max(row['generation_reuses'] for row in resolved),
                                'destructions': max(row['generation_destructions']
                                                    for row in resolved),
                                'selected_reused': sorted({row['key'] for row in resolved
                                    if row['resource36_previous_generation'] or
                                       row['resource40_previous_generation']})}
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
