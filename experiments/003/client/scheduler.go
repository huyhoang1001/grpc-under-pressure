package e3

import (
	"context"
	"encoding/json"
	"fmt"
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"io"
	"sync"
	"sync/atomic"
	"time"
)

// ScheduledExchange is the bounded open-loop scheduler. Arrivals never wait for
// Send, credits or retry timers. Exactly one sender and one receiver own the RPC.
// No per-message goroutines/timers; one shared32-entry heap lives in Ledger.
// This is not a calibrated benchmark runner (Stage3 must add that instrumentation).
func ScheduledExchange(parent context.Context, client p.OverloadServiceClient, ledger *Ledger, target time.Time, output io.Writer) error {
	epoch := monotonicEpoch(target)
	lastDeadline := uint64(0)
	for _, id := range ledger.manifest.Originals {
		if id.Deadline > lastDeadline {
			lastDeadline = id.Deadline
		}
	}
	ctx, cancel := context.WithDeadline(parent, epoch.Add(time.Duration(lastDeadline)+time.Second))
	defer cancel()
	stream, err := client.Exchange(ctx)
	if err != nil {
		return err
	}
	headers, err := stream.Header()
	if err != nil {
		return err
	}
	if headers == nil {
		return fmt.Errorf("RPC ended before headers")
	}
	now := func() uint64 {
		elapsed := time.Since(epoch)
		if elapsed < 0 {
			return 0
		}
		return uint64(elapsed)
	}
	var wg sync.WaitGroup
	responses := make(chan Event, ResponseCapacity)
	errs := make(chan error, 2)
	var arrivalsDone atomic.Bool
	wg.Add(3)
	go func() {
		defer wg.Done()
		for range responses {
		}
	}()
	go func() { defer wg.Done(); errs <- Receive(ctx, stream, ledger, responses, now, cancel) }()
	go func() {
		defer wg.Done()
		var attempt uint64
		ticker := time.NewTicker(time.Millisecond)
		defer ticker.Stop()
		for {
			if ctx.Err() != nil {
				errs <- ctx.Err()
				return
			}
			// Expiry runs independently of a blocked Send in the arrival loop below.
			work, e := ledger.BeginNext(now(), attempt)
			if e == nil {
				attempt++
				e = stream.Send(&p.ClientFrame{Frame: &p.ClientFrame_Work{Work: work}})
				if note := ledger.SendReturn(work.AttemptId, e == nil, now()); note != nil {
					e = note
				}
				if e != nil {
					cancel()
					errs <- e
					return
				}
				continue
			}
			if e != ErrBlocked {
				cancel()
				errs <- e
				return
			}
			s := ledger.Snapshot()
			if arrivalsDone.Load() && s.Pending == 0 && s.Outstanding == 0 {
				errs <- stream.CloseSend()
				return
			}
			select {
			case <-ctx.Done():
				errs <- ctx.Err()
				return
			case <-ticker.C:
			}
		}
	}()
	logDone := make(chan struct{})
	logExited := make(chan struct{})
	go func() {
		defer close(logExited)
		enc := json.NewEncoder(output)
		tick := time.NewTicker(time.Millisecond)
		defer tick.Stop()
		for {
			if e, ok := ledger.PopEvent(); ok {
				if err := enc.Encode(e); err != nil {
					ledger.Invalidate("EVENT_WRITE_FAILED")
					cancel()
					return
				}
				continue
			}
			select {
			case <-logDone: // all producers have joined
				for {
					e, ok := ledger.PopEvent()
					if !ok {
						return
					}
					if err := enc.Encode(e); err != nil {
						ledger.Invalidate("EVENT_WRITE_FAILED")
						return
					}
				}
			case <-tick.C:
			}
		}
	}()
	// One monotonic timer drives arrival slots; delayed wakeups retain their
	// immutable scheduled timestamps. They never shift the remaining schedule.
	ticker := time.NewTicker(time.Millisecond)
	next := 0
arrivals:
	for {
		if !time.Now().Before(epoch) {
			n := now()
			for next < len(ledger.manifest.Originals) && ledger.manifest.Originals[next].Scheduled <= n {
				if e := ledger.Arrive(next, n); e != nil {
					if e != ErrClosed {
						ledger.Invalidate(e.Error())
					}
					cancel()
					break arrivals
				}
				next++
			}
			if e := ledger.ExpirePending(n); e != nil {
				cancel()
				break
			}
			if e := ledger.ObserveOutstandingDeadlines(n); e != nil {
				cancel()
				break
			}
			if next == len(ledger.manifest.Originals) {
				arrivalsDone.Store(true)
			}
		}
		select {
		case <-ctx.Done():
			break arrivals
		case <-ticker.C:
		}
	}
	ticker.Stop()
	cancel()
	wg.Wait()
	ledger.Close(now())
	close(logDone)
	<-logExited
	e1, e2 := <-errs, <-errs
	if err := ledger.Verify(); err != nil {
		return err
	}
	if e1 != nil {
		return e1
	}
	return e2
}
