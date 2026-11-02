package e3

import (
	"context"
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/test/bufconn"
	"io"
	"net"
	"sync"
	"testing"
	"time"
)

type capturedWork struct {
	RunId                string
	MessageId, AttemptId uint64
	AttemptNumber        uint32
	DeadlineOffsetNs     uint64
	PayloadSha256        []byte
}

type refusalServer struct {
	p.UnimplementedOverloadServiceServer
	policy   Policy
	mu       sync.Mutex
	attempts []capturedWork // correctness fixture <=24 identities; payload removed
}

func (s *refusalServer) Exchange(stream grpc.BidiStreamingServer[p.ClientFrame, p.ServerFrame]) error {
	stream.SendHeader(nil)
	var seq uint64
	for {
		frame, err := stream.Recv()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
		w := frame.GetWork()
		if w == nil {
			continue
		}
		copyWork := capturedWork{RunId: w.RunId, MessageId: w.MessageId, AttemptId: w.AttemptId, AttemptNumber: w.AttemptNumber, DeadlineOffsetNs: w.DeadlineOffsetNs, PayloadSha256: append([]byte(nil), w.PayloadSha256...)}
		s.mu.Lock()
		if len(s.attempts) >= 24 {
			s.mu.Unlock()
			return ErrCapacity
		}
		s.attempts = append(s.attempts, copyWork)
		s.mu.Unlock()
		seq++
		code := p.Outcome_COMPLETED
		if s.policy == Drop {
			code = p.Outcome_DROPPED_OVERLOAD
		}
		if s.policy == Reject || s.policy == Retry && w.AttemptNumber < 3 {
			code = p.Outcome_REJECTED_OVERLOAD
		}
		err = stream.Send(&p.ServerFrame{Frame: &p.ServerFrame_TerminalOutcome{TerminalOutcome: &p.TerminalOutcome{RunId: w.RunId, MessageId: w.MessageId, AttemptId: w.AttemptId, Outcome: code, ServerEventSeq: seq, ServerEventOffsetNs: 100}}})
		if err != nil {
			return err
		}
	}
}
func TestSchedulerOpenLoopRetriesAndDrainAllPolicies(t *testing.T) {
	for _, policy := range []Policy{Wait, Reject, Retry, Drop} {
		t.Run(string(policy), func(t *testing.T) {
			listener := bufconn.Listen(1024 * 1024)
			server := grpc.NewServer()
			behavior := &refusalServer{policy: policy}
			p.RegisterOverloadServiceServer(server, behavior)
			serving := make(chan struct{})
			go func() { defer close(serving); server.Serve(listener) }()
			defer func() { server.Stop(); listener.Close(); <-serving }()
			conn, err := grpc.NewClient("passthrough:///fixture", grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return listener.Dial() }), grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithDisableRetry(), grpc.WithDefaultCallOptions(grpc.MaxRetryRPCBufferSize(0)))
			if err != nil {
				t.Fatal(err)
			}
			defer conn.Close()
			m := Primary("scheduler")
			m.Originals = m.Originals[:8]
			for i := range m.Originals {
				m.Originals[i].Scheduled = uint64(i) * 1_000_000
				m.Originals[i].Deadline = m.Originals[i].Scheduled + 1_000_000_000
			}
			l, err := NewPolicyLedger(m, policy, 1)
			if err != nil {
				t.Fatal(err)
			}
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			if err := ScheduledExchange(ctx, p.NewOverloadServiceClient(conn), l, time.Now().Add(20*time.Millisecond), io.Discard); err != nil {
				t.Fatal(err)
			}
			snap := l.Snapshot()
			expected := 8
			if policy == Retry {
				expected = 24
			}
			if snap.Attempts != expected || snap.FirstAttempts != 8 || snap.Outstanding != 0 || snap.Pending != 0 || !snap.Closed || snap.EventQueue != 0 {
				t.Fatal(snap)
			}
			r, err := l.Reconcile(nil, 2_000_000_000)
			if err != nil {
				t.Fatal(err)
			}
			if len(r.Outcomes) != 8 {
				t.Fatal(r)
			}
			behavior.mu.Lock()
			defer behavior.mu.Unlock()
			seen := map[uint64]bool{}
			for i := range behavior.attempts {
				w := &behavior.attempts[i]
				if seen[w.AttemptId] || w.DeadlineOffsetNs != m.Originals[w.MessageId].Deadline || string(w.PayloadSha256) != string(m.Originals[w.MessageId].Hash[:]) {
					t.Fatal(w)
				}
				seen[w.AttemptId] = true
			}
		})
	}
}
func TestRetryAmbiguousSecondAttemptCannotReusePriorRefusal(t *testing.T) {
	l := policyLedger(t, Retry)
	begin(t, l, 0, 1)
	l.Apply(refusal(l, 0, 1, 1), 1)
	if _, err := l.BeginNext(l.originals[0].ReadyAt, 2); err != nil {
		t.Fatal(err)
	}
	l.SendReturn(2, true, 100)
	l.Close(200)
	r, err := l.Reconcile(nil, 39_000_000_000)
	if err != nil {
		t.Fatal(err)
	}
	if r.Counts[Unknown] != 1 || r.Counts[RejectedFinal] != 0 {
		t.Fatal(r.Counts)
	}
}

