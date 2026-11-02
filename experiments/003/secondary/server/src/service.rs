//! Stage 1 transport adapter. No overload-policy selector or retry engine.
use crate::{
    ledger::{Error, Ledger, Manifest},
    protocol::{client_frame, overload_service_server::OverloadService, ClientFrame, ServerFrame},
};
use std::{
    io::{BufWriter, Write},
    pin::Pin,
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Arc, Mutex,
    },
    task::{Context, Poll},
    time::Duration,
};
use tokio::{
    sync::{mpsc, watch, Notify},
    task::JoinSet,
    time::{sleep_until, Instant},
};
use tokio_stream::Stream;
use tonic::{Request, Response, Status, Streaming};

#[derive(Clone)]
pub struct Gate {
    open: watch::Sender<bool>,
}
impl Gate {
    pub fn new(open: bool) -> Self {
        Self {
            open: watch::channel(open).0,
        }
    }
    pub fn set(&self, open: bool) {
        self.open.send_replace(open);
    }
    async fn wait(&self) {
        let mut state = self.open.subscribe();
        loop {
            if *state.borrow() {
                return;
            }
            if state.changed().await.is_err() {
                return;
            }
        }
    }
}
#[derive(Clone)]
pub struct Hooks {
    pub outbound: Gate,
    pub worker_service: Gate,
    pub worker_exit: Gate,
    pub event_writer: Gate,
}
impl Default for Hooks {
    fn default() -> Self {
        Self {
            outbound: Gate::new(true),
            worker_service: Gate::new(true),
            worker_exit: Gate::new(true),
            event_writer: Gate::new(true),
        }
    }
}
type ResponseSender = mpsc::Sender<Result<ServerFrame, Status>>;
pub struct Shared {
    pub bridge_n: AtomicUsize,
    pub bridge_peak: AtomicUsize,
    pub writer_n: AtomicUsize,
    pub writer_peak: AtomicUsize,
    pub logger_n: AtomicUsize,
    pub logger_peak: AtomicUsize,
    bridge_closed: AtomicBool,
    pub ledger: Mutex<Ledger>,
    pub epoch: Instant,
    pub hooks: Hooks,
    changed: Notify,
    cancel: watch::Sender<bool>,
    claimed: AtomicUsize,
    expected_clients: usize,
    incoming: Mutex<Vec<Option<Streaming<ClientFrame>>>>,
    outgoing: Mutex<Vec<Option<ResponseSender>>>,
    bridge_states: Mutex<[u8; 8]>,
    pub finished: AtomicBool,
    pub tasks: AtomicUsize,
    done: Notify,
    output: Mutex<Option<Box<dyn Write + Send>>>,
}
impl Shared {
    pub fn new(
        manifest: Manifest,
        epoch: Instant,
        output: Box<dyn Write + Send>,
        hooks: Hooks,
    ) -> Arc<Self> {
        Self::with_policy(manifest, epoch, output, hooks, crate::ledger::Policy::Wait)
    }
    pub fn with_policy(
        manifest: Manifest,
        epoch: Instant,
        output: Box<dyn Write + Send>,
        hooks: Hooks,
        policy: crate::ledger::Policy,
    ) -> Arc<Self> {
        Self::with_clients(manifest, epoch, output, hooks, policy, 1)
    }
    pub fn with_clients(
        manifest: Manifest,
        epoch: Instant,
        output: Box<dyn Write + Send>,
        hooks: Hooks,
        policy: crate::ledger::Policy,
        clients: usize,
    ) -> Arc<Self> {
        assert!(clients == 1 || clients == 8);
        Arc::new(Self {
            expected_clients: clients,
            incoming: Mutex::new((0..clients).map(|_| None).collect()),
            outgoing: Mutex::new((0..clients).map(|_| None).collect()),
            bridge_states: Mutex::new([0; 8]),
            bridge_n: AtomicUsize::new(0),
            bridge_peak: AtomicUsize::new(0),
            writer_n: AtomicUsize::new(0),
            writer_peak: AtomicUsize::new(0),
            logger_n: AtomicUsize::new(0),
            logger_peak: AtomicUsize::new(0),
            bridge_closed: AtomicBool::new(false),
            ledger: Mutex::new(Ledger::with_policy(manifest, policy).unwrap()),
            epoch,
            hooks,
            changed: Notify::new(),
            cancel: watch::channel(false).0,
            claimed: AtomicUsize::new(0),
            finished: AtomicBool::new(false),
            tasks: AtomicUsize::new(0),
            done: Notify::new(),
            output: Mutex::new(Some(output)),
        })
    }
    pub fn now(&self) -> u64 {
        Instant::now()
            .saturating_duration_since(self.epoch)
            .as_nanos()
            .min(u64::MAX as u128) as u64
    }
    pub fn cancel(&self) {
        self.cancel.send_replace(true);
        self.changed.notify_waiters();
    }
    async fn cancelled(&self) {
        let mut rx = self.cancel.subscribe();
        if !*rx.borrow() {
            let _ = rx.changed().await;
        }
    }
    pub async fn op<T>(
        &self,
        cleanup: bool,
        mut f: impl FnMut(&mut Ledger, u64) -> Result<T, Error>,
    ) -> Result<T, Error> {
        loop {
            let notified = self.changed.notified();
            tokio::pin!(notified);
            notified.as_mut().enable();
            if !cleanup && *self.cancel.borrow() {
                return Err(Error::Closed);
            }
            let (result, changed) = {
                let mut ledger = self.ledger.lock().unwrap();
                let before = ledger.event_seq();
                let result = f(&mut ledger, self.now());
                (result, ledger.event_seq() != before)
            };
            match result {
                Err(Error::Blocked) => {
                    if cleanup {
                        notified.await
                    } else {
                        tokio::select! {_=notified=>{},_=self.cancelled()=>return Err(Error::Closed)}
                    }
                }
                other => {
                    if changed {
                        self.changed.notify_waiters();
                    }
                    return other;
                }
            }
        }
    }
    pub async fn wait_finished(&self) {
        loop {
            let n = self.done.notified();
            tokio::pin!(n);
            n.as_mut().enable();
            if self.finished.load(Ordering::SeqCst) && self.tasks.load(Ordering::SeqCst) == 0 {
                return;
            }
            n.await
        }
    }
}
struct Count(Arc<Shared>);
impl Count {
    fn new(s: Arc<Shared>) -> Self {
        s.tasks.fetch_add(1, Ordering::SeqCst);
        Self(s)
    }
}
impl Drop for Count {
    fn drop(&mut self) {
        self.0.tasks.fetch_sub(1, Ordering::SeqCst);
        self.0.done.notify_waiters();
    }
}
#[derive(Clone)]
pub struct Service {
    pub shared: Arc<Shared>,
}
pub struct Outbound {
    rx: mpsc::Receiver<Result<ServerFrame, Status>>,
    shared: Arc<Shared>,
    ended: bool,
    client_id: usize,
}
impl Stream for Outbound {
    type Item = Result<ServerFrame, Status>;
    fn poll_next(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        match self.rx.poll_recv(cx) {
            Poll::Ready(None) if !self.ended => {
                self.ended = true;
                let failed = self.shared.ledger.lock().unwrap().failed;
                if let Some(reason) = failed {
                    Poll::Ready(Some(Err(Status::cancelled(reason))))
                } else {
                    Poll::Ready(None)
                }
            }
            Poll::Ready(Some(item)) => {
                let mut states = self.shared.bridge_states.lock().unwrap();
                if states[self.client_id] == 1 {
                    states[self.client_id] = 0;
                    self.shared.bridge_n.fetch_sub(1, Ordering::SeqCst);
                }
                Poll::Ready(Some(item))
            }
            other => other,
        }
    }
}
impl Drop for Outbound {
    fn drop(&mut self) {
        self.shared.bridge_closed.store(true, Ordering::SeqCst);
        {
            let mut states = self.shared.bridge_states.lock().unwrap();
            if states[self.client_id] == 1 {
                self.shared.bridge_n.fetch_sub(1, Ordering::SeqCst);
            }
            states[self.client_id] = 2;
        }
        if !self.ended {
            self.shared.cancel();
        }
    }
}
#[tonic::async_trait]
impl OverloadService for Service {
    type ExchangeStream = Outbound;
    async fn exchange(
        &self,
        request: Request<Streaming<ClientFrame>>,
    ) -> Result<Response<Outbound>, Status> {
        let cid = request
            .metadata()
            .get("x-e3-client-id")
            .map(|v| v.to_str().ok().and_then(|v| v.parse::<usize>().ok()))
            .unwrap_or(Some(0))
            .ok_or_else(|| Status::invalid_argument("client-id"))?;
        if cid >= self.shared.expected_clients
            || self.shared.claimed.fetch_or(1 << cid, Ordering::SeqCst) & (1 << cid) != 0
        {
            return Err(Status::resource_exhausted(
                "secondary stream identity/limit",
            ));
        }
        let (tx, rx) = mpsc::channel(1);
        let shared = self.shared.clone();
        {
            let mut inputs = shared.incoming.lock().unwrap();
            let mut outputs = shared.outgoing.lock().unwrap();
            inputs[cid] = Some(request.into_inner());
            outputs[cid] = Some(tx);
            if inputs.iter().all(Option::is_some) {
                let input = inputs.iter_mut().map(Option::take).collect();
                let output = outputs.iter_mut().map(|o| o.take().unwrap()).collect();
                tokio::spawn(supervise(shared.clone(), input, output));
            }
        }
        Ok(Response::new(Outbound {
            rx,
            shared,
            ended: false,
            client_id: cid,
        }))
    }
}
async fn receive(
    shared: Arc<Shared>,
    mut inputs: Vec<Option<Streaming<ClientFrame>>>,
) -> Result<(), Error> {
    tokio::select! {_=sleep_until(shared.epoch)=>{},_=shared.cancelled()=>return Err(Error::Closed)}
    let mut cursor = 0;
    loop {
        shared.op(false, |l, t| l.begin_decode(t)).await?;
        // One global decode reservation, polling at most8 transports round-robin.
        // No per-stream decoded staging or application input queue is introduced.
        let next = tokio::select! {value=std::future::poll_fn(|cx| {
            for step in 0..inputs.len() {
                let i=(cursor+step)%inputs.len();
                if let Some(input)=inputs[i].as_mut() {
                    if let Poll::Ready(frame)=Pin::new(input).poll_next(cx) {return Poll::Ready(Some((i,frame)));}
                }
            }
            if inputs.iter().all(Option::is_none) {Poll::Ready(None)} else {Poll::Pending}
        })=>value,_=shared.cancelled()=>return Err(Error::Closed)};
        let Some((cid, next)) = next else {
            shared.op(false, |l, t| l.end_input(t)).await?;
            return Ok(());
        };
        cursor = (cid + 1) % inputs.len();
        let Some(frame) = next else {
            inputs[cid] = None;
            shared.op(false, |l, t| l.client_done(t)).await?;
            continue;
        };
        let frame = frame.map_err(|_| Error::Closed)?;
        if let Some(client_frame::Frame::Work(ref w)) = frame.frame {
            if w.client_id as usize != cid {
                return Err(Error::Protocol("STREAM_OWNER_MISMATCH"));
            }
        }
        match frame.frame {
            Some(client_frame::Frame::Work(work)) => {
                let ids = (work.message_id, work.attempt_id);
                // A single decoded Work is held while awaiting bounded ledger resources.
                let mut owned = Some(work);
                let result = shared
                    .op(false, |l, t| {
                        // Event pressure returns Blocked before any state mutation.
                        if l.snapshot_event_full() {
                            return Err(Error::Blocked);
                        }
                        l.offer(owned.take().unwrap(), t)
                    })
                    .await;
                if let Err(error) = result {
                    let code = match error {
                        Error::Protocol(code) => code,
                        Error::Capacity => "METADATA_CAPACITY_EXHAUSTED",
                        _ => return Err(error),
                    };
                    shared
                        .op(true, |l, t| {
                            l.protocol_failure(code, Some(ids.0), Some(ids.1), t)
                        })
                        .await?;
                    return Err(Error::Protocol(code));
                }
                loop {
                    let staged = shared.ledger.lock().unwrap().staged();
                    if !staged {
                        break;
                    }
                    shared.op(false, |l, t| l.progress_stage(t)).await?;
                }
            }
            Some(client_frame::Frame::CancelOriginal(cancel)) => {
                let owner = shared
                    .ledger
                    .lock()
                    .unwrap()
                    .manifest()
                    .originals
                    .get(cancel.message_id as usize)
                    .map(|o| o.client_id as usize);
                if owner != Some(cid) {
                    return Err(Error::Protocol("STREAM_OWNER_MISMATCH"));
                }
                let run = shared.ledger.lock().unwrap().manifest().run_id.clone();
                if cancel.run_id != run {
                    return Err(Error::Protocol("RUN_ID_MISMATCH"));
                }
                shared
                    .op(false, |l, t| {
                        l.release_decode();
                        l.request_cancel(cancel.message_id as usize, t, "CLIENT_CANCEL")
                    })
                    .await?;
            }
            Some(client_frame::Frame::ClientDone(_)) => {
                shared.op(false, |l, t| l.client_done(t)).await?;
            }
            None => return Err(Error::Protocol("EMPTY_CLIENT_FRAME")),
        }
    }
}
async fn worker(shared: Arc<Shared>) -> Result<(), Error> {
    loop {
        if *shared.cancel.borrow() {
            return Err(Error::Closed);
        }
        let notified = shared.changed.notified();
        tokio::pin!(notified);
        notified.as_mut().enable();
        let (done, failed) = {
            let l = shared.ledger.lock().unwrap();
            (
                (l.eof || l.failed.is_some()) && l.idle(),
                l.failed.is_some(),
            )
        };
        if done {
            return Ok(());
        }
        if failed {
            notified.await;
            continue;
        }
        let work = shared.op(true, |l, t| l.start(t)).await?;
        let Some((id, deadline, delay)) = work else {
            tokio::select! {_=notified=>{},_=shared.cancelled()=>{}};
            continue;
        };
        let start = Instant::now();
        let completion = start + Duration::from_millis(delay);
        let completed = loop {
            let changed = shared.changed.notified();
            tokio::pin!(changed);
            changed.as_mut().enable();
            if shared.ledger.lock().unwrap().cancelled(id) {
                break false;
            }
            tokio::select! {
                biased;
                _=async{shared.hooks.worker_service.wait().await;sleep_until(completion).await}=>break true,
                _=sleep_until(shared.epoch+Duration::from_nanos(deadline))=>{
                    shared.op(true,|l,t|l.request_cancel(id,t,"DEADLINE")).await?;break false
                },
                _=shared.cancelled()=>{shared.op(true,|l,t|l.request_cancel(id,t,"STREAM_CANCELLED")).await?;break false},
                _=changed=>{},
            }
        };
        let finished = shared.now();
        if !completed {
            shared.op(true, |l, t| l.observe_cancel(id, t)).await?;
        }
        shared.hooks.worker_exit.wait().await; // deterministic checkpoint delay, default open
        shared
            .op(true, |l, t| l.exit(id, finished, t, completed))
            .await?;
    }
}
async fn sweep(shared: Arc<Shared>) -> Result<(), Error> {
    loop {
        let notified = shared.changed.notified();
        tokio::pin!(notified);
        notified.as_mut().enable();
        if shared.op(true, |l, t| l.sweep(t)).await? {
            continue;
        }
        let (done, deadline) = {
            let l = shared.ledger.lock().unwrap();
            ((l.eof || l.failed.is_some()) && l.idle(), l.next_deadline())
        };
        if done {
            return Ok(());
        }
        match deadline {
            Some(d) => {
                tokio::select! {_=notified=>{},_=sleep_until(shared.epoch+Duration::from_nanos(d))=>{}}
            }
            None => notified.await,
        }
    }
}
async fn write_multi(
    shared: Arc<Shared>,
    outputs: Vec<mpsc::Sender<Result<ServerFrame, Status>>>,
) -> Result<(), Error> {
    loop {
        let notified = shared.changed.notified();
        tokio::pin!(notified);
        notified.as_mut().enable();
        if let Some(frame) = shared.op(true, |l, t| l.response(t)).await? {
            shared.writer_n.store(1, Ordering::SeqCst);
            shared.writer_peak.fetch_max(1, Ordering::SeqCst);
            let send = async {
                let progress = async {
                    shared.hooks.outbound.wait().await;
                    let cid = match &frame.frame {
                        Some(crate::protocol::server_frame::Frame::TerminalOutcome(t)) => {
                            shared.ledger.lock().unwrap().manifest().originals
                                [t.message_id as usize]
                                .client_id as usize
                        }
                        _ => 0,
                    };
                    let permit = outputs[cid].reserve().await.map_err(|_| Error::Closed)?;
                    let mut states = shared.bridge_states.lock().unwrap();
                    if states[cid] == 2 {
                        return Err(Error::Closed);
                    }
                    states[cid] = 1;
                    let n = shared.bridge_n.fetch_add(1, Ordering::SeqCst) + 1;
                    shared.bridge_peak.fetch_max(n, Ordering::SeqCst);
                    permit.send(Ok(frame.clone()));
                    Ok(())
                };
                if matches!(
                    frame.frame,
                    Some(crate::protocol::server_frame::Frame::ProtocolError(_))
                ) {
                    progress.await
                } else {
                    tokio::select! {result=progress=>result,_=shared.cancelled()=>Err(Error::Closed)}
                }
            };
            let writer_started = Instant::now();
            let result = tokio::time::timeout(Duration::from_secs(1), send).await;
            shared.writer_n.store(0, Ordering::SeqCst);
            shared.ledger.lock().unwrap().record_writer_progress(
                writer_started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
            );
            match result {
                Ok(Ok(())) => {
                    shared.op(true, |l, t| l.accepted_write(&frame, t)).await?;
                }
                Ok(Err(e)) => return Err(e),
                Err(_) => {
                    shared
                        .op(true, |l, t| l.fail(t, "RESPONSE_PROGRESS_TIMEOUT"))
                        .await?;
                    return Err(Error::Protocol("RESPONSE_PROGRESS_TIMEOUT"));
                }
            }
        } else {
            let done = {
                let l = shared.ledger.lock().unwrap();
                l.drained() || l.failed.is_some()
            };
            if done {
                return Ok(());
            }
            tokio::select! {_=notified=>{},_=shared.cancelled()=>return Err(Error::Closed)}
        }
    }
}
struct LoggerGuard {
    shared: Arc<Shared>,
    flushed: bool,
}
impl Drop for LoggerGuard {
    fn drop(&mut self) {
        if !self.flushed {
            self.shared.cancel();
        }
    }
}
async fn log_events(
    shared: Arc<Shared>,
    output: Box<dyn Write + Send>,
    stop: watch::Receiver<bool>,
) -> Result<(), Error> {
    let _count = Count::new(shared.clone());
    let mut guard = LoggerGuard {
        shared: shared.clone(),
        flushed: false,
    };
    let mut out = BufWriter::with_capacity(65536, output);
    let mut stop = stop;
    loop {
        let notified = shared.changed.notified();
        tokio::pin!(notified);
        notified.as_mut().enable();
        tokio::select! {_=shared.hooks.event_writer.wait()=>{},_=stop.changed()=>{if !*shared.hooks.event_writer.open.borrow(){return Err(Error::Closed)}}}
        let event = shared.ledger.lock().unwrap().pop_event();
        if let Some(event) = event {
            shared.changed.notify_waiters();
            shared.logger_n.store(1, Ordering::SeqCst);
            shared.logger_peak.fetch_max(1, Ordering::SeqCst);
            let failed = serde_json::to_writer(&mut out, &event)
                .and_then(|_| out.write_all(b"\n").map_err(serde_json::Error::io))
                .is_err();
            shared.logger_n.store(0, Ordering::SeqCst);
            if failed {
                shared.cancel();
                return Err(Error::Protocol("EVENT_WRITER_FAILED"));
            }
            tokio::task::yield_now().await;
        } else if *stop.borrow() {
            out.flush()
                .map_err(|_| Error::Protocol("EVENT_WRITER_FAILED"))?;
            guard.flushed = true;
            return Ok(());
        } else {
            tokio::select! {_=notified=>{},_=stop.changed()=>{}}
        }
    }
}
async fn supervise(
    shared: Arc<Shared>,
    input: Vec<Option<Streaming<ClientFrame>>>,
    output: Vec<mpsc::Sender<Result<ServerFrame, Status>>>,
) {
    let _count = Count::new(shared.clone());
    let (stop, stop_rx) = watch::channel(false);
    let logger = tokio::spawn(log_events(
        shared.clone(),
        shared.output.lock().unwrap().take().unwrap(),
        stop_rx,
    ));
    let mut tasks = JoinSet::new();
    let c = shared.clone();
    tasks.spawn(async move {
        let _c = Count::new(c.clone());
        receive(c, input).await
    });
    let c = shared.clone();
    tasks.spawn(async move {
        let _c = Count::new(c.clone());
        worker(c).await
    });
    let c = shared.clone();
    tasks.spawn(async move {
        let _c = Count::new(c.clone());
        sweep(c).await
    });
    let c = shared.clone();
    tasks.spawn(async move {
        let _c = Count::new(c.clone());
        write_multi(c, output).await
    });
    {
        let main = async {
            while let Some(result) = tasks.join_next().await {
                if !matches!(result, Ok(Ok(()))) {
                    shared.cancel();
                    shared
                        .op(true, |l, t| {
                            if l.failed.is_some() {
                                Ok(())
                            } else {
                                l.fail(t, "STREAM_FAILED")
                            }
                        })
                        .await
                        .ok();
                    break;
                }
            }
            while tasks.join_next().await.is_some() {}
        };
        // Healthy runs have no artificial RPC timeout here. Once cancellation is
        // requested, cleanup gets the contract's one-second ACK/cancellation grace.
        tokio::pin!(main);
        tokio::select! {_=main.as_mut()=>{},_=shared.cancelled()=>{
            let cleanup=async{shared.op(true,|l,t|if l.failed.is_some(){Ok(())}else{l.fail(t,"STREAM_FAILED")}).await.ok();main.as_mut().await;};
            if tokio::time::timeout(Duration::from_secs(1),cleanup).await.is_err(){
                // Drop joined task set only after aborting and observing actual exits below.
            }
        }}
    }
    tasks.abort_all();
    while tasks.join_next().await.is_some() {}
    if !shared.ledger.lock().unwrap().idle() {
        shared
            .ledger
            .lock()
            .unwrap()
            .force_unresolved_after_task_exit(shared.now());
    }
    stop.send_replace(true);
    shared.changed.notify_waiters();
    if !matches!(logger.await, Ok(Ok(()))) {
        shared
            .ledger
            .lock()
            .unwrap()
            .force_unresolved_after_task_exit(shared.now());
    }
    shared.finished.store(true, Ordering::SeqCst);
    shared.done.notify_waiters();
}

