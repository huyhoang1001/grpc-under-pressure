package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"math/rand"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	pb "github.com/huyhoang1001/grpc-under-pressure/loadgen/gen/pressure/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const bins = 1024

var bounds = func() [bins]uint64 {
	var b [bins]uint64
	b[1] = 1000
	for i := 2; i < bins-1; i++ {
		b[i] = (b[i-1]*102 + 99) / 100
	}
	b[bins-1] = ^uint64(0)
	return b
}()

type histogram struct {
	Counts [bins]uint64
	Count  uint64
}

func (h *histogram) record(n uint64) {
	lo, hi := 0, bins
	for lo < hi {
		mid := (lo + hi) / 2
		if bounds[mid] < n {
			lo = mid + 1
		} else {
			hi = mid
		}
	}
	h.Counts[lo]++
	h.Count++
}
func (h *histogram) quantile(p uint64) uint64 {
	if h.Count == 0 {
		return 0
	}
	rank := (h.Count*p + 99) / 100
	var seen uint64
	for i, n := range h.Counts {
		seen += n
		if seen >= rank {
			return bounds[i]
		}
	}
	panic("histogram accounting")
}

type counters struct {
	Scheduled, Skipped, Attempted, Successful, Failed uint64
	SendNS, BlockedNS, ExcessNS, BlockedCalls         uint64
	InFlight                                          uint64
	StartNS                                           int64
	Hist                                              histogram
}

func (c *counters) verify(final bool) {
	if c.Scheduled != c.Skipped+c.Attempted {
		panic("scheduled accounting")
	}
	if c.Attempted != c.Successful+c.Failed+c.InFlight {
		panic("Send-return accounting")
	}
	if final && c.InFlight != 0 {
		panic("unfinished Send")
	}
}
func (c *counters) skip(n uint64) { c.Scheduled += n; c.Skipped += n; c.verify(false) }
func (c *counters) begin(start int64) {
	c.Scheduled++
	c.Attempted++
	c.InFlight++
	c.StartNS = start
	c.verify(false)
}
func (c *counters) finish(duration uint64, ok bool) {
	c.InFlight--
	if ok {
		c.Successful++
	} else {
		c.Failed++
	}
	c.SendNS += duration
	c.Hist.record(duration)
	if duration > 20_000_000 {
		c.BlockedCalls++
		c.BlockedNS += duration
		c.ExcessNS += duration - 20_000_000
	}
	c.verify(false)
}

type statistics struct {
	sync.Mutex
	c counters
}

