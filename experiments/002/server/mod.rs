mod histogram;

use histogram::{phase, Histogram};
use pressure_server::protocol::{
    ingest_service_server::{IngestService, IngestServiceServer},
    Payload, Summary,
};
use std::{
    fs::{File, OpenOptions},
    io::{BufWriter, Write},
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tokio::{
    net::TcpListener,
    sync::{mpsc, watch, Notify},
};
use tokio_stream::{wrappers::TcpListenerStream, StreamExt};
use tonic::{Request, Response, Status, Streaming};

const K: usize = 32;
fn ns(d: Duration) -> u64 {
    d.as_nanos().min(u64::MAX as u128) as u64
}
fn epoch() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos()
}
fn create(path: &Path) -> std::io::Result<File> {
    OpenOptions::new().write(true).create_new(true).open(path)
}
#[derive(Default)]
struct Counts {
    received: u64,
    admitted: u64,
    dequeued: u64,
    processed: u64,
    dq: u64,
    dw: u64,
    not_admitted: u64,
    q: usize,
    r: usize,
    w: usize,
    qbytes: u64,
    hbytes: u64,
    wbytes: u64,
    acquired: u64,
    released: u64,
    errors: u64,
    telemetry_errors: u64,
    connections: u64,
    active: u64,
    received_bytes: u64,
    admitted_bytes: u64,
    dequeued_bytes: u64,
    processed_bytes: u64,
    dqbytes: u64,
    dwbytes: u64,
    not_admitted_bytes: u64,
    gate_wait: u64,
    physical_wait: u64,
    busy: u64,
    idle: u64,
    idle_backlog: u64,
    queue_violations: u64,
}
struct Item {
    payload: Payload,
    enqueued: Instant,
    service_start: Option<Instant>,
    phase: usize,
}
#[derive(Clone, Copy, PartialEq)]
enum Mode {
    Idle,
    Busy,
    Stopped,
}
struct State {
    c: Counts,
    rx: mpsc::Receiver<Item>,
    worker: Option<Item>,
    started: Option<Instant>,
    last: Option<Instant>,
    mode: Mode,
    eof: bool,
    terminal: bool,
    ever_started: bool,
    reason: &'static str,
    queue_hist: [Histogram; 4],
    service_hist: [Histogram; 4],
    queue_total: Histogram,
    service_total: Histogram,
    events: Option<BufWriter<File>>,
}
impl State {
    fn new(rx: mpsc::Receiver<Item>, events: Option<File>) -> Self {
        Self {
            c: Counts::default(),
            rx,
            worker: None,
            started: None,
            last: None,
            mode: Mode::Idle,
            eof: false,
            terminal: false,
            ever_started: false,
            reason: "running",
            queue_hist: std::array::from_fn(|_| Histogram::default()),
            service_hist: std::array::from_fn(|_| Histogram::default()),
            queue_total: Histogram::default(),
            service_total: Histogram::default(),
            events: events.map(|f| BufWriter::with_capacity(65536, f)),
        }
    }
    fn elapsed(&self, now: Instant) -> u64 {
        self.started
            .map(|t| ns(now.saturating_duration_since(t)))
            .unwrap_or(0)
    }
    fn touch(&mut self, now: Instant) {
        if let Some(last) = self.last {
            let delta = ns(now.saturating_duration_since(last));
            match self.mode {
                Mode::Busy => self.c.busy += delta,
                Mode::Idle => {
                    self.c.idle += delta;
                    if self.c.q > 0 {
                        self.c.idle_backlog += delta;
                    }
                }
                Mode::Stopped => {}
            }
            self.last = Some(now);
        }
    }
    fn event(
        &mut self,
        kind: &str,
        seq: Option<u64>,
        bytes: u64,
        timing: (u64, u64, u64),
        p: usize,
    ) {
        let (enqueue_ns, queue_ns, service_ns) = timing;
        let elapsed = self.elapsed(Instant::now());
        let dequeue = if matches!(kind, "dequeued" | "processed" | "discarded_worker") {
            Some(enqueue_ns + queue_ns)
        } else {
            None
        };
        let completion = if kind == "processed" {
            dequeue.map(|d| d + service_ns)
        } else {
            None
        };
        if let Some(out) = self.events.as_mut() {
            if writeln!(
                out,
                "{elapsed},{kind},{},{bytes},{enqueue_ns},{},{},{queue_ns},{service_ns},{p}",
                seq.map(|n| n.to_string()).unwrap_or_default(),
                dequeue.map(|n| n.to_string()).unwrap_or_default(),
                completion.map(|n| n.to_string()).unwrap_or_default()
            )
            .is_err()
            {
                self.c.telemetry_errors += 1;
            }
        }
    }
    fn verify(&self) {
        assert_eq!(self.c.queue_violations, 0);
        assert_eq!(
            self.c.q as u64,
            self.c.admitted - self.c.dequeued - self.c.dq
        );
        assert_eq!(
            self.c.w as u64,
            self.c.dequeued - self.c.processed - self.c.dw
        );
        assert_eq!(self.c.q, self.rx.len());
        assert_eq!(self.c.w, usize::from(self.worker.is_some()));
        assert!(self.c.q <= K && self.c.w <= 1 && self.c.r <= 1 && self.c.q + self.c.r <= K);
        assert_eq!(self.c.received, self.c.admitted + self.c.not_admitted);
        assert_eq!(
            self.c.received_bytes,
            self.c.admitted_bytes + self.c.not_admitted_bytes
        );
        assert_eq!(
            self.c.qbytes,
            self.c.admitted_bytes - self.c.dequeued_bytes - self.c.dqbytes
        );
        assert_eq!(
            self.c.wbytes,
            self.c.dequeued_bytes - self.c.processed_bytes - self.c.dwbytes
        );
        assert_eq!(
            self.c.acquired,
            self.c.admitted + self.c.released + self.c.r as u64
        );
        assert_eq!(
            self.c.wbytes,
            self.worker
                .as_ref()
                .map(|p| p.payload.data.len() as u64)
                .unwrap_or(0)
        );
        assert_eq!(
            self.c.admitted,
            self.c.processed + self.c.dq + self.c.dw + self.c.q as u64 + self.c.w as u64
        );
    }
    fn dequeue(&mut self, now: Instant) -> bool {
        self.touch(now);
        if self.terminal {
            return false;
        }
        if let Ok(mut item) = self.rx.try_recv() {
            self.c.q -= 1;
            self.c.qbytes -= item.payload.data.len() as u64;
            self.c.w = 1;
            self.c.wbytes = item.payload.data.len() as u64;
            self.c.dequeued += 1;
            self.c.dequeued_bytes += self.c.wbytes;
            let residence = now.checked_duration_since(item.enqueued);
            if residence.is_none() {
                self.c.queue_violations += 1;
            }
            let queue_ns = residence.map(ns).unwrap_or(0);
            self.queue_hist[item.phase].record(queue_ns);
            self.queue_total.record(queue_ns);
            item.service_start = Some(now);
            self.mode = Mode::Busy;
            self.event(
                "dequeued",
                Some(item.payload.sequence),
                self.c.wbytes,
                (self.elapsed(item.enqueued), queue_ns, 0),
                item.phase,
            );
            self.worker = Some(item);
            self.verify();
            true
        } else {
            false
        }
    }
    fn complete(&mut self, now: Instant) {
        self.touch(now);
        if self.terminal {
            return;
        }
        let item = self
            .worker
            .take()
            .expect("completion requires worker ownership");
        let duration = ns(now.duration_since(item.service_start.unwrap()));
        self.service_hist[item.phase].record(duration);
        self.service_total.record(duration);
        self.event(
            "processed",
            Some(item.payload.sequence),
            item.payload.data.len() as u64,
            (
                self.elapsed(item.enqueued),
                ns(item.service_start.unwrap().duration_since(item.enqueued)),
                duration,
            ),
            item.phase,
        );
        self.c.processed_bytes += item.payload.data.len() as u64;
        drop(item);
        self.c.processed += 1;
        self.c.w = 0;
        self.c.wbytes = 0;
        self.mode = Mode::Idle;
        self.verify();
    }
    fn terminate(&mut self, reason: &'static str) {
        self.touch(Instant::now());
        if self.terminal {
            return;
        }
        self.terminal = true;
        self.reason = reason;
        self.c.errors += 1;
        while let Ok(item) = self.rx.try_recv() {
            self.event(
                "discarded_queue",
                Some(item.payload.sequence),
                item.payload.data.len() as u64,
                (self.elapsed(item.enqueued), 0, 0),
                item.phase,
            );
            self.c.dq += 1;
            self.c.dqbytes += item.payload.data.len() as u64;
            self.c.q -= 1;
            self.c.qbytes -= item.payload.data.len() as u64;
            drop(item);
        }
        if let Some(item) = self.worker.take() {
            self.event(
                "discarded_worker",
                Some(item.payload.sequence),
                item.payload.data.len() as u64,
                (
                    self.elapsed(item.enqueued),
                    item.service_start
                        .map(|t| ns(t.duration_since(item.enqueued)))
                        .unwrap_or(0),
                    item.service_start.map(|t| ns(t.elapsed())).unwrap_or(0),
                ),
                item.phase,
            );
            self.c.dwbytes += item.payload.data.len() as u64;
            drop(item);
            self.c.dw += 1;
            self.c.w = 0;
            self.c.wbytes = 0;
        }
        self.mode = Mode::Stopped;
        self.event("terminal", None, 0, (0, 0, 0), 0);
        self.verify();
    }
}
struct Shared {
    s: Mutex<State>,
    tx: mpsc::Sender<Item>,
    changed: Notify,
    stop: watch::Sender<bool>,
    start: watch::Sender<bool>,
}
impl Shared {
    fn new(events: Option<File>) -> Arc<Self> {
        let (tx, rx) = mpsc::channel(K);
        let (stop, _) = watch::channel(false);
        let (start, _) = watch::channel(false);
        Arc::new(Self {
            s: Mutex::new(State::new(rx, events)),
            tx,
            changed: Notify::new(),
            stop,
            start,
        })
    }
    fn fail(&self, reason: &'static str) {
        self.s.lock().unwrap().terminate(reason);
        self.stop.send_replace(true);
        self.changed.notify_waiters();
    }
}
struct Reservation {
    shared: Arc<Shared>,
    permit: Option<mpsc::OwnedPermit<Item>>,
}
impl Drop for Reservation {
    fn drop(&mut self) {
        if let Some(permit) = self.permit.take() {
            let mut s = self.shared.s.lock().unwrap();
            s.touch(Instant::now());
            drop(permit);
            s.c.r -= 1;
            s.c.released += 1;
            s.event("reservation_released", None, 0, (0, 0, 0), 0);
            s.verify();
            self.shared.changed.notify_one();
        }
    }
}
impl Reservation {
    fn handoff(mut self, payload: Payload) -> Result<(), Status> {
        let mut s = self.shared.s.lock().unwrap();
        let now = Instant::now();
        s.touch(now);
        s.c.received += 1;
        s.c.hbytes = payload.data.len() as u64;
        s.c.received_bytes += s.c.hbytes;
        if s.terminal {
            s.c.not_admitted += 1;
            s.c.not_admitted_bytes += s.c.hbytes;
            let bytes = s.c.hbytes;
            s.event(
                "received_not_admitted",
                Some(payload.sequence),
                bytes,
                (0, 0, 0),
                0,
            );
            drop(payload);
            s.c.hbytes = 0;
            s.verify();
            return Err(Status::cancelled("terminal before handoff"));
        }
        let bytes = payload.data.len() as u64;
        let enqueue_ns = s.elapsed(now);
        let p = phase(enqueue_ns);
        s.event(
            "admitted",
            Some(payload.sequence),
            bytes,
            (enqueue_ns, 0, 0),
            p,
        );
        self.permit.take().unwrap().send(Item {
            payload,
            enqueued: now,
            service_start: None,
            phase: p,
        });
        s.c.r -= 1;
        s.c.q += 1;
        s.c.qbytes += bytes;
        s.c.hbytes = 0;
        s.c.admitted += 1;
        s.c.admitted_bytes += bytes;
        s.verify();
        self.shared.changed.notify_one();
        Ok(())
    }
}
async fn reserve(shared: Arc<Shared>) -> Result<Reservation, Status> {
    let start = Instant::now();
    let mut stopped = shared.stop.subscribe();
    loop {
        // Notify::notify_one stores a permit if a dequeue races this await.
        let notified = shared.changed.notified();
        {
            let mut s = shared.s.lock().unwrap();
            s.touch(Instant::now());
            if s.terminal {
                return Err(Status::cancelled("admission terminated"));
            }
            // Fixed K=32 only: logical R accounts the same physical reservation. No dynamic B.
            if s.c.q + s.c.r < K {
                let physical_start = Instant::now();
                let permit = shared
                    .tx
                    .clone()
                    .try_reserve_owned()
                    .map_err(|_| Status::internal("physical reservation disagrees with Q"))?;
                s.c.gate_wait += ns(start.elapsed());
                s.c.physical_wait += ns(physical_start.elapsed());
                s.c.r += 1;
                s.c.acquired += 1;
                s.event("reservation_acquired", None, 0, (0, 0, 0), 0);
                s.verify();
                return Ok(Reservation {
                    shared: shared.clone(),
                    permit: Some(permit),
                });
            }
        }
        tokio::select! { _=notified=>{}, _=stopped.changed()=>return Err(Status::cancelled("worker stopped while waiting for capacity")) }
    }
}
struct WorkerGuard {
    shared: Arc<Shared>,
    normal: bool,
    reason: &'static str,
}
impl Drop for WorkerGuard {
    fn drop(&mut self) {
        if !self.normal {
            self.shared.fail(if std::thread::panicking() {
                "worker_panic"
            } else {
                self.reason
            });
        }
    }
}
#[derive(Clone, Copy)]
struct Config {
    service_ms: u64,
    fail_after: u64,
    panic_after: u64,
}
async fn worker(shared: Arc<Shared>, config: Config) {
    let mut guard = WorkerGuard {
        shared: shared.clone(),
        normal: false,
        reason: "worker_aborted",
    };
    loop {
        let notified = shared.changed.notified();
        let has_work = {
            let mut s = shared.s.lock().unwrap();
            if s.terminal {
                guard.normal = true;
                return;
            }
            if s.dequeue(Instant::now()) {
                true
            } else if s.eof {
                s.touch(Instant::now());
                s.mode = Mode::Stopped;
                s.reason = "normal_eof_drained";
                s.verify();
                guard.normal = true;
                return;
            } else {
                false
            }
        };
        if has_work {
            shared.changed.notify_one();
            tokio::time::sleep(Duration::from_millis(config.service_ms)).await;
            let ordinal = shared.s.lock().unwrap().c.dequeued;
            if config.fail_after > 0 && ordinal == config.fail_after {
                guard.reason = "worker_error";
                return;
            }
            assert!(
                !(config.panic_after > 0 && ordinal == config.panic_after),
                "injected worker panic"
            );
            shared.s.lock().unwrap().complete(Instant::now());
        } else {
            notified.await;
        }
    }
}
struct HandlerGuard {
    shared: Arc<Shared>,
    task: Option<tokio::task::JoinHandle<()>>,
    normal: bool,
}
impl Drop for HandlerGuard {
    fn drop(&mut self) {
        if !self.normal {
            self.shared.fail("rpc_cancelled_or_failed");
        }
        if let Some(task) = self.task.as_ref() {
            task.abort();
        }
        let mut s = self.shared.s.lock().unwrap();
        s.c.active = 0;
        s.verify();
    }
}
#[allow(async_fn_in_trait)]
trait Inbound {
    async fn message(&mut self) -> Result<Option<Payload>, Status>;
}
impl Inbound for Streaming<Payload> {
    async fn message(&mut self) -> Result<Option<Payload>, Status> {
        self.message().await
    }
}
async fn ingest(
    mut stream: impl Inbound,
    shared: Arc<Shared>,
    config: Config,
) -> Result<Summary, Status> {
    {
        let mut s = shared.s.lock().unwrap();
        if s.ever_started {
            return Err(Status::resource_exhausted("one stream per process"));
        }
        s.ever_started = true;
        s.c.active = 1;
    }
    let mut guard = HandlerGuard {
        shared: shared.clone(),
        task: None,
        normal: false,
    };
    let mut started = shared.start.subscribe();
    let mut stopped = shared.stop.subscribe();
    while !*started.borrow() {
        tokio::select! {_=started.changed()=>{},_=stopped.changed()=>return Err(Status::cancelled("stopped before marker"))}
    }
    guard.task = Some(tokio::spawn(worker(shared.clone(), config)));
    loop {
        let reservation = reserve(shared.clone()).await?;
        let next = tokio::select! { result=stream.message()=>result?,_=stopped.changed()=>return Err(Status::cancelled("worker terminated during receive")) };
        if let Some(payload) = next {
            reservation.handoff(payload)?;
        } else {
            drop(reservation);
            let mut s = shared.s.lock().unwrap();
            s.eof = true;
            s.event("eof", None, 0, (0, 0, 0), 0);
            s.verify();
            shared.changed.notify_one();
            break;
        }
    }
    tokio::select! {
     result=guard.task.as_mut().unwrap()=>{result.map_err(|_|Status::internal("worker failed"))?;},
     _=stopped.changed()=>return Err(Status::internal("worker stopped during drain"))
    }
    guard.task.take();
    let summary = {
        let s = shared.s.lock().unwrap();
        s.verify();
        if s.terminal {
            return Err(Status::internal("terminal worker"));
        }
        Summary {
            accepted: s.c.admitted,
            processed: s.c.processed,
        }
    };
    guard.normal = true;
    Ok(summary)
}
#[derive(Clone)]
struct Service {
    shared: Arc<Shared>,
    config: Config,
}
#[tonic::async_trait]
impl IngestService for Service {
    async fn ingest(
        &self,
        request: Request<Streaming<Payload>>,
    ) -> Result<Response<Summary>, Status> {
        ingest(request.into_inner(), self.shared.clone(), self.config)
            .await
            .map(Response::new)
    }
}
fn rss() -> u64 {
    std::fs::read_to_string("/proc/self/status")
        .unwrap()
        .lines()
        .find_map(|l| {
            l.strip_prefix("VmRSS:")
                .and_then(|s| s.split_whitespace().next())
                .and_then(|n| n.parse::<u64>().ok())
        })
        .unwrap_or(0)
        * 1024
}
fn option(args: &[String], name: &str, default: &str) -> String {
    args.windows(2)
        .find(|w| w[0] == name)
        .map(|w| w[1].clone())
        .unwrap_or(default.to_owned())
}
fn write_histograms(shared: &Shared, path: &Path) -> std::io::Result<()> {
    let s = shared.s.lock().unwrap();
    let mut out = BufWriter::new(create(path)?);
    writeln!(out,"{{\"schema\":\"e2-stage1-histogram-v1\",\"convention\":\"nearest-rank upper bucket bound; exact durations in events.csv\",\"phase_assignment\":\"enqueue time: [0,12),[12,24),[24,36),[36,infinity); Stage1 service is constant\",\"bounds_ns\":{:?},\"queue_counts\":[",histogram::bounds())?;
    for (i, h) in s.queue_hist.iter().enumerate() {
        write!(out, "{}{:?}", if i > 0 { "," } else { "" }, h.counts)?;
    }
    write!(out, "],\"service_counts\":[")?;
    for (i, h) in s.service_hist.iter().enumerate() {
        write!(out, "{}{:?}", if i > 0 { "," } else { "" }, h.counts)?;
    }
    writeln!(out, "]}}")?;
    out.flush()
}
async fn sample(shared: Arc<Shared>, path: PathBuf, rss_limit: u64) {
    let mut out = BufWriter::new(create(&path).unwrap());
    writeln!(out,"unix_ns,elapsed_ns,started,physical_queue_depth,Q,R,W,queued_payload_bytes,handler_payload_bytes,worker_payload_bytes,received,admitted,dequeued,processed,discarded_from_queue,discarded_from_worker,discarded,received_not_admitted,reservations_acquired,reservations_released,logical_gate_wait_ns,physical_reservation_wait_ns,worker_busy_ns,worker_idle_ns,worker_idle_backlog_ns,queue_residence_violations,queue_p50_upper_ns,queue_p95_upper_ns,queue_p99_upper_ns,service_p50_upper_ns,service_p95_upper_ns,service_p99_upper_ns,errors,telemetry_errors,active_streams,connections,B,service_ms,service_phase,terminal_reason,rss_bytes,received_bytes,admitted_bytes,dequeued_bytes,processed_bytes,discarded_queue_bytes,discarded_worker_bytes,received_not_admitted_bytes").unwrap();
    let mut ticker = tokio::time::interval(Duration::from_millis(200));
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    loop {
        ticker.tick().await;
        let memory = rss();
        if memory > rss_limit {
            shared.fail("rss_limit");
        }
        {
            let mut s = shared.s.lock().unwrap();
            let now = Instant::now();
            s.touch(now);
            s.verify();
            let c = &s.c;
            let q = &s.queue_total;
            let h = &s.service_total;
            let values = [
                epoch().to_string(),
                s.elapsed(now).to_string(),
                u8::from(s.started.is_some()).to_string(),
                s.rx.len().to_string(),
                c.q.to_string(),
                c.r.to_string(),
                c.w.to_string(),
                c.qbytes.to_string(),
                c.hbytes.to_string(),
                c.wbytes.to_string(),
                c.received.to_string(),
                c.admitted.to_string(),
                c.dequeued.to_string(),
                c.processed.to_string(),
                c.dq.to_string(),
                c.dw.to_string(),
                (c.dq + c.dw).to_string(),
                c.not_admitted.to_string(),
                c.acquired.to_string(),
                c.released.to_string(),
                c.gate_wait.to_string(),
                c.physical_wait.to_string(),
                c.busy.to_string(),
                c.idle.to_string(),
                c.idle_backlog.to_string(),
                c.queue_violations.to_string(),
                q.quantile(50).to_string(),
                q.quantile(95).to_string(),
                q.quantile(99).to_string(),
                h.quantile(50).to_string(),
                h.quantile(95).to_string(),
                h.quantile(99).to_string(),
                c.errors.to_string(),
                c.telemetry_errors.to_string(),
                c.active.to_string(),
                c.connections.to_string(),
                K.to_string(),
                "10".into(),
                "stage1_constant".into(),
                s.reason.into(),
                memory.to_string(),
                c.received_bytes.to_string(),
                c.admitted_bytes.to_string(),
                c.dequeued_bytes.to_string(),
                c.processed_bytes.to_string(),
                c.dqbytes.to_string(),
                c.dwbytes.to_string(),
                c.not_admitted_bytes.to_string(),
            ];
            writeln!(out, "{}", values.join(",")).unwrap();
            out.flush().unwrap();
            if let Some(events) = s.events.as_mut() {
                events.flush().unwrap();
            }
            if c_telemetry_failed(&s) {
                eprintln!("instrumentation failed");
                std::process::exit(43);
            }
        }
        if memory > rss_limit {
            let _ = write_histograms(&shared, &path.parent().unwrap().join("histograms.json"));
            eprintln!("RSS safety abort");
            std::process::exit(42);
        }
    }
}
fn c_telemetry_failed(s: &State) -> bool {
    s.c.telemetry_errors > 0
}
async fn supervise(
    serving: impl std::future::Future<Output = Result<(), tonic::transport::Error>>,
    sampler: &mut tokio::task::JoinHandle<()>,
    shared: &Shared,
) -> Result<(), Box<dyn std::error::Error>> {
    tokio::select! {
        result = serving => { result?; Ok(()) },
        result = sampler => {
            shared.fail("instrumentation_failed");
            Err(format!("sampling task terminated unexpectedly: {result:?}").into())
        }
    }
}
#[tokio::main(worker_threads = 2)]
pub async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    let dir = PathBuf::from(option(&args, "--output", "stage1-output"));
    std::fs::create_dir_all(&dir)?;
    let mut events = create(&dir.join("events.csv"))?;
    writeln!(events,"observed_elapsed_ns,event,sequence,payload_bytes,enqueue_ns,dequeue_ns,completion_ns,queue_residence_ns,service_duration_ns,enqueue_phase")?;
    let shared = Shared::new(Some(events));
    let config = Config {
        service_ms: option(&args, "--service-ms", "10").parse()?,
        fail_after: option(&args, "--test-fail-after", "0").parse()?,
        panic_after: option(&args, "--test-panic-after", "0").parse()?,
    };
    assert_eq!(
        config.service_ms, 10,
        "Stage1 service is fixed at 10ms; no slowdown schedule"
    );
    let marker = PathBuf::from(option(&args, "--marker", "marker.txt"));
    let marker_shared = shared.clone();
    let marker_out = dir.clone();
    let clock = tokio::spawn(async move {
        let target: u128 = loop {
            if let Ok(text) = std::fs::read_to_string(&marker) {
                break text.trim().parse().unwrap();
            }
            tokio::time::sleep(Duration::from_millis(2)).await;
        };
        let now = epoch();
        let start = Instant::now() + Duration::from_nanos(target.saturating_sub(now) as u64);
        tokio::time::sleep_until(tokio::time::Instant::from_std(start)).await;
        let actual = epoch();
        {
            let mut s = marker_shared.s.lock().unwrap();
            s.started = Some(start);
            s.last = Some(start);
        }
        marker_shared.start.send_replace(true);
        std::fs::write(marker_out.join("clock.json"),format!("{{\"target_unix_ns\":{target},\"actual_start_unix_ns\":{actual},\"start_offset_ns\":{}}}",actual as i128-target as i128)).unwrap();
    });
    let mut metrics = tokio::spawn(sample(shared.clone(), dir.join("server.csv"), 536870912));
    let listener = TcpListener::bind(option(&args, "--addr", "127.0.0.1:50053")).await?;
    let incoming = TcpListenerStream::new(listener).map({
        let shared = shared.clone();
        move |socket| {
            socket.inspect(|_| {
                shared.s.lock().unwrap().c.connections += 1;
            })
        }
    });
    eprintln!("stage1 ready");
    let serving = tonic::transport::Server::builder()
        .initial_stream_window_size(65535)
        .initial_connection_window_size(65535)
        .http2_adaptive_window(Some(false))
        .max_concurrent_streams(1)
        .add_service(
            IngestServiceServer::new(Service {
                shared: shared.clone(),
                config,
            })
            .max_decoding_message_size(1024 * 1024),
        )
        .serve_with_incoming_shutdown(incoming, async {
            tokio::signal::ctrl_c().await.unwrap();
        });
    supervise(serving, &mut metrics, &shared).await?;
    write_histograms(&shared, &dir.join("histograms.json"))?;
    metrics.abort();
    clock.abort();
    Ok(())
}

#[cfg(test)]
mod tests;
