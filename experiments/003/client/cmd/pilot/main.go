// Stage4 real-workload pilot; no barrier, fabricated outcome or policy tuning.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	e3 "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client"
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"io"
	"os"
	"reflect"
	"time"
)

func run() error {
	addr := flag.String("addr", "127.0.0.1:50054", "fixture server")
	manifest := flag.String("manifest", "", "immutable manifest JSON")
	epoch := flag.Int64("epoch-unix-ns", 0, "shared future fixture epoch")
	events := flag.String("events", "", "exclusive event file")
	report := flag.String("report", "", "exclusive report file")
	policy := flag.String("policy", "wait", "wait/reject/retry/drop")
	retrySeed := flag.Uint64("retry-seed", 1, "recorded per-client jitter seed")
	serverLedger := flag.String("server-ledger", "", "authoritative snapshot after joined Rust shutdown")
	profile := flag.String("profile", "overload", "overload or low")
	cutoff := flag.Uint64("cutoff-ns", 39_000_000_000, "declared observation cutoff")
	bufferBytes := flag.Int("event-buffer-bytes", 0, "client event buffering calibration:0 or65536")
	flag.Parse()
	if *manifest == "" || *events == "" || *report == "" || *epoch == 0 {
		return fmt.Errorf("manifest, epoch, events, report are required")
	}
	info, err := os.Stat(*manifest)
	if err != nil {
		return err
	}
	if info.Size() > 2*1024*1024 {
		return e3.ErrCapacity
	}
	data, err := os.ReadFile(*manifest)
	if err != nil {
		return err
	}
	var m e3.Manifest
	if err = json.Unmarshal(data, &m); err != nil {
		return err
	}
	expected := e3.Primary(m.RunID)
	expectedCutoff := uint64(39_000_000_000)
	if *profile == "low" {
		expected.Originals = expected.Originals[:40]
		for i := range expected.Originals {
			expected.Originals[i].Scheduled = uint64(i) * 100_000_000
			expected.Originals[i].Deadline = expected.Originals[i].Scheduled + 2_000_000_000
		}
		expectedCutoff = 7_000_000_000
	} else if *profile != "overload" {
		return fmt.Errorf("unknown pilot profile")
	}
	if !reflect.DeepEqual(m, expected) || *cutoff != expectedCutoff || (*bufferBytes != 0 && *bufferBytes != 65536) {
		return fmt.Errorf("frozen pilot config mismatch")
	}
	ledger, err := e3.NewPolicyLedger(m, e3.Policy(*policy), *retrySeed)
	if err != nil {
		return err
	}

	transport := &e3.Transport{}
	out, err := os.OpenFile(*events, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	defer out.Close()
	conn, err := grpc.NewClient(*addr, grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithDisableRetry(), grpc.WithContextDialer(transport.Dial), grpc.WithStatsHandler(transport), grpc.WithStaticStreamWindowSize(65535), grpc.WithStaticConnWindowSize(65535), grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(1024*1024), grpc.MaxCallSendMsgSize(1024*1024), grpc.MaxRetryRPCBufferSize(0)))
	if err != nil {
		return err
	}
	defer conn.Close()
	epochMono := e3.PilotEpoch(time.Unix(0, *epoch))
	var eventOutput io.Writer = out
	var buffered *bufio.Writer
	if *bufferBytes > 0 {
		buffered = bufio.NewWriterSize(out, *bufferBytes)
		eventOutput = buffered
	}
	ctx, cancel := context.WithDeadline(context.Background(), epochMono.Add(time.Duration(*cutoff)+3*time.Second))
	defer cancel()
	exchangeErr := e3.ScheduledExchangeWithCutoff(ctx, p.NewOverloadServiceClient(conn), ledger, epochMono, eventOutput, *cutoff)
	rpcEnd := time.Since(epochMono).Nanoseconds()
	if buffered != nil {
		if flushErr := buffered.Flush(); flushErr != nil {
			ledger.Invalidate("EVENT_FLUSH_FAILED")
			exchangeErr = flushErr
		}
	}

	// Publish RPC completion even on expected cancellation. The orchestrator then
	// joins/stops Rust and publishes its authoritative snapshot. No status is made up.
	marker, err := os.OpenFile(*report+".transport.pending", os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	text := ""
	if exchangeErr != nil {
		text = exchangeErr.Error()
	}
	if err = json.NewEncoder(marker).Encode(map[string]any{"exchange_error": text, "client": ledger.Snapshot(), "rpc_end_offset_ns": rpcEnd}); err != nil {
		marker.Close()
		return err
	}
	if err = marker.Close(); err != nil {
		return err
	}
	if err = os.Rename(*report+".transport.pending", *report+".transport"); err != nil {
		return err
	}
	if exchangeErr == nil {
		timer := time.NewTimer(time.Until(epochMono.Add(time.Duration(*cutoff))))
		select {
		case <-timer.C:
		case <-ctx.Done():
			timer.Stop()
			return ctx.Err()
		}
	}
	observationEnd := time.Since(epochMono).Nanoseconds()
	ledger.SetClock(false, e3.CalibrateClock(epochMono))
	var authority e3.ServerSnapshot
	deadline := time.Now().Add(3 * time.Second)
	for {
		data, readErr := os.ReadFile(*serverLedger)
		if readErr == nil && json.Unmarshal(data, &authority) == nil {
			break
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("authoritative snapshot unavailable")
		}
		time.Sleep(time.Millisecond)
	}
	result, err := ledger.Reconcile(&authority, *cutoff)
	if err != nil {
		return err
	}
	file, err := os.OpenFile(*report, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	defer file.Close()
	observations := make([]*e3.Observation, len(m.Originals))
	for id := range m.Originals {
		if v, ok := ledger.Observed(id); ok {
			observations[id] = &v
		}
	}
	if err = json.NewEncoder(file).Encode(map[string]any{"observations": observations, "contract_revision": "A01", "client_outstanding_limit": e3.OutstandingCapacity, "client_pending_limit": e3.PendingCapacity, "pilot_only": true, "policy": *policy, "retry_seed": *retrySeed, "exchange_error": text, "client": ledger.Snapshot(), "rpc_end_offset_ns": rpcEnd, "server_reconciliation": result, "transport": transport.Snapshot(), "event_buffer_bytes": *bufferBytes, "profile": *profile, "observation_cutoff_ns": *cutoff, "observation_end_offset_ns": observationEnd}); err != nil {
		return err
	}

	return exchangeErr
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
