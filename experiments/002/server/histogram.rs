use std::sync::OnceLock;

pub const BINS: usize = 1024;
pub fn bounds() -> &'static [u64; BINS] {
    static BOUNDS: OnceLock<[u64; BINS]> = OnceLock::new();
    BOUNDS.get_or_init(|| {
        let mut bins = [0u64; BINS];
        bins[1] = 1000;
        for i in 2..BINS - 1 {
            bins[i] = (bins[i - 1] * 102).div_ceil(100);
        }
        bins[BINS - 1] = u64::MAX;
        bins
    })
}
#[derive(Clone)]
pub struct Histogram {
    pub counts: [u64; BINS],
    pub count: u64,
    pub sum: u64,
}
impl Default for Histogram {
    fn default() -> Self {
        Self {
            counts: [0; BINS],
            count: 0,
            sum: 0,
        }
    }
}
impl Histogram {
    pub fn record(&mut self, ns: u64) {
        let index = bounds().partition_point(|b| *b < ns);
        self.counts[index] += 1;
        self.count += 1;
        self.sum = self.sum.saturating_add(ns);
    }
    pub fn quantile(&self, percent: u64) -> u64 {
        if self.count == 0 {
            return 0;
        }
        let rank = (self.count * percent).div_ceil(100).max(1);
        let mut seen = 0;
        for (i, count) in self.counts.iter().enumerate() {
            seen += count;
            if seen >= rank {
                return bounds()[i];
            }
        }
        unreachable!()
    }
}
pub fn phase(elapsed_ns: u64) -> usize {
    match elapsed_ns {
        0..12_000_000_000 => 0,
        12_000_000_000..24_000_000_000 => 1,
        24_000_000_000..36_000_000_000 => 2,
        _ => 3,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn known_durations_and_frozen_phase_boundaries() {
        let mut h = Histogram::default();
        for i in [10, 20, 30, 40, 50] {
            h.record(bounds()[i]);
        }
        assert_eq!(h.quantile(50), bounds()[30]);
        assert_eq!(h.quantile(95), bounds()[50]);
        assert_eq!(h.quantile(99), bounds()[50]);
        for (ns, p) in [
            (0, 0),
            (11_999_999_999, 0),
            (12_000_000_000, 1),
            (24_000_000_000, 2),
            (36_000_000_000, 3),
        ] {
            assert_eq!(phase(ns), p);
        }
        let size = std::mem::size_of_val(&h);
        for _ in 0..1_000_000 {
            h.record(12345);
        }
        assert_eq!(std::mem::size_of_val(&h), size);
        assert_eq!(h.counts.iter().sum::<u64>(), h.count);
    }
}
