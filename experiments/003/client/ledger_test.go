package e3

import (
	"context"
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"google.golang.org/grpc/metadata"
	"io"
	"sync"
	"testing"
	"time"
)

func testLedger(t *testing.T) *Ledger {
	t.Helper()
	m := Primary("client-test")
	for i := range m.Originals {
		m.Originals[i].Scheduled = 0
		m.Originals[i].Deadline = 2_000_000_000
	}
	l, e := NewLedger(m)
	if e != nil {
		t.Fatal(e)
	}
	return l
}
func begin(t *testing.T, l *Ledger, id int, attempt uint64) {
	t.Helper()
	if e := l.Arrive(id, 0); e != nil {
		t.Fatal(e)
	}
	if _, e := l.BeginNext(0, attempt); e != nil {
		t.Fatal(e)
	}
}
func outcome(l *Ledger, id, attempt, seq, offset uint64) *p.ServerFrame {
	return &p.ServerFrame{Frame: &p.ServerFrame_TerminalOutcome{TerminalOutcome: &p.TerminalOutcome{RunId: l.manifest.RunID, MessageId: id, AttemptId: attempt, Outcome: p.Outcome_COMPLETED, ServerEventSeq: seq, ServerEventOffsetNs: offset, DetailCode: "COMPLETED"}}}
}
func TestT01All2880UnsentAndPartition(t *testing.T) {
	l := testLedger(t)
	r, e := l.Reconcile(&ServerSnapshot{RunID: l.manifest.RunID}, 39_000_000_000)
	if e != nil {
		t.Fatal(e)
	}
	if r.N != 2880 || r.U != 0 || r.Attempts != 0 || len(r.Outcomes) != 2880 || r.Counts[ExpiredBeforeSend] != 2880 {
		t.Fatalf("bad partition: %+v", r.Counts)
	}
}
func TestT02PendingOverflowOutstandingAndExpiry(t *testing.T) {
	l := testLedger(t)
	for id := 0; id < 32; id++ {
		begin(t, l, id, uint64(id))
	}
	for id := 32; id <= 64; id++ {
		if e := l.Arrive(id, 0); e != nil {
			t.Fatal(e)
		}
	}
	s := l.Snapshot()
	if s.Pending != 32 || s.Outstanding != 32 || l.originals[64].ClientObserved != ClientBacklogExhausted {
		t.Fatal(s)
	}
	if _, e := l.BeginNext(0, 100); e != ErrBlocked {
		t.Fatal(e)
	}
	if e := l.ExpirePending(2_000_000_000); e != nil {
		t.Fatal(e)
	}
	if e := l.ObserveOutstandingDeadlines(2_000_000_000); e != nil {
		t.Fatal(e)
	}
	s = l.Snapshot()
	if s.Pending != 0 || s.Outstanding != 32 {
		t.Fatal(s)
	}
	l.Close(3_000_000_000)
	r, e := l.Reconcile(nil, 39_000_000_000)
	if e != nil {
		t.Fatal(e)
	}
	sum := 0
	for _, n := range r.Counts {
		sum += n
	}
	if sum != 2880 || r.Counts[Unknown] != 32 || r.Counts[ClientBacklogExhausted] != 1 {
		t.Fatal(r.Counts)
	}
}
func TestT05SendSuccessNeverImpliesAdmissionOrRetry(t *testing.T) {
	l := testLedger(t)
	begin(t, l, 0, 99)
	if e := l.SendReturn(99, true, 1); e != nil {
		t.Fatal(e)
	}
	l.Close(2)
	r, e := l.Reconcile(&ServerSnapshot{RunID: l.manifest.RunID}, 39_000_000_000)
	if e != nil {
		t.Fatal(e)
	}
	if r.SendSuccess != 1 || r.U != 0 || r.Counts[Unknown] != 1 || !r.Outcomes[0].Ambiguity {
		t.Fatal(r.Counts)
	}
	if _, e := l.BeginNext(3, 100); e != ErrClosed {
		t.Fatal(e)
	}
}
func TestT11T12T19BoundaryLateCompletionAndLostAck(t *testing.T) {
	for _, offset := range []uint64{2_000_000_000, 2_000_000_001} {
		l := testLedger(t)
		begin(t, l, 0, 11)
		if e := l.ObserveOutstandingDeadlines(2_000_000_000); e != nil {
			t.Fatal(e)
		}
		l.Close(3_000_000_000)
		r, e := l.Reconcile(&ServerSnapshot{RunID: l.manifest.RunID, Originals: []ServerOriginal{{ID: 0, Starts: 1, Terminal: &ServerResult{Outcome: 1, Seq: 42, Offset: offset, Detail: "COMPLETED"}}}}, 39_000_000_000)
		if e != nil {
			t.Fatal(e)
		}
		expected := CompletedOnTime
		if offset > 2_000_000_000 {
			expected = CompletedLate
		}
		if r.Outcomes[0].Disposition != expected || !r.Outcomes[0].AckMissing || r.Outcomes[0].ClientObserved != "CLIENT_TIMEOUT" {
			t.Fatal(r.Outcomes[0])
		}
	}
}
func TestTerminalDedupCreditAndChangedResponse(t *testing.T) {
	l := testLedger(t)
	begin(t, l, 0, 7)
	f := outcome(l, 0, 7, 8, 1)
	if e := l.Apply(f, 2); e != nil {
		t.Fatal(e)
	}
	dup := outcome(l, 0, 7, 8, 1)
	term := dup.GetTerminalOutcome()
	term.Outcome = p.Outcome_DUPLICATE_RESULT
	term.ReferencedTerminal = &p.TerminalReference{Outcome: p.Outcome_COMPLETED, ServerEventSeq: 8, ServerEventOffsetNs: 1, DetailCode: "COMPLETED"}
	var group sync.WaitGroup
	for i := 0; i < 20; i++ {
		group.Add(1)
		go func() {
			defer group.Done()
			if e := l.Apply(dup, 3); e != nil {
				t.Error(e)
			}
		}()
	}
	group.Wait()
	if l.Snapshot().Outstanding != 0 {
		t.Fatal("credit leaked")
	}
	changed := outcome(l, 0, 7, 9, 2)
	if e := l.Apply(changed, 4); e != ErrProtocol {
		t.Fatal(e)
	}
	if e := l.Verify(); e != nil {
		t.Fatal(e)
	}
}
func TestReconciliationRefusalSupersededByCompletionAndExpiryKinds(t *testing.T) {
	l := testLedger(t)
	begin(t, l, 0, 0)
	l.Close(1)
	r, e := l.Reconcile(&ServerSnapshot{RunID: l.manifest.RunID, Originals: []ServerOriginal{{ID: 0, Starts: 1, Terminal: &ServerResult{Outcome: int32(p.Outcome_COMPLETED), Seq: 10, Offset: 100}}}}, 39_000_000_000)
	if e != nil || r.Outcomes[0].Disposition != CompletedOnTime {
		t.Fatal(e, r.Counts)
	}
	for _, detail := range []string{"EXPIRED_QUEUED", "EXPIRED_PROCESSING"} {
		srv := &ServerSnapshot{RunID: l.manifest.RunID, Originals: []ServerOriginal{{ID: 0, Terminal: &ServerResult{Outcome: int32(p.Outcome_EXPIRED), Seq: 10, Offset: 2_000_000_000, Detail: detail}}}}
		r, e = l.Reconcile(srv, 39_000_000_000)
		if e != nil {
			t.Fatal(e)
		}
		expected := ExpiredWaitingQueued
		if detail == "EXPIRED_PROCESSING" {
			expected = ExpiredProcessing
		}
		if r.Outcomes[0].Disposition != expected {
			t.Fatal(r.Outcomes[0])
		}
	}
}
func TestT17MetadataAndEventBounds(t *testing.T) {
	m := Primary("x")
	m.Originals = append(m.Originals, m.Originals[0])
	if _, e := NewLedger(m); e == nil {
		t.Fatal("accepted oversized ledger")
	}
	l := testLedger(t)
	for i := 0; i < 1024; i++ {
		if e := l.ExpirePending(uint64(i)); e != nil {
			t.Fatal(e)
		}
	}
	if e := l.Arrive(0, 0); e != ErrEventFull {
		t.Fatal(e)
	}
	if l.originals[0].Arrived {
		t.Fatal("unlogged mutation")
	}
	for i := 1; i <= 1024; i++ {
		event, ok := l.PopEvent()
		if !ok || event.Seq != uint64(i) {
			t.Fatal(i, event)
		}
	}
	if l.Verify() == nil {
		t.Fatal("event pressure cancellation not marked invalid")
	}
	l = testLedger(t)
	if e := l.Arrive(0, 0); e != nil {
		t.Fatal(e)
	}
	l.used = AttemptCapacity
	if _, e := l.BeginNext(0, 99); e != ErrCapacity {
		t.Fatal(e)
	}
}

