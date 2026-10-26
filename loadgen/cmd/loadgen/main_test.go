package main

import "testing"

func TestLatencyPercentiles(t *testing.T) {
	if latencyPercentile(nil, .5) != 0 {
		t.Fatal("empty sample")
	}
	values := []int64{1000000, 2000000, 3000000, 4000000, 5000000}
	for _, tc := range []struct{ p, want float64 }{{0, 1}, {.5, 3}, {.95, 4}, {.99, 4}, {1, 5}} {
		if got := latencyPercentile(values, tc.p); got != tc.want {
			t.Fatalf("p=%v got %v want %v", tc.p, got, tc.want)
		}
	}
}
