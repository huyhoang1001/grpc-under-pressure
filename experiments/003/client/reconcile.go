package e3

import (
	"fmt"
	p "github.com/huyhoang1001/grpc-under-pressure/experiments/003/client/gen"
	"unsafe"
)

func ledgerBytes(l *Ledger) int {
	observed := 0
	for i := 0; i < l.used; i++ {
		if l.attempts[i].Observed != nil {
			observed++
		}
	}
	return int(unsafe.Sizeof(*l)) + cap(l.originals)*int(unsafe.Sizeof(OriginalRecord{})) + cap(l.manifest.Originals)*int(unsafe.Sizeof(Identity{})) + observed*int(unsafe.Sizeof(Observation{})) + len(l.manifest.RunID)
}

// Serialized authoritative server snapshot: no delivery inference from write_accepted.
type ServerResult struct {
	Outcome int32  `json:"outcome"`
	Seq     uint64 `json:"event_seq"`
	Offset  uint64 `json:"offset_ns"`
	Service uint64 `json:"worker_service_ns"`
	Detail  string `json:"detail_code"`
}
type ServerOriginal struct {
	ID       uint64        `json:"message_id"`
	Starts   uint32        `json:"starts"`
	Terminal *ServerResult `json:"terminal"`
}
type ServerAttempt struct {
	ID       uint64 `json:"attempt_id"`
	Original uint64 `json:"message_id"`
}
type ServerSnapshot struct {
	Attempts  []ServerAttempt  `json:"attempts"`
	RunID     string           `json:"run_id"`
	Failed    *string          `json:"failed"`
	Originals []ServerOriginal `json:"originals"`
	Occupied  int              `json:"occupied"`
}
type Reconciled struct {
	ID             uint64      `json:"message_id"`
	Disposition    Disposition `json:"disposition"`
	ClientObserved Disposition `json:"client_observed"`
	AckMissing     bool        `json:"ack_missing"`
	Ambiguity      bool        `json:"ambiguity"`
}
type Reconciliation struct {
	N, U, Attempts, FirstAttempts, Retries, SendSuccess int
	Outcomes                                            []Reconciled
	Counts                                              map[Disposition]int
}

func (l *Ledger) Reconcile(server *ServerSnapshot, cutoff uint64) (Reconciliation, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	r := Reconciliation{N: len(l.originals), Attempts: l.used, FirstAttempts: l.first, Retries: l.used - l.first, SendSuccess: l.success, Counts: make(map[Disposition]int), Outcomes: make([]Reconciled, len(l.originals))}
	if l.invalid != "" {
		return r, fmt.Errorf("invalid ledger: %s", l.invalid)
	}
	if server != nil && (len(server.Attempts) > AttemptCapacity || len(server.Originals) > OriginalCapacity) {
		return r, ErrCapacity
	}
	if server != nil && server.Failed != nil && (*server.Failed == "UNRESOLVED_SHUTDOWN" || *server.Failed == "METADATA_CAPACITY_EXHAUSTED") {
		return r, fmt.Errorf("invalid server ledger: %s", *server.Failed)
	}
	if server != nil && (server.RunID != l.manifest.RunID || server.Occupied != 0) {
		return r, ErrProtocol
	}
	if server != nil {
		seen := make(map[uint64]bool, len(server.Attempts))
		for _, attempt := range server.Attempts {
			a := l.attempt(attempt.ID)
			if a == nil || uint64(a.Original) != attempt.Original || seen[attempt.ID] {
				return r, ErrProtocol
			}
			seen[attempt.ID] = true
		}
	}
	index := make([]*ServerOriginal, len(l.originals))
	if server != nil {
		for i := range server.Originals {
			s := &server.Originals[i]
			if s.ID >= uint64(len(index)) || index[s.ID] != nil || s.Starts > 1 || l.originals[s.ID].Attempts == 0 {
				return r, ErrProtocol
			}
			index[s.ID] = s
		}
	}
	for id, o := range l.originals {
		entry := Reconciled{ID: uint64(id), ClientObserved: o.ClientObserved}
		s := index[id]
		if s != nil && s.Terminal != nil {
			v := Observation{p.Outcome(s.Terminal.Outcome), s.Terminal.Seq, s.Terminal.Offset, s.Terminal.Service, detail(s.Terminal.Detail)}
			if v.Seq == 0 || v.Outcome < p.Outcome_COMPLETED || v.Outcome > p.Outcome_CANCELLED {
				return r, ErrProtocol
			}
			entry.Disposition = classify(v, l.manifest.Originals[id].Deadline)
			if o.Observed != nil && *o.Observed != v && !(o.Observed.Outcome == p.Outcome_REJECTED_OVERLOAD && v.Seq > o.Observed.Seq) {
				return r, fmt.Errorf("contradictory terminal for %d", id)
			}
			entry.AckMissing = o.Observed == nil || *o.Observed != v
		} else if o.Observed != nil {
			entry.Disposition = classify(*o.Observed, l.manifest.Originals[id].Deadline)
		} else if o.Attempts == 0 {
			if o.ClientObserved == ClientBacklogExhausted || o.ClientObserved == Cancelled {
				entry.Disposition = o.ClientObserved
			} else if cutoff >= l.manifest.Originals[id].Deadline {
				entry.Disposition = ExpiredBeforeSend
			} else {
				return r, fmt.Errorf("cutoff before unsent deadline")
			}
		} else {
			if !l.closed {
				return r, fmt.Errorf("ambiguous attempt without definitive stream closure")
			}
			entry.Disposition = Unknown
			entry.Ambiguity = true
		}
		if entry.Disposition == CompletedOnTime {
			r.U++
		}
		r.Outcomes[id] = entry
		r.Counts[entry.Disposition]++
	}
	return r, nil
}
