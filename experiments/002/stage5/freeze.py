#!/usr/bin/env python3
"""Exclusive-create a primary run freeze. Never invokes a workload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import time

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'experiments/002'
APP='ccbd497f85346c7825394924a25db5617e5680e5'
SERVER=ROOT/'server/target/debug/pressure-stage1'
CLIENT=Path('/workspace/toolchains/bin/pressure-stage1-client')

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def version(*args,cwd=ROOT):return subprocess.check_output(args,cwd=cwd,text=True).strip()
def order():
    rng=random.Random(2005);rows=[]
    for block in range(1,6):
        policies=['fixed32','fixed8','adaptive'];rng.shuffle(policies)
        for position,policy in enumerate(policies,1):
            rows.append({'block':block,'position':position,'policy':policy,'name':f'b{block:02}-{position:02}-{policy}'})
    return rows

def check(frozen):
    issues=[]
    for section in ['application_source_sha256','harness_source_sha256']:
        for name,digest in frozen[section].items():
            if not (ROOT/name).is_file() or sha(ROOT/name)!=digest:issues.append('frozen source mismatch '+name)
    for name,digest in frozen['binary_sha256'].items():
        if not Path(name).is_file() or sha(Path(name))!=digest:issues.append('frozen binary mismatch '+name)
    if sorted(os.sched_getaffinity(0))!=frozen['environment']['cpu_affinity']:issues.append('affinity changed')
    for key,path in [('cgroup_cpu_max','/sys/fs/cgroup/cpu.max'),('cgroup_memory_max','/sys/fs/cgroup/memory.max')]:
        if Path(path).read_text().strip()!=frozen['environment'][key]:issues.append(key+' changed')
    return issues

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    assert not git('diff','HEAD'), 'commit tracked source first'
    paths=git('ls-files','server','loadgen','proto','rust-toolchain.toml','experiments/002/server','experiments/002/client').splitlines()
    for name in paths:
        expected=subprocess.check_output(['git','show',APP+':'+name],cwd=ROOT)
        assert (ROOT/name).read_bytes()==expected,name
    accepted=json.loads((BASE/'results/stage4/environment.json').read_text())
    binaries={str(p):sha(p) for p in [SERVER,CLIENT]}
    assert binaries==accepted['binary_sha256'],'retained accepted binary mismatch; diagnose before running'
    harness=git('ls-files','experiments/002','scripts/dev-env.sh').splitlines()
    harness=[p for p in harness if '/results/' not in p]
    template=json.loads((BASE/'results/stage4/exploratory-adaptive/manifest.json').read_text())
    config={k:template[k] for k in ['service_schedule','event_io','sample_ms','rate','offered_seconds','payload_bytes','seed','physical_K','controller','windows','runtime','build_mode','limits']}
    value={'schema':'e2-stage5-freeze-v1','frozen_unix_ns':time.time_ns(),'application_source_commit':APP,'harness_commit':git('rev-parse','HEAD'),'client_build_source_commit':'84509545abf6a5f139687250757e67703477a5c1','git_status_porcelain':git('status','--porcelain=v1','--untracked-files=all'),'application_source_sha256':{p:sha(ROOT/p) for p in paths},'harness_source_sha256':{p:sha(ROOT/p) for p in harness},'binary_sha256':binaries,'configuration':config,'policy_initial_budgets':{'fixed32':32,'fixed8':8,'adaptive':16},'order_seed':2005,'order':order(),'analysis_plan':'experiments/002/stage5/PLAN.md','analysis_plan_sha256':sha(BASE/'stage5/PLAN.md'),'resampling':'all 3125 ordered block bootstrap samples; nearest-rank percentile 95%','environment':{'os_release':Path('/etc/os-release').read_text(),'kernel':platform.release(),'cpu_affinity':sorted(os.sched_getaffinity(0)),'cgroup_cpu_max':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),'cgroup_memory_max':Path('/sys/fs/cgroup/memory.max').read_text().strip(),'rustc':version('rustc','-Vv'),'cargo':version('cargo','-V'),'go':version('go','version'),'client_build_info':version('go','version','-m',str(CLIENT)),'rust_dependencies':version('cargo','tree','--locked','--manifest-path','server/Cargo.toml'),'go_modules':version('go','list','-mod=readonly','-m','all',cwd=BASE/'client'),'python':platform.python_version(),'protoc':'31.1 via pinned protoc-bin-vendored3.2.0'}}
    assert not check(value)
    a.output.mkdir(parents=True,exist_ok=False)
    with (a.output/'FROZEN.json').open('x') as out:json.dump(value,out,indent=2);out.write('\n')
    print('Freeze SHA256',sha(a.output/'FROZEN.json'))
    for row in value['order']:print(row['name'])
if __name__=='__main__':main()
