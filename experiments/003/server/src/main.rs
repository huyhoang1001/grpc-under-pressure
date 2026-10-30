use pressure_e3_stage1::{
    ledger::{Manifest, Policy},
    protocol::overload_service_server::OverloadServiceServer,
    service::{Hooks, Service, Shared},
};
use std::{
    fs::{self, File},
    io::Write,
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
    let finish_shared = shared.clone();
    let finish_out = out.clone();
    let finished_task = tokio::spawn(async move {
        finish_shared.wait_finished().await;
        fs::write(
            finish_out.join("finished.pending"),
            serde_json::to_vec(
                &serde_json::json!({"contract_revision":"A01","rpc_finished_offset_ns":finish_shared.now(),"supervised_tasks_joined":true,"logs_flushed":true}),
            )?,
        )?;
        fs::rename(
            finish_out.join("finished.pending"),
            finish_out.join("finished.json"),
        )?;
        Ok::<(), std::io::Error>(())
    });
    let observation_cutoff = std::env::args()
        .collect::<Vec<_>>()
        .windows(2)
        .find(|w| w[0] == "--observation-cutoff-ns")
        .map(|w| w[1].parse::<u64>())
        .transpose()?;
    let (observation_stop, mut observation_cancel) = tokio::sync::watch::channel(false);
    let phase_shared = shared.clone();
    let phase_out = out.clone();
    let observation_task = tokio::spawn(async move {
        if let Some(cutoff) = observation_cutoff {
            let mut file = File::create_new(phase_out.join("phases.jsonl"))?;
            let mut phases = vec![0, 12_000_000_000, 24_000_000_000, 36_000_000_000, cutoff];
            phases.retain(|p| *p <= cutoff);
            phases.sort_unstable();
            phases.dedup();
            for expected in phases {
                tokio::select! {_=tokio::time::sleep_until(epoch+Duration::from_nanos(expected))=>{},_=observation_cancel.changed()=>return Ok::<(),std::io::Error>(())}
                serde_json::to_writer(
                    &mut file,
                    &serde_json::json!({"contract_revision":"A01","expected_offset_ns":expected,"actual_offset_ns":phase_shared.now()}),
                )?;
                file.write_all(b"\n")?;
                file.flush()?;
                if expected == cutoff {
                    fs::write(
                        phase_out.join("observation-complete.pending"),
                        serde_json::to_vec(
                            &serde_json::json!({"contract_revision":"A01","cutoff_ns":cutoff,"actual_offset_ns":phase_shared.now()}),
                        )?,
                    )?;
                    fs::rename(
                        phase_out.join("observation-complete.pending"),
                        phase_out.join("observation-complete.json"),
                    )?;
                }
            }
        }
        Ok::<(), std::io::Error>(())
    });
    let listener = TcpListener::bind(arg("--addr")?).await?;
    let addr = listener.local_addr()?;
    fs::write(
        out.join("ready.json.pending"),
        serde_json::to_vec(
            &serde_json::json!({"addr":addr.to_string(),"contract_revision":"A01","default_hooks_only":true,"epoch_unix_ns":target,"observation_cutoff_ns":observation_cutoff}),
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
    tokio::select! {r=serving.as_mut()=>{r?;},_=tokio::signal::ctrl_c()=>{
        let drained={let l=shared.ledger.lock().unwrap();l.eof && l.idle() && l.failed.is_none()};
        if !drained{shared.cancel();}
        let _=stop.send(());
        if shared.tasks.load(Ordering::SeqCst)>0{tokio::time::timeout(Duration::from_secs(2),shared.wait_finished()).await?;}
        tokio::time::timeout(Duration::from_secs(2),serving.as_mut()).await??;
    }}
    observation_stop.send_replace(true);
    tokio::time::timeout(Duration::from_secs(2), observation_task).await???;
    if shared.finished.load(Ordering::SeqCst) {
        tokio::time::timeout(Duration::from_secs(2), finished_task).await???;
    } else {
        finished_task.abort();
        let _ = finished_task.await;
    }

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
