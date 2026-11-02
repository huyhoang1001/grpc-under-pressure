package e3

import "testing"

func TestSecondaryPartitionImmutableDeadlineAndNamespace(t *testing.T) {
	for _, deadline := range []uint64{500_000_000, 5_000_000_000} {
		for cid := 0; cid < 8; cid++ {
			m := Primary("secondary-test")
			for i := range m.Originals {
				m.Originals[i].ClientID = uint32(i % 8)
				m.Originals[i].Deadline = m.Originals[i].Scheduled + deadline
			}
			l, e := NewPolicyLedger(m, Retry, 42)
			if e != nil {
				t.Fatal(e)
			}
			if e = l.ConfigureSecondary(uint32(cid), 8, true); e != nil {
				t.Fatal(e)
			}
			if e = l.Arrive((cid+1)%8, 1_000_000_000); e != ErrProtocol {
				t.Fatal("foreign arrival", e)
			}
			now := m.Originals[cid].Scheduled
			if e = l.Arrive(cid, now); e != nil {
				t.Fatal(e)
			}
			w, e := l.BeginNext(now, uint64(cid))
			if e != nil {
				t.Fatal(e)
			}
			if w.MessageId != uint64(cid) || w.ClientId != uint32(cid) || w.DeadlineOffsetNs-w.ScheduledOffsetNs != deadline {
				t.Fatal(w)
			}
			if l.jitter(1) != 100_000_000 || l.jitter(2) != 200_000_000 {
				t.Fatal("deterministic delay")
			}
			if e = l.Verify(); e != nil {
				t.Fatal(e)
			}
		}
	}
}
func TestSecondaryPartialReconciliationHasOnlyOwnedOriginals(t *testing.T) {
	m := Primary("secondary-owned")
	for i := range m.Originals {
		m.Originals[i].ClientID = uint32(i % 8)
	}
	l, e := NewPolicyLedger(m, Retry, 42)
	if e != nil {
		t.Fatal(e)
	}
	if e = l.ConfigureSecondary(3, 8, false); e != nil {
		t.Fatal(e)
	}
	// An intentionally never-sent fixture: every owned original is still reconciled.
	l.Close(39_000_000_000)
	r, e := l.Reconcile(nil, 39_000_000_000)
	if e != nil {
		t.Fatal(e)
	}
	if r.N != 360 || len(r.Outcomes) != 360 || r.Counts[ExpiredBeforeSend] != 360 {
		t.Fatal(r.N, len(r.Outcomes), r.Counts)
	}
	for _, o := range r.Outcomes {
		if o.ID%8 != 3 {
			t.Fatal(o)
		}
	}
}

func TestSecondaryIndependentJitterGoldenVectors(t *testing.T) {
	vectors := []struct {
		seed uint64
		want [4]uint64
	}{{1, [4]uint64{88659719, 80202808, 64499479, 36876671}}, {^uint64(0), [4]uint64{65082916, 117654105, 37141423, 289017}}}
	for _, v := range vectors {
		l, e := NewPolicyLedger(Primary("jitter-golden"), Retry, v.seed)
		if e != nil {
			t.Fatal(e)
		}
		for i, number := range []uint32{1, 2, 1, 2} {
			if got := l.jitter(number); got != v.want[i] {
				t.Fatalf("seed %d index %d: %d != %d", v.seed, i, got, v.want[i])
			}
		}
	}
}
