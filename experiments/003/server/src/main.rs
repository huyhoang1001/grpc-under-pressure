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
fn arg(name: &str) -> Result<String, Box<dyn std::error::Error>> {
    let a: Vec<_> = std::env::args().collect();
    a.windows(2)
        .find(|w| w[0] == name)
        .map(|w| w[1].clone())
        .ok_or_else(|| format!("required {name}").into())
}
#[tokio::main(worker_threads = 2)]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let manifest_path = arg("--manifest")?;
    if fs::metadata(&manifest_path)?.len() > 2 * 1024 * 1024 {
        return Err("manifest resource guard".into());
    }
    let manifest: Manifest = serde_json::from_slice(&fs::read(manifest_path)?)?;
    manifest.validate().map_err(|e| format!("{e:?}"))?;
    let out = std::path::PathBuf::from(arg("--output")?);
    fs::create_dir(&out)?;
    let target: u128 = arg("--epoch-unix-ns")?.parse()?;
    let wall = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    if target <= wall {
        return Err("Stage1 smoke epoch must be in the future".into());
    }
    let epoch = Instant::now() + Duration::from_nanos(u64::try_from(target - wall)?);
    let clock_start = pressure_e3_stage1::measurement::calibrate(epoch);
    let policy = std::env::args()
        .collect::<Vec<_>>()
        .windows(2)
        .find(|w| w[0] == "--policy")
        .map(|w| w[1].clone())
        .unwrap_or_else(|| "wait".into());
    let policy = Policy::parse(&policy)?;
    let shared = Shared::with_policy(
        manifest,
        epoch,
        Box::new(File::create_new(out.join("server-events.jsonl"))?),
        Hooks::default(),
        policy,
    );
    let listener = TcpListener::bind(arg("--addr")?).await?;
    let addr = listener.local_addr()?;
    fs::write(
        out.join("ready.json.pending"),
        serde_json::to_vec(
            &serde_json::json!({"addr":addr.to_string(),"fixture_only":true,"epoch_unix_ns":target}),
        )?,
    )?;
    fs::rename(out.join("ready.json.pending"), out.join("ready.json"))?;
    let (stop, shutdown) = tokio::sync::oneshot::channel::<()>();
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
    tokio::select! {r=serving.as_mut()=>{r?;},_=tokio::signal::ctrl_c()=>{shared.cancel();let _=stop.send(());if shared.tasks.load(Ordering::SeqCst)>0{tokio::time::timeout(Duration::from_secs(2),shared.wait_finished()).await?;}tokio::time::timeout(Duration::from_secs(2),serving.as_mut()).await??;}}
    serde_json::to_writer_pretty(
        File::create_new(out.join("server-ledger.json"))?,
        &shared.ledger.lock().unwrap().snapshot(),
    )?;
    serde_json::to_writer_pretty(
        File::create_new(out.join("clock.json"))?,
        &serde_json::json!({"contract_revision":"A01","start":clock_start,"end":pressure_e3_stage1::measurement::calibrate(epoch),"bounded_io":{"bridge_current":shared.bridge_n.load(Ordering::SeqCst),"bridge_peak":shared.bridge_peak.load(Ordering::SeqCst),"writer_current":shared.writer_n.load(Ordering::SeqCst),"writer_peak":shared.writer_peak.load(Ordering::SeqCst),"logger_current":shared.logger_n.load(Ordering::SeqCst),"logger_peak":shared.logger_peak.load(Ordering::SeqCst)}}),
    )?;
    Ok(())
}
