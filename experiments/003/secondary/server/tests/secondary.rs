use pressure_e3_stage1::{
    ledger::{Manifest, Policy},
    protocol::{
        client_frame, overload_service_client::OverloadServiceClient,
        overload_service_server::OverloadServiceServer, ClientFrame,
    },
    service::{Hooks, Service, Shared},
};
use std::{sync::atomic::Ordering, time::Duration};
use tokio::{
    net::TcpListener,
    sync::{mpsc, oneshot},
    time::Instant,
};
use tokio_stream::wrappers::{ReceiverStream, TcpListenerStream};
#[tokio::test]
async fn eight_streams_share_one_worker_route_and_drain() {
    let mut m = Manifest::primary("eight-test");
    m.originals.truncate(32);
    for (i, o) in m.originals.iter_mut().enumerate() {
        o.client_id = (i % 8) as u32;
        o.scheduled_offset_ns = 0;
        o.deadline_offset_ns = 5_000_000_000;
    }
    let s = Shared::with_clients(
        m.clone(),
        Instant::now(),
        Box::new(std::io::sink()),
        Hooks::default(),
        Policy::Retry,
        8,
    );
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let (stop, rx) = oneshot::channel();
    let service = Service { shared: s.clone() };
    let server = tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(OverloadServiceServer::new(service))
            .serve_with_incoming_shutdown(TcpListenerStream::new(listener), async {
                let _ = rx.await;
            })
            .await
            .unwrap()
    });
    let mut clients = tokio::task::JoinSet::new();
    for cid in 0..8 {
        let m = m.clone();
        clients.spawn(async move {
            let mut client = OverloadServiceClient::connect(format!("http://{addr}"))
                .await
                .unwrap();
            let (tx, rx) = mpsc::channel(4);
            let mut req = tonic::Request::new(ReceiverStream::new(rx));
            req.metadata_mut()
                .insert("x-e3-client-id", cid.to_string().parse().unwrap());
            let mut response = client.exchange(req).await.unwrap().into_inner();
            for id in (cid..32).step_by(8) {
                tx.send(ClientFrame {
                    frame: Some(client_frame::Frame::Work(m.work(id, id as u64, 1))),
                })
                .await
                .unwrap();
            }
            drop(tx);
            let mut received = 0;
            while let Some(frame) = response.message().await.unwrap() {
                if let Some(pressure_e3_stage1::protocol::server_frame::Frame::TerminalOutcome(t)) =
                    frame.frame
                {
                    assert_eq!(t.message_id % 8, cid as u64);
                    received += 1;
                } else {
                    panic!("unexpected frame")
                }
            }
            assert_eq!(received, 4);
        });
    }
    tokio::time::timeout(Duration::from_secs(8), async {
        while let Some(r) = clients.join_next().await {
            r.unwrap();
        }
    })
    .await
    .unwrap();
    tokio::time::timeout(Duration::from_secs(2), s.wait_finished())
        .await
        .unwrap();
    let snap = s.ledger.lock().unwrap().snapshot();
    assert!(snap.failed.is_none());
    assert_eq!(snap.occupied, 0);
    assert_eq!(snap.permits_acquired, 32);
    assert_eq!(snap.permits_released, 32);
    assert_eq!(snap.high_water.running, 1);
    assert!(snap.high_water.staging <= 1);
    assert_eq!(snap.originals.iter().map(|o| o.starts).sum::<u32>(), 32);
    assert_eq!(s.tasks.load(Ordering::SeqCst), 0);
    assert_eq!(s.bridge_n.load(Ordering::SeqCst), 0);
    stop.send(()).unwrap();
    server.await.unwrap();
}

#[tokio::test]
async fn one_cancelled_stream_cancels_global_run_without_permit_or_task_leak() {
    let mut m = Manifest::primary("eight-cancel");
    m.originals.truncate(8);
    for (i, o) in m.originals.iter_mut().enumerate() {
        o.client_id = i as u32;
        o.scheduled_offset_ns = 0;
        o.deadline_offset_ns = 5_000_000_000;
    }
    let hooks = Hooks::default();
    hooks.worker_service.set(false);
    let shared = Shared::with_clients(
        m.clone(),
        Instant::now(),
        Box::new(std::io::sink()),
        hooks,
        Policy::Retry,
        8,
    );
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let (stop, rx) = oneshot::channel();
    let service = Service {
        shared: shared.clone(),
    };
    let server = tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(OverloadServiceServer::new(service))
            .serve_with_incoming_shutdown(TcpListenerStream::new(listener), async {
                let _ = rx.await;
            })
            .await
            .unwrap()
    });
    let mut responses = Vec::new();
    let mut senders = Vec::new();
    for cid in 0..8 {
        let mut client = OverloadServiceClient::connect(format!("http://{addr}"))
            .await
            .unwrap();
        let (tx, rx) = mpsc::channel(1);
        let mut req = tonic::Request::new(ReceiverStream::new(rx));
        req.metadata_mut()
            .insert("x-e3-client-id", cid.to_string().parse().unwrap());
        responses.push(client.exchange(req).await.unwrap().into_inner());
        senders.push(tx);
    }
    senders[0]
        .send(ClientFrame {
            frame: Some(client_frame::Frame::Work(m.work(0, 0, 1))),
        })
        .await
        .unwrap();
    tokio::time::timeout(Duration::from_secs(2), async {
        while shared.ledger.lock().unwrap().snapshot().running == 0 {
            tokio::time::sleep(Duration::from_millis(1)).await;
        }
    })
    .await
    .unwrap();
    // Abort both halves, as in the accepted primary abort fixture.
    drop(responses.remove(0));
    drop(senders.remove(0));
    tokio::time::timeout(Duration::from_secs(3), shared.wait_finished())
        .await
        .unwrap();
    drop(responses);
    drop(senders);
    let state = shared.ledger.lock().unwrap().snapshot();
    assert_eq!(state.occupied, 0);
    assert_eq!(state.permits_acquired, state.permits_released);
    assert_eq!(state.failed, Some("STREAM_FAILED"));
    assert_eq!(shared.tasks.load(Ordering::SeqCst), 0);
    stop.send(()).unwrap();
    server.await.unwrap();
}
