package e3

import (
	"context"
	"golang.org/x/sys/unix"
	"google.golang.org/grpc/stats"
	"net"
	"sync/atomic"
	"syscall"
	"time"
)

// Plaintext TCP stream bytes include HTTP/2 frames, headers and preface. They
// exclude IP/TCP headers, retransmissions and NIC traffic. One connection/run.
type Transport struct{ ReadBytes, WriteBytes, OutMessages, InMessages, OutGRPCBytes, InGRPCBytes atomic.Uint64 }
type countingConn struct {
	net.Conn
	t *Transport
}

func (c *countingConn) Read(b []byte) (int, error) {
	n, e := c.Conn.Read(b)
	c.t.ReadBytes.Add(uint64(n))
	return n, e
}
func (c *countingConn) Write(b []byte) (int, error) {
	n, e := c.Conn.Write(b)
	c.t.WriteBytes.Add(uint64(n))
	return n, e
}
func (t *Transport) Dial(ctx context.Context, addr string) (net.Conn, error) {
	c, e := (&net.Dialer{KeepAlive: time.Duration(-1), Control: func(_, _ string, c syscall.RawConn) error {
		var socketErr error
		if err := c.Control(func(fd uintptr) { socketErr = unix.SetsockoptInt(int(fd), unix.SOL_SOCKET, unix.SO_KEEPALIVE, 1) }); err != nil {
			return err
		}
		return socketErr
	}}).DialContext(ctx, "tcp", addr)
	if e != nil {
		return nil, e
	}
	return &countingConn{c, t}, nil
}
func (t *Transport) TagRPC(ctx context.Context, _ *stats.RPCTagInfo) context.Context { return ctx }
func (t *Transport) HandleRPC(_ context.Context, s stats.RPCStats) {
	switch v := s.(type) {
	case *stats.OutPayload:
		t.OutMessages.Add(1)
		t.OutGRPCBytes.Add(uint64(v.WireLength))
	case *stats.InPayload:
		t.InMessages.Add(1)
		t.InGRPCBytes.Add(uint64(v.WireLength))
	}
}
func (t *Transport) TagConn(ctx context.Context, _ *stats.ConnTagInfo) context.Context { return ctx }
func (t *Transport) HandleConn(context.Context, stats.ConnStats)                       {}
func (t *Transport) Snapshot() map[string]uint64 {
	return map[string]uint64{"tcp_stream_read_bytes": t.ReadBytes.Load(), "tcp_stream_write_bytes": t.WriteBytes.Load(), "grpc_out_messages": t.OutMessages.Load(), "grpc_in_messages": t.InMessages.Load(), "grpc_out_wire_bytes": t.OutGRPCBytes.Load(), "grpc_in_wire_bytes": t.InGRPCBytes.Load()}
}

// Preserve access to socket options used by grpc-go's transport with a raw TCP connection.
func (c *countingConn) SyscallConn() (syscall.RawConn, error) {
	return c.Conn.(syscall.Conn).SyscallConn()
}
