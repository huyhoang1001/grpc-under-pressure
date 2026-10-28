import hashlib,json,platform,subprocess,time
from pathlib import Path
ROOT=Path('/workspace/grpc-under-pressure');R=ROOT/'experiments/002/results/stage5';V=R/'primary-v2'
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
checks=R/'checks';checks.mkdir(exist_ok=True)
for label in ['python-tests','python-tests-amendment','fmt','rust-tests','clippy','build','go','freeze','matrix','freeze-v2','matrix-v2','verify-original','verify-v2','analysis-original','analysis-v2']:
    path=Path('/tmp/e2-stage5-'+label+'.log')
    if path.exists():(checks/(label+'.log')).write_bytes(path.read_bytes())
base='ccbd497f85346c7825394924a25db5617e5680e5'
paths=git('ls-tree','-r','--name-only',base,'experiments/001','experiments/002/results','experiments/002/EXPERIMENT-002.md','experiments/002/STAGE1-REPORT.md','experiments/002/STAGE2-REPORT.md','experiments/002/STAGE3-REPORT.md','experiments/002/STAGE4-REPORT.md').splitlines()
files=[]
for name in paths:
    expected=subprocess.check_output(['git','show',base+':'+name],cwd=ROOT);current=(ROOT/name).read_bytes()
    assert current==expected,name
    files.append({'path':name,'sha256':hashlib.sha256(current).hexdigest(),'bytes':len(current)})
save(R/'historical-integrity.json',{'baseline_commit':base,'verified_unchanged_files':len(files),'files':files})
sourceproof=[]
for folder in [R,V]:
    frozen=json.loads((folder/'FROZEN.json').read_text());commit=frozen['harness_commit']
    for name,digest in frozen['harness_source_sha256'].items():
        expected=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        assert hashlib.sha256(expected).hexdigest()==digest,(commit,name)
    for name,digest in frozen['application_source_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    for name,digest in frozen['binary_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    sourceproof.append({'cohort':str(folder.relative_to(R)),'harness_commit':commit,'all_harness_hashes_match_committed_bytes':True,'application_and_binaries_still_match_freeze':True})
save(R/'source-proof.json',sourceproof)
allrows=[];exclusions=[]
for prefix,folder,primary in [('original',R,False),('primary-v2',V,True)]:
    independent=json.loads((folder/'verification.json').read_text())
    for line in (folder/'ledger.jsonl').read_text().splitlines():
        row=json.loads(line);name=row['name'];m=json.loads((folder/name/'manifest.json').read_text())
        value={**row,'cohort':prefix,'path':str((folder/name).relative_to(ROOT)),'independent_issues':independent[name],'included_in_final_primary_estimates':primary and not independent[name]}
        allrows.append(value)
        if not value['included_in_final_primary_estimates']:
            exclusions.append({'cohort':prefix,'name':name,'valid_for_original_purpose':m['valid_for_declared_purpose'],'reason':'Entire original incomplete matrix kept separate under predeclared whole-matrix restart amendment; no selection by measured endpoints' if not independent[name] else 'Marker-reader task panic on transient empty file; no server workload start; client deadline120s; see startup-failure-diagnosis.json'})
(R/'ALL-ATTEMPTS.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in allrows))
save(R/'EXCLUSIONS.json',{'attempted_runs':len(allrows),'valid_attempts':sum(not row['independent_issues'] for row in allrows),'invalid_attempts':sum(bool(row['independent_issues']) for row in allrows),'final_primary_runs':sum(row['included_in_final_primary_estimates'] for row in allrows),'excluded_from_final_primary_estimates':exclusions,'individual_policy_replacements':0,'whole_matrix_restarts':1})
model={}
for line in Path('/proc/cpuinfo').read_text().splitlines():
    if ':' in line:
        key,value=line.split(':',1)
        if key.strip() in ['vendor_id','model name','cpu cores','siblings'] and key.strip() not in model:model[key.strip()]=value.strip()
save(R/'postrun-environment-supplement.json',{'captured_unix_ns':time.time_ns(),'cpu_info_selected_fields':model,'note':'Selected hardware detail captured after collection, not a change of experimental configuration. Primary pre-run environment/affinity/cgroup values are in FROZEN.json.'})
print('Preserved historical files',len(files),'attempts',len(allrows))
