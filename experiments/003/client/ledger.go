// Package e3 is a Stage1 protocol/ledger skeleton, not an overload load generator.
package e3

import (
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"sync"
)

const (
	OriginalCapacity    = 2880
	AttemptCapacity     = 8640
	PendingCapacity     = 32
	OutstandingCapacity = 32
	ResponseCapacity    = 64
	EventCapacity       = 1024
	PayloadBytes        = 16384
)

var (
	ErrBlocked   = errors.New("bounded resource unavailable")
	ErrClosed    = errors.New("stream closed")
	ErrProtocol  = errors.New("protocol violation")
	ErrCapacity  = errors.New("METADATA_CAPACITY_EXHAUSTED")
	ErrEventFull = errors.New("EVENT_WRITER_BACKPRESSURE_CANCEL")
)

type Identity struct {
	MessageID  uint64   `json:"message_id"`
	ClientID   uint32   `json:"client_id"`
	Scheduled  uint64   `json:"scheduled_offset_ns"`
	Deadline   uint64   `json:"deadline_offset_ns"`
	Hash       [32]byte `json:"payload_sha256"`
	Expendable bool     `json:"expendable"`
}
type Manifest struct {
	RunID     string     `json:"run_id"`
	Seed      uint64     `json:"payload_seed"`
	Originals []Identity `json:"originals"`
}

func Payload(seed uint64) []byte {
	out := make([]byte, PayloadBytes)
	var input [16]byte
	binary.LittleEndian.PutUint64(input[:8], seed)
	for i := 0; i < PayloadBytes/32; i++ {
		binary.LittleEndian.PutUint64(input[8:], uint64(i))
		sum := sha256.Sum256(input[:])
		copy(out[i*32:], sum[:])
	}
	return out
}
func Primary(run string) Manifest {
	m := Manifest{RunID: run, Seed: 1, Originals: make([]Identity, OriginalCapacity)}
	hash := sha256.Sum256(Payload(1))
	for i := range m.Originals {
		scheduled := uint64(i) * 12500000
		m.Originals[i] = Identity{uint64(i), 0, scheduled, scheduled + 2000000000, hash, true}
	}
	return m
}
func (m Manifest) Work(id int, attempt uint64, number uint32) *p.Work {
	s := m.Originals[id]
	return &p.Work{RunId: m.RunID, MessageId: uint64(id), AttemptId: attempt, AttemptNumber: number, ClientId: s.ClientID, ScheduledOffsetNs: s.Scheduled, DeadlineOffsetNs: s.Deadline, Payload: Payload(m.Seed), PayloadSha256: s.Hash[:], Expendable: s.Expendable}
}

type Disposition string

const (
	CompletedOnTime        Disposition = "COMPLETED_ON_TIME"
	CompletedLate          Disposition = "COMPLETED_LATE"
	RejectedFinal          Disposition = "REJECTED_FINAL"
	Dropped                Disposition = "DROPPED"
	ExpiredBeforeSend      Disposition = "EXPIRED_BEFORE_SEND"
	ExpiredWaitingQueued   Disposition = "EXPIRED_WAITING_OR_QUEUED"
	ExpiredProcessing      Disposition = "EXPIRED_PROCESSING"
	ClientBacklogExhausted Disposition = "CLIENT_BACKLOG_EXHAUSTED"
	ProcessingFailed       Disposition = "PROCESSING_FAILED"
	Cancelled              Disposition = "CANCELLED"
	Unknown                Disposition = "UNKNOWN"
)

type Observation struct {
	Outcome              p.Outcome
	Seq, Offset, Service uint64
	Detail               uint8
}

func detail(s string) uint8 {
	switch s {
	case "EXPIRED_PROCESSING":
		return 1
	case "EXPIRED_QUEUED", "EXPIRED_WAITING":
		return 2
	}
	return 0
}

type OriginalRecord struct {
	Arrived              bool
	Pending, Outstanding bool
	Attempts             int
	ClientObserved       Disposition
	Observed             *Observation
}
type AttemptRecord struct {
	ID                    uint64
	Original              int
	Number                uint32
	Returned, SendSuccess bool
	Observed              *Observation
}
type Event struct {
	Seq       uint64 `json:"seq"`
	Offset    uint64 `json:"offset_ns"`
	Kind      string `json:"kind"`
	MessageID uint64 `json:"message_id"`
	AttemptID uint64 `json:"attempt_id"`
}
type Snapshot struct {
	Pending, Outstanding, Originals, Attempts, FirstAttempts, Retries, SendSuccess int
	Closed                                                                         bool
	Invalid                                                                        string
	LedgerAllocatedBytes                                                           int
	EventQueue                                                                     int
	EventSeq                                                                       uint64
}
type Ledger struct {
	mu                                sync.Mutex
	manifest                          Manifest
	originals                         []OriginalRecord
	attempts                          [AttemptCapacity]AttemptRecord
	used, first, success, outstanding int
	pending                           [PendingCapacity]int
	pendingN                          int
	events                            [EventCapacity]Event
	eventHead, eventN                 int
	seq                               uint64
	closed                            bool
	invalid                           string
}

