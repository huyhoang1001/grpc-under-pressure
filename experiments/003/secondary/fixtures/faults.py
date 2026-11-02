#!/usr/bin/env python3
"""Synthetic offline corruption fixtures only; never measurement evidence."""
import copy,importlib.util,json,shutil,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'experiments/003/results/stage6'
spec=importlib.util.spec_from_file_location('verify',Path(__file__).with_name('verify.py'));V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
def main():
 source=OUT/'preflight/pinned/b-jitter';results=[]
 for fault in ['missing_event','wrong_deadline','credit_overflow','attempt_collision','bridge_overflow','wrong_seed']:
  with tempfile.TemporaryDirectory(prefix='e3-stage6-corrupt-') as directory:
   run=Path(directory)/'case';shutil.copytree(source,run)
   def mutate(path,fn):
    p=run/path;o=json.loads(p.read_text());fn(o);p.write_text(json.dumps(o))
   if fault=='missing_event':
    p=run/'client-0/events.jsonl';p.write_text('\n'.join(p.read_text().splitlines()[1:])+'\n')
   if fault=='wrong_deadline':mutate('workload.json',lambda o:o['originals'][0].update(deadline_offset_ns=9_000_000_000))
   if fault=='credit_overflow':mutate('client-0/report.json',lambda o:o['client']['HighWater'].update(Outstanding=34))
   if fault=='attempt_collision':mutate('server/server-ledger.json',lambda o:o['attempts'][1].update(attempt_id=o['attempts'][0]['attempt_id']))
   if fault=='bridge_overflow':mutate('server/clock.json',lambda o:o['bounded_io'].update(bridge_peak=9))
   if fault=='wrong_seed':mutate('client-0/report.json',lambda o:o.update(retry_seed=0))
   try:V.verify(run)
   except (V.V.Invalid,KeyError,ValueError,AssertionError) as error:results.append({'fault':fault,'verdict':'REJECTED_AS_REQUIRED','reason':str(error)})
   else:raise AssertionError('accepted corrupted fixture '+fault)
 (OUT/'checks/fault-verification-pinned.json').write_text(json.dumps({'synthetic_not_measurements':True,'fixture_source':str(source.relative_to(ROOT)),'results':results,'verdict':'PASS'},indent=2)+'\n');print('PASS: six corruptions rejected')
if __name__=='__main__':main()
