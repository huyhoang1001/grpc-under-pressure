package loadgen_test

import (
	"bytes"
	"testing"

	pressurev1 "github.com/huyhoang1001/grpc-under-pressure/loadgen/gen/pressure/v1"
	"google.golang.org/protobuf/proto"
)

func TestPayloadRoundTrip(t *testing.T) {
	original := &pressurev1.Payload{Sequence: 42, Data: bytes.Repeat([]byte{0x5a}, 16384)}
	encoded, err := proto.Marshal(original)
	if err != nil {
		t.Fatal(err)
	}
	decoded := new(pressurev1.Payload)
	if err := proto.Unmarshal(encoded, decoded); err != nil {
		t.Fatal(err)
	}
	if !proto.Equal(original, decoded) {
		t.Fatal("payload changed in transit")
	}
	decoded.Data[0] = 0
	if original.Data[0] != 0x5a {
		t.Fatal("decoded payload aliases original")
	}
}

func TestStreamingContract(t *testing.T) {
	service := pressurev1.File_ingest_proto.Services().ByName("IngestService")
	if service == nil {
		t.Fatal("missing service")
	}
	method := service.Methods().ByName("Ingest")
	if method == nil || !method.IsStreamingClient() || method.IsStreamingServer() {
		t.Fatal("expected client-streaming unary-response RPC")
	}
	if string(method.Input().FullName()) != "pressure.v1.Payload" || string(method.Output().FullName()) != "pressure.v1.Summary" {
		t.Fatal("unexpected RPC message types")
	}
}
