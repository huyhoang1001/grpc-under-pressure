#!/usr/bin/env python3
"""Short correctness fixtures only. Never included in secondary comparisons."""
import importlib.util,json,subprocess,sys,time,platform
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'experiments/003/results/stage6'
spec=importlib.util.spec_from_file_location('run',Path(__file__).with_name('run.py'));R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
def main():
 tag=sys.argv[1];directory=OUT/'preflight'/tag;directory.mkdir(parents=True,exist_ok=False)
 paths=[p for p in (ROOT/'experiments/003/secondary').rglob('*') if p.is_file() and 'target' not in p.parts and '__pycache__' not in p.parts]
 server=ROOT/'experiments/003/secondary/server/target/debug/pressure-e3-stage1';client=Path('/tmp/e3-secondary-client')
 frozen={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_sha256':{str(p.relative_to(ROOT)):R.sha(p) for p in paths},'binary_sha256':{str(p):R.sha(p) for p in [server,client]},'server_binary':str(server),'client_binary':str(client),'cgroup':{p:Path('/sys/fs/cgroup/'+p).read_text().strip() for p in ['cpu.max','memory.max']},'toolchains':subprocess.check_output(['bash','-c','source scripts/dev-env.sh; rustc -Vv; cargo -V; go version'],cwd=ROOT,text=True),'fixture_only':True,'dirty_state':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)}
 R.save(directory/'FROZEN-MANIFEST.json',frozen);R.FREEZE=directory/'FROZEN-MANIFEST.json'
 plan=json.loads((OUT/'RUN-PLAN.json').read_text());cases=[next(c for c in plan['blocks'][0]['cases'] if c['name']==name) for name in ['a500-wait','a5000-wait']]+plan['blocks'][5]['cases']
 results=[]
 for case in cases:
  verdict=R.run(case,directory/case['name'],True);results.append({'case':case,'outcome':verdict});R.save(directory/(case['name']+'-registry.json'),results[-1])
  if verdict['verdict']!='PASS':raise SystemExit(1)
 print('PASS: four short fixtures, not secondary performance evidence')
if __name__=='__main__':main()
