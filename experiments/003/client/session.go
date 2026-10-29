package e3

import (
	"context"
	"encoding/json"
	"fmt"
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"google.golang.org/grpc"
	"io"
	"sync"
	"time"
)

// Receive updates the ledger before forwarding a small diagnostic event. It never
// waits for send credits or the sender. Overflow explicitly cancels an invalid run.
func Receive(ctx context.Context, stream grpc.BidiStreamingClient[p.ClientFrame, p.ServerFrame], ledger *Ledger, events chan<- Event, now func() uint64, cancel context.CancelFunc) error {
	defer close(events)
	defer func() { ledger.Close(now()); cancel() }()
	for {
		frame, err := stream.Recv()
		if err != nil {
			ledger.Close(now())
			cancel()
			if err == io.EOF {
				return nil
			}
			return err
		}
		if err = ledger.Apply(frame, now()); err != nil {
			ledger.Invalidate("RESPONSE_PROTOCOL_ERROR: " + err.Error())
			ledger.Close(now())
			cancel()
			return err
		}
		t := frame.GetTerminalOutcome()
		event := Event{Kind: "terminal_processed", MessageID: t.MessageId, AttemptID: t.AttemptId, Offset: now()}
		select {
		case events <- event:
		case <-ctx.Done():
			return ctx.Err()
		default:
			ledger.Invalidate("RESPONSE_EVENT_QUEUE_OVERFLOW")
			ledger.Close(now())
			cancel()
			return ErrCapacity
		}
	}
}

// FixtureExchange sends at most32 selected originals, not a workload schedule or
// retry/policy implementation. Send and Recv are independent; all goroutines join.
func FixtureExchange(parent context.Context, client p.OverloadServiceClient, ledger *Ledger, ids []int, epoch time.Time, events io.Writer) error {
	if len(ids) > PendingCapacity {
		return ErrCapacity
	}
	ctx, cancel := context.WithCancel(parent)
	defer cancel()
	stream, err := client.Exchange(ctx)
	if err != nil {
		return err
	}
	// Header success commits this grpc-go RPC before any application Work.
	// WithDisableRetry alone does not disable transparent pre-commit retries.
	headers, e := stream.Header()
	if e != nil {
		return e
	}
	if headers == nil {
		return fmt.Errorf("RPC ended before headers; no Work sent")
	}
	now := func() uint64 {
		d := time.Since(epoch)
		if d < 0 {
			return 0
		}
		return uint64(d)
	}
	responseEvents := make(chan Event, ResponseCapacity)
	var group sync.WaitGroup
	errors := make(chan error, 3)
	group.Add(1)
	go func() {
		defer group.Done()
		for range responseEvents {
		}
	}()
	group.Add(1)
	go func() { defer group.Done(); errors <- Receive(ctx, stream, ledger, responseEvents, now, cancel) }()
	// Event writer is bounded by the ledger's fixed1024 entry ring, and flushes on exit.
	logDone := make(chan struct{})
	group.Add(1)
	go func() {
		defer group.Done()
		encoder := json.NewEncoder(events)
		ticker := time.NewTicker(time.Millisecond)
		defer ticker.Stop()
		for {
			if event, ok := ledger.PopEvent(); ok {
				if e := encoder.Encode(event); e != nil {
					ledger.Invalidate("EVENT_WRITE_FAILED")
					cancel()
					return
				}
				continue
			}
			select {
			case <-logDone:
				for {
					event, ok := ledger.PopEvent()
					if !ok {
						return
					}
					if e := encoder.Encode(event); e != nil {
						ledger.Invalidate("EVENT_WRITE_FAILED")
						return
					}
				}
			case <-ticker.C:
			}
		}
	}()
	for _, id := range ids {
		due := epoch.Add(time.Duration(ledger.manifest.Originals[id].Scheduled))
		timer := time.NewTimer(time.Until(due))
		select {
		case <-timer.C:
		case <-ctx.Done():
			timer.Stop()
			break
		}
		if ctx.Err() != nil {
			break
		}
		if err = ledger.Arrive(id, now()); err != nil {
			cancel()
			break
		}
		work, e := ledger.BeginNext(now(), uint64(id))
		if e != nil {
			err = e
			cancel()
			break
		}
		e = stream.Send(&p.ClientFrame{Frame: &p.ClientFrame_Work{Work: work}})
		if note := ledger.SendReturn(work.AttemptId, e == nil, now()); note != nil {
			err = note
			cancel()
			break
		}
		if e != nil {
			err = e
			cancel()
			break
		}
	}
	if ctx.Err() == nil {
		if e := stream.CloseSend(); e != nil {
			err = e
			cancel()
		}
	}
	// Recv completes on server EOF; a caller deadline bounds any stalled transport.
	receiveErr := <-errors
	close(logDone)
	group.Wait()
	if err != nil {
		return err
	}
	if receiveErr != nil {
		return fmt.Errorf("exchange: %w", receiveErr)
	}
	return ledger.Verify()
}
