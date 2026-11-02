#!/usr/bin/env python3
"""Preregistered B-only seed correction; identical compiled application binaries."""
import fcntl,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'experiments/003/results/stage6'
spec=importlib.util.spec_from_file_location('run_b2',Path(__file__).with_name('run_b2.py'));R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
def atomic(p,o):
 q=p.with_suffix('.pending');q.write_text(json.dumps(o,indent=2)+'\n');q.replace(p)
def freeze():
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(),'commit B2 preregistration first'
 old=json.loads((OUT/'FROZEN-MANIFEST.json').read_text());assert all(R.sha(ROOT/p)==h for p,h in old['source_sha256'].items())
 assert all(R.sha(p)==h for p,h in old['binary_sha256'].items()),'reuse exact app executables'
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();frozen=dict(old)
 frozen.update({'source_commit':revision,'binary_build_source_commit':old['source_commit'],'application_source_identical_to':old['source_commit'],'seed_amendment':'B2','created_unix_ns':time.time_ns(),'before_StudyB_execution':True,'prior_freeze_sha256':R.sha(OUT/'FROZEN-MANIFEST.json'),'normal_debug_builds_reused_without_rebuild':True})
 source=dict(old['source_sha256'])
 new=[ROOT/'experiments/003/STAGE6-B-SEED-AMENDMENT.md',OUT/'RUN-PLAN-B2.json',OUT/'SEED-STREAM-REVIEW.md',OUT/'analysis/analyze_b2.py',OUT/'analysis/combine.py']
 new += [p for p in (ROOT/'experiments/003/secondary/fixtures').glob('*_b2.py') if p.is_file()]
 for p in new:source[str(p.relative_to(ROOT))]=R.sha(p)
 frozen['source_sha256']=source;frozen.pop('before_study_execution',None);R.save(R.FREEZE,frozen);print('B2 FROZEN',revision,'app binaries built at',old['source_commit'],flush=True)
def preflight():
 plan=json.loads((OUT/'RUN-PLAN-B2.json').read_text());directory=OUT/'preflight/b2-pinned';directory.mkdir(exist_ok=False)
 for case in plan['blocks'][0]['cases']:
  verdict=R.run(case,directory/case['name'],True);R.save(directory/(case['name']+'-registry.json'),{'case':case,'outcome':verdict})
  if verdict['verdict']!='PASS':raise SystemExit(1)
def execute():
 R.source_guard();plan=json.loads((OUT/'RUN-PLAN-B2.json').read_text());matrix={'status':'RUNNING','started_unix_ns':time.time_ns(),'frozen_sha256':R.sha(R.FREEZE),'seed_amendment':'B2','blocks':[],'attempts':[]}
 for name in ['b-deterministic','b-jitter']:assert json.loads((OUT/f'preflight/b2-pinned/{name}-registry.json').read_text())['outcome']['verdict']=='PASS'
 assert json.loads((OUT/'checks/fault-verification-b2-pinned.json').read_text())['verdict']=='PASS'
 R.save(OUT/'MATRIX-B2.json',matrix);categories={category for block in json.loads((OUT/'MATRIX.json').read_text())['blocks'] if block['study']=='A' and block['status']!='VALID' for category in ['clock','sampling','startup'] if category in block.get('exclusion_reason','').lower()}
 with open('/tmp/grpc-under-pressure-e3-stage4.lock','a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for block in plan['blocks']:
   for attempt in [1,2]:
    directory=OUT/f'B2-block-{block["block"]:02}-attempt-{attempt:02}';directory.mkdir(exist_ok=False);R.save(directory/'block-manifest.json',{**block,'attempt':attempt,'seed_amendment':'B2','frozen_sha256':matrix['frozen_sha256']})
    entry={**block,'attempt':attempt,'seed_amendment':'B2','status':'RUNNING','runs':{}};matrix['blocks'].append(entry);atomic(OUT/'MATRIX-B2.json',matrix);failed=None
    for case in block['cases']:
     path=directory/case['name'];print('START B2',block['block'],attempt,case['name'],flush=True)
     try:verdict=R.run(case,path)
     except BaseException as error:
      verdict={'verdict':'FAIL','reason':repr(error),'safety_abort':False}
      if path.exists() and not (path/'outcome.json').exists():R.save(path/'outcome.json',verdict)
     entry['runs'][case['name']]={'directory':str(path.relative_to(ROOT)),**verdict};matrix['attempts'].append({'study':'B','block':block['block'],'attempt':attempt,'case':case['name'],'seed_amendment':'B2','directory':str(path.relative_to(ROOT)),**verdict});atomic(OUT/'MATRIX-B2.json',matrix)
     if verdict['verdict']!='PASS':failed=verdict;break
    if failed is None:entry['status']='VALID';atomic(OUT/'MATRIX-B2.json',matrix);print('VALID BLOCK B2',block['block'],flush=True);break
    entry['status']='EXCLUDED_WHOLE_BLOCK';reason=failed['reason'] or 'unknown failure';category=next((c for c in ['clock','sampling','startup'] if c in reason.lower()),None)
    if category is None and any(x in reason.lower() for x in ['timeout waiting','exited before']):category='startup'
    stop=failed['safety_abort'] or category is None or category in categories or attempt==2
    if category:categories.add(category)
    entry['exclusion_reason']=reason;atomic(OUT/'MATRIX-B2.json',matrix)
    if stop:matrix['status']='STOPPED_FOR_REVIEW';atomic(OUT/'MATRIX-B2.json',matrix);exclusions(matrix);raise SystemExit(1)
  matrix['status']='COMPLETE';matrix['completed_unix_ns']=time.time_ns();atomic(OUT/'MATRIX-B2.json',matrix);exclusions(matrix);print('B2 MATRIX COMPLETE',flush=True)
def exclusions(matrix):atomic(OUT/'EXCLUSIONS-B2.json',{'attempts':matrix['attempts'],'excluded_blocks':[b for b in matrix['blocks'] if b['status']!='VALID'],'replacement_attempts':[b for b in matrix['blocks'] if b['attempt']>1],'seed_amendment':'B2','primary_stage5_runs_used':0})
if __name__=='__main__':{'freeze':freeze,'preflight':preflight,'execute':execute}[sys.argv[1]]()
