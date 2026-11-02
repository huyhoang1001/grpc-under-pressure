use serde::Serialize;
use tokio::time::Instant;
#[derive(Clone, Copy, Debug, Serialize)]
pub struct ClockBounds {
    pub epoch_min_ns: i128,
    pub epoch_max_ns: i128,
    pub bracket_ns: i128,
    pub samples: usize,
}
fn monotonic() -> i128 {
    let mut t = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // CLOCK_MONOTONIC uses the same host/time namespace as the Go calibration.
    assert_eq!(
        unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t) },
        0
    );
    i128::from(t.tv_sec) * 1_000_000_000 + i128::from(t.tv_nsec)
}
pub fn calibrate(epoch: Instant) -> ClockBounds {
    let mut best = ClockBounds {
        epoch_min_ns: 0,
        epoch_max_ns: 0,
        bracket_ns: i128::MAX,
        samples: 8,
    };
    for _ in 0..8 {
        let a = monotonic();
        let n = Instant::now();
        let elapsed = if n >= epoch {
            n.duration_since(epoch).as_nanos() as i128
        } else {
            -(epoch.duration_since(n).as_nanos() as i128)
        };
        let b = monotonic();
        if b - a < best.bracket_ns {
            best = ClockBounds {
                epoch_min_ns: a - elapsed,
                epoch_max_ns: b - elapsed,
                bracket_ns: b - a,
                samples: 8,
            }
        }
    }
    best
}
