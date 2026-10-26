import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / 'server/target/debug/pressure-server'
CLIENT = Path('/workspace/toolchains/bin/pressure-loadgen')

class RuntimeTests(unittest.TestCase):
    def run_case(self, variant, *, seconds='0.5', rate='100', service='1', deadline='10s', cancel=False, queue_limit='268435456'):
        with tempfile.TemporaryDirectory(prefix='pressure-test-') as tmp:
            p = Path(tmp)
            with (p/'server.log').open('w') as log:
                server = subprocess.Popen([str(SERVER), '--variant', variant, '--addr', '127.0.0.1:50052', '--service-ms', service, '--queue-limit', queue_limit, '--csv', str(p/'server.csv')], stderr=log)
                try:
                    for _ in range(100):
                        if 'ready ' in (p/'server.log').read_text(): break
                        if server.poll() is not None: self.fail((p/'server.log').read_text())
                        time.sleep(.02)
                    else: self.fail('server not ready')
                    result = subprocess.run([str(CLIENT), '--addr','127.0.0.1:50052','--rate',rate,'--seconds',seconds,'--timeout',deadline,'--csv',str(p/'client.csv'),'--summary',str(p/'client.json')], capture_output=True, text=True, timeout=15)
                    time.sleep(.6)
                    with (p/'server.csv').open() as samples:
                        rows = list(csv.DictReader(samples))
                    final = rows[-1]
                    if cancel:
                        self.assertNotEqual(result.returncode,0)
                        self.assertEqual(int(final['active_streams']),0, 'cancelled handler/worker still active')
                        self.assertEqual(int(final['queue_bytes']),0)
                        self.assertEqual(int(final['worker_bytes']),0)
                        self.assertGreater(int(final['errors']),0)
                        self.assertEqual(int(final['received']),int(final['processed'])+int(final['discarded']))
                    else:
                        self.assertEqual(result.returncode,0,result.stderr)
                        summary=json.loads((p/'client.json').read_text())
                        self.assertGreater(summary['completed_sends'],0)
                        self.assertEqual(summary['completed_sends'],summary['summary']['accepted'])
                        self.assertEqual(summary['completed_sends'],summary['summary']['processed'])
                        self.assertEqual(int(final['queue_depth']),0)
                        self.assertEqual(int(final['received']),int(final['processed']))
                    for row in rows:
                        if int(row['errors'])==0:
                            self.assertEqual(int(row['queue_depth']),int(row['enqueued'])-int(row['dequeued']))
                            self.assertEqual(int(row['queue_bytes']),int(row['queue_depth'])*16384)
                        if variant=='bounded': self.assertLessEqual(int(row['queue_depth']),32)
                    self.assertEqual(max(int(r['connections_accepted']) for r in rows),1)
                finally:
                    server.send_signal(signal.SIGINT)
                    try: server.wait(timeout=3)
                    except subprocess.TimeoutExpired: server.kill();server.wait()

    def test_normal_direct(self): self.run_case('direct')
    def test_normal_unbounded(self): self.run_case('unbounded', rate='300', service='10')
    def test_normal_bounded(self): self.run_case('bounded', rate='300', service='10')
    def test_queue_safety_abort(self): self.run_case('unbounded', rate='1000', service='100', cancel=True, queue_limit='16384')
    def test_rss_safety_abort(self):
        with tempfile.TemporaryDirectory(prefix='pressure-rss-') as tmp:
            path = Path(tmp)/'samples.csv'
            process = subprocess.run([str(SERVER), '--addr', '127.0.0.1:50052', '--rss-limit', '1', '--csv', str(path)], capture_output=True, text=True, timeout=5)
            self.assertEqual(process.returncode,42)
            self.assertIn('RSS safety limit exceeded',process.stderr)
            with path.open() as samples: self.assertGreaterEqual(len(list(csv.DictReader(samples))),1)

    def test_cancel_unbounded(self): self.run_case('unbounded',seconds='0.2',rate='1000',service='100',deadline='400ms',cancel=True)
    def test_cancel_bounded(self): self.run_case('bounded',seconds='1',rate='1000',service='100',deadline='400ms',cancel=True)
    def test_cancel_direct(self): self.run_case('direct',seconds='1',rate='1000',service='100',deadline='400ms',cancel=True)

if __name__ == '__main__': unittest.main(verbosity=2)
