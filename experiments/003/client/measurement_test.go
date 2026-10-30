package e3

import (
	"context"
	"golang.org/x/sys/unix"
	"net"
	"testing"
	"time"
)

func TestNoOpSweepsSilentButExpirationPreserved(t *testing.T) {
	l := testLedger(t)
	for i := 0; i < 10000; i++ {
		if e := l.ExpirePending(uint64(i)); e != nil {
			t.Fatal(e)
		}
	}
	if l.Snapshot().EventSeq != 0 {
		t.Fatal("no-op sweep logged")
	}
	l.Arrive(0, 0)
	l.ExpirePending(2_000_000_000)
	if l.originals[0].ClientObserved != ExpiredBeforeSend {
		t.Fatal(l.originals[0])
	}
	kinds := map[string]int{}
	for {
		e, ok := l.PopEvent()
		if !ok {
			break
		}
		kinds[e.Kind]++
	}
	if kinds["expired_before_send"] != 1 || kinds["pending_deadline_sweep"] != 0 {
		t.Fatal(kinds)
	}
}
func TestMeasuredNotificationPhysicalCapacityAndDrain(t *testing.T) {
	l := testLedger(t)
	q := NewNotifications(l, func() uint64 { return 0 })
	for i := 0; i < ResponseCapacity; i++ {
		if e := q.Push(Event{}); e != nil {
			t.Fatal(e)
		}
	}
	if e := q.Push(Event{}); e != ErrCapacity {
		t.Fatal(e)
	}
	if l.Snapshot().ResponseQueue != 64 || l.Snapshot().HighWater.Responses != 64 {
		t.Fatal(l.Snapshot())
	}
	q.Close()
	q.Drain()
	if l.Snapshot().ResponseQueue != 0 {
		t.Fatal(l.Snapshot())
	}
}
func TestClockBracketFutureAndPastEpoch(t *testing.T) {
	for _, delta := range []time.Duration{-time.Second, time.Second} {
		b := CalibrateClock(time.Now().Add(delta))
		if b.Samples != 8 || b.EpochMaxNS < b.EpochMinNS || b.BracketNS >= 5_000_000 {
			t.Fatal(b)
		}
	}
}

func TestCountingDialPreservesGRPCKeepaliveDefaults(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	accepted := make(chan net.Conn, 1)
	go func() { c, _ := listener.Accept(); accepted <- c }()
	raw, err := (&net.Dialer{KeepAlive: -1}).DialContext(context.Background(), "tcp", listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer raw.Close()
	peer := <-accepted
	if peer != nil {
		defer peer.Close()
	}
	var defaultIdle, defaultInterval int
	fd, _ := raw.(*net.TCPConn).SyscallConn()
	fd.Control(func(fd uintptr) {
		defaultIdle, _ = unix.GetsockoptInt(int(fd), unix.IPPROTO_TCP, unix.TCP_KEEPIDLE)
		defaultInterval, _ = unix.GetsockoptInt(int(fd), unix.IPPROTO_TCP, unix.TCP_KEEPINTVL)
	})
	go func() { c, _ := listener.Accept(); accepted <- c }()
	m := &Transport{}
	counted, err := m.Dial(context.Background(), listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer counted.Close()
	peer2 := <-accepted
	if peer2 != nil {
		defer peer2.Close()
	}
	fd, err = counted.(*countingConn).SyscallConn()
	if err != nil {
		t.Fatal(err)
	}
	fd.Control(func(fd uintptr) {
		keep, _ := unix.GetsockoptInt(int(fd), unix.SOL_SOCKET, unix.SO_KEEPALIVE)
		idle, _ := unix.GetsockoptInt(int(fd), unix.IPPROTO_TCP, unix.TCP_KEEPIDLE)
		interval, _ := unix.GetsockoptInt(int(fd), unix.IPPROTO_TCP, unix.TCP_KEEPINTVL)
		if keep != 1 || idle != defaultIdle || interval != defaultInterval {
			t.Errorf("socket drift: keep=%d idle=%d interval=%d expected%d/%d", keep, idle, interval, defaultIdle, defaultInterval)
		}
	})
}

func TestLatestServerRefusalWithLostACKIsKnownNotAmbiguous(t *testing.T) {
	l := policyLedger(t, Retry)
	begin(t, l, 0, 10)
	l.Apply(refusal(l, 0, 10, 1), 1)
	l.BeginNext(l.originals[0].ReadyAt, 11)
	l.SendReturn(11, true, 100)
	l.Close(200)
	s := &ServerSnapshot{RunID: l.manifest.RunID, Attempts: []ServerAttempt{{10, 0}, {11, 0}}, Originals: []ServerOriginal{{ID: 0, Terminal: &ServerResult{Outcome: 2, Seq: 2, Offset: 100, Detail: "REJECTED_OVERLOAD"}}}}
	r, err := l.Reconcile(s, 39_000_000_000)
	if err != nil {
		t.Fatal(err)
	}
	if r.Outcomes[0].Disposition != RejectedFinal || !r.Outcomes[0].AckMissing || r.Outcomes[0].Ambiguity {
		t.Fatal(r.Outcomes[0])
	}
	s.Attempts = s.Attempts[:1]
	r, err = l.Reconcile(s, 39_000_000_000)
	if err != nil || r.Outcomes[0].Disposition != Unknown {
		t.Fatal(r.Outcomes[0], err)
	}
}
