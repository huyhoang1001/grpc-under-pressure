use super::*;

fn adaptive(n: usize) -> (Arc<Shared>, Input, Arc<AtomicUsize>) {
    let (s, input, reads) = setup_budget(n, 16);
    s.s.lock().unwrap().adaptive = true;
    (s, input, reads)
}
async fn fill(s: &Arc<Shared>, count: u64) {
    for sequence in 0..count {
        reserve(s.clone())
            .await
            .unwrap()
            .handoff(Payload {
                sequence,
                data: vec![0; (sequence + 1) as usize],
            })
            .unwrap();
    }
}
fn update(s: &Shared, b: usize) {
    assert!(s.s.lock().unwrap().set_budget(b));
    s.changed.notify_waiters();
}

#[tokio::test]
async fn shrink_preserves_existing_reservation_and_handoff_or_release() {
    for handoff in [false, true] {
        let (s, _, _) = adaptive(0);
        fill(&s, 15).await;
        let reservation = reserve(s.clone()).await.unwrap();
        update(&s, 8);
        {
            let m = s.s.lock().unwrap();
            assert_eq!((m.c.q, m.c.r, m.budget, m.shrink_occupancy), (15, 1, 8, 16));
            assert_eq!(s.tx.capacity(), 16);
            m.verify();
        }
        if handoff {
            reservation
                .handoff(Payload {
                    sequence: 15,
                    data: vec![0; 16],
                })
                .unwrap();
        } else {
            drop(reservation);
        }
        let pending = tokio::spawn(reserve(s.clone()));
        let count = if handoff { 16 } else { 15 };
        for q in (8..count).rev() {
            let mut m = s.s.lock().unwrap();
            assert!(m.dequeue(Instant::now()));
            m.complete(Instant::now());
            assert_eq!(m.c.q, q);
        }
        s.changed.notify_waiters();
        tokio::task::yield_now().await;
        assert!(!pending.is_finished()); // O == B still blocks
        {
            let mut m = s.s.lock().unwrap();
            assert!(m.dequeue(Instant::now()));
            m.complete(Instant::now());
            assert_eq!(m.c.q, 7);
        }
        s.changed.notify_waiters();
        let permit = tokio::time::timeout(Duration::from_secs(1), pending)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        assert_eq!(s.s.lock().unwrap().c.r, 1);
        drop(permit);
        s.fail("test_cleanup");
        let m = s.s.lock().unwrap();
        m.verify();
        assert_eq!(m.c.admitted, m.c.processed + m.c.dq + m.c.dw);
        assert_eq!(s.tx.capacity(), 32);
    }
}

#[tokio::test]
async fn controller_growth_wakes_blocked_gate_and_fixed_policies_only_observe() {
    for budget in [8, 16, 32] {
        let (s, _, _) = setup_budget(0, budget);
        s.s.lock().unwrap().adaptive = budget == 16;
        fill(&s, budget as u64).await;
        let mut window = TickWindow::default();
        let pending = tokio::spawn(reserve(s.clone()));
        tokio::task::yield_now().await;
        assert!(!pending.is_finished());
        for i in 0..2 {
            {
                let mut m = s.s.lock().unwrap();
                for _ in 0..5 {
                    m.service_total.record(1_000_000);
                }
            }
            assert!(control_tick(&s, (i + 1) * 500_000_000, &mut window));
        }
        if budget == 16 {
            let reservation = tokio::time::timeout(Duration::from_secs(1), pending)
                .await
                .unwrap()
                .unwrap()
                .unwrap();
            drop(reservation);
            assert_eq!(s.s.lock().unwrap().budget, 17);
        } else {
            assert_eq!(s.s.lock().unwrap().budget, budget);
            assert!(!pending.is_finished());
            s.fail("test_cancel");
            assert!(pending.await.unwrap().is_err());
        }
        s.fail("test_cleanup");
        s.s.lock().unwrap().verify();
    }
}

