package e3

import (
	"golang.org/x/sys/unix"
	"time"
)

type HighWater struct{ Pending, Outstanding, Events, Responses int }
type ClockBounds struct {
	EpochMinNS, EpochMaxNS int64
	BracketNS              int64
	Samples                int
	Clock                  string
}

// Bracket Go's own epoch against the host-wide monotonic clock, without using
// wall time for comparisons. Signed offsets support calibration before start.
func CalibrateClock(epoch time.Time) ClockBounds {
	var out ClockBounds
	out.Clock = "Linux CLOCK_MONOTONIC (same host/time namespace)"
	for i := 0; i < 8; i++ {
		var a, b unix.Timespec
		if unix.ClockGettime(unix.CLOCK_MONOTONIC, &a) != nil {
			return ClockBounds{}
		}
		elapsed := time.Since(epoch).Nanoseconds()
		if unix.ClockGettime(unix.CLOCK_MONOTONIC, &b) != nil {
			return ClockBounds{}
		}
		low, high := a.Nano()-elapsed, b.Nano()-elapsed
		if i == 0 || high-low < out.BracketNS {
			out.EpochMinNS = low
			out.EpochMaxNS = high
			out.BracketNS = high - low
		}
		out.Samples++
	}
	return out
}
func (l *Ledger) SetClock(start bool, b ClockBounds) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if start {
		l.clockStart = b
	} else {
		l.clockEnd = b
	}
}
func (l *Ledger) LegacySweepLogging(enable bool) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.legacySweeps = enable
}
func (l *Ledger) Diagnostic(now uint64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if e := l.room(); e != nil {
		return e
	}
	l.event(now, "diagnostic", 0, 0)
	return nil
}
func (l *Ledger) MarkSendStart(id, now uint64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if e := l.room(); e != nil {
		return e
	}
	a := l.attempt(id)
	if a == nil || a.ExplicitSendStart {
		return ErrProtocol
	}
	a.SendStartNS = now
	a.ExplicitSendStart = true
	l.event(now, "grpc_send_start", a.Original, id)
	return nil
}

func (l *Ledger) SetEpoch(epoch time.Time) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.clockNow = func() int64 { return time.Since(epoch).Nanoseconds() }
}

// PilotEpoch preserves one wall-to-monotonic mapping for RPC and observation.
func PilotEpoch(target time.Time) time.Time { return monotonicEpoch(target) }
func (l *Ledger) MarkHalfClose(now uint64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if e := l.room(); e != nil {
		return e
	}
	l.event(now, "client_half_close", 0, 0)
	return nil
}
