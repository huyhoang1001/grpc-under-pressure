//! Calibration microfixture: incremental JSON+file I/O cost, not a policy benchmark.
use pressure_e3_stage1::ledger::{Ledger, Manifest};
use std::{
    fs::File,
    io::{BufWriter, Write},
    time::Instant,
};
fn arg(name: &str) -> String {
    std::env::args()
        .collect::<Vec<_>>()
        .windows(2)
        .find(|a| a[0] == name)
        .unwrap()[1]
        .clone()
}
fn cpu_ns() -> u64 {
    let mut r = std::mem::MaybeUninit::<libc::rusage>::uninit();
    assert_eq!(
        unsafe { libc::getrusage(libc::RUSAGE_SELF, r.as_mut_ptr()) },
        0
    );
    let r = unsafe { r.assume_init() };
    ((r.ru_utime.tv_sec + r.ru_stime.tv_sec) as u64) * 1_000_000_000
        + ((r.ru_utime.tv_usec + r.ru_stime.tv_usec) as u64) * 1000
}
fn main() {
    let mode = arg("--mode");
    assert!(mode == "file" || mode == "no-encoding");
    let dir = std::path::PathBuf::from(arg("--output"));
    std::fs::create_dir(&dir).unwrap();
    let mut out =
        BufWriter::with_capacity(65536, File::create_new(dir.join("events.jsonl")).unwrap());
    let start = Instant::now();
    let before = cpu_ns();
    let mut events = 0;
    let mut total = 0;
    for _ in 0..5 {
        let mut manifest = Manifest::primary("measurement-cost");
        manifest.originals.truncate(64);
        let mut l = Ledger::new(manifest).unwrap();
        for id in 0..64 {
            let now = id as u64 * 12_500_000;
            l.begin_decode(now).unwrap();
            l.offer(l.manifest().work(id, id as u64, 1), now).unwrap();
            l.progress_stage(now).unwrap();
            l.start(now + 1).unwrap();
            l.exit(id, now + 2, now + 2, true).unwrap();
            let frame = l.response(now + 3).unwrap().unwrap();
            l.accepted_write(&frame, now + 4).unwrap();
            while let Some(event) = l.pop_event() {
                events += 1;
                if mode == "file" {
                    serde_json::to_writer(&mut out, &event).unwrap();
                    out.write_all(b"\n").unwrap();
                }
            }
        }
        let s = l.snapshot();
        assert_eq!(s.occupied, 0);
        assert_eq!(s.permits_acquired, s.permits_released);
        assert_eq!(s.permits_acquired, 64);
        total += 64;
    }
    out.flush().unwrap();
    let cpu = cpu_ns() - before;
    let wall = start.elapsed().as_nanos();
    serde_json::to_writer_pretty(File::create_new(dir.join("summary.json")).unwrap(),&serde_json::json!({"contract_revision":"A01","calibration_only":true,"mode":mode,"wall_ns":wall,"cpu_ns":cpu,"events":events,"unique_fixture_completions":total,"cpu_resolution_ns":1000,"note":"No service timers or network: only incremental JSON/file I/O cost; event construction and ledger instrumentation enabled in both modes."})).unwrap();
}
