package e3

import "fmt"

type Policy string

const (
	Wait   Policy = "wait"
	Reject Policy = "reject"
	Retry  Policy = "retry"
	Drop   Policy = "drop"
)

func NewPolicyLedger(m Manifest, policy Policy, seed uint64) (*Ledger, error) {
	if policy != Wait && policy != Reject && policy != Retry && policy != Drop {
		return nil, fmt.Errorf("unknown policy %q", policy)
	}
	l, err := NewLedger(m)
	if err != nil {
		return nil, err
	}
	l.policy, l.rng = policy, seed
	return l, nil
}

// SplitMix64 with rejection sampling: reproducible inclusive uniform nanosecond
// jitter. One ledger per client; seed must be recorded in its run manifest.
func (l *Ledger) jitter(number uint32) uint64 {
	capNS := uint64(100000000) << (number - 1)
	if capNS > 400000000 {
		capNS = 400000000
	}
	bound := capNS + 1
	for {
		l.rng += 0x9e3779b97f4a7c15
		z := l.rng
		z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9
		z = (z ^ (z >> 27)) * 0x94d049bb133111eb
		z ^= z >> 31
		if z >= -bound%bound {
			return z % bound
		}
	}
}

// Fixed-array min heap: new originals and retries share exactly32 entries.
// Earliest ready time first; insertion order breaks ties, with no retry priority.
func (l *Ledger) lessPending(i, j int) bool {
	a, b := l.originals[l.pending[i]], l.originals[l.pending[j]]
	return a.ReadyAt < b.ReadyAt || a.ReadyAt == b.ReadyAt && a.PendingOrder < b.PendingOrder
}
func (l *Ledger) down(i int) {
	for {
		j := 2*i + 1
		if j >= l.pendingN {
			return
		}
		if j+1 < l.pendingN && l.lessPending(j+1, j) {
			j++
		}
		if !l.lessPending(j, i) {
			return
		}
		l.pending[i], l.pending[j] = l.pending[j], l.pending[i]
		i = j
	}
}
func (l *Ledger) heapify() {
	for i := l.pendingN/2 - 1; i >= 0; i-- {
		l.down(i)
	}
}
func (l *Ledger) pushPending(id int) {
	l.pendingOrder++
	l.originals[id].PendingOrder = l.pendingOrder
	i := l.pendingN
	l.pending[i] = id
	l.pendingN++
	for i > 0 {
		parent := (i - 1) / 2
		if !l.lessPending(i, parent) {
			break
		}
		l.pending[i], l.pending[parent] = l.pending[parent], l.pending[i]
		i = parent
	}
}
func (l *Ledger) popPending() {
	l.pendingN--
	l.pending[0] = l.pending[l.pendingN]
	if l.pendingN > 0 {
		l.down(0)
	}
}
