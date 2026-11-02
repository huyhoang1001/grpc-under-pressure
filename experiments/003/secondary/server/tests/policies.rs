use pressure_e3_stage1::{ledger::*, protocol::Outcome};
fn setup(policy: Policy) -> Ledger {
    let mut m = Manifest::primary("policies");
    m.originals.truncate(36);
    for s in &mut m.originals {
        s.scheduled_offset_ns = 0;
        s.deadline_offset_ns = 2_000_000_000;
    }
    Ledger::with_policy(m, policy).unwrap()
}
fn send(l: &mut Ledger, id: usize, attempt: u64, n: u32, now: u64) -> Result<(), Error> {
    l.begin_decode(now)?;
    l.offer(l.manifest().work(id, attempt, n), now)?;
    l.progress_stage(now)
}
fn fill(l: &mut Ledger) {
    for id in 0..32 {
        send(l, id, id as u64, 1, 0).unwrap();
    }
}
#[test]
fn t03_t04_shared_policy_boundary_and_refused_work_never_starts() {
    for policy in [Policy::Wait, Policy::Reject, Policy::Retry, Policy::Drop] {
        let mut l = setup(policy);
        fill(&mut l);
        let result = send(&mut l, 32, 32, 1, 1);
        if policy == Policy::Wait {
            assert_eq!(result, Err(Error::Blocked));
            assert_eq!(l.begin_decode(2), Err(Error::Blocked));
        } else {
            result.unwrap();
            let s = l.snapshot();
            let o = &s.originals[32];
            assert_eq!(o.starts, 0);
            assert_eq!(
                o.terminal.as_ref().unwrap().outcome,
                if policy == Policy::Drop {
                    Outcome::DroppedOverload
                } else {
                    Outcome::RejectedOverload
                } as i32
            );
            assert_eq!(s.immediate_responses, 1);
            assert_eq!(s.decoded_staging, 0);
        }
        assert_eq!(l.snapshot().occupied, 32);
        assert_eq!(l.snapshot().permits_acquired, 32);
    }
}
#[test]
fn t14_real_refusal_then_first_admission_and_immutable_attempt_history() {
    let mut l = setup(Policy::Retry);
    fill(&mut l);
    send(&mut l, 32, 100, 1, 1).unwrap();
    let old = l.snapshot().attempts[32].terminal.clone().unwrap();
    l.start(2).unwrap();
    l.exit(0, 3, 3, true).unwrap();
    // Free a terminal response slot without coupling worker permit release to ACK.
    while l.snapshot().terminal_responses_reserved == 32 {
        l.response(4).unwrap();
    }
    send(&mut l, 32, 101, 2, 5).unwrap();
    for time in 6..38 {
        let Some((id, _, _)) = l.start(time).unwrap() else {
            break;
        };
        l.exit(id, time, time, true).unwrap();
    }
    let s = l.snapshot();
    assert_eq!(s.originals[32].starts, 1);
    assert_eq!(
        s.attempts[32].terminal.as_ref().unwrap().event_seq,
        old.event_seq
    );
    assert_eq!(
        s.attempts[32].terminal.as_ref().unwrap().outcome,
        Outcome::RejectedOverload as i32
    );
    assert_eq!(
        s.attempts[33].terminal.as_ref().unwrap().outcome,
        Outcome::Completed as i32
    );
    assert_eq!(s.permits_acquired, s.permits_released);
    assert_eq!(l.manifest().originals[32].deadline_offset_ns, 2_000_000_000);
}
#[test]
fn policies_expiry_cancellation_permit_lifetime_and_terminal_capacity() {
    for policy in [Policy::Wait, Policy::Reject, Policy::Retry, Policy::Drop] {
        let mut l = setup(policy);
        fill(&mut l);
        l.start(1).unwrap();
        l.request_cancel(0, 2, "CLIENT_CANCEL").unwrap();
        assert_eq!(l.snapshot().occupied, 32);
        l.observe_cancel(0, 3).unwrap();
        assert_eq!(l.snapshot().occupied, 32);
        l.exit(0, 3, 4, false).unwrap();
        assert_eq!(l.snapshot().occupied, 31);
        // Free admission does not override exhausted terminal reservations.
        assert_eq!(send(&mut l, 32, 100, 1, 5), Err(Error::Blocked));
        while l.sweep(2_000_000_000).unwrap() {}
        let s = l.snapshot();
        assert_eq!(s.occupied, 0);
        assert_eq!(s.permits_acquired, s.permits_released);
        assert_eq!(s.originals[32].starts, 0);
        assert_eq!(
            s.originals[32].terminal.as_ref().unwrap().outcome,
            Outcome::Expired as i32
        );
        l.end_input(2_000_000_001).unwrap();
        while l.response(2_000_000_002).unwrap().is_some() {}
        assert!(l.drained());
    }
}
#[test]
fn full_immediate_queue_stops_decode_for_every_refusal_policy() {
    for policy in [Policy::Reject, Policy::Retry, Policy::Drop] {
        let mut m = Manifest::primary("full-responses");
        for s in &mut m.originals {
            s.scheduled_offset_ns = 0;
            s.deadline_offset_ns = 2_000_000_000;
        }
        let mut l = Ledger::with_policy(m, policy).unwrap();
        fill(&mut l);
        for id in 32..64 {
            send(&mut l, id, id as u64, 1, 1).unwrap();
        }
        assert_eq!(l.snapshot().immediate_responses, 32);
        assert_eq!(l.begin_decode(2), Err(Error::Blocked));
        for t in 3..35 {
            let (id, _, _) = l.start(t).unwrap().unwrap();
            l.exit(id, t, t, true).unwrap();
        }
        assert_eq!(l.snapshot().occupied, 0);
        assert_eq!(l.snapshot().permits_released, 32);
        while l.response(40).unwrap().is_some() {}
        l.end_input(41).unwrap();
        assert!(l.drained());
    }
}
#[test]
fn drop_nonexpendable_is_correlated_protocol_error_not_silent_drop() {
    let mut m = Manifest::primary("nonexpendable");
    m.originals[0].expendable = false;
    let mut l = Ledger::with_policy(m, Policy::Drop).unwrap();
    l.begin_decode(0).unwrap();
    assert_eq!(
        l.offer(l.manifest().work(0, 0, 1), 0),
        Err(Error::Protocol("DROP_REQUIRES_EXPENDABLE"))
    );
    assert_eq!(l.snapshot().permits_acquired, 0);
}
#[test]
fn stream_failure_cleanup_and_duplicate_execution_for_all_policies() {
    for policy in [Policy::Wait, Policy::Reject, Policy::Retry, Policy::Drop] {
        let mut l = setup(policy);
        send(&mut l, 0, 0, 1, 0).unwrap();
        send(&mut l, 0, 1, 2, 0).unwrap();
        l.start(1).unwrap();
        l.fail(2, "STREAM_FAILED").unwrap();
        l.observe_cancel(0, 3).unwrap();
        l.exit(0, 3, 4, false).unwrap();
        let s = l.snapshot();
        assert_eq!(s.originals[0].starts, 1);
        assert_eq!(s.occupied, 0);
        assert_eq!(s.permits_acquired, s.permits_released);
        assert!(l.response(5).unwrap().is_none());
    }
}
#[test]
fn t15_attempt_index_limit_after_three_real_refusals() {
    let mut l = setup(Policy::Retry);
    fill(&mut l);
    for n in 1..=3 {
        send(&mut l, 32, 100 + n as u64, n, n as u64).unwrap();
    }
    l.begin_decode(4).unwrap();
    assert_eq!(
        l.offer(l.manifest().work(32, 104, 3), 4),
        Err(Error::Protocol("ATTEMPT_LIMIT"))
    );
    assert_eq!(l.snapshot().attempt_entries, 35);
    assert_eq!(l.snapshot().originals[32].starts, 0);
}
