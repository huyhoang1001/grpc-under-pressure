use pressure_e3_stage1::{
    ledger::{Ledger, Manifest},
    measurement::calibrate,
};
#[test]
fn event_resources_queue_timing_and_writer_counter_are_reconstructible() {
    let mut l = Ledger::new(Manifest::primary("measurement")).unwrap();
    l.begin_decode(0).unwrap();
    l.offer(l.manifest().work(0, 0, 1), 1).unwrap();
    l.progress_stage(2).unwrap();
    l.start(5).unwrap();
    l.exit(0, 15, 15, true).unwrap();
    l.record_writer_progress(7);
    let frame = l.response(16).unwrap().unwrap();
    l.accepted_write(&frame, 17).unwrap();
    let s = l.snapshot();
    assert_eq!(s.originals[0].admitted_ns, Some(2));
    assert_eq!(s.originals[0].start_ns, Some(5));
    assert_eq!(s.writer_progress_ns, 7);
    assert_eq!(s.writer_calls, 1);
    let mut last = 0;
    while let Some(e) = l.pop_event() {
        assert_eq!(e.seq, last + 1);
        last = e.seq;
        assert!(e.resources.events <= 1024);
        assert!(e.resources.staging + e.resources.receive <= 1);
        if e.kind == "worker_exit" {
            assert_eq!(e.terminal.unwrap().worker_service_ns, 10);
        }
    }
    assert_eq!(last, s.event_seq);
    assert_eq!(s.high_water.terminal, 1);
}
#[test]
fn real_clock_brackets_are_bounded_for_future_epoch() {
    let b = calibrate(tokio::time::Instant::now() + std::time::Duration::from_secs(1));
    assert_eq!(b.samples, 8);
    assert!(b.epoch_max_ns >= b.epoch_min_ns);
    assert!(b.bracket_ns < 5_000_000);
}
