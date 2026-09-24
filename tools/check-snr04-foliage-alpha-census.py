#!/usr/bin/env python3
"""Replay every captured textured foliage draw against its exact prior depth."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


def check(args):
    census = json.loads(args.census.read_text())
    events = json.loads(args.events.read_text())
    order = json.loads(args.order.read_text())
    depth = json.loads(args.depth.read_text())
    assert census['stage'] == events['stage'] == depth['stage'] == 'done'
    assert order['source_frame'] == args.frame
    assert depth['events'] == [draw['event'] for draw in census['draws']]
    assert depth['completed'] == depth['events']
    sequences = {row['event']: row['sequence'] for row in events['matches']}
    ids = {row['sequence']: draw_id for draw_id, row in
           enumerate(order['order'], 1)}
    assert len(ids) == len(order['order'])
    assert len(census['draws']) == len(set(draw['event'] for draw in census['draws']))
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'frame': args.frame, 'draws': len(census['draws']),
              'results': [], 'failures': []}
    for draw in census['draws']:
        event = draw['event']
        probe = args.depth.with_name(f'{args.depth.stem}-{event}.json')
        state = json.loads(probe.read_text())
        assert state['stage'] == 'done' and state['event'] == event
        tile_y = 720 - int(state['viewport'][3])
        assert tile_y in (0, 256, 512)
        rows = min(256, 720 - tile_y)
        sequence = sequences[event]
        chain = args.bc3 / (draw['bc3'].replace('::', '-') + '.bc3mips')
        output = args.output / str(event)
        command = [sys.executable, str(Path(__file__).with_name(
            'check-snr04-matched-vegetation-draw.py')), str(probe),
            str(args.fixture), str(args.shader), str(args.executable),
            str(output), '--frame', str(args.frame), '--sequence',
            str(sequence), '--draw-id', str(ids[sequence]), '--rows',
            str(rows), '--tile-y', str(tile_y), '--alpha-bc3', str(chain)]
        run = subprocess.run(command, capture_output=True, text=True)
        if run.returncode:
            report['failures'].append({'event': event,
                                       'error': run.stderr.strip()[-1000:]})
        else:
            result = json.loads(run.stdout)
            assert result['event'] == event and result['alpha_bc3']
            exact = all(sample['reference'] == sample['private'] ==
                        sample['overlap'] and sample['depth_max'] in (None, 0.0)
                        for sample in result['samples'])
            if exact:
                report['results'].append(result)
            else:
                report['failures'].append({'event': event, 'comparison': result})
        (args.output / 'census.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('census', 'events', 'order', 'depth', 'fixture', 'shader',
                 'bc3', 'executable', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--frame', type=int, required=True)
    report = check(parser.parse_args())
    print(json.dumps({'draws': report['draws'],
                      'matched': len(report['results']),
                      'failed': len(report['failures'])}))
    if report['failures']:
        sys.exit(1)
