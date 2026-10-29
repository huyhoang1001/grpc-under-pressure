use pressure_e3_stage1::{
    ledger::*,
    protocol::{server_frame, Outcome},
};
fn manifest(n: usize) -> Manifest {
    let mut m = Manifest::primary("test");
    m.originals.truncate(n);
    for s in &mut m.originals {
        s.scheduled_offset_ns = 0;
        s.deadline_offset_ns = 2_000_000_000;
    }
    m
}
fn offer(l: &mut Ledger, id: usize, attempt: u64, number: u32, now: u64) {
    let w = l.manifest().work(id, attempt, number);
    l.begin_decode(now).unwrap();
    l.offer(w, now).unwrap();
    l.progress_stage(now).unwrap();
}
fn terminal(
    frame: pressure_e3_stage1::protocol::ServerFrame,
) -> pressure_e3_stage1::protocol::TerminalOutcome {
    match frame.frame.unwrap() {
        server_frame::Frame::TerminalOutcome(t) => t,
        _ => panic!(),
    }
}
#[test]
fn identity_duplicate_join_replay_and_cancel_after_completion() {
    let mut l = Ledger::new(manifest(1)).unwrap();
    offer(&mut l, 0, 10, 1, 0);
    l.begin_decode(1).unwrap();
    l.offer(l.manifest().work(0, 11, 2), 1).unwrap();
    assert_eq!(l.start(2).unwrap().unwrap().0, 0);
    assert!(l.start(3).unwrap().is_none());
    l.exit(0, 10, 10, true).unwrap();
    assert_eq!(l.snapshot().permits_released, 1);
    l.request_cancel(0, 11, "CLIENT_CANCEL").unwrap();
    let a = terminal(l.response(12).unwrap().unwrap());
    let b = terminal(l.response(13).unwrap().unwrap());
    assert_eq!(a.outcome, Outcome::Completed as i32);
    assert_eq!(b.outcome, Outcome::DuplicateResult as i32);
    assert_eq!(
        b.referenced_terminal.unwrap().server_event_seq,
        a.server_event_seq
    );
    assert_eq!(a.server_event_offset_ns, 10);
    l.begin_decode(14).unwrap();
    l.offer(l.manifest().work(0, 10, 1), 14).unwrap();
    let replay = terminal(l.response(15).unwrap().unwrap());
    assert_eq!(
        replay.referenced_terminal.unwrap().server_event_offset_ns,
        10
    );
    let s = l.snapshot();
    assert_eq!(s.originals[0].starts, 1);
    assert_eq!(s.attempt_entries, 2);
    assert_eq!(s.occupied, 0);
}
#[test]
fn all_capacity_domains_and_no_worker_ack_dependency() {
    let mut l = Ledger::new(manifest(33)).unwrap();
    for id in 0..32 {
        offer(&mut l, id, id as u64, 1, 0);
    }
    l.begin_decode(0).unwrap();
    l.offer(l.manifest().work(32, 32, 1), 0).unwrap();
    assert_eq!(l.progress_stage(0), Err(Error::Blocked));
    assert_eq!(l.begin_decode(0), Err(Error::Blocked));
    let s = l.snapshot();
    assert_eq!(
        (s.occupied, s.decoded_staging, s.terminal_responses_reserved),
        (32, 1, 32)
    );
    assert_eq!(s.queued_payload_bytes, 32 * PAYLOAD);
    for time in 1..=32 {
        let (id, _, _) = l.start(time).unwrap().unwrap();
        l.exit(id, time, time, true).unwrap();
    }
    assert_eq!(l.snapshot().occupied, 0); // all workers exit without any ACK consumption
    assert_eq!(l.snapshot().terminal_responses_reserved, 32);
    assert_eq!(l.progress_stage(33), Err(Error::Blocked)); // no admission permit held while waiting for outcome capacity
    l.response(34).unwrap().unwrap();
    l.progress_stage(35).unwrap();
    assert_eq!(l.snapshot().occupied, 1);
}
#[test]
fn immediate_reservations_stop_decode_without_hidden_duplicate_queue() {
    let mut l = Ledger::new(manifest(32)).unwrap();
    for id in 0..32 {
        offer(&mut l, id, id as u64, 1, 0);
    }
    for id in 0..32 {
        l.begin_decode(1).unwrap();
        l.offer(l.manifest().work(id, 100 + id as u64, 2), 1)
            .unwrap();
    }
    assert_eq!(l.snapshot().immediate_responses, 32);
    assert_eq!(l.begin_decode(2), Err(Error::Blocked));
    for t in 3..35 {
        let (id, _, _) = l.start(t).unwrap().unwrap();
        l.exit(id, t, t, true).unwrap();
    }
    assert_eq!(l.snapshot().permits_acquired, l.snapshot().permits_released);
    for t in 35..99 {
        assert!(l.response(t).unwrap().is_some());
    }
    assert!(l.response(100).unwrap().is_none());
    assert_eq!(l.snapshot().immediate_responses, 0);
}
#[test]
fn deadline_boundary_late_race_and_delayed_cancellation_exit() {
    for late in [false, true] {
        let mut l = Ledger::new(manifest(1)).unwrap();
        offer(&mut l, 0, 0, 1, 0);
        l.start(0).unwrap();
        l.request_cancel(0, 2_000_000_000, "DEADLINE").unwrap();
        assert_eq!(l.snapshot().occupied, 1);
        let time = 2_000_000_000 + u64::from(late);
        l.exit(0, time, time, true).unwrap();
        let r = terminal(l.response(time).unwrap().unwrap());
        assert_eq!(r.outcome, Outcome::Completed as i32);
        assert_eq!(r.server_event_offset_ns <= 2_000_000_000, !late);
    }
    let mut l = Ledger::new(manifest(1)).unwrap();
    offer(&mut l, 0, 0, 1, 0);
    l.start(0).unwrap();
    l.request_cancel(0, 2_000_000_000, "DEADLINE").unwrap();
    l.observe_cancel(0, 2_100_000_000).unwrap();
    assert_eq!(l.snapshot().occupied, 1);
    assert_eq!(l.snapshot().permits_released, 0);
    l.exit(0, 2_100_000_000, 2_200_000_000, false).unwrap();
    let s = l.snapshot();
    assert_eq!(s.occupied, 0);
    assert_eq!(
        s.originals[0].terminal.as_ref().unwrap().worker_service_ns,
        2_200_000_000
    );
    assert_eq!(s.originals[0].cancellation_observed_ns, Some(2_100_000_000));
}
#[test]
fn expire_waiting_queued_no_start_after_deadline_and_stream_abort() {
    let mut l = Ledger::new(manifest(33)).unwrap();
    for id in 0..32 {
        offer(&mut l, id, id as u64, 1, 0);
    }
    l.begin_decode(0).unwrap();
    l.offer(l.manifest().work(32, 32, 1), 0).unwrap();
    assert!(l.start(2_000_000_001).unwrap().is_none());
    while l.sweep(2_000_000_001).unwrap() {}
    let s = l.snapshot();
    assert_eq!((s.occupied, s.decoded_staging), (0, 0));
    assert_eq!(s.permits_acquired, s.permits_released);
    assert!(s.originals.iter().all(|o| o.starts == 0));
    let mut l = Ledger::new(manifest(2)).unwrap();
    offer(&mut l, 0, 0, 1, 0);
    offer(&mut l, 1, 1, 1, 0);
    l.start(0).unwrap();
    l.fail(1, "STREAM_FAILED").unwrap();
    l.sweep(2).unwrap();
    l.observe_cancel(0, 3).unwrap();
    l.exit(0, 3, 4, false).unwrap();
    assert!(l.response(5).unwrap().is_none());
    let s = l.snapshot();
    assert_eq!(s.occupied, 0);
    assert!(s.attempts.iter().all(|a| a.undelivered));
    assert!(s
        .originals
        .iter()
        .all(|o| o.terminal.as_ref().unwrap().outcome == Outcome::Cancelled as i32));
}
#[test]
fn reject_changed_identity_and_attempt_id_alias_without_mutation() {
    for change in 0..7 {
        let mut l = Ledger::new(manifest(2)).unwrap();
        offer(&mut l, 0, 7, 1, 0);
        l.begin_decode(0).unwrap();
        let mut w = l.manifest().work(0, 8, 2);
        match change {
            0 => w.payload[0] ^= 1,
            1 => w.deadline_offset_ns += 1,
            2 => w.client_id += 1,
            3 => w.payload_sha256[0] ^= 1,
            4 => w.attempt_number = 4,
            5 => w.run_id = "changed-run".into(),
            _ => w.expendable = false,
        }
        assert!(matches!(l.offer(w, 0), Err(Error::Protocol(_))));
        assert_eq!(l.snapshot().attempt_entries, 1);
    }
    let mut l = Ledger::new(manifest(2)).unwrap();
    offer(&mut l, 0, 7, 1, 0);
    l.begin_decode(0).unwrap();
    assert_eq!(
        l.offer(l.manifest().work(1, 7, 1), 0),
        Err(Error::Protocol("ATTEMPT_ID_REUSED"))
    );
}
#[test]
fn metadata_exhaustion_never_evicts_and_log_pressure_never_silently_loses() {
    for (logical, attempts) in [(1, 8640), (2880, 1)] {
        let mut l = Ledger::with_limits(manifest(2), logical, attempts).unwrap();
        offer(&mut l, 0, 0, 1, 0);
        l.begin_decode(0).unwrap();
        assert_eq!(l.offer(l.manifest().work(1, 1, 1), 0), Err(Error::Capacity));
        assert_eq!(l.snapshot().logical_entries, 1);
        assert_eq!(l.snapshot().attempt_entries, 1);
    }
    let mut l = Ledger::new(manifest(1)).unwrap();
    for t in 0..1024 {
        l.note(t).unwrap();
    }
    assert_eq!(l.begin_decode(1024), Err(Error::Blocked));
    assert_eq!(l.snapshot().logical_entries, 0);
    for seq in 1..=1024 {
        assert_eq!(l.pop_event().unwrap().seq, seq);
    }
    assert!(l.pop_event().is_none());
    l.begin_decode(1025).unwrap();
    assert_eq!(l.pop_event().unwrap().seq, 1025);
}
#[test]
fn concurrent_same_identity_registration_is_atomic() {
    use std::sync::{Arc, Barrier, Mutex};
    let l = Arc::new(Mutex::new(Ledger::new(manifest(1)).unwrap()));
    let b = Arc::new(Barrier::new(3));
    std::thread::scope(|scope| {
        for id in 1..=2 {
            let l = l.clone();
            let b = b.clone();
            scope.spawn(move || {
                b.wait();
                let mut l = l.lock().unwrap();
                l.begin_decode(0).unwrap();
                let w = l.manifest().work(0, id, id as u32);
                l.offer(w, 0).unwrap();
                l.progress_stage(0).unwrap();
            });
        }
        b.wait();
    });
    let mut l = l.lock().unwrap();
    l.start(1).unwrap();
    l.exit(0, 2, 2, true).unwrap();
    assert_eq!(l.snapshot().originals[0].starts, 1);
    assert_eq!(l.snapshot().attempt_entries, 2);
}