#[tokio::test]
async fn shrink_stops_read_ahead_then_eof_drains_without_rejecting_work() {
    let (s, input, reads) = adaptive(65);
    let task = tokio::spawn(ingest(
        input,
        s.clone(),
        Config {
            service_ms: 10,
            ..config()
        },
    ));
    until(&s, |m| m.c.q == 16 && m.c.w == 1).await;
    assert_eq!(reads.load(Ordering::SeqCst), 17);
    update(&s, 1);
    // At least one worker completion cannot open a budget of one from O=16.
    until(&s, |m| m.c.processed >= 1).await;
    assert_eq!(reads.load(Ordering::SeqCst), 17);
    let result = tokio::time::timeout(Duration::from_secs(2), task)
        .await
        .unwrap()
        .unwrap()
        .unwrap();
    assert_eq!((result.accepted, result.processed), (65, 65));
    assert_eq!(reads.load(Ordering::SeqCst), 66);
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!((m.c.r, m.c.q, m.c.w, m.c.dq, m.c.dw), (0, 0, 0, 0, 0));
    assert!(!m.controller_running);
    assert_eq!((m.c.qbytes, m.c.hbytes, m.c.wbytes), (0, 0, 0));
}

#[tokio::test]
async fn updates_during_cancel_worker_error_and_panic_leave_no_controller_or_work() {
    for fault in [0, 1, 2] {
        let (s, input, _) = adaptive(100);
        let task = tokio::spawn(ingest(
            input,
            s.clone(),
            Config {
                service_ms: 60,
                fail_after: if fault == 1 { 1 } else { 0 },
                panic_after: if fault == 2 { 1 } else { 0 },
                ..config()
            },
        ));
        until(&s, |m| m.c.q == 16 && m.c.w == 1).await;
        update(&s, 4);
        if fault == 0 {
            s.fail("test_cancellation");
        }
        assert!(tokio::time::timeout(Duration::from_secs(1), task)
            .await
            .unwrap()
            .unwrap()
            .is_err());
        until(&s, |m| !m.controller_running).await;
        let m = s.s.lock().unwrap();
        m.verify();
        assert_eq!(
            (
                m.c.admitted,
                m.c.dq,
                m.c.dw,
                m.c.q,
                m.c.r,
                m.c.w,
                m.c.active
            ),
            (17, 16, 1, 0, 0, 0, 0)
        );
        assert_eq!(s.tx.capacity(), 32);
    }
}

#[tokio::test]
async fn controller_stops_at_eof_and_cancellation_without_orphan_references() {
    for cancel in [false, true] {
        let (s, _, _) = adaptive(0);
        s.s.lock().unwrap().started = Some(Instant::now() - Duration::from_millis(490));
        let references = Arc::strong_count(&s);
        let task = tokio::spawn(control(s.clone()));
        until(&s, |m| m.controller_ticks >= 1).await;
        if cancel {
            s.fail("test_cancel");
        } else {
            s.s.lock().unwrap().eof = true;
            s.controller_stop.send_replace(true);
        }
        tokio::time::timeout(Duration::from_secs(1), task)
            .await
            .unwrap()
            .unwrap();
        assert_eq!(Arc::strong_count(&s), references);
        let mut window = TickWindow::default();
        let ticks = s.s.lock().unwrap().controller_ticks;
        assert!(!control_tick(&s, 1_000_000_000, &mut window));
        let mut m = s.s.lock().unwrap();
        assert!(!m.set_budget(8));
        assert_eq!(m.controller_ticks, ticks);
        assert!(!m.controller_running);
        m.verify();
    }
}

