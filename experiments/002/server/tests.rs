use super::*;
use std::{
    collections::VecDeque,
    sync::atomic::{AtomicUsize, Ordering},
};

struct Input {
    items: VecDeque<Payload>,
    shared: Arc<Shared>,
    reads: Arc<AtomicUsize>,
}
impl Inbound for Input {
    async fn message(&mut self) -> Result<Option<Payload>, Status> {
        let s = self.shared.s.lock().unwrap();
        assert_eq!(s.c.r, 1);
        assert_eq!(self.shared.tx.capacity(), K - s.c.q - s.c.r);
        drop(s);
        self.reads.fetch_add(1, Ordering::SeqCst);
        Ok(self.items.pop_front())
    }
}
fn setup(n: usize) -> (Arc<Shared>, Input, Arc<AtomicUsize>) {
    setup_budget(n, 32)
}
fn setup_budget(n: usize, budget: usize) -> (Arc<Shared>, Input, Arc<AtomicUsize>) {
    let shared = Shared::new(None, budget);
    {
        let mut s = shared.s.lock().unwrap();
        let now = Instant::now();
        s.started = Some(now);
        s.last = Some(now);
    }
    shared.start.send_replace(true);
    let reads = Arc::new(AtomicUsize::new(0));
    let items = (0..n)
        .map(|i| Payload {
            sequence: i as u64,
            data: vec![i as u8; 7 + i % 3],
        })
        .collect();
    let input = Input {
        items,
        shared: shared.clone(),
        reads: reads.clone(),
    };
    (shared, input, reads)
}
fn config() -> Config {
    Config {
        service_ms: 1,
        fail_after: 0,
        panic_after: 0,
        scheduled: false,
    }
}
async fn until(shared: &Shared, condition: impl Fn(&State) -> bool) {
    tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            if condition(&shared.s.lock().unwrap()) {
                break;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
}
#[tokio::test]
async fn handoff_drain_and_unused_eof_reservation() {
    let (s, input, reads) = setup(65);
    let summary = tokio::time::timeout(Duration::from_secs(2), ingest(input, s.clone(), config()))
        .await
        .unwrap()
        .unwrap();
    assert_eq!((summary.accepted, summary.processed), (65, 65));
    assert_eq!(reads.load(Ordering::SeqCst), 66);
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!((m.c.q, m.c.r, m.c.w), (0, 0, 0));
    assert_eq!(m.c.released, 1);
    assert_eq!((m.c.qbytes, m.c.hbytes, m.c.wbytes), (0, 0, 0));
    assert_eq!(m.c.queue_violations, 0);
    assert_eq!(m.queue_hist.iter().map(|h| h.count).sum::<u64>(), 65);
    assert_eq!(m.service_hist.iter().map(|h| h.count).sum::<u64>(), 65);
    assert!(m.c.busy > 0 && m.c.idle > 0);
}
#[tokio::test]
async fn empty_eof_releases_reservation() {
    let (s, input, _) = setup(0);
    let result = ingest(input, s.clone(), config()).await.unwrap();
    assert_eq!(result.processed, 0);
    let m = s.s.lock().unwrap();
    assert_eq!((m.c.acquired, m.c.released, m.c.r), (1, 1, 0));
    m.verify();
}
#[tokio::test]
async fn full_queue_prevents_read_ahead_and_cancel_wakes_capacity() {
    let (s, input, reads) = setup(100);
    let task = tokio::spawn(ingest(
        input,
        s.clone(),
        Config {
            service_ms: 10000,
            ..config()
        },
    ));
    until(&s, |m| m.c.q == K && m.c.w == 1).await;
    assert_eq!(reads.load(Ordering::SeqCst), 33);
    assert_eq!(s.s.lock().unwrap().c.r, 0);
    s.fail("test_cancellation");
    assert!(tokio::time::timeout(Duration::from_secs(1), task)
        .await
        .unwrap()
        .unwrap()
        .is_err());
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!((m.c.dq, m.c.dw, m.c.r, m.c.active), (32, 1, 0, 0));
}
#[tokio::test]
async fn worker_error_wakes_blocked_handler() {
    let (s, input, _) = setup(100);
    let task = tokio::spawn(ingest(
        input,
        s.clone(),
        Config {
            service_ms: 30,
            fail_after: 1,
            ..config()
        },
    ));
    let result = tokio::time::timeout(Duration::from_secs(2), task)
        .await
        .unwrap()
        .unwrap();
    assert!(result.is_err());
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!(m.reason, "worker_error");
    assert_eq!((m.c.admitted, m.c.dq), (33, 32));
    assert_eq!(m.c.dw, 1);
    assert_eq!(m.c.r, 0);
    assert_eq!(m.c.active, 0);
}
#[tokio::test]
async fn worker_panic_wakes_blocked_handler() {
    let (s, input, _) = setup(100);
    let task = tokio::spawn(ingest(
        input,
        s.clone(),
        Config {
            service_ms: 30,
            panic_after: 1,
            ..config()
        },
    ));
    assert!(tokio::time::timeout(Duration::from_secs(2), task)
        .await
        .unwrap()
        .unwrap()
        .is_err());
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!(m.reason, "worker_panic");
    assert_eq!(m.c.dw, 1);
    assert_eq!(m.c.r, 0);
}
#[tokio::test]
async fn cancel_during_service_and_receive_cleans_permit() {
    let (s, input, _) = setup(1);
    let task = tokio::spawn(ingest(
        input,
        s.clone(),
        Config {
            service_ms: 10000,
            ..config()
        },
    ));
    until(&s, |m| m.c.w == 1).await;
    task.abort();
    let _ = task.await;
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!((m.c.dw, m.c.r, m.c.q, m.c.w), (1, 0, 0, 0));
}
#[tokio::test]
async fn received_handoff_failure_has_own_disposition() {
    let (s, _, _) = setup(0);
    let permit = reserve(s.clone()).await.unwrap();
    s.fail("worker_error");
    assert!(permit
        .handoff(Payload {
            sequence: 7,
            data: vec![1; 9]
        })
        .is_err());
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!(
        (m.c.received, m.c.admitted, m.c.not_admitted, m.c.r),
        (1, 0, 1, 0)
    );
}
#[tokio::test]
async fn payload_ownership_and_synthetic_queue_phase() {
    let (s, _, _) = setup(0);
    let p = reserve(s.clone()).await.unwrap();
    p.handoff(Payload {
        sequence: 1,
        data: vec![0; 13],
    })
    .unwrap();
    let mut m = s.s.lock().unwrap();
    assert_eq!((m.rx.len(), m.c.qbytes, m.c.wbytes), (1, 13, 0));
    let enqueue = m.rx.try_recv().unwrap(); // Reinsert synthetic time/phase without changing occupancy.
    let elapsed = Duration::from_secs(13);
    let now = Instant::now();
    s.tx.try_send(Item {
        enqueued: now - elapsed,
        payload: enqueue.payload,
        service_start: None,
        phase: 1,
        selected_ms: 0,
    })
    .unwrap();
    assert!(m.dequeue(now));
    assert_eq!((m.rx.len(), m.c.qbytes, m.c.wbytes), (0, 0, 13));
    assert_eq!(m.queue_hist[1].count, 1);
    assert!(m.queue_hist[1].quantile(95) >= ns(elapsed));
    m.complete(now + Duration::from_millis(40));
    assert_eq!(m.service_hist[1].count, 1);
    assert!(m.service_hist[1].quantile(95) >= 40_000_000);
    assert_eq!((m.c.w, m.c.wbytes), (0, 0));
    m.verify();
}
#[tokio::test]
async fn completion_cancellation_races_never_double_dispose() {
    for _ in 0..200 {
        let (s, _, _) = setup(0);
        reserve(s.clone())
            .await
            .unwrap()
            .handoff(Payload {
                sequence: 1,
                data: vec![0; 16],
            })
            .unwrap();
        assert!(s.s.lock().unwrap().dequeue(Instant::now()));
        let barrier = Arc::new(std::sync::Barrier::new(3));
        std::thread::scope(|scope| {
            let a = s.clone();
            let b = barrier.clone();
            scope.spawn(move || {
                b.wait();
                a.s.lock().unwrap().complete(Instant::now());
            });
            let a = s.clone();
            let b = barrier.clone();
            scope.spawn(move || {
                b.wait();
                a.fail("race_cancel");
            });
            barrier.wait();
        });
        let m = s.s.lock().unwrap();
        m.verify();
        assert_eq!(m.c.processed + m.c.dw, 1);
        assert_eq!((m.c.q, m.c.w, m.c.wbytes), (0, 0, 0));
    }
}

#[tokio::test]
async fn sampler_failure_stops_the_server_instead_of_leaving_a_metrics_gap() {
    let (shared, _, _) = setup(0);
    let mut sampler = tokio::spawn(async {
        panic!("injected sampler failure");
    });
    let result = supervise(std::future::pending(), &mut sampler, &shared).await;
    assert!(result.is_err());
    let state = shared.s.lock().unwrap();
    assert!(state.terminal);
    assert_eq!(state.reason, "instrumentation_failed");
    state.verify();
}

#[tokio::test]
async fn phase_is_assigned_at_enqueue_even_when_dequeue_crosses_a_boundary() {
    let (shared, _, _) = setup(0);
    shared.s.lock().unwrap().started = Some(Instant::now() - Duration::from_secs(13));
    reserve(shared.clone())
        .await
        .unwrap()
        .handoff(Payload {
            sequence: 1,
            data: vec![0; 16],
        })
        .unwrap();
    let mut state = shared.s.lock().unwrap();
    let item = state.rx.try_recv().unwrap();
    assert_eq!(item.phase, 1); // actual handoff chose the slowdown enqueue window
    let later = item.enqueued + Duration::from_secs(13); // dequeue occurs in recovery
    shared.tx.try_send(item).unwrap();
    assert!(state.dequeue(later));
    state.complete(later + Duration::from_millis(40));
    assert_eq!(
        (state.queue_hist[1].count, state.queue_hist[2].count),
        (1, 0)
    );
    assert_eq!(
        (state.service_hist[1].count, state.service_hist[2].count),
        (1, 0)
    );
    state.verify();
}

#[test]
fn contract_schedule_has_exact_boundaries_and_retains_drain_delay() {
    for (t, expected) in [
        (0, 10),
        (11_999_999_999, 10),
        (12_000_000_000, 40),
        (23_999_999_999, 40),
        (24_000_000_000, 10),
        (35_999_999_999, 10),
        (36_000_000_000, 10),
        (120_000_000_000, 10),
    ] {
        assert_eq!(service_delay(t, true, 999), expected);
    }
    assert_eq!(service_delay(13_000_000_000, false, 10), 10);
}

#[tokio::test]
async fn delay_uses_service_start_not_enqueue_completion_or_message_count() {
    for (enqueue_ns, start_ns, end_ns, expected) in [
        (11_000_000_000, 12_001_000_000, 12_050_000_000, 40),
        (23_000_000_000, 23_999_000_000, 24_045_000_000, 40),
        (13_000_000_000, 24_001_000_000, 24_013_000_000, 10),
        (13_000_000_000, 36_001_000_000, 36_013_000_000, 10),
    ] {
        let (shared, _, _) = setup(0);
        let origin = Instant::now() - Duration::from_nanos(enqueue_ns);
        {
            let mut s = shared.s.lock().unwrap();
            s.started = Some(origin);
            s.scheduled = true;
        }
        reserve(shared.clone())
            .await
            .unwrap()
            .handoff(Payload {
                sequence: 0,
                data: vec![0; 16],
            })
            .unwrap();
        let mut s = shared.s.lock().unwrap();
        assert!(s.dequeue(origin + Duration::from_nanos(start_ns)));
        assert_eq!(s.worker.as_ref().unwrap().selected_ms, expected);
        s.complete(origin + Duration::from_nanos(end_ns));
        assert_eq!(s.last_selected_ms, expected);
        s.verify();
    }
}

#[tokio::test]
async fn scheduled_worker_failure_keeps_capacity_wakeup_and_disposition() {
    let (shared, input, _) = setup(100);
    shared.s.lock().unwrap().started = Some(Instant::now() - Duration::from_secs(13));
    let task = tokio::spawn(ingest(
        input,
        shared.clone(),
        Config {
            scheduled: true,
            fail_after: 1,
            ..config()
        },
    ));
    assert!(tokio::time::timeout(Duration::from_secs(2), task)
        .await
        .unwrap()
        .unwrap()
        .is_err());
    let s = shared.s.lock().unwrap();
    s.verify();
    assert_eq!((s.c.admitted, s.c.dq, s.c.dw, s.c.r), (33, 32, 1, 0));
    assert_eq!(s.last_selected_ms, 40);
}

#[tokio::test]
async fn discard_sink_retains_formatting_histograms_and_counter_invariants() {
    let (shared, input, _) = setup(5);
    shared.s.lock().unwrap().events =
        Some(BufWriter::with_capacity(65536, Box::new(std::io::sink())));
    let summary = ingest(input, shared.clone(), config()).await.unwrap();
    assert_eq!(summary.processed, 5);
    let mut s = shared.s.lock().unwrap();
    s.flush_events().unwrap();
    s.verify();
    assert!(s.c.event_write_calls > 0);
    assert_eq!(s.c.event_flush_calls, 1);
    assert_eq!(s.service_total.count, 5);
    assert_eq!(s.queue_total.count, 5);
}

#[tokio::test]
async fn fixed8_blocks_read_ahead_with_24_unused_physical_slots_and_worker_excluded() {
    let (s, input, reads) = setup_budget(100, 8);
    let task = tokio::spawn(ingest(
        input,
        s.clone(),
        Config {
            service_ms: 10000,
            ..config()
        },
    ));
    until(&s, |m| m.c.q == 8 && m.c.w == 1).await;
    assert_eq!(s.tx.max_capacity(), 32);
    assert_eq!(s.tx.capacity(), 24);
    assert_eq!(reads.load(Ordering::SeqCst), 9); // eight pending + one executing
    {
        let m = s.s.lock().unwrap();
        assert_eq!(m.c.r, 0);
        m.verify();
    }
    s.fail("test_cancel_logical_gate");
    assert!(tokio::time::timeout(Duration::from_secs(1), task)
        .await
        .unwrap()
        .unwrap()
        .is_err());
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!((m.c.dq, m.c.dw, m.c.r, m.c.active), (8, 1, 0, 0));
    assert_eq!(s.tx.capacity(), 32);
}

#[tokio::test]
async fn fixed8_counts_reserved_slot_in_pending_budget_and_releases_unused_permit() {
    let (s, _, _) = setup_budget(0, 8);
    for sequence in 0..7 {
        reserve(s.clone())
            .await
            .unwrap()
            .handoff(Payload {
                sequence,
                data: vec![0; 16],
            })
            .unwrap();
    }
    let unused = reserve(s.clone()).await.unwrap();
    {
        let m = s.s.lock().unwrap();
        assert_eq!((m.c.q, m.c.r, m.c.w), (7, 1, 0));
        m.verify();
    }
    assert_eq!(s.tx.capacity(), 24);
    assert!(
        tokio::time::timeout(Duration::from_millis(20), reserve(s.clone()))
            .await
            .is_err()
    );
    drop(unused);
    let eof_reservation = tokio::time::timeout(Duration::from_millis(100), reserve(s.clone()))
        .await
        .unwrap()
        .unwrap();
    drop(eof_reservation);
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!((m.c.r, m.c.released), (0, 2));
}

#[tokio::test]
async fn fixed8_eof_progresses_and_drains_multiple_budget_windows() {
    let (s, input, reads) = setup_budget(65, 8);
    let summary = tokio::time::timeout(Duration::from_secs(2), ingest(input, s.clone(), config()))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        (
            summary.accepted,
            summary.processed,
            reads.load(Ordering::SeqCst)
        ),
        (65, 65, 66)
    );
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!(
        (m.c.q, m.c.r, m.c.w, m.c.qbytes, m.c.wbytes),
        (0, 0, 0, 0, 0)
    );
    assert_eq!((m.c.acquired, m.c.released, m.c.dq + m.c.dw), (66, 1, 0));
    assert_eq!(s.tx.capacity(), 32);
}

