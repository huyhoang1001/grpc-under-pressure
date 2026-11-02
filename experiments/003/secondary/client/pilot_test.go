package e3

import "testing"

func TestPilotBulkExpiryEventsHavePostRemovalOccupancy(t *testing.T) {
	l := testLedger(t)
	for i := 0; i < 5; i++ {
		if e := l.Arrive(i, 0); e != nil {
			t.Fatal(e)
		}
	}
	for {
		_, ok := l.PopEvent()
		if !ok {
			break
		}
	}
	if e := l.ExpirePending(2_000_000_000); e != nil {
		t.Fatal(e)
	}
	n := 5
	for {
		e, ok := l.PopEvent()
		if !ok {
			break
		}
		if e.Kind == "expired_before_send" {
			n--
			if e.Pending != n {
				t.Fatalf("stale occupancy: event%+v expected%d", e, n)
			}
		}
	}
	if n != 0 || l.Snapshot().Pending != 0 {
		t.Fatal(n, l.Snapshot())
	}
	if e := l.Verify(); e != nil {
		t.Fatal(e)
	}
}
