#!/usr/bin/env python3
"""Finalize interrupted orchestration metadata without changing any raw run file."""
import collections,hashlib,json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5];OUT=ROOT/'experiments/003/results/stage6'
def main():
 boundary=json.loads((OUT/'BOUNDARY-STOP.json').read_text());matrix=json.loads((OUT/'MATRIX.json').read_text());assert sum(b['study']=='A' and b['status']=='VALID' for b in matrix['blocks'])==5
 try:os.kill(boundary['pid'],0)
 except ProcessLookupError:pass
 else:raise AssertionError('original driver still alive; do not change its metadata')
 counts=collections.Counter();files=[]
 for directory in OUT.glob('B-block-*-attempt-*'):
  for p in directory.rglob('*.jsonl'):
   for line in p.read_text().splitlines():
    e=json.loads(line)
    if e.get('kind') in ['original_arrival','attempt_initiated','decoded','duplicate_linked','attempt_replay']:counts[e['kind']]+=1
   files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 assert not any(counts.values()),counts
 reason='Original B seed derivation has overlapping SplitMix streams; pre-outcome source review stopped startup before any original arrival/attempt/decode. Superseded by separately preregistered B2 domain-separated seeds; all A measurements retained.'
 shutil.copyfile(OUT/'MATRIX.json',OUT/'MATRIX-AT-BOUNDARY.json')
 if (OUT/'EXCLUSIONS.json').exists():shutil.copyfile(OUT/'EXCLUSIONS.json',OUT/'EXCLUSIONS-AT-BOUNDARY.json')
 for b in matrix['blocks']:
  if b['study']=='B':b['original_status_before_boundary_finalization']=b['status'];b['status']='SUPERSEDED_PRETRAFFIC';b['seed_review_reason']=reason
 matrix['status']='STOPPED_FOR_REVIEW';matrix['boundary_reason']=reason;matrix['A_study_complete']=True
 (OUT/'MATRIX.json').write_text(json.dumps(matrix,indent=2)+'\n')
 (OUT/'EXCLUSIONS.json').write_text(json.dumps({'attempts':matrix['attempts'],'excluded_blocks':[b for b in matrix['blocks'] if b['status']!='VALID'],'replacement_attempts':[],'seed_review_reason':reason,'primary_stage5_runs_used':0},indent=2)+'\n')
 (OUT/'BOUNDARY-VERIFICATION.json').write_text(json.dumps({'verdict':'PASS','A_valid_blocks':5,'A_valid_runs':40,'original_B_traffic_counts':dict(counts),'original_B_event_files':files,'no_original_B_traffic':True,'boundary_stop':boundary,'interrupted_matrix_sha256':hashlib.sha256((OUT/'MATRIX-AT-BOUNDARY.json').read_bytes()).hexdigest(),'reason':reason,'no_run_measurements_modified':True},indent=2)+'\n');print('PASS:40 valid A runs; original B stopped before any traffic; raw files preserved')
if __name__=='__main__':main()
