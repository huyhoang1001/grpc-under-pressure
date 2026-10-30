package e3

import (
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"testing"
)

func policyLedger(t *testing.T, policy Policy) *Ledger {
	t.Helper()
	m := Primary("retry-test")
	for i := range m.Originals {
		m.Originals[i].Scheduled = 0
		m.Originals[i].Deadline = 2_000_000_000
	}
	l, e := NewPolicyLedger(m, policy, 1)
	if e != nil {
		t.Fatal(e)
	}
	return l
}
func refusal(l *Ledger, id, attempt, seq uint64) *p.ServerFrame {
	f := outcome(l, id, attempt, seq, 10)
	f.GetTerminalOutcome().Outcome = p.Outcome_REJECTED_OVERLOAD
	return f
}
func TestT14RealRetryLedgerAndT15MaximumAttempts(t *testing.T) {
	l := policyLedger(t, Retry)
	begin(t, l, 0, 10)
	for number := 1; number <= 3; number++ {
		id := uint64(9 + number)
		if err := l.Apply(refusal(l, 0, id, uint64(number)), uint64(number)*100); err != nil {
			t.Fatal(err)
		}
		if number == 3 {
			break
		}
		due := l.originals[0].ReadyAt
		if due < uint64(number)*100 || due > uint64(number)*100+(100_000_000<<uint(number-1)) {
			t.Fatal(due)
		}
		if due > uint64(number)*100 {
			if _, e := l.BeginNext(due-1, id+1); e != ErrBlocked {
				t.Fatal(e)
			}
		}
		w, e := l.BeginNext(due, id+1)
		if e != nil {
			t.Fatal(e)
		}
		if w.AttemptNumber != uint32(number+1) || w.DeadlineOffsetNs != 2_000_000_000 || string(w.Payload) != string(Payload(1)) {
			t.Fatal(w)
		}
	}
	s := l.Snapshot()
	if s.Attempts != 3 || s.FirstAttempts != 1 || s.Retries != 2 || s.Pending != 0 || s.Outstanding != 0 {
		t.Fatal(s)
	}
	if _, e := l.BeginNext(1_999_999_999, 100); e != ErrBlocked {
		t.Fatal(e)
	}
	if l.originals[0].ClientObserved != RejectedFinal {
		t.Fatal(l.originals[0])
	}
	if e := l.Verify(); e != nil {
		t.Fatal(e)
	}
}
func TestRetryOnlyExplicitRefusalNoAmbiguousOrDuplicateRetry(t *testing.T) {
	for _, policy := range []Policy{Wait, Reject, Drop, Retry} {
		l := policyLedger(t, policy)
		begin(t, l, 0, 1)
		f := refusal(l, 0, 1, 1)
		if policy == Retry {
			f.GetTerminalOutcome().Outcome = p.Outcome_DROPPED_OVERLOAD
		}
		if e := l.Apply(f, 10); e != nil {
			t.Fatal(e)
		}
		if l.Snapshot().Pending != 0 {
			t.Fatal(policy)
		}
	}
	l := policyLedger(t, Retry)
	begin(t, l, 0, 1)
	l.SendReturn(1, true, 1)
	l.Close(2)
	if l.Snapshot().Retries != 0 || l.Snapshot().Pending != 0 {
		t.Fatal(l.Snapshot())
	}
}
func TestT15DeadlineAndSharedPendingCapacity(t *testing.T) {
	l := policyLedger(t, Retry)
	begin(t, l, 0, 1)
	for i := 1; i <= 32; i++ {
		if e := l.Arrive(i, 0); e != nil {
			t.Fatal(e)
		}
	}
	if e := l.Apply(refusal(l, 0, 1, 1), 1); e != nil {
		t.Fatal(e)
	}
	if l.Snapshot().Pending != 32 || l.originals[0].Pending || l.originals[0].ClientObserved != RejectedFinal {
		t.Fatal(l.Snapshot())
	}
	for _, now := range []uint64{2_000_000_000, 2_000_000_001} {
		l := policyLedger(t, Retry)
		begin(t, l, 0, 1)
		if e := l.Apply(refusal(l, 0, 1, 1), now); e != nil {
			t.Fatal(e)
		}
		if l.Snapshot().Pending != 0 || l.originals[0].ClientObserved != ExpiredWaitingQueued {
			t.Fatal(l.originals[0])
		}
	}
	l = policyLedger(t, Retry)
	begin(t, l, 0, 1)
	if e := l.Apply(refusal(l, 0, 1, 1), 1_999_999_999); e != nil {
		t.Fatal(e)
	}
	if _, e := l.BeginNext(2_000_000_000, 2); e != ErrBlocked {
		t.Fatal(e)
	}
	if l.Snapshot().Attempts != 1 || l.originals[0].ClientObserved != ExpiredWaitingQueued {
		t.Fatal(l.originals[0])
	}
}
func TestRetrySeedReplayAndNoRetryPriority(t *testing.T) {
	a, b := policyLedger(t, Retry), policyLedger(t, Retry)
	for i := 0; i < 100; i++ {
		for n := uint32(1); n <= 2; n++ {
			x, y := a.jitter(n), b.jitter(n)
			if x != y || x > 100_000_000<<(n-1) {
				t.Fatal(x, y)
			}
		}
	}
	l := policyLedger(t, Retry)
	begin(t, l, 0, 1)
	if e := l.Arrive(1, 0); e != nil {
		t.Fatal(e)
	}
	if e := l.Apply(refusal(l, 0, 1, 1), 1); e != nil {
		t.Fatal(e)
	}
	w, e := l.BeginNext(2_000_000, 2)
	if e != nil || w.MessageId != 1 {
		t.Fatal(w, e)
	}
	// Duplicate old refusal cannot enqueue a second retry or release another credit.
	if e := l.Apply(refusal(l, 0, 1, 1), 2); e != nil {
		t.Fatal(e)
	}
	if l.Snapshot().Pending != 1 || l.Snapshot().Outstanding != 1 {
		t.Fatal(l.Snapshot())
	}
}
func TestRetryPendingExpiryReconcilesEveryOriginal(t *testing.T) {
	l := policyLedger(t, Retry)
	begin(t, l, 0, 1)
	l.Apply(refusal(l, 0, 1, 1), 1)
	if e := l.ExpirePending(2_000_000_000); e != nil {
		t.Fatal(e)
	}
	l.Close(3_000_000_000)
	r, e := l.Reconcile(nil, 39_000_000_000)
	if e != nil {
		t.Fatal(e)
	}
	if r.N != 2880 || r.Attempts != 1 || r.Retries != 0 || r.Counts[ExpiredWaitingQueued] != 1 || r.Counts[ExpiredBeforeSend] != 2879 {
		t.Fatal(r.Counts)
	}
}
