// A01 exactly33-original conforming saturation correctness fixture; no fabricated outcomes.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	e3 "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client"
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"os"
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
	expectCancel := flag.Bool("expect-cancel", false, "expected WAIT cancellation fixture")
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
	if len(m.Originals) != 33 {
		return fmt.Errorf("credit-smoke requires exactly33 fixture originals")
	}
	ledger, err := e3.NewPolicyLedger(m, e3.Policy(*policy), *retrySeed)
	if err != nil {
		return err
	}
	out, err := os.OpenFile(*events, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	defer out.Close()
	conn, err := grpc.NewClient(*addr, grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithDisableRetry(), grpc.WithStaticStreamWindowSize(65535), grpc.WithStaticConnWindowSize(65535), grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(1024*1024), grpc.MaxCallSendMsgSize(1024*1024), grpc.MaxRetryRPCBufferSize(0)))
	if err != nil {
		return err
	}
	defer conn.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	exchangeErr := e3.ScheduledExchange(ctx, p.NewOverloadServiceClient(conn), ledger, time.Unix(0, *epoch), out)
	// Publish RPC completion even on expected cancellation. The orchestrator then
	// joins/stops Rust and publishes its authoritative snapshot. No status is made up.
	marker, err := os.OpenFile(*report+".transport", os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	text := ""
	if exchangeErr != nil {
		text = exchangeErr.Error()
	}
	if err = json.NewEncoder(marker).Encode(map[string]any{"exchange_error": text, "client": ledger.Snapshot()}); err != nil {
		marker.Close()
		return err
	}
	marker.Close()
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
	result, err := ledger.Reconcile(&authority, 39_000_000_000)
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
	if err = json.NewEncoder(file).Encode(map[string]any{"observations": observations, "contract_revision": "A01", "client_outstanding_limit": e3.OutstandingCapacity, "client_pending_limit": e3.PendingCapacity, "fixture_only": true, "policy": *policy, "retry_seed": *retrySeed, "exchange_error": text, "client": ledger.Snapshot(), "server_reconciliation": result}); err != nil {
		return err
	}
	if *expectCancel {
		if exchangeErr == nil {
			return fmt.Errorf("expected cancellation was absent")
		}
		return nil
	}
	return exchangeErr
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