// A deliberately blocking transport, not a claim about remote application reads.
type fakeStream struct {
	ctx     context.Context
	frames  chan *p.ServerFrame
	unblock chan struct{}
	entered chan struct{}
}

func (f *fakeStream) Send(*p.ClientFrame) error {
	close(f.entered)
	select {
	case <-f.unblock:
		return nil
	case <-f.ctx.Done():
		return f.ctx.Err()
	}
}
func (f *fakeStream) Recv() (*p.ServerFrame, error) {
	select {
	case v, ok := <-f.frames:
		if !ok {
			return nil, io.EOF
		}
		return v, nil
	case <-f.ctx.Done():
		return nil, f.ctx.Err()
	}
}
func (f *fakeStream) Header() (metadata.MD, error) { return nil, nil }
func (f *fakeStream) Trailer() metadata.MD         { return nil }
func (f *fakeStream) CloseSend() error             { return nil }
func (f *fakeStream) Context() context.Context     { return f.ctx }
func (f *fakeStream) SendMsg(any) error            { return nil }
func (f *fakeStream) RecvMsg(any) error            { return nil }
func TestT08ReceiveReleasesCreditWhileSendBlocked(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	l := testLedger(t)
	begin(t, l, 0, 4)
	f := &fakeStream{ctx: ctx, frames: make(chan *p.ServerFrame, 1), unblock: make(chan struct{}), entered: make(chan struct{})}
	sent := make(chan error, 1)
	go func() { sent <- f.Send(nil) }()
	<-f.entered
	events := make(chan Event, 64)
	done := make(chan error, 1)
	go func() { done <- Receive(ctx, f, l, events, func() uint64 { return 1 }, cancel) }()
	f.frames <- outcome(l, 0, 4, 1, 1)
	select {
	case <-events:
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	}
	if l.Snapshot().Outstanding != 0 {
		t.Fatal("receiver waits for sender")
	}
	select {
	case <-sent:
		t.Fatal("Send unexpectedly returned")
	default:
	}
	close(f.unblock)
	if e := <-sent; e != nil {
		t.Fatal(e)
	}
	close(f.frames)
	if e := <-done; e != nil {
		t.Fatal(e)
	}
}
func TestResponseEventQueueOverflowCancelsExplicitly(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	l := testLedger(t)
	begin(t, l, 0, 0)
	f := &fakeStream{ctx: ctx, frames: make(chan *p.ServerFrame, 65)}
	for i := 0; i < 65; i++ {
		f.frames <- outcome(l, 0, 0, 1, 1)
	}
	events := make(chan Event, 64)
	if e := Receive(ctx, f, l, events, func() uint64 { return 1 }, cancel); e != ErrCapacity {
		t.Fatal(e)
	}
	if len(events) != 64 || l.Snapshot().Outstanding != 0 || l.Verify() == nil {
		t.Fatal(l.Snapshot())
	}
}

