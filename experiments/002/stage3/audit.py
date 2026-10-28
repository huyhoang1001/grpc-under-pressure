#!/usr/bin/env python3
"""Offline Stage 3 accounting and historical-byte audit; executes no workload."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'experiments/002'))
from stage3.run import validate


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = args.directory
    validation = {}
    for path in sorted(root.glob('*/manifest.json')):
        issues = validate(path.parent)
        validation[path.parent.name] = {'issues': issues, 'valid_for_declared_purpose': not issues}
        assert not issues, (path, issues)
    save(root / 'verification.json', validation)
    baseline = '4763ce8b7f2798a3bdfb0dcb5ae61b48914c7fdc'
    paths = subprocess.check_output([
        'git', 'ls-tree', '-r', '--name-only', baseline, 'experiments/001',
        'experiments/002/results', 'experiments/002/EXPERIMENT-002.md',
        'experiments/002/STAGE1-REPORT.md', 'experiments/002/STAGE2-REPORT.md',
    ], cwd=ROOT, text=True).splitlines()
    inventory = []
    for name in paths:
        original = subprocess.check_output(['git', 'show', baseline + ':' + name], cwd=ROOT)
        current = (ROOT / name).read_bytes()
        assert current == original, name
        inventory.append({'path': name, 'sha256': hashlib.sha256(current).hexdigest(), 'bytes': len(current)})
    save(root / 'historical-integrity.json', {
        'baseline_commit': baseline, 'verified_unchanged_files': len(inventory), 'files': inventory,
    })
    for label, folder in [('old', ROOT / 'experiments/002/results/stage2/exploratory-1'),
                          ('new', root / 'exploratory-fixed8')]:
        def read(path):
            with path.open(newline='') as stream:
                return list(csv.DictReader(stream))
        server = read(folder / 'server/server.csv')
        client = read(folder / 'client/client.csv')
        process = read(folder / 'process.csv')
        cpu = {}
        for role in ['server', 'client']:
            rows = [row for row in process if row['role'] == role]
            first, end = rows[0], rows[-1]
            wall = (int(end['monotonic_ns']) - int(first['monotonic_ns'])) / 1e9
            ticks = lambda row: int(row['utime_ticks']) + int(row['stime_ticks'])
            elapsed = (ticks(end) - ticks(first)) / int(end['CLK_TCK'])
            cpu[role] = {'observed_cpu_s': elapsed, 'observed_wall_s': wall,
                         'mean_one_core_percent': 100 * elapsed / wall,
                         'peak_rss_bytes': max(int(row['rss_bytes']) for row in rows)}
        gaps = {}
        for role, rows in [('server', server), ('client', client)]:
            times = [int(row['elapsed_ns']) for row in rows if row.get('started', '1') == '1']
            delta = [b - a for a, b in zip(times, times[1:])]
            gaps[role] = {'median': statistics.median(delta) / 1e6, 'max': max(delta) / 1e6}
        save(root / ('supplement-' + label + '.json'), {
            'cpu_and_rss': cpu, 'final_server': server[-1], 'sample_gaps_ms': gaps,
        })
    print(f'{len(validation)} cases valid; {len(inventory)} historical files byte-identical')


if __name__ == '__main__':
    main()