func NewLedger(m Manifest) (*Ledger, error) {
	if len(m.Originals) == 0 || len(m.Originals) > OriginalCapacity || m.RunID == "" {
		return nil, ErrProtocol
	}
	for i, s := range m.Originals {
		if s.MessageID != uint64(i) || s.Deadline < s.Scheduled {
			return nil, ErrProtocol
		}
	}
	m.Originals = append([]Identity(nil), m.Originals...)
	return &Ledger{manifest: m, originals: make([]OriginalRecord, len(m.Originals))}, nil
}
func (l *Ledger) room() error {
	if l.eventN == EventCapacity {
		l.invalid = ErrEventFull.Error()
		return ErrEventFull
	}
	return nil
}
func (l *Ledger) event(now uint64, kind string, id int, attempt uint64) {
	l.seq++
	l.events[(l.eventHead+l.eventN)%EventCapacity] = Event{l.seq, now, kind, uint64(id), attempt}
	l.eventN++
}
func (l *Ledger) PopEvent() (Event, bool) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.eventN == 0 {
		return Event{}, false
	}
	e := l.events[l.eventHead]
	l.eventHead = (l.eventHead + 1) % EventCapacity
	l.eventN--
	return e, true
}
func (l *Ledger) arrive(id int, now uint64) error {
	if id < 0 || id >= len(l.originals) || l.originals[id].Arrived || now < l.manifest.Originals[id].Scheduled {
		return ErrProtocol
	}
	o := &l.originals[id]
	o.Arrived = true
	if now >= l.manifest.Originals[id].Deadline {
		o.ClientObserved = ExpiredBeforeSend
	} else if l.pendingN == PendingCapacity {
		o.ClientObserved = ClientBacklogExhausted
	} else {
		o.Pending = true
		l.pending[l.pendingN] = id
		l.pendingN++
	}
	l.event(now, "original_arrival", id, 0)
	return nil
}
func (l *Ledger) Arrive(id int, now uint64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return ErrClosed
	}
	if e := l.room(); e != nil {
		return e
	}
	return l.arrive(id, now)
}
func (l *Ledger) expire(now uint64) error {
	count := 1
	for i := 0; i < l.pendingN; i++ {
		if now >= l.manifest.Originals[l.pending[i]].Deadline {
			count++
		}
	}
	if l.eventN+count > EventCapacity {
		l.invalid = ErrEventFull.Error()
		return ErrEventFull
	}
	n := 0
	for i := 0; i < l.pendingN; i++ {
		id := l.pending[i]
		if now >= l.manifest.Originals[id].Deadline {
			l.originals[id].Pending = false
			l.originals[id].ClientObserved = ExpiredBeforeSend
			l.event(now, "expired_before_send", id, 0)
		} else {
			l.pending[n] = id
			n++
		}
	}
	l.pendingN = n
	l.event(now, "pending_deadline_sweep", 0, 0)
	return nil
}
func (l *Ledger) ExpirePending(now uint64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.expire(now)
}
func (l *Ledger) ObserveOutstandingDeadlines(now uint64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	count := 0
	for id, o := range l.originals {
		if o.Outstanding && now >= l.manifest.Originals[id].Deadline && o.ClientObserved != "CLIENT_TIMEOUT" {
			count++
		}
	}
	if l.eventN+count > EventCapacity {
		l.invalid = ErrEventFull.Error()
		return ErrEventFull
	}
	for id := range l.originals {
		o := &l.originals[id]
		if o.Outstanding && now >= l.manifest.Originals[id].Deadline && o.ClientObserved != "CLIENT_TIMEOUT" {
			o.ClientObserved = "CLIENT_TIMEOUT"
			l.event(now, "client_timeout_credit_retained", id, 0)
		}
	}
	return nil
}
func (l *Ledger) BeginNext(now, attempt uint64) (*p.Work, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return nil, ErrClosed
	}
	if err := l.expire(now); err != nil {
		return nil, err
	}
	if l.pendingN == 0 || l.outstanding == OutstandingCapacity {
		return nil, ErrBlocked
	}
	if err := l.room(); err != nil {
		return nil, err
	}
	if l.used == AttemptCapacity {
		l.invalid = ErrCapacity.Error()
		return nil, ErrCapacity
	}
	for i := 0; i < l.used; i++ {
		if l.attempts[i].ID == attempt {
			return nil, ErrProtocol
		}
	}
	id := l.pending[0]
	o := &l.originals[id]
	if o.Outstanding || o.Attempts != 0 {
		return nil, ErrProtocol
	}
	copy(l.pending[:], l.pending[1:l.pendingN])
	l.pendingN--
	o.Pending = false
	o.Outstanding = true
	o.Attempts++
	l.first++
	l.outstanding++
	l.attempts[l.used] = AttemptRecord{ID: attempt, Original: id, Number: 1}
	l.used++
	l.event(now, "attempt_initiated", id, attempt)
	return l.manifest.Work(id, attempt, 1), nil
}
func (l *Ledger) attempt(id uint64) *AttemptRecord {
	for i := 0; i < l.used; i++ {
		if l.attempts[i].ID == id {
			return &l.attempts[i]
		}
	}
	return nil
}
func (l *Ledger) SendReturn(id uint64, success bool, now uint64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if e := l.room(); e != nil {
		return e
	}
	a := l.attempt(id)
	if a == nil || a.Returned {
		return ErrProtocol
	}
	a.Returned = true
	a.SendSuccess = success
	if success {
		l.success++
	}
	l.event(now, "grpc_send_return", a.Original, id)
	return nil
}
func (l *Ledger) Apply(frame *p.ServerFrame, now uint64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if e := l.room(); e != nil {
		return e
	}
	t := frame.GetTerminalOutcome()
	if t == nil {
		return ErrProtocol
	}
	a := l.attempt(t.AttemptId)
	if a == nil || uint64(a.Original) != t.MessageId || t.RunId != l.manifest.RunID {
		return ErrProtocol
	}
	v := Observation{t.Outcome, t.ServerEventSeq, t.ServerEventOffsetNs, t.WorkerServiceNs, detail(t.DetailCode)}
	if t.Outcome == p.Outcome_DUPLICATE_RESULT {
		ref := t.ReferencedTerminal
		if ref == nil || ref.Outcome == p.Outcome_DUPLICATE_RESULT {
			return ErrProtocol
		}
		v = Observation{ref.Outcome, ref.ServerEventSeq, ref.ServerEventOffsetNs, ref.WorkerServiceNs, detail(ref.DetailCode)}
	}
	if v.Outcome < p.Outcome_COMPLETED || v.Outcome > p.Outcome_CANCELLED || v.Seq == 0 {
		return ErrProtocol
	}
	if a.Observed != nil {
		if *a.Observed != v {
			return ErrProtocol
		}
		l.event(now, "terminal_replay_observed", a.Original, a.ID)
		return nil
	}
	a.Observed = &v
	o := &l.originals[a.Original]
	o.Observed = &v
	if o.Outstanding {
		o.Outstanding = false
		l.outstanding--
	}
	o.ClientObserved = classify(v, l.manifest.Originals[a.Original].Deadline)
	l.event(now, "terminal_observed", a.Original, a.ID)
	return nil
}
func classify(v Observation, deadline uint64) Disposition {
	switch v.Outcome {
	case p.Outcome_COMPLETED:
		if v.Offset <= deadline {
			return CompletedOnTime
		}
		return CompletedLate
	case p.Outcome_REJECTED_OVERLOAD:
		return RejectedFinal
	case p.Outcome_DROPPED_OVERLOAD:
		return Dropped
	case p.Outcome_EXPIRED:
		if v.Detail == 1 {
			return ExpiredProcessing
		}
		return ExpiredWaitingQueued
	case p.Outcome_PROCESSING_FAILED:
		return ProcessingFailed
	case p.Outcome_CANCELLED:
		return Cancelled
	}
	return Unknown
}
func (l *Ledger) Close(now uint64) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return
	}
	l.closed = true
	for i := range l.originals {
		o := &l.originals[i]
		if o.Outstanding {
			o.Outstanding = false
			if o.ClientObserved == "" {
				o.ClientObserved = Unknown
			}
		}
		if o.Pending {
			o.Pending = false
			o.ClientObserved = Cancelled
		}
	}
	l.pendingN = 0
	l.outstanding = 0
	if l.room() == nil {
		l.event(now, "stream_closed", 0, 0)
	}
}
func (l *Ledger) Invalidate(reason string) { l.mu.Lock(); defer l.mu.Unlock(); l.invalid = reason }
func (l *Ledger) Snapshot() Snapshot {
	l.mu.Lock()
	defer l.mu.Unlock()
	return Snapshot{l.pendingN, l.outstanding, len(l.originals), l.used, l.first, l.used - l.first, l.success, l.closed, l.invalid, ledgerBytes(l), l.eventN, l.seq}
}
func (l *Ledger) Verify() error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.invalid != "" {
		return errors.New(l.invalid)
	}
	if l.pendingN > 32 || l.outstanding > 32 || l.used > AttemptCapacity {
		return ErrCapacity
	}
	n := 0
	for _, o := range l.originals {
		if o.Outstanding {
			n++
		}
	}
	if n != l.outstanding {
		return fmt.Errorf("credit mismatch")
	}
	return nil
}

func (l *Ledger) Observed(id int) (Observation, bool) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if id < 0 || id >= len(l.originals) || l.originals[id].Observed == nil {
		return Observation{}, false
	}
	return *l.originals[id].Observed, true
}