func TestImmutableManifestAndForeignServerPopulation(t *testing.T) {
	m := Primary("immutable")
	l, e := NewLedger(m)
	if e != nil {
		t.Fatal(e)
	}
	m.Originals[0].Deadline = 1
	if l.manifest.Originals[0].Deadline != 2_000_000_000 {
		t.Fatal("identity mutated through caller")
	}
	if _, e = l.Reconcile(&ServerSnapshot{RunID: l.manifest.RunID, Originals: []ServerOriginal{{ID: 0, Starts: 1, Terminal: &ServerResult{Outcome: 1, Seq: 1, Offset: 0}}}}, 39_000_000_000); e == nil {
		t.Fatal("accepted unknown original population")
	}
}
func TestSyntheticRefusalRetryHistoryAndAuthoritySupersession(t *testing.T) {
	// A reconciliation fixture only. No retry scheduler/policy is implemented.
	l := testLedger(t)
	begin(t, l, 0, 10)
	first := outcome(l, 0, 10, 5, 100)
	first.GetTerminalOutcome().Outcome = p.Outcome_REJECTED_OVERLOAD
	if e := l.Apply(first, 101); e != nil {
		t.Fatal(e)
	}
	l.mu.Lock()
	l.attempts[1] = AttemptRecord{ID: 11, Original: 0, Number: 2}
	l.used = 2
	l.originals[0].Attempts = 2
	l.mu.Unlock()
	l.Close(200)
	server := &ServerSnapshot{RunID: l.manifest.RunID, Attempts: []ServerAttempt{{10, 0}, {11, 0}}, Originals: []ServerOriginal{{ID: 0, Starts: 1, Terminal: &ServerResult{Outcome: 1, Seq: 10, Offset: 1000, Detail: "COMPLETED"}}}}
	r, e := l.Reconcile(server, 39_000_000_000)
	if e != nil {
		t.Fatal(e)
	}
	if r.Attempts != 2 || r.FirstAttempts != 1 || r.Retries != 1 || r.Outcomes[0].Disposition != CompletedOnTime || !r.Outcomes[0].AckMissing || r.Outcomes[0].ClientObserved != RejectedFinal {
		t.Fatal(r.Outcomes[0])
	}
	server.Attempts = append(server.Attempts, ServerAttempt{99, 0})
	if _, e = l.Reconcile(server, 39_000_000_000); e == nil {
		t.Fatal("accepted unknown server attempt")
	}
}

func TestFixtureEpochRetainsWallTargetAndMonotonicComponent(t *testing.T) {
	target := time.Unix(0, time.Now().Add(time.Second).UnixNano())
	epoch := monotonicEpoch(target)
	if epoch.UnixNano() != target.UnixNano() {
		t.Fatal("epoch target changed")
	}
	if epoch == epoch.Round(0) {
		t.Fatal("epoch lacks monotonic component")
	}
}
