//! Frozen E2 feedback law. Constant storage; durations are measured nanoseconds.
#[derive(Default)]
pub(super) struct Controller {
    pub ewma_ms: Option<f64>,
    pub high: u8,
    pub low: u8,
}

pub(super) struct Decision {
    pub mean_ms: Option<f64>,
    pub delay_ms: Option<f64>,
    pub near_full: bool,
    pub high_before: u8,
    pub low_before: u8,
    pub proposed: usize,
    pub reason: &'static str,
}

impl Controller {
    pub fn tick(&mut self, n: u64, service_ns: u64, q: usize, r: usize, b: usize) -> Decision {
        assert!((1..=32).contains(&b));
        let mut d = Decision {
            mean_ms: (n > 0).then(|| service_ns as f64 / n as f64 / 1e6),
            delay_ms: None,
            near_full: q + r >= b - 1,
            high_before: self.high,
            low_before: self.low,
            proposed: b,
            reason: "insufficient_feedback",
        };
        if n < 5 {
            self.high = 0;
            self.low = 0;
            // Hold the previous estimate, but do not use ineligible feedback.
            d.delay_ms = self.ewma_ms.map(|s| q as f64 * s);
            return d;
        }
        let mean = d.mean_ms.unwrap();
        let ewma = self
            .ewma_ms
            .map(|old| 0.2 * mean + 0.8 * old)
            .unwrap_or(mean);
        self.ewma_ms = Some(ewma);
        let delay = q as f64 * ewma;
        d.delay_ms = Some(delay);
        self.high = if delay > 125.0 { self.high + 1 } else { 0 };
        self.low = if delay < 75.0 && d.near_full {
            self.low + 1
        } else {
            0
        };
        d.reason = "hold";
        if self.high >= 2 {
            d.proposed = b.div_ceil(2).max(1);
            d.reason = "decrease";
            self.high = 0;
            self.low = 0;
        } else if self.low >= 2 {
            d.proposed = (b + 1).min(32);
            d.reason = "increase";
            self.high = 0;
            self.low = 0;
        }
        d
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn tick(c: &mut Controller, mean_ms: u64, q: usize, r: usize, b: usize) -> Decision {
        c.tick(5, 5 * mean_ms * 1_000_000, q, r, b)
    }
    #[test]
    fn eligibility_initialization_ewma_and_missing_feedback_reset() {
        let mut c = Controller::default();
        assert_eq!(
            c.tick(4, 400_000_000, 16, 0, 16).reason,
            "insufficient_feedback"
        );
        assert_eq!(c.ewma_ms, None);
        assert_eq!(tick(&mut c, 10, 13, 0, 16).proposed, 16);
        assert_eq!((c.ewma_ms, c.high), (Some(10.0), 1));
        assert_eq!(tick(&mut c, 40, 13, 0, 16).proposed, 8);
        assert_eq!(c.ewma_ms, Some(16.0));
        tick(&mut c, 16, 13, 0, 16);
        c.tick(0, 0, 13, 0, 16);
        assert_eq!((c.ewma_ms, c.high, c.low), (Some(16.0), 0, 0));
        assert_eq!(tick(&mut c, 16, 13, 0, 16).proposed, 16);
    }
    #[test]
    fn strict_thresholds_near_full_hysteresis_and_bounds() {
        let mut c = Controller::default();
        for _ in 0..3 {
            let d = tick(&mut c, 25, 5, 0, 6); // exactly 125ms
            assert_eq!((d.reason, c.high), ("hold", 0));
        }
        c = Controller::default();
        for _ in 0..3 {
            let d = tick(&mut c, 25, 3, 0, 4); // exactly 75ms, near-full
            assert_eq!((d.reason, c.low), ("hold", 0));
        }
        c = Controller::default();
        tick(&mut c, 10, 6, 0, 8); // not near-full
        assert_eq!(c.low, 0);
        tick(&mut c, 10, 6, 1, 8); // R matters for demand, not delay
        assert_eq!(c.low, 1);
        assert_eq!(tick(&mut c, 10, 6, 1, 8).proposed, 9);
        assert_eq!((c.high, c.low), (0, 0));
        c = Controller::default();
        tick(&mut c, 10, 17, 0, 17);
        assert_eq!(tick(&mut c, 10, 17, 0, 17).proposed, 9); // ceil
        c = Controller::default();
        tick(&mut c, 200, 1, 0, 1);
        assert_eq!(tick(&mut c, 200, 1, 0, 1).proposed, 1);
        c = Controller::default();
        tick(&mut c, 1, 31, 0, 32);
        assert_eq!(tick(&mut c, 1, 31, 0, 32).proposed, 32);
    }
    #[test]
    fn intervening_eligible_tick_resets_each_threshold_streak() {
        let mut c = Controller::default();
        tick(&mut c, 10, 13, 0, 16);
        tick(&mut c, 10, 8, 0, 16); // middle band
        assert_eq!((c.high, c.low), (0, 0));
        assert_eq!(tick(&mut c, 10, 13, 0, 16).proposed, 16);
        tick(&mut c, 10, 6, 1, 8);
        tick(&mut c, 10, 6, 0, 8); // demand absent resets low
        assert_eq!(c.low, 0);
        c.tick(4, 40_000_000, 6, 1, 8);
        assert_eq!(tick(&mut c, 10, 6, 1, 8).proposed, 8);
    }
}
