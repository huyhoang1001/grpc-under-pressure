package e3

import (
	"context"
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"google.golang.org/grpc"
	"sync"
)

// Diagnostic queue only. Same nonblocking full->invalid behavior as the former
// channel. A fixed ring makes physical occupancy/high-water exact under its lock.
// Receive still updates attempt credit before forwarding any notification.
type Notifications struct {
	mu      sync.Mutex
	ring    [ResponseCapacity]Event
	head, n int
	closed  bool
	wake    chan struct{}
	ledger  *Ledger
	now     func() uint64
}

func NewNotifications(l *Ledger, now func() uint64) *Notifications {
	return &Notifications{wake: make(chan struct{}, 1), ledger: l, now: now}
}
func (q *Notifications) record() error {
	q.ledger.mu.Lock()
	defer q.ledger.mu.Unlock()
	if e := q.ledger.room(); e != nil {
		return e
	}
	q.ledger.responseN = q.n
	q.ledger.event(q.now(), "response_depth", 0, 0)
	return nil
}
func (q *Notifications) Push(e Event) error {
	q.mu.Lock()
	defer q.mu.Unlock()
	if q.closed {
		return ErrClosed
	}
	if q.n == ResponseCapacity {
		return ErrCapacity
	}
	q.ring[(q.head+q.n)%ResponseCapacity] = e
	q.n++
	err := q.record()
	select {
	case q.wake <- struct{}{}:
	default:
	}
	return err
}
func (q *Notifications) Close() {
	q.mu.Lock()
	q.closed = true
	q.mu.Unlock()
	select {
	case q.wake <- struct{}{}:
	default:
	}
}
func (q *Notifications) Drain() {
	for {
		q.mu.Lock()
		if q.n > 0 {
			q.ring[q.head] = Event{}
			q.head = (q.head + 1) % ResponseCapacity
			q.n--
			q.record()
			q.mu.Unlock()
			continue
		}
		closed := q.closed
		q.mu.Unlock()
		if closed {
			return
		}
		<-q.wake
	}
}
func ReceiveNotifications(ctx context.Context, stream grpc.BidiStreamingClient[p.ClientFrame, p.ServerFrame], l *Ledger, q *Notifications, now func() uint64, cancel context.CancelFunc) error {
	defer q.Close()
	return receiveFrames(ctx, stream, l, q.Push, now, cancel)
}