func create(path string) *os.File {
	f, e := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0644)
	if e != nil {
		panic(e)
	}
	return f
}
func rss() uint64 {
	b, e := os.ReadFile("/proc/self/status")
	if e != nil {
		panic(e)
	}
	for _, line := range strings.Split(string(b), "\n") {
		if strings.HasPrefix(line, "VmRSS:") {
			v, _ := strconv.ParseUint(strings.Fields(line)[1], 10, 64)
			return v * 1024
		}
	}
	return 0
}
func phase(ns int64) int {
	switch {
	case ns < 12e9:
		return 0
	case ns < 24e9:
		return 1
	case ns < 36e9:
		return 2
	default:
		return 3
	}
}
func dueSlots(elapsed time.Duration, interval time.Duration, total int) int {
	if elapsed < 0 {
		return 0
	}
	n := int(elapsed/interval) + 1
	if n > total {
		return total
	}
	return n
}
func main() {
	runtime.GOMAXPROCS(2)
	addr := flag.String("addr", "127.0.0.1:50053", "server")
	output := flag.String("output", "stage1-client", "new output directory")
	marker := flag.String("marker", "marker.txt", "runner barrier target Unix ns file")
	rate := flag.Int("rate", 80, "scheduled slots/s (80 contract; other values are test fixtures)")
	seconds := flag.Float64("seconds", 36, "offered schedule (smokes shorter than contract primary)")
	timeout := flag.Duration("timeout", 120*time.Second, "whole-RPC deadline including drain")
	flag.Parse()
	if *rate < 1 || *rate > 100000 || *seconds <= 0 {
		panic("invalid workload")
	}
	if err := os.MkdirAll(*output, 0755); err != nil {
		panic(err)
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	conn, err := grpc.NewClient(*addr, grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithDisableRetry(), grpc.WithInitialWindowSize(65535), grpc.WithInitialConnWindowSize(65535), grpc.WithDefaultCallOptions(grpc.MaxCallSendMsgSize(1024*1024)))
	if err != nil {
		panic(err)
	}
	defer conn.Close()
	rpcStart := time.Now()
	ctx, deadlineCancel := context.WithTimeout(ctx, *timeout)
	defer deadlineCancel()
	stream, err := pb.NewIngestServiceClient(conn).Ingest(ctx)
	if err != nil {
		panic(err)
	}
	ready := create(filepath.Join(*output, "ready"))
	fmt.Fprintln(ready, "ready")
	ready.Close()
	var target int64
	for target == 0 {
		b, e := os.ReadFile(*marker)
		if e == nil {
			target, e = strconv.ParseInt(strings.TrimSpace(string(b)), 10, 64)
			if e != nil {
				panic(e)
			}
		}
		if ctx.Err() != nil {
			panic(ctx.Err())
		}
		if target == 0 {
			time.Sleep(2 * time.Millisecond)
		}
	}
	targetTime := time.Unix(0, target)
	wait := time.Until(targetTime)
	if wait > 0 {
		select {
		case <-time.After(wait):
		case <-ctx.Done():
			panic(ctx.Err())
		}
	}
	actual := time.Now()
	start := actual.Add(-actual.Sub(targetTime)) // retain local monotonic anchor at common target
	clock := create(filepath.Join(*output, "clock.json"))
	json.NewEncoder(clock).Encode(map[string]any{"target_unix_ns": target, "actual_start_unix_ns": actual.UnixNano(), "start_offset_ns": actual.UnixNano() - target})
	clock.Close()
	csvFile := create(filepath.Join(*output, "client.csv"))
	defer csvFile.Close()
	fmt.Fprintln(csvFile, "unix_ns,elapsed_ns,scheduled,skipped,attempted,successful_sends,failed_sends,inflight,send_duration_ns,send_gt20ms_calls,send_gt20ms_duration_ns,send_excess_gt20ms_ns,inflight_elapsed_ns,send_p50_upper_ns,send_p95_upper_ns,send_p99_upper_ns,rss_bytes")
	eventsFile := create(filepath.Join(*output, "sends.csv"))
	defer eventsFile.Close()
	events := bufio.NewWriterSize(eventsFile, 65536)
	fmt.Fprintln(events, "slot,sequence,send_start_ns,send_return_ns,send_duration_ns,outcome,phase")
	s := &statistics{}
	done := make(chan struct{})
	samplerJoined := make(chan struct{})
	sample := func() {
		s.Lock()
		defer s.Unlock()
		s.c.verify(false)
		c := &s.c
		inflight := int64(0)
		if c.InFlight > 0 {
			inflight = time.Since(start).Nanoseconds() - c.StartNS
		}
		fmt.Fprintf(csvFile, "%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n", time.Now().UnixNano(), time.Since(start).Nanoseconds(), c.Scheduled, c.Skipped, c.Attempted, c.Successful, c.Failed, c.InFlight, c.SendNS, c.BlockedCalls, c.BlockedNS, c.ExcessNS, inflight, c.Hist.quantile(50), c.Hist.quantile(95), c.Hist.quantile(99), rss())
		if e := csvFile.Sync(); e != nil {
			panic(e)
		}
	}
	go func() {
		defer close(samplerJoined)
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
	type job struct {
		slot int
		seq  uint64
	}
	jobs := make(chan job)
	readySender := make(chan struct{}, 1)
	senderDone := make(chan struct{})
	sendError := make(chan error, 1)
	// Zero-capacity rendezvous: one sequential Send, never a client work backlog.
	go func() {
		defer close(senderDone)
		rng := rand.New(rand.NewSource(1))
		readySender <- struct{}{}
		for j := range jobs {
			payload := make([]byte, 16384)
			rng.Read(payload)
			s.Lock()
			begin := time.Now()
			beginNS := begin.Sub(start).Nanoseconds()
			s.c.begin(beginNS)
			s.Unlock()
			e := stream.Send(&pb.Payload{Sequence: j.seq, Data: payload})
			end := time.Now()
			duration := uint64(end.Sub(begin))
			s.Lock()
			s.c.finish(duration, e == nil)
			s.Unlock()
			outcome := "success"
			if e != nil {
				outcome = "failed"
			}
			if _, e2 := fmt.Fprintf(events, "%d,%d,%d,%d,%d,%s,%d\n", j.slot, j.seq, beginNS, end.Sub(start).Nanoseconds(), duration, outcome, phase(beginNS)); e2 != nil {
				panic(e2)
			}
			if e != nil {
				sendError <- e
				return
			}
			readySender <- struct{}{}
		}
	}()
	<-readySender
	readySender <- struct{}{}
	total := int(float64(*rate) * (*seconds))
	interval := time.Second / time.Duration(*rate)
	endTime := start.Add(time.Duration(*seconds * float64(time.Second)))
	slot := 0
	var sequence uint64
	var firstSendError error
scheduling:
	for slot < total {
		wait := time.Until(start.Add(time.Duration(slot) * interval))
		if wait > 0 {
			select {
			case <-time.After(wait):
			case <-ctx.Done():
				break scheduling
			case e := <-sendError:
				firstSendError = e
				break scheduling
			}
		}
		if ctx.Err() != nil {
			break
		}
		due := dueSlots(time.Since(start), interval, total)
		if due > slot+1 {
			s.Lock()
			s.c.skip(uint64(due - slot - 1))
			s.Unlock()
			slot = due - 1
		}
		if !time.Now().Before(endTime) {
			break
		}
		select {
		case e := <-sendError:
			firstSendError = e
			break scheduling
		default:
		}
		select {
		case <-readySender:
			jobs <- job{slot, sequence}
			sequence++
		default:
			s.Lock()
			s.c.skip(1)
			s.Unlock()
		}
		slot++
	}
	// Complete the planned offered interval after the final scheduled slot.
	if slot >= total && ctx.Err() == nil {
		if wait := time.Until(endTime); wait > 0 {
			select {
			case <-time.After(wait):
			case <-ctx.Done():
			}
		}
	}
	// Classify elapsed but unattempted slots on early errors as skipped; not future slots.
	due := dueSlots(time.Since(start), interval, total)
	if due > slot {
		s.Lock()
		s.c.skip(uint64(due - slot))
		s.Unlock()
	}
	close(jobs)
	<-senderDone
	select {
	case e := <-sendError:
		if firstSendError == nil {
			firstSendError = e
		}
	default:
	}
	halfCloseNS := time.Since(start).Nanoseconds()
	summary, closeErr := stream.CloseAndRecv()
	close(done)
	<-samplerJoined
	sample()
	if e := events.Flush(); e != nil {
		panic(e)
	}
	s.Lock()
	s.c.verify(true)
	c := s.c
	s.Unlock()
	result := map[string]any{"schema": "e2-stage1-client-v1", "rate": *rate, "offered_seconds": *seconds, "planned_slots": total, "payload_bytes": 16384, "seed": 1, "scheduled": c.Scheduled, "skipped": c.Skipped, "attempted": c.Attempted, "successful_sends": c.Successful, "failed_sends": c.Failed, "send_duration_ns": c.SendNS, "send_gt20ms_calls": c.BlockedCalls, "send_gt20ms_duration_ns": c.BlockedNS, "send_excess_gt20ms_ns": c.ExcessNS, "blocked_time_definition": "sum of entire Send-call wall durations for completed calls >20ms; not isolated transport wait", "half_close_ns": halfCloseNS, "rpc_elapsed_ns": time.Since(rpcStart).Nanoseconds(), "summary": summary, "send_error": fmt.Sprint(firstSendError), "rpc_error": fmt.Sprint(closeErr), "histogram_bounds_ns": bounds, "send_histogram_counts": c.Hist.Counts}
	f := create(filepath.Join(*output, "summary.json"))
	if e := json.NewEncoder(f).Encode(result); e != nil {
		panic(e)
	}
	f.Close()
	if firstSendError != nil || closeErr != nil {
		fmt.Fprintln(os.Stderr, firstSendError, closeErr)
		os.Exit(1)
	}
}
