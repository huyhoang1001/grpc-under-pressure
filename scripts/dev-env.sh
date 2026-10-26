# Source from the repository root; all writable caches stay outside the checkout.
export RUSTUP_HOME=/workspace/toolchains/rustup
export CARGO_HOME=/workspace/toolchains/cargo
export GOPATH=/workspace/toolchains/gopath
export GOCACHE=/workspace/toolchains/go-cache
export GOBIN=/workspace/toolchains/bin
export PATH="$CARGO_HOME/bin:/workspace/toolchains/go/bin:$GOBIN:$PATH"
