#!/usr/bin/env python3
"""Offline publication/preservation checks. Writes only this review package."""
import collections,csv,hashlib,json,platform,re,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 audit=read(OUT/'audit/REVIEW-AUDIT.json');assert audit['verdict']=='PASS' and audit['performance_runs_executed']==0 and audit['previous_evidence_modified'] is False
 assert sha(OUT/'audit.py')==audit['audit_script_sha256']
 assert len(audit['runs'])==70 and collections.Counter(r['family'] for r in audit['runs'])=={'PRIMARY':20,'A':40,'B2':10}
 for stage in [5,6]:
  p=ROOT/f'experiments/003/results/stage{stage}';m=read(p/'SHA256SUMS.json');assert sha(p/'SHA256SUMS.json')==audit['integrity']['manifests'][str(stage)]['sha256']
  assert all(sha(ROOT/path)==v['sha256'] and (ROOT/path).stat().st_size==v['bytes'] for path,v in m.items())
 assert all(sha(ROOT/path)==h for path,h in audit['integrity']['documents'].items())
 metric_rows=[]
 for run in audit['runs']:
  directory=ROOT/run['directory'];m=read(directory/'verification.json');roles=['server','client'] if run['family']=='PRIMARY' else ['server']+[f'client-{i}' for i in range(run['clients'])]
  assert m['safety']['cpu_seconds_per_process']==30 and m['safety']['file_bytes']==67108864
  cap=m['safety'].get('rss_abort_bytes_per_process',m['safety'].get('rss_bytes_per_process'));assert cap==268435456
  for role in roles:
   file=directory/(role+'-metrics.csv');samples=list(csv.DictReader(file.open()));times=[int(x['host_monotonic_ns']) for x in samples];rss=[int(x['rss_bytes']) for x in samples];cpu=[int(x['cpu_user_ns'])+int(x['cpu_system_ns']) for x in samples]
   assert len(samples)>=2 and all(x<y for x,y in zip(times,times[1:])) and max(y-x for x,y in zip(times,times[1:]))<500_000_000
   assert min(rss)>=0 and max(rss)<=cap and max(cpu)<30_000_000_000 and len({x['pid'] for x in samples})==1
   metric_rows.append({'family':run['family'],'block':run['block'],'condition':run['condition'],'role':role,'file':str(file.relative_to(ROOT)),'samples':len(samples),'max_gap_ns':max(y-x for x,y in zip(times,times[1:])),'sampled_peak_rss_bytes':max(rss),'maximum_observed_cpu_ns':max(cpu),'PASS':True})
 (OUT/'METRIC-CHECKS.json').write_text(json.dumps({'verdict':'PASS','process_traces':len(metric_rows),'rows':metric_rows,'note':'Sampled/quantized guard verification, not continuous-memory proof or pooled performance comparison.'},indent=2)+'\n')
 claims=read(OUT/'CLAIMS.json');allowed={'SUPPORTED','QUALIFIED','INCONCLUSIVE','UNSUPPORTED'};assert len({c['id'] for c in claims})==len(claims)==29
 assert all(c['classification'] in allowed and c['evidence'] and c['qualification'] and c['publication_wording'] for c in claims)
 for c in claims:
  for target in c['evidence']:assert (OUT/target.split('#')[0]).exists(),target
 registry=read(OUT/'CHARTS.json');assert registry['performance_runs_executed']==0 and registry['no_new_endpoints'] and registry['generator_sha256']==sha(OUT/'charts.py')
 points=read(OUT/'CHART-DATA.json');assert len(points)==30 and {p['family'] for p in points}=={'PRIMARY'}
 for point in points:
  if point['panel']=='all-original':
   raw=next(r for r in audit['runs'] if (r['family'],r['block'],r['condition'])==('PRIMARY',point['block'],point['policy']));assert abs(point['value']-raw['U_over_N']*100)<1e-12
  else:
   raw=next(r for r in audit['primary_recovery_conditional'] if r['block']==point['block'])[point['policy']];assert point['cohort_n']==raw['n'] and abs(point['value']-raw['p95']/1e9)<1e-12
 assert next(c for c in registry['charts'] if c['id']=='original-recovery-sentinel')['publication_status']=='DO_NOT_PROMOTE'
 assert read(OUT/'CONTEXT-CHECKS.json')['verdict']=='PASS'
 files=[OUT/'CLAIMS.md',OUT/'PUBLICATION-OUTLINE.md',OUT/'EVIDENCE-INDEX.md',ROOT/'experiments/003/STAGE7-REPORT.md'];links=[]
 expected={(OUT/'PUBLICATION-CHECKS.json').resolve(),(OUT/'SHA256SUMS.json').resolve()}
 for file in files:
  for target in re.findall(r'\]\(([^)]+)\)',file.read_text()):
   if '://' in target or target.startswith('#'):continue
   path=(file.parent/target.split('#')[0]).resolve();assert path.exists() or path in expected,(file,target);links.append({'document':str(file.relative_to(ROOT)),'target':target})
 report=(ROOT/'experiments/003/STAGE7-REPORT.md').read_text();outline=(OUT/'PUBLICATION-OUTLINE.md').read_text()
 assert '**Verdict: PUBLISH' in report and 'no article draft' in (OUT/'EVIDENCE-INDEX.md').read_text()
 for term in ['conditional','original','backoff','outlier','jitter','primary','secondary','2,880','five']:
  assert term in (report+' '+outline).lower(),term
 protected=subprocess.check_output(['git','diff','--name-only',audit['reviewed_revision'],'--','experiments'],cwd=ROOT,text=True).splitlines()
 assert all(p=='experiments/003/STAGE7-REPORT.md' or p.startswith('experiments/003/results/stage7/') for p in protected),protected
 snapshots=[p for p in OUT.rglob('*') if p.is_file() and p.name not in ['SHA256SUMS.json','PUBLICATION-CHECKS.json'] and '__pycache__' not in p.parts]+[ROOT/'experiments/003/STAGE7-REPORT.md']
 manifest={str(p.relative_to(ROOT)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(snapshots)}
 assert all(not p.read_bytes().startswith(b'\x7fELF') and p.suffix not in ['.pyc','.exe','.zip'] for p in snapshots)
 (OUT/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
 result={'verdict':'PASS','publication_recommendation':'PUBLISH','publication_scope':'Qualified evidence/outline ready for drafting; no manuscript reviewed or written.','performance_runs_executed':0,'raw_or_frozen_artifacts_modified':False,'historical_checksums_verified':audit['integrity']['checked_unique_files'],'gate_replays':70,'new_arithmetic_families':{'primary':20,'secondary_A':40,'secondary_B2':10},'claims':dict(collections.Counter(c['classification'] for c in claims)),'local_evidence_links_checked':len(links),'chart_data_points_checked':len(points),'source_reviewed_revision':audit['reviewed_revision'],'python':sys.version,'platform':platform.platform(),'stage7_files_hashed':len(manifest),'stage7_max_file_bytes':max(v['bytes'] for v in manifest.values()),'stage7_sha256_manifest_sha256':sha(OUT/'SHA256SUMS.json'),'script_sha256':sha(Path(__file__)),'no_new_protocol_validator_claimed':True,'limits':'Automated data/schema/link/preservation checks supplement the human-readable editorial review; they do not validate an unwritten article or provide external execution attestation.'}
 (OUT/'PUBLICATION-CHECKS.json').write_text(json.dumps(result,indent=2)+'\n')
 assert all((file.parent/target.split('#')[0]).resolve().exists() for file in files for target in re.findall(r'\]\(([^)]+)\)',file.read_text()) if '://' not in target and not target.startswith('#'))
 print('PASS:',len(manifest),'Stage7 files hashed;',len(links),'evidence links;',audit['integrity']['checked_unique_files'],'historical checksums unchanged; PUBLISH within stated scope')
if __name__=='__main__':main()