#[tokio::test]
async fn fixed8_worker_error_and_panic_wake_the_blocked_logical_gate() {
    for panic in [false, true] {
        let (s, input, reads) = setup_budget(100, 8);
        let c = Config {
            service_ms: 40,
            fail_after: if panic { 0 } else { 1 },
            panic_after: if panic { 1 } else { 0 },
            ..config()
        };
        let task = tokio::spawn(ingest(input, s.clone(), c));
        until(&s, |m| m.c.q == 8 && m.c.w == 1).await;
        assert_eq!(s.tx.capacity(), 24);
        assert_eq!(reads.load(Ordering::SeqCst), 9);
        assert!(tokio::time::timeout(Duration::from_secs(1), task)
            .await
            .unwrap()
            .unwrap()
            .is_err());
        let m = s.s.lock().unwrap();
        m.verify();
        assert_eq!(
            (m.c.admitted, m.c.dq, m.c.dw, m.c.r, m.c.active),
            (9, 8, 1, 0, 0)
        );
        assert_eq!(
            m.reason,
            if panic {
                "worker_panic"
            } else {
                "worker_error"
            }
        );
    }
}

#[tokio::test]
async fn physical_acquisition_error_releases_the_prior_logical_reservation() {
    for budget in [8, 32] {
        let (s, _, _) = setup_budget(0, budget);
        s.s.lock().unwrap().rx.close();
        assert!(reserve(s.clone()).await.is_err());
        let m = s.s.lock().unwrap();
        m.verify();
        assert_eq!(
            (m.c.acquired, m.c.released, m.c.r, m.c.received),
            (1, 1, 0, 0)
        );
    }
}

