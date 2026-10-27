package main

import (
	"testing"
	"time"
)

func TestHistogramKnownValuesAndConstantStorage(t *testing.T) {
	var h histogram
	for _, i := range []int{10, 20, 30, 40, 50} {
		h.record(bounds[i])
	}
	if h.quantile(50) != bounds[30] || h.quantile(95) != bounds[50] || h.quantile(99) != bounds[50] {
		t.Fatal("wrong percentiles")
	}
	for i := 0; i < 1000000; i++ {
		h.record(12345)
	}
	var sum uint64
	for _, n := range h.Counts {
		sum += n
	}
	if sum != h.Count || len(h.Counts) != 1024 {
		t.Fatal("histogram lost samples")
	}
}
func TestLifecycleBalancesSuccessfulFailedAndSkipped(t *testing.T) {
	var c counters
	c.skip(3)
	c.begin(0)
	c.verify(false)
	c.finish(25000000, true)
	c.begin(1)
	c.finish(50000000, false)
	c.verify(true)
	if c.Scheduled != 5 || c.Skipped != 3 || c.Attempted != 2 || c.Successful != 1 || c.Failed != 1 || c.BlockedNS != 75000000 || c.ExcessNS != 35000000 {
		t.Fatal(c)
	}
}
func TestDueSlotsAndPhaseBoundaries(t *testing.T) {
	for _, v := range []struct {
		ns   int64
		want int
	}{{-1, 0}, {0, 1}, {12499999, 1}, {12500000, 2}, {36000000000, 2880}} {
		if got := dueSlots(time.Duration(v.ns), 12500000, 2880); got != v.want {
			t.Fatal(v, got)
		}
	}
	if phase(12e9) != 1 || phase(24e9) != 2 || phase(36e9) != 3 {
		t.Fatal("phase bounds")
	}
}