// A transport barrier, not a stopped-reader assumption. The real scheduler must
// continue recording all arrivals and deadline/overflow events while Send stalls.
type blockedClient struct{ stream *blockedScheduleStream }

func (c *blockedClient) Exchange(ctx context.Context, _ ...grpc.CallOption) (grpc.BidiStreamingClient[p.ClientFrame, p.ServerFrame], error) {
	c.stream = &blockedScheduleStream{ctx: ctx}
	return c.stream, nil
}

type blockedScheduleStream struct{ ctx context.Context }

func (f *blockedScheduleStream) Send(*p.ClientFrame) error { <-f.ctx.Done(); return f.ctx.Err() }
func (f *blockedScheduleStream) Recv() (*p.ServerFrame, error) {
	<-f.ctx.Done()
	return nil, f.ctx.Err()
}
func (f *blockedScheduleStream) Header() (metadata.MD, error) {
	return metadata.Pairs("fixture", "committed"), nil
}
func (f *blockedScheduleStream) Trailer() metadata.MD     { return nil }
func (f *blockedScheduleStream) CloseSend() error         { return nil }
func (f *blockedScheduleStream) Context() context.Context { return f.ctx }
func (f *blockedScheduleStream) SendMsg(any) error        { return nil }
func (f *blockedScheduleStream) RecvMsg(any) error        { return nil }
func TestT02OpenLoopArrivalsNotBlockedBySend(t *testing.T) {
	for _, policy := range []Policy{Wait, Reject, Retry, Drop} {
		t.Run(string(policy), func(t *testing.T) {
			m := Primary("blocked-send")
			m.Originals = m.Originals[:128]
			for i := range m.Originals {
				m.Originals[i].Scheduled = uint64(i) * 100_000
				m.Originals[i].Deadline = 1_000_000_000
			}
			l, err := NewPolicyLedger(m, policy, 1)
			if err != nil {
				t.Fatal(err)
			}
			ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
			defer cancel()
			err = ScheduledExchange(ctx, &blockedClient{}, l, time.Now().Add(10*time.Millisecond), io.Discard)
			if err == nil {
				t.Fatal("expected transport deadline")
			}
			for id, o := range l.originals {
				if !o.Arrived {
					t.Fatalf("missing arrival %d", id)
				}
			}
			s := l.Snapshot()
			if s.Attempts > 1 || s.Pending != 0 || s.Outstanding != 0 || s.Invalid != "" {
				t.Fatal(s)
			}
			r, err := l.Reconcile(nil, 2_000_000_000)
			if err != nil {
				t.Fatal(err)
			}
			if len(r.Outcomes) != 128 || r.Counts[ClientBacklogExhausted] < 95 {
				t.Fatal(r.Counts)
			}
		})
	}
}