#[tokio::test]
async fn fixed8_handoff_cancel_races_release_permits_and_classify_received_work_once() {
    for _ in 0..200 {
        let (s, _, _) = setup_budget(0, 8);
        reserve(s.clone())
            .await
            .unwrap()
            .handoff(Payload {
                sequence: 1,
                data: vec![0; 16],
            })
            .unwrap();
        assert!(s.s.lock().unwrap().dequeue(Instant::now()));
        let reservation = reserve(s.clone()).await.unwrap();
        let barrier = Arc::new(std::sync::Barrier::new(3));
        std::thread::scope(|scope| {
            let b = barrier.clone();
            scope.spawn(move || {
                b.wait();
                let _ = reservation.handoff(Payload {
                    sequence: 2,
                    data: vec![0; 24],
                });
            });
            let b = barrier.clone();
            let a = s.clone();
            scope.spawn(move || {
                b.wait();
                a.fail("test_handoff_race");
            });
            barrier.wait();
        });
        let m = s.s.lock().unwrap();
        m.verify();
        assert_eq!(m.c.received, 2);
        assert_eq!(m.c.received_bytes, 40);
        assert_eq!(m.c.admitted, m.c.dq + m.c.dw);
        assert_eq!(m.c.admitted + m.c.not_admitted, 2);
        assert_eq!(
            (m.c.q, m.c.r, m.c.w, m.c.qbytes, m.c.wbytes),
            (0, 0, 0, 0, 0)
        );
        assert_eq!(s.tx.capacity(), 32);
    }
}
