use pressure_e3_stage1::{
    ledger::{Manifest, Phase},
    protocol::{
        client_frame, overload_service_client::OverloadServiceClient,
        overload_service_server::OverloadServiceServer, server_frame, ClientFrame,
    },
    service::{Hooks, Service, Shared},
};
use std::{
    io::Write,
    sync::{atomic::Ordering, Arc},
    time::Duration,
};
use tokio::{
    net::TcpListener,
    sync::{mpsc, oneshot},
    time::Instant,
};
use tokio_stream::wrappers::{ReceiverStream, TcpListenerStream};
#[derive(Clone)]
struct Output(Arc<std::sync::Mutex<Vec<u8>>>);
impl Write for Output {
    fn write(&mut self, b: &[u8]) -> std::io::Result<usize> {
        let mut output = self.0.lock().unwrap();
        if output.len() + b.len() > 2 * 1024 * 1024 {
            return Err(std::io::Error::other("test log capture bound"));
        }
        output.extend_from_slice(b);
        Ok(b.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
struct Harness {
    shared: Arc<Shared>,
    client: OverloadServiceClient<tonic::transport::Channel>,
    stop: oneshot::Sender<()>,
    server: tokio::task::JoinHandle<()>,
    events: Arc<std::sync::Mutex<Vec<u8>>>,
}
async fn harness(hooks: Hooks) -> Harness {
    let events = Arc::new(std::sync::Mutex::new(Vec::new()));
    let shared = Shared::new(
        Manifest::primary("transport-test"),
        Instant::now(),
        Box::new(Output(events.clone())),
        hooks,
    );
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let (stop, shutdown) = oneshot::channel();
    let service = Service {
        shared: shared.clone(),
    };
    let server = tokio::spawn(async move {
        tonic::transport::Server::builder()
            .initial_stream_window_size(65535)
            .initial_connection_window_size(65535)
            .http2_adaptive_window(Some(false))
            .add_service(OverloadServiceServer::new(service).max_decoding_message_size(1024 * 1024))
            .serve_with_incoming_shutdown(TcpListenerStream::new(listener), async {
                let _ = shutdown.await;
            })
            .await
            .unwrap()
    });
    let client = OverloadServiceClient::connect(format!("http://{addr}"))
        .await
        .unwrap();
    Harness {
        shared,
        client,
        stop,
        server,
        events,
    }
}
async fn until(h: &Harness, f: impl Fn(&pressure_e3_stage1::ledger::Snapshot) -> bool) {
    tokio::time::timeout(Duration::from_secs(3), async {
        loop {
            if f(&h.shared.ledger.lock().unwrap().snapshot()) {
                break;
            }
            tokio::time::sleep(Duration::from_millis(1)).await;
        }
    })
    .await
    .unwrap()
}
async fn finish(h: Harness) {
    tokio::time::timeout(Duration::from_secs(3), h.shared.wait_finished())
        .await
        .unwrap();
    assert_eq!(h.shared.tasks.load(Ordering::SeqCst), 0);
    let state = h.shared.ledger.lock().unwrap().snapshot();
    assert_eq!(state.occupied, 0);
    assert_eq!(state.permits_acquired, state.permits_released);
    let log = String::from_utf8(h.events.lock().unwrap().clone()).unwrap();
    for (i, line) in log.lines().enumerate() {
        let e: serde_json::Value = serde_json::from_str(line).unwrap();
        assert_eq!(e["seq"].as_u64().unwrap(), i as u64 + 1);
    }
    assert_eq!(log.lines().count() as u64, state.event_seq);
    h.stop.send(()).unwrap();
    tokio::time::timeout(Duration::from_secs(2), h.server)
        .await
        .unwrap()
        .unwrap();
}
fn work(shared: &Shared, id: usize, attempt: u64, n: u32) -> ClientFrame {
    ClientFrame {
        frame: Some(client_frame::Frame::Work(
            shared
                .ledger
                .lock()
                .unwrap()
                .manifest()
                .work(id, attempt, n),
        )),
    }
}
#[tokio::test]
async fn half_close_drains_terminal_and_duplicate_frames_then_clean_eof() {
    let mut h = harness(Hooks::default()).await;
    let (tx, rx) = mpsc::channel(32);
    let mut responses = h
        .client
        .exchange(ReceiverStream::new(rx))
        .await
        .unwrap()
        .into_inner();
    tx.send(work(&h.shared, 0, 10, 1)).await.unwrap();
    tx.send(work(&h.shared, 0, 11, 2)).await.unwrap();
    drop(tx);
    let mut frames = Vec::new();
    while let Some(frame) = responses.message().await.unwrap() {
        frames.push(frame)
    }
    assert_eq!(frames.len(), 2);
    assert!(frames
        .iter()
        .all(|f| matches!(&f.frame, Some(server_frame::Frame::TerminalOutcome(_)))));
    let s = h.shared.ledger.lock().unwrap().snapshot();
    assert_eq!(s.originals[0].starts, 1);
    assert!(s.failed.is_none());
    drop(responses);
    finish(h).await;
}
#[tokio::test]
async fn t06_writer_barrier_timeout_cancels_and_holds_permit_until_exit() {
    let hooks = Hooks::default();
    hooks.outbound.set(false);
    let mut h = harness(hooks).await;
    let (tx, rx) = mpsc::channel(32);
    let responses = h
        .client
        .exchange(ReceiverStream::new(rx))
        .await
        .unwrap()
        .into_inner();
    tx.send(work(&h.shared, 0, 0, 1)).await.unwrap();
    until(&h, |s| {
        s.originals
            .first()
            .is_some_and(|o| o.phase == Phase::Terminal)
    })
    .await;
    h.shared.hooks.worker_service.set(false);
    h.shared.hooks.worker_exit.set(false);
    tx.send(work(&h.shared, 1, 1, 1)).await.unwrap();
    until(&h, |s| s.running == 1).await;
    until(&h, |s| s.failed == Some("RESPONSE_PROGRESS_TIMEOUT")).await;
    until(&h, |s| {
        s.originals
            .get(1)
            .is_some_and(|o| o.cancellation_observed_ns.is_some())
    })
    .await;
    {
        let s = h.shared.ledger.lock().unwrap().snapshot();
        assert_eq!(s.occupied, 1);
        assert_eq!(s.permits_acquired, 2);
        assert_eq!(s.permits_released, 1);
        assert!(s.terminal_responses_reserved <= 32);
        assert!(s.immediate_responses <= 32);
    }
    h.shared.hooks.worker_exit.set(true);
    drop(tx);
    drop(responses);
    finish(h).await;
}
#[tokio::test]
async fn stream_abort_before_decode_does_not_fabricate_admission() {
    let mut h = harness(Hooks::default()).await;
    let (tx, rx) = mpsc::channel(1);
    let responses = h
        .client
        .exchange(ReceiverStream::new(rx))
        .await
        .unwrap()
        .into_inner();
    drop(responses);
    drop(tx);
    finish(h).await;
}
#[tokio::test]
async fn stream_abort_during_service_records_request_observation_exit() {
    let hooks = Hooks::default();
    hooks.worker_service.set(false);
    let mut h = harness(hooks).await;
    let (tx, rx) = mpsc::channel(1);
    let responses = h
        .client
        .exchange(ReceiverStream::new(rx))
        .await
        .unwrap()
        .into_inner();
    tx.send(work(&h.shared, 0, 0, 1)).await.unwrap();
    until(&h, |s| s.running == 1).await;
    drop(responses);
    drop(tx);
    until(&h, |s| s.occupied == 0).await;
    let s = h.shared.ledger.lock().unwrap().snapshot();
    assert!(s.originals[0].cancellation_requested_ns.is_some());
    assert!(s.originals[0].cancellation_observed_ns.is_some());
    assert!(s.originals[0].exit_ns.is_some());
    assert_eq!(
        s.originals[0].terminal.as_ref().unwrap().detail_code,
        "CANCELLED_PROCESSING"
    );
    finish(h).await;
}
#[tokio::test]
async fn invalid_identity_produces_correlated_error_without_second_start() {
    let mut h = harness(Hooks::default()).await;
    let (tx, rx) = mpsc::channel(1);
    let mut responses = h
        .client
        .exchange(ReceiverStream::new(rx))
        .await
        .unwrap()
        .into_inner();
    let mut w = h.shared.ledger.lock().unwrap().manifest().work(0, 99, 1);
    w.payload[0] ^= 1;
    tx.send(ClientFrame {
        frame: Some(client_frame::Frame::Work(w)),
    })
    .await
    .unwrap();
    drop(tx);
    let frame = responses.message().await.unwrap().unwrap();
    let Some(server_frame::Frame::ProtocolError(error)) = frame.frame else {
        panic!()
    };
    assert_eq!(error.message_id, Some(0));
    assert_eq!(error.attempt_id, Some(99));
    drop(responses);
    finish(h).await;
}

#[tokio::test]
async fn t07_full_immediate_path_pauses_decoder_but_worker_does_not_wait_for_ack() {
    let hooks = Hooks::default();
    hooks.outbound.set(false);
    let mut h = harness(hooks).await;
    let (tx, rx) = mpsc::channel(32);
    let mut responses = h
        .client
        .exchange(ReceiverStream::new(rx))
        .await
        .unwrap()
        .into_inner();
    // Deliberate raw protocol fault fixture bypassing the normal Go credit gate:
    // exercise duplicate-response reservations, never a primary workload.
    for id in 0..32 {
        tx.send(work(&h.shared, id, id as u64, 1)).await.unwrap();
    }
    for id in 0..32 {
        tx.send(work(&h.shared, id, 100 + id as u64, 2))
            .await
            .unwrap();
    }
    tx.send(work(&h.shared, 0, 200, 3)).await.unwrap();
    until(&h, |s| s.immediate_responses == 32).await;
    until(&h, |s| s.occupied == 0).await;
    {
        let s = h.shared.ledger.lock().unwrap().snapshot();
        assert_eq!(s.attempt_entries, 64);
        assert_eq!(s.decoded_staging, 0);
        assert_eq!(s.permits_acquired, s.permits_released);
        assert!(s.terminal_responses_reserved <= 32);
    }
    h.shared.hooks.outbound.set(true);
    drop(tx);
    let mut count = 0;
    while responses.message().await.unwrap().is_some() {
        count += 1
    }
    assert_eq!(count, 65);
    drop(responses);
    finish(h).await;
}
#[tokio::test]
async fn client_done_is_diagnostic_not_a_substitute_for_eof() {
    let mut h = harness(Hooks::default()).await;
    let (tx, rx) = mpsc::channel(2);
    let mut responses = h
        .client
        .exchange(ReceiverStream::new(rx))
        .await
        .unwrap()
        .into_inner();
    tx.send(ClientFrame {
        frame: Some(client_frame::Frame::ClientDone(Default::default())),
    })
    .await
    .unwrap();
    tx.send(work(&h.shared, 0, 1, 1)).await.unwrap();
    drop(tx);
    assert!(responses.message().await.unwrap().is_some());
    assert!(responses.message().await.unwrap().is_none());
    drop(responses);
    finish(h).await;
}
#[tokio::test]
async fn lost_terminal_frame_preserves_authoritative_completion() {
    let hooks = Hooks::default();
    hooks.outbound.set(false);
    let mut h = harness(hooks).await;
    let (tx, rx) = mpsc::channel(1);
    let responses = h
        .client
        .exchange(ReceiverStream::new(rx))
        .await
        .unwrap()
        .into_inner();
    tx.send(work(&h.shared, 0, 0, 1)).await.unwrap();
    until(&h, |s| {
        s.originals
            .first()
            .is_some_and(|o| o.phase == Phase::Terminal)
    })
    .await;
    drop(responses);
    drop(tx);
    until(&h, |s| s.failed.is_some()).await;
    let s = h.shared.ledger.lock().unwrap().snapshot();
    assert_eq!(s.originals[0].terminal.as_ref().unwrap().outcome, 1);
    assert!(!s.attempts[0].write_accepted);
    assert!(s.attempts[0].undelivered);
    finish(h).await;
}

#[tokio::test]
async fn logger_io_failure_invalidates_even_if_application_completed() {
    struct Failing;
    impl Write for Failing {
        fn write(&mut self, _: &[u8]) -> std::io::Result<usize> {
            Err(std::io::Error::other("injected log failure"))
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Err(std::io::Error::other("injected log failure"))
        }
    }
    let shared = Shared::new(
        Manifest::primary("log-failure"),
        Instant::now(),
        Box::new(Failing),
        Hooks::default(),
    );
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let (stop, shutdown) = oneshot::channel();
    let service = Service {
        shared: shared.clone(),
    };
    let server = tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(OverloadServiceServer::new(service))
            .serve_with_incoming_shutdown(TcpListenerStream::new(listener), async {
                let _ = shutdown.await;
            })
            .await
            .unwrap()
    });
    let mut client = OverloadServiceClient::connect(format!("http://{addr}"))
        .await
        .unwrap();
    let (tx, rx) = mpsc::channel(1);
    let mut stream = client
        .exchange(ReceiverStream::new(rx))
        .await
        .unwrap()
        .into_inner();
    tx.send(work(&shared, 0, 0, 1)).await.unwrap();
    drop(tx);
    while let Ok(Some(_)) = stream.message().await {}
    tokio::time::timeout(Duration::from_secs(3), shared.wait_finished())
        .await
        .unwrap();
    let s = shared.ledger.lock().unwrap().snapshot();
    assert_eq!(s.failed, Some("UNRESOLVED_SHUTDOWN"));
    assert_eq!(s.occupied, 0);
    assert_eq!(shared.tasks.load(Ordering::SeqCst), 0);
    drop(stream);
    stop.send(()).unwrap();
    server.await.unwrap();
}
