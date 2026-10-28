"""Known-value endpoint and design checks; never runs an application workload."""
import itertools
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'experiments/002'))
from stage5.analyze import cohort,recovery,ownership,pooled_bootstrap,interval
from stage5.freeze import order


class AnalysisTests(unittest.TestCase):
    def test_order_has_five_complete_interleaved_blocks_and_is_deterministic(self):
        rows=order();self.assertEqual(rows,order());self.assertEqual(len(rows),15)
        for block in range(1,6):
            group=[r for r in rows if r['block']==block]
            self.assertEqual(sorted(r['policy'] for r in group),['adaptive','fixed32','fixed8'])
            self.assertEqual([r['position'] for r in group],[1,2,3])
        self.assertEqual(len({r['name'] for r in rows}),15)

    def test_primary_verifier_accepts_historical_copy_and_rejects_config_tamper(self):
        import hashlib,json,shutil,tempfile
        from stage5.verify import validate
        source=ROOT/'experiments/002/results/stage4/exploratory-adaptive'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'historical-fixture';shutil.copytree(source,folder)
            m=json.loads((folder/'manifest.json').read_text())
            config={k:m[k] for k in ['service_schedule','event_io','sample_ms','rate','offered_seconds','payload_bytes','seed','physical_K','controller','windows','runtime','build_mode','limits']}
            freeze={'application_source_sha256':m['server_source_sha256'],'binary_sha256':m['binary_sha256'],'configuration':config,'policy_initial_budgets':{'adaptive':16},'order':[{'name':'historical-fixture','policy':'adaptive','block':1,'position':1}]}
            path=root/'FROZEN.json';path.write_text(json.dumps(freeze))
            m.update(name='historical-fixture',primary_run=True,purpose='primary_controlled_comparison',block=1,position=1,frozen_checks_before=[],frozen_checks_after=[],freeze_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            (folder/'manifest.json').write_text(json.dumps(m))
            self.assertEqual(validate(folder),[])
            m['rate']=81;(folder/'manifest.json').write_text(json.dumps(m))
            self.assertIn('configuration drift rate',validate(folder))

    def test_enqueue_cohort_half_open_boundaries_not_completion_time(self):
        events=[{'event':'dequeued','enqueue_ns':str(t),'queue_residence_ns':str(value)} for t,value in [(11_999_999_999,1),(12_000_000_000,2),(35_999_999_999,3),(36_000_000_000,4)]]
        self.assertEqual(cohort(events,12_000_000_000,36_000_000_000),[2,3])

    def test_cluster_weighted_nearest_rank_matches_expanded_cohorts(self):
        values=[[1,3,20],[2,7],[8,9,10]]
        for counts in itertools.product(range(3),repeat=3):
            expanded=sorted(v for i,group in enumerate(values) for _ in range(counts[i]) for v in group)
            if not expanded:continue
            import math
            expected=expanded[math.ceil(.95*len(expanded))-1]/1e6
            self.assertEqual(pooled_bootstrap(values,counts),expected)
        self.assertEqual(interval(list(range(100))),[2,97])

    def test_recovery_contiguous_window_and_right_censoring(self):
        events=[]
        # Healthy and recovery streams have the same10/s rate and synthetic1ms residence.
        for offset in [0,24_000_000_000]:
            for i in range(120):
                t=offset+i*100_000_000
                events.append({'event':'dequeued','enqueue_ns':str(t),'queue_residence_ns':'1000000'})
                events.append({'event':'processed','completion_ns':str(t+10_000_000)})
        r=recovery(events)
        self.assertEqual((r['start_delay_s'],r['confirmation_delay_s'],r['right_censored']),(0,3,False))
        for e in events:
            if e['event']=='dequeued' and int(e['enqueue_ns'])>=24e9:e['queue_residence_ns']='2000000'
        r=recovery(events)
        self.assertTrue(r['right_censored']);self.assertIsNone(r['confirmation_delay_s'])

    def test_worker_utilization_backlog_ownership_and_clipping(self):
        events=[{'event':'admitted','enqueue_ns':'100'}, {'event':'dequeued','dequeue_ns':'200'}, {'event':'admitted','enqueue_ns':'250'}, {'event':'processed','completion_ns':'500'}, {'event':'dequeued','dequeue_ns':'600'}, {'event':'processed','completion_ns':'1000'}]
        r=ownership(events,900)
        self.assertAlmostEqual(r['busy_s'],600e-9)
        self.assertAlmostEqual(r['backlog_s'],450e-9)
        self.assertAlmostEqual(r['idle_backlog_s'],200e-9)
        self.assertAlmostEqual(r['utilization'],2/3)

if __name__=='__main__':unittest.main()
