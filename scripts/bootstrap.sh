#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p /workspace/toolchains
python3 - <<'PY'
import hashlib, json, pathlib, tarfile, urllib.request
base = pathlib.Path('/workspace/toolchains')
def download(url, path, checksum):
    urllib.request.urlretrieve(url, path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise RuntimeError('SHA256 verification failed: ' + path.name)
if not (base / 'go/bin/go').exists():
    releases = json.load(urllib.request.urlopen('https://go.dev/dl/?mode=json&include=all'))
    artifact = next(f for v in releases if v['version'] == 'go1.27.3' for f in v['files']
                    if f['os'] == 'linux' and f['arch'] == 'amd64' and f['kind'] == 'archive')
    archive = base / artifact['filename']
    download('https://go.dev/dl/' + artifact['filename'], archive, artifact['sha256'])
    with tarfile.open(archive) as source:
        source.extractall(base, filter='data')
if not (base / 'cargo/bin/rustup').exists():
    url = 'https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init'
    digest = urllib.request.urlopen(url + '.sha256').read().decode().split()[0]
    installer = base / 'rustup-init'
    download(url, installer, digest)
    installer.chmod(0o755)
PY
source scripts/dev-env.sh
if [[ ! -x "$CARGO_HOME/bin/rustup" ]]; then
 /workspace/toolchains/rustup-init -y --no-modify-path --profile minimal --default-toolchain 1.99.1
fi
rustup toolchain install 1.99.1 --profile minimal --component rustfmt --component clippy
[[ "$(go version)" == 'go version go1.27.3 linux/amd64' ]]
cargo fetch --locked --manifest-path server/Cargo.toml
(cd loadgen && go mod download && go mod verify)
bash scripts/check.sh
