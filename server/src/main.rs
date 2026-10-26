use pressure_server::protocol::{
    ingest_service_server::{IngestService, IngestServiceServer},
    Payload, Summary,
};
use std::{
    io::Write,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};
use tokio::{
    net::TcpListener,
    sync::{mpsc, Notify},
};
use tokio_stream::{wrappers::TcpListenerStream, StreamExt};
use tonic::{Request, Response, Status, Streaming};

#[derive(Default, Clone)]
struct Counts {
    cancelled: bool,
    received: u64,
    enqueued: u64,
    dequeued: u64,
    processed: u64,
    queued: u64,
    queue_bytes: u64,
    handler_bytes: u64,
    worker_bytes: u64,
    errors: u64,
    discarded: u64,
    wait_ns: u64,
    service_ns: u64,
    active: u64,
}
struct State {
    counts: Mutex<Counts>,
    notify: Notify,
}
#[derive(Clone)]
struct Service {
    state: Arc<State>,
    variant: String,
    capacity: usize,
    service_ms: u64,
    queue_limit: u64,
}
// A handler future dropped by tonic also drops this guard: no orphan worker survives.
struct Cleanup {
    task: Option<tokio::task::JoinHandle<()>>,
    state: Arc<State>,
    normal: bool,
}
impl Drop for Cleanup {
    fn drop(&mut self) {
        if let Some(task) = &self.task {
            task.abort();
        }
        let mut c = self.state.counts.lock().unwrap();
        if !self.normal {
            c.cancelled = true;
            c.errors += 1;
            c.discarded += c.received - c.processed - c.discarded;
        }
        c.active = 0;
        c.queued = 0;
        c.queue_bytes = 0;
        c.handler_bytes = 0;
        c.worker_bytes = 0;
    }
}
enum Rx {
    B(mpsc::Receiver<Payload>),
    U(mpsc::UnboundedReceiver<Payload>),
}
impl Rx {
    fn try_recv(&mut self) -> Result<Payload, mpsc::error::TryRecvError> {
        match self {
            Self::B(rx) => rx.try_recv(),
            Self::U(rx) => rx.try_recv(),
        }
    }
}
async fn worker(mut rx: Rx, state: Arc<State>, ms: u64) {
    loop {
        // Receive and logical ownership transition share the sample/enqueue lock.
        let notified = state.notify.notified();
        let item = {
            let mut c = state.counts.lock().unwrap();
            match rx.try_recv() {
                Ok(p) => {
                    c.dequeued += 1;
                    c.queued -= 1;
                    c.queue_bytes -= p.data.len() as u64;
                    c.worker_bytes = p.data.len() as u64;
                    Some(p)
                }
                Err(mpsc::error::TryRecvError::Empty) => None,
                Err(mpsc::error::TryRecvError::Disconnected) => return,
            }
        };
        if let Some(p) = item {
            let start = Instant::now();
            tokio::time::sleep(Duration::from_millis(ms)).await;
            let mut c = state.counts.lock().unwrap();
            if c.cancelled {
                return;
            }
            c.processed += 1;
            c.worker_bytes = 0;
            c.service_ns += start.elapsed().as_nanos() as u64;
            drop(p);
        } else {
            notified.await;
        }
    }
}
#[tonic::async_trait]
impl IngestService for Service {
    async fn ingest(
        &self,
        request: Request<Streaming<Payload>>,
    ) -> Result<Response<Summary>, Status> {
        {
            let mut c = self.state.counts.lock().unwrap();
            if c.active != 0 || c.received != 0 {
                return Err(Status::resource_exhausted("one stream per fresh process"));
            }
            c.active = 1;
        }
        let mut cleanup = Cleanup {
            task: None,
            state: self.state.clone(),
            normal: false,
        };
        let mut stream = request.into_inner();
        if self.variant == "direct" {
            while let Some(p) = stream.message().await? {
                {
                    let mut c = self.state.counts.lock().unwrap();
                    c.received += 1;
                    c.worker_bytes = p.data.len() as u64;
                }
                let start = Instant::now();
                tokio::time::sleep(Duration::from_millis(self.service_ms)).await;
                let mut c = self.state.counts.lock().unwrap();
                c.processed += 1;
                c.worker_bytes = 0;
                c.service_ns += start.elapsed().as_nanos() as u64;
            }
        } else if self.variant == "bounded" {
            let (tx, rx) = mpsc::channel(self.capacity);
            cleanup.task = Some(tokio::spawn(worker(
                Rx::B(rx),
                self.state.clone(),
                self.service_ms,
            )));
            loop {
                let start = Instant::now();
                let permit = tx
                    .reserve()
                    .await
                    .map_err(|_| Status::internal("worker closed"))?;
                self.state.counts.lock().unwrap().wait_ns += start.elapsed().as_nanos() as u64;
                let Some(p) = stream.message().await? else {
                    drop(permit);
                    break;
                };
                let mut c = self.state.counts.lock().unwrap();
                c.received += 1;
                c.handler_bytes = p.data.len() as u64;
                c.enqueued += 1;
                c.queued += 1;
                c.queue_bytes += c.handler_bytes;
                c.handler_bytes = 0;
                permit.send(p);
                self.state.notify.notify_one();
            }
            drop(tx);
            self.state.notify.notify_one();
        } else {
            let (tx, rx) = mpsc::unbounded_channel();
            cleanup.task = Some(tokio::spawn(worker(
                Rx::U(rx),
                self.state.clone(),
                self.service_ms,
            )));
            while let Some(p) = stream.message().await? {
                let mut c = self.state.counts.lock().unwrap();
                c.received += 1;
                c.handler_bytes = p.data.len() as u64;
                if c.queue_bytes + c.handler_bytes > self.queue_limit {
                    return Err(Status::resource_exhausted("queue payload safety limit"));
                }
                let bytes = c.handler_bytes;
                tx.send(p).map_err(|_| Status::internal("worker closed"))?;
                c.enqueued += 1;
                c.queued += 1;
                c.queue_bytes += bytes;
                c.handler_bytes = 0;
                self.state.notify.notify_one();
            }
            drop(tx);
            self.state.notify.notify_one();
        }
        if let Some(task) = cleanup.task.as_mut() {
            task.await
                .map_err(|_| Status::internal("worker task failed"))?;
        }
        cleanup.task.take();
        let result = {
            let c = self.state.counts.lock().unwrap();
            Summary {
                accepted: if self.variant == "direct" {
                    c.received
                } else {
                    c.enqueued
                },
                processed: c.processed,
            }
        };
        cleanup.normal = true;
        Ok(Response::new(result))
    }
}
fn option(args: &[String], name: &str, default: &str) -> String {
    args.windows(2)
        .find(|v| v[0] == name)
        .map(|v| v[1].clone())
        .unwrap_or(default.into())
}
fn rss() -> u64 {
    std::fs::read_to_string("/proc/self/status")
        .unwrap()
        .lines()
        .find_map(|l| {
            l.strip_prefix("VmRSS:")
                .and_then(|s| s.split_whitespace().next())
                .and_then(|s| s.parse::<u64>().ok())
        })
        .unwrap_or(0)
        * 1024
}
#[tokio::main(worker_threads = 2)]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .with_ansi(false)
        .with_writer(std::io::stderr)
        .init();
    let args: Vec<String> = std::env::args().collect();
    let variant = option(&args, "--variant", "direct");
    assert!(["direct", "unbounded", "bounded"].contains(&variant.as_str()));
    let capacity: usize = option(&args, "--capacity", "32").parse()?;
    assert!(capacity > 0);
    let ms = option(&args, "--service-ms", "10").parse()?;
    let queue_limit = option(&args, "--queue-limit", "268435456").parse()?;
    let rss_limit: u64 = option(&args, "--rss-limit", "536870912").parse()?;
    let addr: std::net::SocketAddr = option(&args, "--addr", "127.0.0.1:50051").parse()?;
    let file = option(&args, "--csv", "server.csv");
    let state = Arc::new(State {
        counts: Mutex::new(Counts::default()),
        notify: Notify::new(),
    });
    let connections = Arc::new(AtomicUsize::new(0));
    let listener = TcpListener::bind(addr).await?;
    let incoming = TcpListenerStream::new(listener).map({
        let connections = connections.clone();
        move |socket| {
            socket.inspect(|_| {
                connections.fetch_add(1, Ordering::SeqCst);
            })
        }
    });
    let sampling = state.clone();
    let sample_task = tokio::spawn(async move {
        let mut out = std::fs::File::create(file).unwrap();
        writeln!(out,"elapsed_s,received,enqueued,dequeued,processed,queue_depth,queue_bytes,handler_bytes,worker_bytes,enqueue_wait_ns,service_ns,rss_bytes,active_streams,connections_accepted,errors,discarded").unwrap();
        let start = Instant::now();
        loop {
            let c = sampling.counts.lock().unwrap().clone();
            let rss = rss();
            writeln!(
                out,
                "{:.6},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}",
                start.elapsed().as_secs_f64(),
                c.received,
                c.enqueued,
                c.dequeued,
                c.processed,
                c.queued,
                c.queue_bytes,
                c.handler_bytes,
                c.worker_bytes,
                c.wait_ns,
                c.service_ns,
                rss,
                c.active,
                connections.load(Ordering::SeqCst),
                c.errors,
                c.discarded
            )
            .unwrap();
            out.flush().unwrap();
            if rss > rss_limit {
                eprintln!("RSS safety limit exceeded");
                std::process::exit(42);
            }
            tokio::time::sleep(Duration::from_millis(200)).await;
        }
    });
    eprintln!("ready {addr} variant={variant} K={capacity} service_ms={ms}");
    let service = Service {
        state,
        variant,
        capacity,
        service_ms: ms,
        queue_limit,
    };
    let result = tonic::transport::Server::builder()
        .initial_stream_window_size(65535)
        .initial_connection_window_size(65535)
        .http2_adaptive_window(Some(false))
        .max_concurrent_streams(1)
        .add_service(IngestServiceServer::new(service).max_decoding_message_size(1024 * 1024))
        .serve_with_incoming_shutdown(incoming, async {
            tokio::signal::ctrl_c().await.unwrap();
        })
        .await;
    sample_task.abort();
    result?;
    Ok(())
}
