module github.com/huyhoang1001/grpc-under-pressure/experiments/002/client

go 1.27.3

require (
	github.com/huyhoang1001/grpc-under-pressure/loadgen v0.0.0
	google.golang.org/grpc v1.76.0
)

require (
	golang.org/x/net v0.42.0 // indirect
	golang.org/x/sys v0.34.0 // indirect
	golang.org/x/text v0.27.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20250804133106-a7a43d27e69b // indirect
	google.golang.org/protobuf v1.36.10 // indirect
)

replace github.com/huyhoang1001/grpc-under-pressure/loadgen => ../../../loadgen
