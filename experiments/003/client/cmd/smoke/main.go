// A two-original interoperability correctness fixture, not a load generator.
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
	ledger, err := e3.NewLedger(m)
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
	if err = e3.FixtureExchange(ctx, p.NewOverloadServiceClient(conn), ledger, []int{0, 1}, time.Unix(0, *epoch), out); err != nil {
		return err
	}
	result, err := ledger.Reconcile(nil, 39_000_000_000)
	if err != nil {
		return err
	}
	file, err := os.OpenFile(*report, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	defer file.Close()
	observations := make([]e3.Observation, 2)
	for id := 0; id < 2; id++ {
		v, ok := ledger.Observed(id)
		if !ok {
			return fmt.Errorf("missing terminal for %d", id)
		}
		observations[id] = v
	}
	return json.NewEncoder(file).Encode(map[string]any{"observations": observations, "fixture_only": true, "client": ledger.Snapshot(), "client_observed_reconciliation": result, "note": "Server reconciliation and clock calibration are separate; this is not primary benchmark evidence."})
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
