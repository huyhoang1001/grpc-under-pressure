#!/usr/bin/env python3
"""Integrity/provenance and high-confidence credential-pattern scan; no workloads."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5];OUT=ROOT/'experiments/003/results/stage5'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 frozen=json.loads((OUT/'FROZEN-MANIFEST.json').read_text());matrix=json.loads((OUT/'MATRIX.json').read_text())
 assert matrix['status']=='COMPLETE' and digest(OUT/'FROZEN-MANIFEST.json')==matrix['frozen_sha256']
 assert all(digest(ROOT/p)==h for p,h in frozen['source_sha256'].items())
 excluded={'SHA256SUMS.json','PACKAGE-VERIFICATION.json'}
 files=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name not in excluded)
 files += [ROOT/'experiments/003/STAGE5-REPORT.md',ROOT/'experiments/003/STAGE5-PLAN.md']
 files += [ROOT/'experiments/003/fixtures'/p for p in ['stage5.py','primary-run.py','verify-stage5.py','analyze-stage5.py']]
 patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'\bAKIA[0-9A-Z]{16}\b',rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b',rb'\bgithub_pat_[A-Za-z0-9_]{50,}\b']
 hits=[];bad=[];expected_large=[];manifest={}
 for p in files:
  data=p.read_bytes();relative=str(p.relative_to(ROOT));manifest[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
  if any(re.search(pattern,data) for pattern in patterns):hits.append(relative)
  if data.startswith(b'\x7fELF') or p.suffix in ['.pyc','.zip','.exe'] or p.name in ['.env','credentials']:bad.append(relative)
  if len(data)>2*1024*1024:
   assert p.name in ['server-events.jsonl','client-events.jsonl','server-ledger.json','client-report.json'],relative
   expected_large.append(relative)
  assert len(data)<64*1024*1024,relative
 assert not hits and not bad,(hits,bad)
 old_modified=subprocess.check_output(['git','diff','--diff-filter=MD','--name-only',frozen['application_baseline_commit'],'--','experiments/001','experiments/002','experiments/003'],cwd=ROOT,text=True).splitlines()
 assert not old_modified,old_modified
 (OUT/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
 result={'verdict':'PASS','source_commit':frozen['source_commit'],'frozen_hashes_unchanged':True,'historical_modified_or_deleted_files':old_modified,'files_hashed':len(manifest),'bytes_hashed':sum(x['bytes'] for x in manifest.values()),'max_file_bytes':max(x['bytes'] for x in manifest.values()),'credential_pattern_matches':hits,'binary_cache_or_credential_file_matches':bad,'intentional_raw_artifacts_over_2MiB':expected_large,'scan_limitations':'High-confidence known credential formats and file types; not a proof that every possible sensitive value is absent. Manifests contain selected runtime variables only, not complete environment dumps.','checksum_manifest_sha256':digest(OUT/'SHA256SUMS.json'),'excluded_self_referential_files':sorted(excluded)}
 (OUT/'PACKAGE-VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS:',len(manifest),'files hashed;',result['max_file_bytes'],'largest bytes; no known credentials or executable/cache artifacts; historical files unchanged')
if __name__=='__main__':main()
