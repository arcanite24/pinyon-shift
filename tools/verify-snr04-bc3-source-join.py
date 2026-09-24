#!/usr/bin/env python3
"""Join sampled foliage BC3 cache sources to fenced mips and RenderDoc mips."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


MIP_LINE = re.compile(
    r'FH1 SNR04 BC3 mip chain frame=(\d+) submission=(\d+) srv=(\d+) '
    r'written=(\w+) path=(.+)$')


def verify(args):
    reference = {hashlib.sha256(path.read_bytes()).hexdigest(): path.name
                 for path in args.reference.glob('*.bc3mips')}
    assert len(reference) == 5
    bound = None
    sources, chains, changes = [], {}, []
    for line_index, line in enumerate(args.log.open(encoding='utf-8')):
        timestamp = line[1:24]
        if 'FH1 SNR04 bound pixel ' in line:
            row = json.loads(line.split('FH1 SNR04 bound pixel ', 1)[1])
            if row['fetch'] == 0 and not row['signed']:
                bound = row
        elif 'FH1 SNR04 BC3 source ' in line:
            row = json.loads(line.split('FH1 SNR04 BC3 source ', 1)[1])
            assert bound and row['fetch'] == bound['fetch']
            if bound['frame'] == args.frame:
                row.update(srv=bound['absolute'], packet=bound['packet'],
                           timestamp=timestamp, line_index=line_index)
                sources.append(row)
            bound = None
        elif 'FH1 texture reload attempt ' in line:
            changes.append(('reload', timestamp, line_index, json.loads(
                line.split('FH1 texture reload attempt ', 1)[1])))
        elif 'FH1 texture reload complete ' in line:
            changes.append(('complete', timestamp, line_index, json.loads(
                line.split('FH1 texture reload complete ', 1)[1])))
        elif 'FH1 texture invalidated ' in line:
            changes.append(('invalidated', timestamp, line_index, json.loads(
                line.split('FH1 texture invalidated ', 1)[1])))
        else:
            match = MIP_LINE.search(line)
            if match and int(match[1]) == args.frame:
                assert int(match[2]) == args.frame and match[4] == 'true'
                assert int(match[3]) not in chains
                chains[int(match[3])] = Path(match[5]).name
    assert len(sources) == len(chains) == 5
    assert len({row['srv'] for row in sources}) == 5
    assert len({row['texture'] for row in sources}) == 5
    if all('allocation_id' in row for row in sources):
        assert len({row['allocation_id'] for row in sources}) == 5
    rows = []
    for source in sorted(sources, key=lambda row: row['srv']):
        srv = source['srv']
        assert source['base'] % 4096 == source['mips'] % 4096 == 0
        assert source['base_bytes'] == source['mips_bytes'] == 65536
        assert source['outdated'] == 0
        if 'allocation_id' in source:
            assert source['allocation_id'] > 0
            assert source['payload_generation'] > 0
        path = args.live / chains[srv]
        payload = path.read_bytes()
        assert len(payload) == 87408
        digest = hashlib.sha256(payload).hexdigest()
        assert digest in reference
        base, mips = f"{source['base']:08X}", f"{source['mips']:08X}"
        events = [{'kind': kind, 'timestamp': timestamp, 'line_index': index,
                   'part': row.get('part'), 'gpu': row.get('gpu'),
                   'base_dirty': row.get('base_dirty'),
                   'mips_dirty': row.get('mips_dirty'),
                   'load_base': row.get('load_base'),
                   'load_mips': row.get('load_mips'),
                   'outdated': row.get('outdated'),
                   'payload_generation': row.get('payload_generation')}
                  for kind, timestamp, index, row in changes
                  if row['base'] == base and row['mips'] == mips
                  and row.get('texture', source['texture']) == source['texture']
                  and row.get('allocation_id', source.get('allocation_id')) ==
                  source.get('allocation_id')
                  and index < source['line_index']]
        generations = [event['payload_generation'] for event in events
                       if event['kind'] == 'complete' and
                       event['payload_generation'] is not None]
        if generations:
            assert generations == sorted(generations)
            assert generations[-1] == source['payload_generation']
        if any(event['kind'] == 'complete' for event in events):
            for invalidation in (event for event in events
                                 if event['kind'] == 'invalidated'):
                part, start = invalidation['part'], invalidation['line_index']
                assert any(attempt['kind'] == 'reload' and attempt[f'{part}_dirty']
                           and attempt['line_index'] > start
                           and any(done['kind'] == 'complete' and done[f'load_{part}']
                                   and done['line_index'] > attempt['line_index']
                                   for done in events)
                           for attempt in events)
        rows.append({'srv': srv, 'packet': source['packet'],
                     'texture': source['texture'], 'resource': source['resource'],
                     'base': base, 'mips': mips, 'outdated': source['outdated'],
                     'allocation_id': source.get('allocation_id'),
                     'payload_generation': source.get('payload_generation'),
                     'sample_time': source['timestamp'],
                     'payload_sha256': digest, 'reference': reference[digest],
                     'events': events})
    assert len({row['payload_sha256'] for row in rows}) == 5
    report = {'frame': args.frame, 'sources': rows,
              'invalidation_counts': dict(Counter(
                  (event['part'], event['gpu'])
                  for row in rows for event in row['events']
                  if event['kind'] == 'invalidated'))}
    report['invalidation_counts'] = {
        f'{part}:{"gpu" if gpu else "cpu"}': count
        for (part, gpu), count in report['invalidation_counts'].items()}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('log', 'live', 'reference', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--frame', type=int, required=True)
    report = verify(parser.parse_args())
    print(json.dumps({'sources': len(report['sources']),
                      'invalidations': report['invalidation_counts']}))
