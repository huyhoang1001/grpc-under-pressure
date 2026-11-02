#!/usr/bin/env python3
"""Explicit study-boundary stop for the pre-outcome RNG design correction.
The original immutable runner cannot pause between studies; intercept its first
B startup before the3s future workload epoch. Preserve the attempt, never erase it.
"""
import json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5];OUT=ROOT/'experiments/003/results/stage6'
def main():
 # Find the actual Python driver, not its shell/sandbox supervisors.
 processes=subprocess.check_output(['ps','-eo','pid,args'],text=True).splitlines()
 matches=[int(line.split(None,1)[0]) for line in processes if line.split(None,1)[1:] and line.split(None,1)[1].strip()=='python3 experiments/003/secondary/fixtures/study.py execute']
 assert len(matches)==1,matches;pid=matches[0]
 while True:
  matrix=json.loads((OUT/'MATRIX.json').read_text())
  if matrix['status']!='RUNNING':return
  if any(b['study']=='B' for b in matrix['blocks']):
   os.kill(pid,signal.SIGINT)
   (OUT/'BOUNDARY-STOP.json').write_text(json.dumps({'reason':'Pre-outcome source review found overlapping per-client SplitMix state sequences; stop original B startup before workload, preserve attempt; separately preregister domain-separated seeds.','pid':pid,'signal':'SIGINT','sent_unix_ns':time.time_ns(),'completed_A_blocks':sum(b['study']=='A' and b['status']=='VALID' for b in matrix['blocks']),'study_B_numeric_outcomes_viewed':False},indent=2)+'\n');print('Stopped original driver at B boundary',flush=True);return
  time.sleep(.01)
if __name__=='__main__':main()
