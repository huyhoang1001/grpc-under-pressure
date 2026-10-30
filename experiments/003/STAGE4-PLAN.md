# E3 Stage4 pre-execution pilot plan

Contract A01, no worker barriers or injected outcomes; no primary comparison.

Predeclared sequence, one fresh server/client per run:

1. `low-wait`: WAIT,10 scheduled originals/s for4s,40 originals, cutoff7s.
2. `overload-wait`: WAIT, frozen80/s for36s,N2880, cutoff39s.
3. `overload-reject`: REJECT, same frozen workload/cutoff.
4. `overload-retry`: RETRY, same frozen workload/cutoff.
5. `overload-drop`: DROP, same frozen workload/cutoff.
6. `overhead-wait-buffered`: WAIT, same frozen workload/cutoff, only client event-output buffering changes from0 to65536 bytes. One matched instrumentation control, not a policy comparison or sufficient replication for performance conclusions.

All runs: payload16384, seed1/jitter seed1, scheduled+2s immutable deadlines, max3 attempts, outstanding33/pending32/server admission32, one worker, service10/40/10ms selected at start with12/24s boundaries, HTTP/2 windows65535, no compression/configured retry/replay buffer. Debug build preserved from Stage3; no build-profile comparison. Default Hooks only, never the correctness fixture executable. No optional legacy no-op sweep logging. Hold both processes/ledgers and process sampling through the declared cutoff even when RPC EOF occurs earlier.

Safety limits declared before pilots: per-process CPU30s, RSS256MiB (external200ms monitor, observed-bound guard), log/output file64MiB, core0, overall wall bound cutoff+12s; hard-kill/reap on supervision failure. These explicit pilot guards scale the short Stage3 fixture's CPU5s/file16MiB budget for a39s/2880-original run; they are not changes to application queues/deadlines. No guard will be weakened after an abort. Record inherited cgroup/host limits, all commands and process exits. Only one pilot active at a time. A safety violation stops subsequent pilots pending diagnosis; preserve every attempt.

Validity: strict clock span<5ms;200ms process sampling with gaps<500ms, covering epoch through cutoff; complete logs/tails and all originals/attempts independently reconciled; bounded queues/permits with zero final ownership; normal EOF, joined tasks and flushed logs before shutdown; phase markers aligned and actual service time checked by worker start phase. Genuine refusal/retry/drop activation is measured, not required to manufacture a PASS. Unexpected absence must be reported. No claim of policy superiority, hypothesis confirmation or negligible instrumentation overhead.

If a correctness/measurement blocker requires a source fix, preserve the failure, document it, rerun relevant tests and explicitly identify final-source pilot evidence. Do not silently change parameters or select favorable outcomes.
