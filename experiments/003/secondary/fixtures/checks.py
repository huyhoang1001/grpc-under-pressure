#!/usr/bin/env python3
"""Final structured pre-study checks; no performance workloads."""
import json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'experiments/003/results/stage6/checks/validated'
commands=[('rust-fmt','cargo fmt --manifest-path experiments/003/secondary/server/Cargo.toml --check'),('rust-tests','cargo test --locked --manifest-path experiments/003/secondary/server/Cargo.toml'),('clippy','cargo clippy --locked --manifest-path experiments/003/secondary/server/Cargo.toml --all-targets -- -D warnings'),('go-race','cd experiments/003/secondary/client\ngo test -race -count=3 ./...'),('go-vet','cd experiments/003/secondary/client\ngo vet ./...'),('go-mod','cd experiments/003/secondary/client\ngo mod verify'),('analysis','python3 experiments/003/secondary/fixtures/analyze.py --selftest'),('normal-build','cargo build --locked --manifest-path experiments/003/secondary/server/Cargo.toml')]
def main():
 OUT.mkdir(exist_ok=False);results=[]
 for name,command in commands:
  argv=['bash','-e','-c','source scripts/dev-env.sh\n'+command];started=time.time_ns();r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True);(OUT/(name+'.log')).write_text(r.stdout+r.stderr);results.append({'name':name,'argv':argv,'exit':r.returncode,'started_unix_ns':started,'log':name+'.log'});(OUT/'COMMANDS.json').write_text(json.dumps(results,indent=2)+'\n');print(name,r.returncode,flush=True)
  if r.returncode:raise SystemExit(r.returncode)
 print('PASS: eight structured check steps; normal target restored')
if __name__=='__main__':main()
