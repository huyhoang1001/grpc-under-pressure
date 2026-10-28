mod controller;
mod histogram;

use controller::Controller;

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
    event_write_calls: u64,
    event_write_ns: u64,
    event_write_max_ns: u64,
    event_flush_calls: u64,
    event_flush_ns: u64,
    event_flush_max_ns: u64,
}
struct Item {
    payload: Payload,
    enqueued: Instant,
    service_start: Option<Instant>,
    phase: usize,
    selected_ms: u64,
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
    budget: usize,
    shrink_occupancy: usize,
    adaptive: bool,
    controller: Controller,
    controller_running: bool,
    controller_ticks: u64,
    budget_updates: u64,
    controller_io_ns: u64,
    controller_out: Option<BufWriter<File>>,
    queue_hist: [Histogram; 4],
    service_hist: [Histogram; 4],
    queue_total: Histogram,
    service_total: Histogram,
    events: Option<BufWriter<Box<dyn Write + Send>>>,
    scheduled: bool,
    constant_service_ms: u64,
    last_service_start_ns: u64,
    last_selected_ms: u64,
    last_service_phase: usize,
}
impl State {
    fn new(rx: mpsc::Receiver<Item>, events: Option<File>, budget: usize) -> Self {
        assert!((1..=K).contains(&budget));
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
            budget,
            shrink_occupancy: 0,
            adaptive: false,
            controller: Controller::default(),
            controller_running: false,
            controller_ticks: 0,
            budget_updates: 0,
            controller_io_ns: 0,
            controller_out: None,
            queue_hist: std::array::from_fn(|_| Histogram::default()),
            service_hist: std::array::from_fn(|_| Histogram::default()),
            queue_total: Histogram::default(),
            service_total: Histogram::default(),
            events: events
                .map(|f| BufWriter::with_capacity(65536, Box::new(f) as Box<dyn Write + Send>)),
            scheduled: false,
            constant_service_ms: 10,
            last_service_start_ns: 0,
            last_selected_ms: 0,
            last_service_phase: 0,
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
        let service_event = matches!(kind, "dequeued" | "processed" | "discarded_worker");
        let start_ns = if service_event {
            self.last_service_start_ns.to_string()
        } else {
            String::new()
        };
        let selected_ms = if service_event {
            self.last_selected_ms.to_string()
        } else {
            String::new()
        };
        let service_phase = if service_event {
            self.last_service_phase.to_string()
        } else {
            String::new()
        };
        if let Some(out) = self.events.as_mut() {
            let io_start = Instant::now();
            if writeln!(
                out,
                "{elapsed},{kind},{},{bytes},{enqueue_ns},{},{},{queue_ns},{service_ns},{p},{start_ns},{selected_ms},{service_phase}",
                seq.map(|n| n.to_string()).unwrap_or_default(),
                dequeue.map(|n| n.to_string()).unwrap_or_default(),
                completion.map(|n| n.to_string()).unwrap_or_default()
            )
            .is_err()
            {
                self.c.telemetry_errors += 1;
            }
            let cost = ns(io_start.elapsed());
            self.c.event_write_calls += 1;
            self.c.event_write_ns += cost;
            self.c.event_write_max_ns = self.c.event_write_max_ns.max(cost);
        }
    }
    fn flush_events(&mut self) -> std::io::Result<()> {
        if let Some(out) = self.events.as_mut() {
            let start = Instant::now();
            let result = out.flush();
            let cost = ns(start.elapsed());
            self.c.event_flush_calls += 1;
            self.c.event_flush_ns += cost;
            self.c.event_flush_max_ns = self.c.event_flush_max_ns.max(cost);
            result?;
        }
        Ok(())
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
        assert!(
            self.c.q <= K
                && self.c.w <= 1
                && self.c.r <= 1
                && self.c.q + self.c.r <= self.budget.max(self.shrink_occupancy)
        );
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
    fn set_budget(&mut self, budget: usize) -> bool {
        assert!((1..=K).contains(&budget));
        if self.eof || self.terminal || !self.adaptive || budget == self.budget {
            return false;
        }
        if budget < self.budget {
            self.shrink_occupancy = self.c.q + self.c.r;
        }
        self.budget = budget;
        self.budget_updates += 1;
        self.verify();
        true
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
            item.selected_ms =
                service_delay(self.elapsed(now), self.scheduled, self.constant_service_ms);
            self.last_service_start_ns = self.elapsed(now);
            self.last_selected_ms = item.selected_ms;
            self.last_service_phase = if self.scheduled {
                phase(self.elapsed(now))
            } else {
                0
            };
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
    controller_stop: watch::Sender<bool>,
}
impl Shared {
    fn new(events: Option<File>, budget: usize) -> Arc<Self> {
        let (tx, rx) = mpsc::channel(K);
        let (stop, _) = watch::channel(false);
        let (start, _) = watch::channel(false);
        let (controller_stop, _) = watch::channel(false);
        Arc::new(Self {
            s: Mutex::new(State::new(rx, events, budget)),
            tx,
            changed: Notify::new(),
            stop,
            start,
            controller_stop,
        })
    }
    fn fail(&self, reason: &'static str) {
        self.s.lock().unwrap().terminate(reason);
        self.stop.send_replace(true);
        self.controller_stop.send_replace(true);
        self.changed.notify_waiters();
    }
}

#[derive(Default)]
struct TickWindow {
    start_ns: u64,
    completions: u64,
    service_ns: u64,
}
fn number(value: Option<f64>) -> String {
    value.map(|v| v.to_string()).unwrap_or_default()
}
fn control_tick(shared: &Shared, scheduled_ns: u64, previous: &mut TickWindow) -> bool {
    let mut s = shared.s.lock().unwrap();
    if s.eof || s.terminal {
        return false;
    }
    let now = Instant::now();
    s.touch(now);
    let observed = s.elapsed(now);
    let (n, total) = (s.service_total.count, s.service_total.sum);
    let count = n - previous.completions;
    let service_ns = total - previous.service_ns;
    let (q, r, w, before) = (s.c.q, s.c.r, s.c.w, s.budget);
    let decision = s.controller.tick(count, service_ns, q, r, before);
    let changed = s.set_budget(decision.proposed);
    s.controller_ticks += 1;
    let values = [
        scheduled_ns.to_string(),
        observed.to_string(),
        observed.saturating_sub(scheduled_ns).to_string(),
        previous.start_ns.to_string(),
        count.to_string(),
        service_ns.to_string(),
        number(decision.mean_ms),
        number(s.controller.ewma_ms),
        number(decision.delay_ms),
        q.to_string(),
        r.to_string(),
        w.to_string(),
        before.to_string(),
        decision.proposed.to_string(),
        s.budget.to_string(),
        u8::from(decision.near_full).to_string(),
        decision.high_before.to_string(),
        decision.low_before.to_string(),
        s.controller.high.to_string(),
        s.controller.low.to_string(),
        decision.reason.into(),
        if s.adaptive {
            decision.reason
        } else {
            "fixed_policy_hold"
        }
        .into(),
        s.shrink_occupancy.to_string(),
        n.to_string(),
        total.to_string(),
    ];
    let io_start = Instant::now();
    if let Some(out) = s.controller_out.as_mut() {
        if writeln!(out, "{}", values.join(","))
            .and_then(|_| out.flush())
            .is_err()
        {
            s.c.telemetry_errors += 1;
        }
    }
    s.controller_io_ns += ns(io_start.elapsed());
    *previous = TickWindow {
        start_ns: observed,
        completions: n,
        service_ns: total,
    };
    s.verify();
    let healthy = s.c.telemetry_errors == 0;
    drop(s);
    if changed {
        // Both growth and shrink wake already-registered waiters to recheck O<B.
        shared.changed.notify_waiters();
    }
    healthy
}

struct ControllerGuard {
    shared: Arc<Shared>,
    normal: bool,
}
impl Drop for ControllerGuard {
    fn drop(&mut self) {
        if !self.normal {
            self.shared.fail("controller_failed");
        }
        let mut s = self.shared.s.lock().unwrap();
        s.controller_running = false;
        s.event("controller_stopped", None, 0, (0, 0, 0), 0);
    }
}
async fn control(shared: Arc<Shared>) {
    let mut guard = ControllerGuard {
        shared: shared.clone(),
        normal: false,
    };
    let mut stopped = shared.controller_stop.subscribe();
    let start = {
        let mut s = shared.s.lock().unwrap();
        s.controller_running = true;
        s.event("controller_started", None, 0, (0, 0, 0), 0);
        s.started.expect("controller starts after workload marker")
    };
    let period = Duration::from_millis(500);
    let mut ticker =
        tokio::time::interval_at(tokio::time::Instant::from_std(start + period), period);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut previous = TickWindow::default();
    loop {
        if *stopped.borrow() {
            guard.normal = true;
            return;
        }
        tokio::select! {
            biased;
            _ = stopped.changed() => {},
            target = ticker.tick() => {
                let scheduled = ns(target.into_std().duration_since(start));
                if !control_tick(&shared, scheduled, &mut previous) {
                    guard.normal = {
                        let s = shared.s.lock().unwrap();
                        s.eof || s.terminal
                    };
                    return;
                }
            }
        }
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
            selected_ms: 0,
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
        tokio::pin!(notified);
        notified.as_mut().enable();
        {
            let mut s = shared.s.lock().unwrap();
            s.touch(Instant::now());
            if s.terminal {
                return Err(Status::cancelled("admission terminated"));
            }
            // One gate for every policy. Carryover never authorizes new acquisition; W is excluded.
            if s.c.q + s.c.r < s.budget {
                s.c.r += 1;
                s.c.acquired += 1;
                let physical_start = Instant::now();
                let permit = match shared.tx.clone().try_reserve_owned() {
                    Ok(permit) => permit,
                    Err(_) => {
                        // Logical acquisition has exactly one terminal outcome even on failure.
                        s.event("reservation_acquired", None, 0, (0, 0, 0), 0);
                        s.c.r -= 1;
                        s.c.released += 1;
                        s.event("reservation_released", None, 0, (0, 0, 0), 0);
                        s.verify();
                        return Err(Status::internal("physical reservation failed"));
                    }
                };
                s.c.gate_wait += ns(start.elapsed());
                s.c.physical_wait += ns(physical_start.elapsed());
                s.event("reservation_acquired", None, 0, (0, 0, 0), 0);
                s.verify();
                return Ok(Reservation {
                    shared: shared.clone(),
                    permit: Some(permit),
                });
            }
        }
        tokio::select! { _=notified.as_mut()=>{}, _=stopped.changed()=>return Err(Status::cancelled("worker stopped while waiting for capacity")) }
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
    scheduled: bool,
}
fn service_delay(elapsed_ns: u64, scheduled: bool, constant_ms: u64) -> u64 {
    if scheduled && (12_000_000_000..24_000_000_000).contains(&elapsed_ns) {
        40
    } else if scheduled {
        10
    } else {
        constant_ms
    }
}
fn service_phase(elapsed_ns: u64, scheduled: bool) -> &'static str {
    if !scheduled {
        return "stage1_constant";
    }
    ["healthy", "slowdown", "recovery", "drain"][phase(elapsed_ns)]
}
async fn worker(shared: Arc<Shared>, config: Config) {
    {
        let mut state = shared.s.lock().unwrap();
        state.scheduled = config.scheduled;
        state.constant_service_ms = config.service_ms;
    }
    let mut guard = WorkerGuard {
        shared: shared.clone(),
        normal: false,
        reason: "worker_aborted",
    };
    loop {
        let notified = shared.changed.notified();
        tokio::pin!(notified);
        notified.as_mut().enable();
        let selected_delay = {
            let mut s = shared.s.lock().unwrap();
            if s.terminal {
                guard.normal = true;
                return;
            }
            if s.dequeue(Instant::now()) {
                Some(s.worker.as_ref().unwrap().selected_ms)
            } else if s.eof {
                s.touch(Instant::now());
                s.mode = Mode::Stopped;
                s.reason = "normal_eof_drained";
                s.verify();
                guard.normal = true;
                return;
            } else {
                None
            }
        };
        if let Some(selected_ms) = selected_delay {
            shared.changed.notify_one();
            tokio::time::sleep(Duration::from_millis(selected_ms)).await;
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
    controller_task: Option<tokio::task::JoinHandle<()>>,
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
        if let Some(task) = self.controller_task.as_ref() {
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
        controller_task: None,
        normal: false,
    };
    let mut started = shared.start.subscribe();
    let mut stopped = shared.stop.subscribe();
    while !*started.borrow() {
        tokio::select! {_=started.changed()=>{},_=stopped.changed()=>return Err(Status::cancelled("stopped before marker"))}
    }
    guard.controller_task = Some(tokio::spawn(control(shared.clone())));
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
            shared.controller_stop.send_replace(true);
            shared.changed.notify_one();
            break;
        }
    }
    if let Some(task) = guard.controller_task.as_mut() {
        task.await
            .map_err(|_| Status::internal("controller failed"))?;
    }
    guard.controller_task.take();
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
    writeln!(out,"{{\"schema\":\"e2-stage1-histogram-v1\",\"convention\":\"nearest-rank upper bucket bound; exact durations in events.csv\",\"phase_assignment\":\"enqueue time: [0,12),[12,24),[24,36),[36,infinity); enqueue-phase assignment is independent of selected service schedule\",\"bounds_ns\":{:?},\"queue_counts\":[",histogram::bounds())?;
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
    writeln!(out,"unix_ns,elapsed_ns,started,physical_queue_depth,Q,R,W,queued_payload_bytes,handler_payload_bytes,worker_payload_bytes,received,admitted,dequeued,processed,discarded_from_queue,discarded_from_worker,discarded,received_not_admitted,reservations_acquired,reservations_released,logical_gate_wait_ns,physical_reservation_wait_ns,worker_busy_ns,worker_idle_ns,worker_idle_backlog_ns,queue_residence_violations,queue_p50_upper_ns,queue_p95_upper_ns,queue_p99_upper_ns,service_p50_upper_ns,service_p95_upper_ns,service_p99_upper_ns,errors,telemetry_errors,active_streams,connections,B,service_ms,service_phase,terminal_reason,rss_bytes,received_bytes,admitted_bytes,dequeued_bytes,processed_bytes,discarded_queue_bytes,discarded_worker_bytes,received_not_admitted_bytes,event_write_calls,event_write_ns,event_write_max_ns,event_flush_calls,event_flush_ns,event_flush_max_ns,inflight_selected_ms,queue_observations,queue_residence_sum_ns,service_observations,service_duration_sum_ns,physical_capacity,physical_available_capacity,logical_pending,shrink_occupancy,controller_running,controller_ticks,budget_updates,controller_io_ns,adaptive_policy").unwrap();
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
            s.flush_events().unwrap();
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
                s.budget.to_string(),
                service_delay(s.elapsed(now), s.scheduled, s.constant_service_ms).to_string(),
                service_phase(s.elapsed(now), s.scheduled).into(),
                s.reason.into(),
                memory.to_string(),
                c.received_bytes.to_string(),
                c.admitted_bytes.to_string(),
                c.dequeued_bytes.to_string(),
                c.processed_bytes.to_string(),
                c.dqbytes.to_string(),
                c.dwbytes.to_string(),
                c.not_admitted_bytes.to_string(),
                c.event_write_calls.to_string(),
                c.event_write_ns.to_string(),
                c.event_write_max_ns.to_string(),
                c.event_flush_calls.to_string(),
                c.event_flush_ns.to_string(),
                c.event_flush_max_ns.to_string(),
                s.worker
                    .as_ref()
                    .map(|item| item.selected_ms)
                    .unwrap_or(0)
                    .to_string(),
                q.count.to_string(),
                q.sum.to_string(),
                h.count.to_string(),
                h.sum.to_string(),
                shared.tx.max_capacity().to_string(),
                shared.tx.capacity().to_string(),
                (c.q + c.r).to_string(),
                s.shrink_occupancy.to_string(),
                u8::from(s.controller_running).to_string(),
                s.controller_ticks.to_string(),
                s.budget_updates.to_string(),
                s.controller_io_ns.to_string(),
                u8::from(s.adaptive).to_string(),
            ];
            writeln!(out, "{}", values.join(",")).unwrap();
            out.flush().unwrap();
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
    writeln!(events,"observed_elapsed_ns,event,sequence,payload_bytes,enqueue_ns,dequeue_ns,completion_ns,queue_residence_ns,service_duration_ns,enqueue_phase,service_start_ns,selected_service_ms,service_start_phase")?;
    let policy = option(&args, "--policy", "fixed32");
    let budget = match policy.as_str() {
        "fixed32" => 32,
        "fixed8" => 8,
        "adaptive" => 16,
        _ => return Err("policy must be fixed32, fixed8 or adaptive".into()),
    };
    let shared = Shared::new(Some(events), budget);
    {
        let mut s = shared.s.lock().unwrap();
        s.adaptive = policy == "adaptive";
        let mut out = BufWriter::with_capacity(65536, create(&dir.join("controller.csv"))?);
        writeln!(out, "scheduled_ns,observed_ns,lateness_ns,window_start_ns,interval_completions,interval_service_ns,interval_mean_ms,ewma_ms,estimated_delay_ms,Q,R,W,B_before,B_proposed,B_after,near_full,high_before,low_before,high_after,low_after,proposal_reason,decision_reason,shrink_occupancy,total_completions,total_service_ns")?;
        out.flush()?;
        s.controller_out = Some(out);
    }
    let event_io = option(&args, "--event-io", "buffered");
    assert!(
        ["buffered", "discard"].contains(&event_io.as_str()),
        "invalid event I/O mode"
    );
    if event_io == "discard" {
        shared.s.lock().unwrap().events =
            Some(BufWriter::with_capacity(65536, Box::new(std::io::sink())));
    }
    let schedule = option(&args, "--service-schedule", "constant");
    assert!(
        ["constant", "contract"].contains(&schedule.as_str()),
        "invalid schedule"
    );
    let config = Config {
        service_ms: option(&args, "--service-ms", "10").parse()?,
        fail_after: option(&args, "--test-fail-after", "0").parse()?,
        panic_after: option(&args, "--test-panic-after", "0").parse()?,
        scheduled: schedule == "contract",
    };
    assert_eq!(
        config.service_ms, 10,
        "base service must remain 10ms; contract flag alone selects the frozen schedule"
    );
    shared.s.lock().unwrap().scheduled = config.scheduled;
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
    let phase_shared = shared.clone();
    let phase_path = dir.join("phase-transitions.csv");
    let transitions = tokio::spawn(async move {
        let result: std::io::Result<()> = async {
            let mut started = phase_shared.start.subscribe();
            while !*started.borrow() {
                started.changed().await.map_err(std::io::Error::other)?;
            }
            let start = phase_shared.s.lock().unwrap().started.unwrap();
            let mut out = BufWriter::new(create(&phase_path)?);
            writeln!(
                out,
                "scheduled_ns,observed_ns,lateness_ns,phase,configured_ms,unix_ns"
            )?;
            let boundaries: &[u64] = if config.scheduled {
                &[0, 12, 24, 36]
            } else {
                &[0]
            };
            for seconds in boundaries {
                let target = start + Duration::from_secs(*seconds);
                tokio::time::sleep_until(tokio::time::Instant::from_std(target)).await;
                let observed = ns(start.elapsed());
                let expected = seconds * 1_000_000_000;
                writeln!(
                    out,
                    "{expected},{observed},{},{},{},{}",
                    observed.saturating_sub(expected),
                    service_phase(expected, config.scheduled),
                    service_delay(expected, config.scheduled, 10),
                    epoch()
                )?;
                out.flush()?;
            }
            Ok(())
        }
        .await;
        if let Err(error) = result {
            phase_shared.fail("phase_marker_failed");
            eprintln!("phase marker failed: {error}");
        }
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
    transitions.abort();
    Ok(())
}

#[cfg(test)]
mod tests;
