#!/usr/bin/env python3
"""Stage4 pilot regressions; no primary workload."""
import argparse,json,subprocess,time,hashlib,platform,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sources():return {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'experiments/003').rglob('*') if p.is_file() and not any(x in p.parts for x in ['target','results','__pycache__'])}
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);args=a.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 manifest={'fixture_only':True,'not_primary':True,'contract_revision':'A01','client_outstanding_limit':33,'client_pending_limit':32,'server_admission_limit':32,'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'dirty_state':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'source_hashes_before':sources(),'environment':platform.uname()._asdict(),'commands':[]}
 steps=[('rust-fmt','cargo fmt --manifest-path experiments/003/server/Cargo.toml -- --check'),('rust-build','cargo build --locked --manifest-path experiments/003/server/Cargo.toml'),('rust-tests','cargo test --locked --manifest-path experiments/003/server/Cargo.toml'),('rust-clippy','cargo clippy --locked --manifest-path experiments/003/server/Cargo.toml --all-targets -- -D warnings'),('go-checks','cd experiments/003/client && go mod verify && go test -mod=readonly -race -count=3 -v ./... && go vet ./... && go build -mod=readonly -o /workspace/toolchains/bin/e3-stage1-smoke ./cmd/smoke && go build -mod=readonly -o /workspace/toolchains/bin/e3-stage2-policy-smoke ./cmd/policy-smoke && go build -mod=readonly -o /workspace/toolchains/bin/e3-a01-credit-smoke ./cmd/credit-smoke && go build -mod=readonly -o /workspace/toolchains/bin/e3-pilot ./cmd/pilot'),('fixture-build','cargo build --locked --manifest-path experiments/003/server/Cargo.toml --examples'),('legacy-rust','cargo test --locked --manifest-path server/Cargo.toml'),('legacy-go','cd experiments/002/client && go test -mod=readonly -race ./...'),('versions','rustc -Vv && cargo -V && go version')]
 for policy in ['wait','reject','retry','drop']:
  for rep in range(1,4):steps.append((f'transport-{policy}-{rep}',f'E3_TEST_POLICY={policy} cargo test --locked --manifest-path experiments/003/server/Cargo.toml --test transport -- --test-threads=1'))
 try:
  for name,command in steps:
   print(name,flush=True);cmd=['bash','-c','source scripts/dev-env.sh\n'+command];start=time.monotonic()
   with (out/(name+'.log')).open('x') as log:run=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=120)
   manifest['commands'].append({'name':name,'argv':cmd,'exit':run.returncode,'elapsed_seconds':time.monotonic()-start})
   if run.returncode:raise RuntimeError(name+' failed')
  manifest['source_hashes_after']=sources();assert manifest['source_hashes_before']==manifest['source_hashes_after'];manifest['verdict']='PASS'
 except Exception as error:manifest['verdict']='FAIL';manifest['error']=repr(error);raise
 finally:(out/'verification.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
