package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"math/rand"
	"os"
	"os/signal"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	pb "github.com/huyhoang1001/grpc-under-pressure/loadgen/gen/pressure/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type stats struct {
	sync.Mutex
	Attempts, Completed, Skipped, Blocked uint64
	SendNS                                uint64
	Latencies                             []int64
}

func rss() uint64 {
	b, _ := os.ReadFile("/proc/self/status")
	for _, line := range strings.Split(string(b), "\n") {
		if strings.HasPrefix(line, "VmRSS:") {
			fields := strings.Fields(line)
			n, _ := strconv.ParseUint(fields[1], 10, 64)
			return n * 1024
		}
	}
	return 0
}
func main() {
	runtime.GOMAXPROCS(2)
	addr := flag.String("addr", "127.0.0.1:50051", "server")
	rate := flag.Int("rate", 300, "scheduled messages per second")
	seconds := flag.Float64("seconds", 60, "offered-load duration")
	size := flag.Int("payload", 16384, "payload bytes")
	timeout := flag.Duration("timeout", 240*time.Second, "whole RPC deadline including drain")
	csv := flag.String("csv", "client.csv", "aggregate samples")
	summary := flag.String("summary", "client.json", "final result")
	flag.Parse()
	if *rate <= 0 || *rate > 100000 || *seconds <= 0 || *size <= 0 || *size > 1024*1024-64 {
		panic("invalid workload")
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	ctx, deadlineCancel := context.WithTimeout(ctx, *timeout)
	defer deadlineCancel()
	conn, err := grpc.NewClient(*addr, grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithDisableRetry(), grpc.WithInitialWindowSize(65535), grpc.WithInitialConnWindowSize(65535), grpc.WithDefaultCallOptions(grpc.MaxCallSendMsgSize(1024*1024)))
	if err != nil {
		panic(err)
	}
	defer conn.Close()
	stream, err := pb.NewIngestServiceClient(conn).Ingest(ctx)
	if err != nil {
		panic(err)
	}
	file, err := os.Create(*csv)
	if err != nil {
		panic(err)
	}
	defer file.Close()
	fmt.Fprintln(file, "elapsed_s,scheduled,attempts,completed,skipped,send_ns,blocked_gt20ms,rss_bytes")
	start := time.Now()
	stop := start.Add(time.Duration(*seconds * float64(time.Second)))
	s := &stats{}
	sample := func() {
		s.Lock()
		defer s.Unlock()
		elapsed := time.Since(start).Seconds()
		sched := int(elapsed * float64(*rate))
		if sched > int(*seconds*float64(*rate)) {
			sched = int(*seconds * float64(*rate))
		}
		fmt.Fprintf(file, "%.6f,%d,%d,%d,%d,%d,%d,%d\n", elapsed, sched, s.Attempts, s.Completed, s.Skipped, s.SendNS, s.Blocked, rss())
		file.Sync()
	}
	done := make(chan struct{})
	joined := make(chan struct{})
	go func() {
		defer close(joined)
		ticker := time.NewTicker(200 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				sample()
			case <-done:
				return
			}
		}
	}()
	rng := rand.New(rand.NewSource(1))
	interval := time.Second / time.Duration(*rate)
	next := start
	var sendErr error
	for sequence := uint64(0); time.Now().Before(stop); sequence++ {
		if wait := time.Until(next); wait > 0 {
			select {
			case <-time.After(wait):
			case <-ctx.Done():
				sendErr = ctx.Err()
			}
		}
		if sendErr != nil || !time.Now().Before(stop) {
			break
		}
		// No catch-up bursts: missed schedule slots are explicitly skipped.
		if late := time.Since(next); late >= interval {
			missed := uint64(late / interval)
			s.Lock()
			s.Skipped += missed
			s.Unlock()
			next = next.Add(time.Duration(missed) * interval)
		}
		payload := make([]byte, *size)
		rng.Read(payload)
		s.Lock()
		s.Attempts++
		s.Unlock()
		before := time.Now()
		err = stream.Send(&pb.Payload{Sequence: sequence, Data: payload})
		elapsed := time.Since(before)
		s.Lock()
		s.SendNS += uint64(elapsed)
		if elapsed > 20*time.Millisecond {
			s.Blocked++
		}
		if len(s.Latencies) < 1000000 {
			s.Latencies = append(s.Latencies, int64(elapsed))
		}
		if err == nil {
			s.Completed++
		}
		s.Unlock()
		if err != nil {
			sendErr = err
			break
		}
		next = next.Add(interval)
	}
	sendEnd := time.Since(start).Seconds()
	response, closeErr := stream.CloseAndRecv()
	close(done)
	<-joined
	sample()
	sort.Slice(s.Latencies, func(i, j int) bool { return s.Latencies[i] < s.Latencies[j] })
	percentile := func(p float64) float64 {
		if len(s.Latencies) == 0 {
			return 0
		}
		return float64(s.Latencies[int(float64(len(s.Latencies)-1)*p)]) / 1e6
	}
	result := map[string]any{"rate": *rate, "offered_seconds": *seconds, "payload_bytes": *size, "seed": 1, "attempts": s.Attempts, "completed_sends": s.Completed, "skipped_slots": s.Skipped, "send_seconds": sendEnd, "rpc_seconds": time.Since(start).Seconds(), "send_blocked_gt20ms": s.Blocked, "send_total_ns": s.SendNS, "send_p50_ms": percentile(.50), "send_p95_ms": percentile(.95), "send_p99_ms": percentile(.99), "summary": response, "send_error": fmt.Sprint(sendErr), "rpc_error": fmt.Sprint(closeErr)}
	b, _ := json.MarshalIndent(result, "", "  ")
	if err := os.WriteFile(*summary, append(b, '\n'), 0644); err != nil {
		panic(err)
	}
	if sendErr != nil || closeErr != nil {
		fmt.Fprintln(os.Stderr, sendErr, closeErr)
		os.Exit(1)
	}
}