#[tokio::test]
async fn update_handoff_completion_and_cancellation_races_preserve_ownership() {
    for _ in 0..100 {
        let (s, _, _) = adaptive(0);
        fill(&s, 1).await;
        assert!(s.s.lock().unwrap().dequeue(Instant::now()));
        let reservation = reserve(s.clone()).await.unwrap();
        let barrier = Arc::new(std::sync::Barrier::new(5));
        std::thread::scope(|scope| {
            let b = barrier.clone();
            let shared = s.clone();
            scope.spawn(move || {
                b.wait();
                shared.s.lock().unwrap().set_budget(1);
                shared.changed.notify_waiters();
            });
            let b = barrier.clone();
            scope.spawn(move || {
                b.wait();
                let _ = reservation.handoff(Payload {
                    sequence: 1,
                    data: vec![0; 19],
                });
            });
            let b = barrier.clone();
            let shared = s.clone();
            scope.spawn(move || {
                b.wait();
                shared.s.lock().unwrap().complete(Instant::now());
            });
            let b = barrier.clone();
            let shared = s.clone();
            scope.spawn(move || {
                b.wait();
                shared.fail("test_race");
            });
            barrier.wait();
        });
        let m = s.s.lock().unwrap();
        m.verify();
        assert_eq!(m.c.received_bytes, 20);
        assert_eq!(m.c.received, 2);
        assert_eq!(m.c.admitted, m.c.processed + m.c.dq + m.c.dw);
        assert_eq!(
            (m.c.q, m.c.r, m.c.w, m.c.qbytes, m.c.hbytes, m.c.wbytes),
            (0, 0, 0, 0, 0, 0)
        );
        assert_eq!(s.tx.capacity(), 32);
    }
}

#[tokio::test]
async fn controller_abort_is_supervised_and_stops_without_orphan_work() {
    let (s, _, _) = adaptive(0);
    fill(&s, 4).await;
    let task = tokio::spawn(control(s.clone()));
    until(&s, |m| m.controller_running).await;
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    let m = s.s.lock().unwrap();
    m.verify();
    assert_eq!(m.reason, "controller_failed");
    assert_eq!((m.c.q, m.c.w, m.c.r, m.c.dq), (0, 0, 0, 4));
    assert!(!m.controller_running);
}

struct EndDuringShrink {
    shared: Arc<Shared>,
    error: bool,
}
impl Inbound for EndDuringShrink {
    async fn message(&mut self) -> Result<Option<Payload>, Status> {
        {
            let mut m = self.shared.s.lock().unwrap();
            assert_eq!(m.c.r, 1);
            assert!(m.set_budget(1));
        }
        self.shared.changed.notify_waiters();
        if self.error {
            Err(Status::invalid_argument("injected receive error"))
        } else {
            Ok(None)
        }
    }
}
#[tokio::test]
async fn eof_and_receive_error_release_existing_r_after_shrink() {
    for error in [false, true] {
        let (s, _, _) = adaptive(0);
        fill(&s, 3).await;
        let result = ingest(
            EndDuringShrink {
                shared: s.clone(),
                error,
            },
            s.clone(),
            config(),
        )
        .await;
        assert_eq!(result.is_err(), error);
        until(&s, |m| !m.controller_running).await;
        let m = s.s.lock().unwrap();
        m.verify();
        assert_eq!((m.c.r, m.c.q, m.c.w, m.c.received), (0, 0, 0, 3));
        assert_eq!(m.c.released, 1);
        assert_eq!(m.c.admitted, m.c.processed + m.c.dq + m.c.dw);
        assert_eq!(s.tx.capacity(), 32);
    }
}

struct Paced {
    inner: Input,
    next: Instant,
}
impl Inbound for Paced {
    async fn message(&mut self) -> Result<Option<Payload>, Status> {
        tokio::time::sleep_until(tokio::time::Instant::from_std(self.next)).await;
        self.next += Duration::from_micros(12_500);
        self.inner.message().await
    }
}
#[tokio::test]
async fn healthy_paced_work_makes_progress_with_live_controller_and_no_starvation() {
    let (s, input, _) = adaptive(100);
    let result = tokio::time::timeout(
        Duration::from_secs(3),
        ingest(
            Paced {
                inner: input,
                next: Instant::now(),
            },
            s.clone(),
            Config {
                service_ms: 10,
                ..config()
            },
        ),
    )
    .await
    .unwrap()
    .unwrap();
    assert_eq!((result.accepted, result.processed), (100, 100));
    let m = s.s.lock().unwrap();
    m.verify();
    assert!(m.controller_ticks >= 2);
    assert_eq!(m.budget, 16);
    assert_eq!(m.budget_updates, 0);
    assert!(!m.controller_running);
    assert!(m.c.idle_backlog < 100_000_000); // progress check, not a performance claim
}