#[test]
fn worker_start_phase_is_selected_once_and_worker_time_partitions_exactly() {
    let mut m = manifest(2);
    for s in &mut m.originals {
        s.deadline_offset_ns = 100_000_000_000;
    }
    let mut l = Ledger::new(m).unwrap();
    offer(&mut l, 0, 0, 1, 0);
    offer(&mut l, 1, 1, 1, 0);
    let (_, _, delay) = l.start(12_000_000_000).unwrap().unwrap();
    assert_eq!(delay, 40);
    l.exit(0, 24_000_000_000, 24_000_000_000, true).unwrap();
    let (_, _, delay) = l.start(24_000_000_000).unwrap().unwrap();
    assert_eq!(delay, 10);
    l.request_cancel(1, 24_000_000_001, "CLIENT_CANCEL")
        .unwrap();
    l.observe_cancel(1, 24_000_000_002).unwrap();
    l.exit(1, 24_000_000_002, 24_000_000_003, false).unwrap();
    let s = l.snapshot();
    let by_outcome: u64 = s
        .originals
        .iter()
        .map(|o| o.terminal.as_ref().unwrap().worker_service_ns)
        .sum();
    let all: u64 = s
        .originals
        .iter()
        .map(|o| o.exit_ns.unwrap() - o.start_ns.unwrap())
        .sum();
    assert_eq!(by_outcome, all);
    assert_eq!(all, 12_000_000_003);
}
