#!/usr/bin/env python3
"""Capture selected reproducibility data or audit historical bytes; no benchmarks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'experiments/002'))
from verify import read


def command(*args,cwd=ROOT):
    return subprocess.check_output(args,cwd=cwd,text=True).strip()

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--environment',action='store_true');a=p.parse_args();root=a.directory;root.mkdir(parents=True,exist_ok=True)
    if a.environment:
        save(root/'environment.json',{
            'source_commit':command('git','rev-parse','HEAD'),'captured_unix_ns':__import__('time').time_ns(),
            'accepted_archive_commit':'e32bc0ab4639ece7991a587758f5ccb441db3627',
            'client_source_commit':'84509545abf6a5f139687250757e67703477a5c1',
            'rustc':command('rustc','-Vv'),'cargo':command('cargo','-V'),'go':command('go','version'),
            'client_build_info':command('go','version','-m','/workspace/toolchains/bin/pressure-stage1-client'),
            'os_release':Path('/etc/os-release').read_text(),'kernel':platform.release(),
            'cpu_affinity':sorted(os.sched_getaffinity(0)),
            'cgroup_cpu_max':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
            'cgroup_memory_max':Path('/sys/fs/cgroup/memory.max').read_text().strip(),
            'rust_dependencies':command('cargo','tree','--locked','--manifest-path','server/Cargo.toml'),
            'go_modules':command('go','list','-mod=readonly','-m','all',cwd=ROOT/'experiments/002/client'),
            'protoc':'31.1 via pinned protoc-bin-vendored 3.2.0',
            'build_mode':'debug Rust; default optimized Go; identical to Stage2/3',
            'binary_sha256':{str(path):sha(path) for path in [ROOT/'server/target/debug/pressure-stage1',Path('/workspace/toolchains/bin/pressure-stage1-client')]},
            'buildcheck_only_client':'/workspace/toolchains/bin/pressure-stage4-client-buildcheck; never used for measurements',
            'contract_sha256':sha(ROOT/'experiments/002/EXPERIMENT-002.md')})
        print('Selected environment captured (no environment-variable dump)');return
    base='e32bc0ab4639ece7991a587758f5ccb441db3627'
    paths=command('git','ls-tree','-r','--name-only',base,'experiments/001','experiments/002/results','experiments/002/EXPERIMENT-002.md','experiments/002/STAGE1-REPORT.md','experiments/002/STAGE2-REPORT.md','experiments/002/STAGE3-REPORT.md').splitlines()
    files=[]
    for name in paths:
        original=subprocess.check_output(['git','show',base+':'+name],cwd=ROOT);current=(ROOT/name).read_bytes()
        assert current==original,name
        files.append({'path':name,'sha256':hashlib.sha256(current).hexdigest(),'bytes':len(current)})
    save(root/'historical-integrity.json',{'baseline_commit':base,'verified_unchanged_files':len(files),'files':files})
    supplements={}
    for path in sorted(root.glob('*/manifest.json')):
        process=read(path.parent/'process.csv');stats={}
        for role in ['server','client']:
            rows=[r for r in process if r['role']==role]
            first,last=rows[0],rows[-1]
            wall=(int(last['monotonic_ns'])-int(first['monotonic_ns']))/1e9
            ticks=lambda r:int(r['utime_ticks'])+int(r['stime_ticks'])
            cpu=(ticks(last)-ticks(first))/int(last['CLK_TCK'])
            stats[role]={'observed_cpu_s':cpu,'observed_wall_s':wall,'one_core_percent':100*cpu/wall,'peak_rss_bytes':max(int(r['rss_bytes']) for r in rows)}
        supplements[path.parent.name]={'process':stats,'final_server':read(path.parent/'server/server.csv')[-1]}
    save(root/'supplement.json',supplements)
    print(f'{len(paths)} historical files byte-identical; {len(supplements)} process summaries')
if __name__=='__main__':main()