#[cfg(test)]
async fn write(
    shared: Arc<Shared>,
    output: mpsc::Sender<Result<ServerFrame, Status>>,
) -> Result<(), Error> {
    write_multi(shared, vec![output]).await
}
#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test(start_paused = true)]
    async fn deterministic_outbound_timeout_is_one_second_of_local_blocking() {
        let hooks = Hooks::default();
        hooks.outbound.set(false);
        let shared = Shared::new(
            Manifest::primary("clock"),
            Instant::now(),
            Box::new(std::io::sink()),
            hooks,
        );
        {
            let mut l = shared.ledger.lock().unwrap();
            let w = l.manifest().work(0, 0, 1);
            l.begin_decode(0).unwrap();
            l.offer(w, 0).unwrap();
            l.progress_stage(0).unwrap();
            l.start(0).unwrap();
            l.exit(0, 0, 0, true).unwrap();
        }
        let (tx, mut rx) = mpsc::channel(1);
        let task = tokio::spawn(write(shared.clone(), tx));
        tokio::task::yield_now().await;
        tokio::time::advance(Duration::from_millis(999)).await;
        tokio::task::yield_now().await;
        assert!(!task.is_finished());
        assert!(shared.ledger.lock().unwrap().failed.is_none());
        tokio::time::advance(Duration::from_millis(1)).await;
        assert_eq!(
            task.await.unwrap(),
            Err(Error::Protocol("RESPONSE_PROGRESS_TIMEOUT"))
        );
        assert!(rx.try_recv().is_err());
        let s = shared.ledger.lock().unwrap().snapshot();
        assert_eq!(s.occupied, 0);
        assert_eq!(s.terminal_responses_reserved, 0);
        assert!(s.attempts[0].undelivered);
        assert_eq!(
            s.originals[0].terminal.as_ref().unwrap().outcome,
            crate::protocol::Outcome::Completed as i32
        );
    }
    #[tokio::test]
    async fn log_backpressure_wait_is_cancellable_without_unlogged_mutation() {
        let shared = Shared::new(
            Manifest::primary("log"),
            Instant::now(),
            Box::new(std::io::sink()),
            Hooks::default(),
        );
        {
            let mut l = shared.ledger.lock().unwrap();
            for t in 0..1024 {
                l.note(t).unwrap();
            }
        }
        let c = shared.clone();
        let task = tokio::spawn(async move { c.op(false, |l, t| l.begin_decode(t)).await });
        tokio::task::yield_now().await;
        assert!(!task.is_finished());
        shared.cancel();
        assert_eq!(task.await.unwrap(), Err(Error::Closed));
        let mut l = shared.ledger.lock().unwrap();
        assert_eq!(l.snapshot().logical_entries, 0);
        for seq in 1..=1024 {
            assert_eq!(l.pop_event().unwrap().seq, seq)
        }
        l.fail(1024, "EVENT_WRITER_CANCELLED").unwrap();
        assert_eq!(l.pop_event().unwrap().seq, 1025);
        assert_eq!(l.snapshot().occupied, 0);
    }
}
