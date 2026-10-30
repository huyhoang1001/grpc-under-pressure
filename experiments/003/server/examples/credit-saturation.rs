//! Correctness fixture only: real Service/worker/policies with a bounded worker
//! barrier. No prefilled ledger, fabricated outcome, extra RPC or policy override.
use pressure_e3_stage1::{
    ledger::{Manifest, Policy},
    protocol::overload_service_server::OverloadServiceServer,
    service::{Hooks, Service, Shared},
};
use std::{
    fs::{self, File},
    sync::atomic::Ordering,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::{net::TcpListener, time::Instant};
use tokio_stream::wrappers::TcpListenerStream;
fn arg(name: &str) -> String {
    let args: Vec<_> = std::env::args().collect();
    args.windows(2)
        .find(|a| a[0] == name)
        .unwrap_or_else(|| panic!("required {name}"))
        .get(1)
        .unwrap()
        .clone()
}
#[tokio::main(worker_threads = 2)]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = arg("--manifest");
    assert!(fs::metadata(&path)?.len() < 2 * 1024 * 1024);
    let manifest: Manifest = serde_json::from_slice(&fs::read(path)?)?;
    assert_eq!(
        manifest.originals.len(),
        33,
        "exactly33 scheduled fixture originals"
    );
    let policy = Policy::parse(&arg("--policy"))?;
    let mode = arg("--mode");
    assert!(mode == "drain" || mode == "cancel" && policy == Policy::Wait);
    let out = std::path::PathBuf::from(arg("--output"));
    fs::create_dir(&out)?;
    let target: u128 = arg("--epoch-unix-ns").parse()?;
    let wall = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    assert!(target > wall);
    let epoch = Instant::now() + Duration::from_nanos(u64::try_from(target - wall)?);
    let hooks = Hooks::default();
    hooks.worker_service.set(false);
    let shared = Shared::with_policy(
        manifest,
        epoch,
        Box::new(File::create_new(out.join("server-events.jsonl"))?),
        hooks,
        policy,
    );
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let addr = listener.local_addr()?;
    fs::write(
        out.join("ready.pending"),
        serde_json::to_vec(
            &serde_json::json!({"addr":addr.to_string(),"fixture_only":true,"contract_revision":"A01","client_outstanding_limit":33,"server_admission_limit":32}),
        )?,
    )?;
    fs::rename(out.join("ready.pending"), out.join("ready.json"))?;
    let monitor_shared = shared.clone();
    let monitor_out = out.clone();
    let monitor = tokio::spawn(async move {
        let target_attempts = if policy == Policy::Retry { 35 } else { 33 };
        let saturation = async {
            loop {
                {
                    let s = monitor_shared.ledger.lock().unwrap().snapshot();
                    if s.occupied == 32
                        && s.attempt_entries == target_attempts
                        && (if policy == Policy::Wait {
                            s.decoded_staging == 1
                        } else {
                            s.attempts.last().is_some_and(|a| a.terminal.is_some())
                        })
                    {
                        assert_eq!(s.permits_released, 0);
                        assert_eq!(s.running, 1);
                        assert_eq!(s.queued, 31);
                        assert!(s.originals.iter().all(|o| o.starts <= 1));
                        if policy != Policy::Wait {
                            assert_eq!(s.originals[32].starts, 0);
                        }
                        let proof = serde_json::json!({"fixture_only":true,"mode":mode,"offset_ns":monitor_shared.now(),"at_full_budget":s});
                        fs::write(
                            monitor_out.join("barrier.json"),
                            serde_json::to_vec_pretty(&proof).unwrap(),
                        )
                        .unwrap();
                        break;
                    }
                }
                tokio::time::sleep(Duration::from_millis(1)).await;
            }
        };
        let reached = tokio::time::timeout_at(epoch + Duration::from_secs(3), saturation).await;
        if reached.is_err() {
            monitor_shared.cancel();
            return Err("saturation barrier timeout".to_string());
        }
        if mode == "cancel" {
            monitor_shared.cancel()
        } else {
            monitor_shared.hooks.worker_service.set(true)
        }
        Ok(())
    });
    let (stop, shutdown) = tokio::sync::oneshot::channel();
    let serving = tonic::transport::Server::builder()
        .initial_stream_window_size(65535)
        .initial_connection_window_size(65535)
        .http2_adaptive_window(Some(false))
        .add_service(
            OverloadServiceServer::new(Service {
                shared: shared.clone(),
            })
            .max_decoding_message_size(1024 * 1024),
        )
        .serve_with_incoming_shutdown(TcpListenerStream::new(listener), async {
            let _ = shutdown.await;
        });
    tokio::pin!(serving);
    tokio::select! {r=serving.as_mut()=>r?,_=tokio::signal::ctrl_c()=>{
     shared.cancel();let _=stop.send(());
     tokio::time::timeout(Duration::from_secs(2),shared.wait_finished()).await?;
     tokio::time::timeout(Duration::from_secs(2),serving.as_mut()).await??;
    }}
    let monitor_result = monitor.await?;
    assert_eq!(shared.tasks.load(Ordering::SeqCst), 0);
    serde_json::to_writer_pretty(
        File::create_new(out.join("server-ledger.json"))?,
        &shared.ledger.lock().unwrap().snapshot(),
    )?;
    monitor_result.map_err(std::io::Error::other)?;
    Ok(())
}
