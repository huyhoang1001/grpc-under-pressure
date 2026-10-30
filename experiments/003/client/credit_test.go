package e3

import "testing"

func TestA01Exact33CreditBoundaryAndRelease(t *testing.T) {
	l := testLedger(t)
	if OutstandingCapacity != 33 || PendingCapacity != 32 || ResponseCapacity != 64 {
		t.Fatal("contract drift")
	}
	for i := 0; i < OutstandingCapacity; i++ {
		begin(t, l, i, uint64(i))
	}
	if err := l.Verify(); err != nil {
		t.Fatal("33 must be valid", err)
	}
	if err := l.Arrive(33, 0); err != nil {
		t.Fatal(err)
	}
	if _, err := l.BeginNext(0, 33); err != ErrBlocked {
		t.Fatal("34th outstanding must block", err)
	}
	if l.Snapshot().Pending != 1 || l.Snapshot().Outstanding != 33 {
		t.Fatal(l.Snapshot())
	}
	if err := l.Apply(outcome(l, 0, 0, 1, 1), 1); err != nil {
		t.Fatal(err)
	}
	w, err := l.BeginNext(1, 33)
	if err != nil || w.MessageId != 33 {
		t.Fatal(w, err)
	}
	if err := l.Verify(); err != nil {
		t.Fatal(err)
	}
	l.Close(2)
	if l.Snapshot().Outstanding != 0 || l.Snapshot().Pending != 0 {
		t.Fatal(l.Snapshot())
	}
}
