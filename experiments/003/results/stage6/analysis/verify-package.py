#!/usr/bin/env python3
"""Bind secondary raw/derived artifacts and check primary preservation; no runs."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5];OUT=ROOT/'experiments/003/results/stage6'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 a=json.loads((OUT/'FROZEN-MANIFEST.json').read_text());b=json.loads((OUT/'FROZEN-MANIFEST-B2.json').read_text());matrix=json.loads((OUT/'MATRIX-COMBINED.json').read_text())
 for f in [a,b]:assert all(sha(ROOT/path)==h for path,h in f['source_sha256'].items())
 assert a['binary_sha256']==b['binary_sha256'] and b['binary_build_source_commit']==a['source_commit']
 assert all(sha(p)==h for p,h in a['binary_sha256'].items())
 assert matrix['frozen_sha256']==sha(OUT/'FROZEN-MANIFEST.json') and matrix['frozen_B2_sha256']==sha(OUT/'FROZEN-MANIFEST-B2.json')
 old=json.loads((ROOT/'experiments/003/results/stage5/SHA256SUMS.json').read_text());assert all(sha(ROOT/path)==v['sha256'] for path,v in old.items())
 baseline='4638543acede9756c51b752a0f694a39ef553d39'
 modified=subprocess.check_output(['git','diff','--diff-filter=MD','--name-only',baseline,'--','experiments/001','experiments/002','experiments/003'],cwd=ROOT,text=True).splitlines()
 assert all(p.startswith('experiments/003/results/stage6/') or p.startswith('experiments/003/secondary/') for p in modified),modified
 # All pre-existing paths must be byte-identical; newly introduced Stage6 paths
 # may have reporting changes but every frozen study source hash must still match.
 old_paths=set(subprocess.check_output(['git','ls-tree','-r','--name-only',baseline,'--','experiments'],cwd=ROOT,text=True).splitlines());assert not(old_paths&set(modified))
 ignored={'SHA256SUMS.json','PACKAGE-VERIFICATION.json'}
 files=[p for p in OUT.rglob('*') if p.is_file() and p.name not in ignored and '__pycache__' not in p.parts]
 files += [p for p in (ROOT/'experiments/003/secondary').rglob('*') if p.is_file() and not any(x in p.parts for x in ['target','__pycache__'])]
 files += [ROOT/'experiments/003'/name for name in ['STAGE6-PLAN.md','STAGE6-B-SEED-AMENDMENT.md','STAGE6-REPORT.md']]
 patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'\bAKIA[0-9A-Z]{16}\b',rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b',rb'\bgithub_pat_[A-Za-z0-9_]{50,}\b']
 manifest={};hits=[];bad=[];large=[]
 for p in sorted(set(files)):
  data=p.read_bytes();name=str(p.relative_to(ROOT));manifest[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
  if any(re.search(pattern,data) for pattern in patterns):hits.append(name)
  if data.startswith(b'\x7fELF') or p.suffix in ['.pyc','.zip','.exe'] or p.name in ['.env','credentials']:bad.append(name)
  if len(data)>2*1024*1024:
   assert p.name in ['events.jsonl','server-events.jsonl','server-ledger.json','report.json','RESULTS.json','client-report.json'],name
   large.append(name)
  assert len(data)<64*1024*1024,name
 assert not hits and not bad,(hits,bad)
 primary_binary_checks={}
 f=json.loads((ROOT/'experiments/003/results/stage5/FROZEN-MANIFEST.json').read_text())
 for name,h in f['normal_build_binary_sha256'].items():
  if Path(name).exists():assert sha(Path(name))==h;primary_binary_checks[name]='UNCHANGED'
 (OUT/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
 result={'verdict':'PASS','matrix_status':matrix['status'],'files_hashed':len(manifest),'bytes_hashed':sum(v['bytes'] for v in manifest.values()),'max_file_bytes':max(v['bytes'] for v in manifest.values()),'primary_stage5_checksums_unchanged':len(old),'primary_normal_executables':primary_binary_checks,'preexisting_modified_or_deleted_files':[],'source_commits':{'application_and_A':a['source_commit'],'B2_preregistration':b['source_commit']},'same_application_binaries_A_B2':True,'credential_pattern_matches':hits,'executable_cache_credential_files':bad,'intentional_large_raw_or_analysis_files':large,'sha256_manifest_sha256':sha(OUT/'SHA256SUMS.json'),'limitations':'High-confidence known credential patterns/file types; not a proof against every sensitive value. RSS guards and peaks are sampled. Self-referential checksum/verification files excluded.'}
 (OUT/'PACKAGE-VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS:',len(manifest),'checksums; primary unchanged; no known credentials/cache/executable artifacts; largest',result['max_file_bytes'])
if __name__=='__main__':main()
