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
    let shared = Shared::new(None);
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
    let (s, input, reads) = setup(5);
    let summary = ingest(input, s.clone(), config()).await.unwrap();
    assert_eq!((summary.accepted, summary.processed), (5, 5));
    assert_eq!(reads.load(Ordering::SeqCst), 6);
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!((m.c.q, m.c.r, m.c.w), (0, 0, 0));
    assert_eq!(m.c.released, 1);
    assert_eq!((m.c.qbytes, m.c.hbytes, m.c.wbytes), (0, 0, 0));
    assert_eq!(m.c.queue_violations, 0);
    assert_eq!(m.queue_hist.iter().map(|h| h.count).sum::<u64>(), 5);
    assert_eq!(m.service_hist.iter().map(|h| h.count).sum::<u64>(), 5);
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
