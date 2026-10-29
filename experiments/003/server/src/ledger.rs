use crate::protocol::{
    server_frame, Outcome, ServerFrame, TerminalOutcome, TerminalReference, Work,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{collections::VecDeque, mem::size_of};

pub const ORIGINALS: usize = 2880;
pub const ATTEMPTS: usize = 8640;
pub const BUDGET: usize = 32;
pub const EVENTS: usize = 1024;
pub const PAYLOAD: usize = 16384;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Identity {
    pub message_id: u64,
    pub client_id: u32,
    pub scheduled_offset_ns: u64,
    pub deadline_offset_ns: u64,
    pub payload_sha256: [u8; 32],
    pub expendable: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Manifest {
    pub run_id: String,
    pub payload_seed: u64,
    pub originals: Vec<Identity>,
}
impl Manifest {
    pub fn validate(&self) -> Result<(), Error> {
        if self.originals.is_empty() || self.originals.len() > ORIGINALS || self.run_id.is_empty() {
            return Err(Error::Protocol("INVALID_MANIFEST"));
        }
        for (id, spec) in self.originals.iter().enumerate() {
            if spec.message_id != id as u64 || spec.deadline_offset_ns < spec.scheduled_offset_ns {
                return Err(Error::Protocol("INVALID_MANIFEST"));
            }
        }
        Ok(())
    }
    pub fn primary(run_id: &str) -> Self {
        let hash = Sha256::digest(payload(1)).into();
        Self {
            run_id: run_id.into(),
            payload_seed: 1,
            originals: (0..ORIGINALS)
                .map(|id| Identity {
                    message_id: id as u64,
                    client_id: 0,
                    scheduled_offset_ns: id as u64 * 12_500_000,
                    deadline_offset_ns: id as u64 * 12_500_000 + 2_000_000_000,
                    payload_sha256: hash,
                    expendable: true,
                })
                .collect(),
        }
    }
    pub fn work(&self, id: usize, attempt_id: u64, attempt_number: u32) -> Work {
        let spec = &self.originals[id];
        Work {
            run_id: self.run_id.clone(),
            message_id: id as u64,
            attempt_id,
            attempt_number,
            client_id: spec.client_id,
            scheduled_offset_ns: spec.scheduled_offset_ns,
            deadline_offset_ns: spec.deadline_offset_ns,
            payload: payload(self.payload_seed),
            payload_sha256: spec.payload_sha256.to_vec(),
            expendable: spec.expendable,
        }
    }
}
pub fn payload(seed: u64) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(PAYLOAD);
    for counter in 0..PAYLOAD / 32 {
        let mut hash = Sha256::new();
        hash.update(seed.to_le_bytes());
        hash.update((counter as u64).to_le_bytes());
        bytes.extend_from_slice(&hash.finalize());
    }
    bytes
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    Blocked,
    Protocol(&'static str),
    Capacity,
    Closed,
}
#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
pub enum Phase {
    Staged,
    Queued,
    Running,
    Terminal,
}
#[derive(Debug, Clone, Serialize)]
pub struct ResultRecord {
    pub outcome: i32,
    pub event_seq: u64,
    pub offset_ns: u64,
    pub worker_service_ns: u64,
    pub detail_code: &'static str,
}
#[derive(Clone, Debug, Serialize)]
pub struct Original {
    pub message_id: u64,
    pub phase: Phase,
    pub first_attempt: usize,
    pub starts: u32,
    pub start_ns: Option<u64>,
    pub exit_ns: Option<u64>,
    pub cancellation_requested_ns: Option<u64>,
    pub cancellation_observed_ns: Option<u64>,
    pub cancellation_reason: Option<&'static str>,
    pub terminal: Option<ResultRecord>,
}
#[derive(Clone, Debug, Serialize)]
pub struct Attempt {
    pub attempt_id: u64,
    pub message_id: u64,
    pub attempt_number: u32,
    pub duplicate: bool,
    pub terminal: Option<ResultRecord>,
    pub response_generated: bool,
    pub write_accepted: bool,
    pub undelivered: bool,
    pub immediate_reservation: bool,
}
struct Job {
    work: Work,
    terminal_slot: usize,
}
enum TerminalSlot {
    Free,
    Reserved(usize),
    Ready(ServerFrame),
}
#[derive(Clone, Debug, Serialize)]
pub struct Event {
    pub seq: u64,
    pub offset_ns: u64,
    pub kind: &'static str,
    pub message_id: Option<u64>,
    pub attempt_id: Option<u64>,
    pub occupied: usize,
    pub queued: usize,
    pub running: usize,
}
#[derive(Debug, Serialize)]
pub struct Snapshot {
    pub run_id: String,
    pub logical_capacity: usize,
    pub attempt_capacity: usize,
    pub logical_entries: usize,
    pub attempt_entries: usize,
    pub allocated_ledger_bytes: usize,
    pub queued: usize,
    pub running: usize,
    pub cancellation_pending_subset: usize,
    pub occupied: usize,
    pub decoded_staging: usize,
    pub receive_stage_reservation: usize,
    pub queued_payload_bytes: usize,
    pub worker_payload_bytes: usize,
    pub staging_payload_bytes: usize,
    pub terminal_responses_reserved: usize,
    pub immediate_responses: usize,
    pub event_writer_queue: usize,
    pub permits_acquired: u64,
    pub permits_released: u64,
    pub decoded_frames: u64,
    pub decoded_attempts: usize,
    pub failed: Option<&'static str>,
    pub event_seq: u64,
    pub originals: Vec<Original>,
    pub attempts: Vec<Attempt>,
}

pub struct Ledger {
    manifest: Manifest,
    originals: Vec<Option<Original>>,
    attempts: Vec<Option<Attempt>>,
    logical_limit: usize,
    attempt_limit: usize,
    queue: VecDeque<Job>,
    running: Option<Job>,
    staging: Option<Work>,
    reading: bool,
    terminal_slots: Vec<TerminalSlot>,
    immediate: VecDeque<ServerFrame>,
    protocol_error: Option<ServerFrame>,
    events: VecDeque<Event>,
    seq: u64,
    acquired: u64,
    released: u64,
    decoded: u64,
    pub eof: bool,
    pub failed: Option<&'static str>,
}
impl Ledger {
    pub fn new(manifest: Manifest) -> Result<Self, Error> {
        Self::with_limits(manifest, ORIGINALS, ATTEMPTS)
    }
    pub fn with_limits(manifest: Manifest, logical: usize, attempts: usize) -> Result<Self, Error> {
        manifest.validate()?;
        assert!(logical <= ORIGINALS && attempts <= ATTEMPTS);
        Ok(Self {
            originals: vec![None; ORIGINALS],
            attempts: vec![None; ATTEMPTS],
            manifest,
            logical_limit: logical,
            attempt_limit: attempts,
            queue: VecDeque::with_capacity(BUDGET),
            running: None,
            staging: None,
            reading: false,
            terminal_slots: (0..BUDGET).map(|_| TerminalSlot::Free).collect(),
            immediate: VecDeque::with_capacity(BUDGET),
            protocol_error: None,
            events: VecDeque::with_capacity(EVENTS),
            seq: 0,
            acquired: 0,
            released: 0,
            decoded: 0,
            eof: false,
            failed: None,
        })
    }
    fn room(&self) -> Result<(), Error> {
        if self.events.len() == EVENTS {
            Err(Error::Blocked)
        } else {
            Ok(())
        }
    }
    fn event(&mut self, now: u64, kind: &'static str, id: Option<usize>, attempt: Option<u64>) {
        assert!(self.events.len() < EVENTS);
        self.seq += 1;
        self.events.push_back(Event {
            seq: self.seq,
            offset_ns: now,
            kind,
            message_id: id.map(|i| i as u64),
            attempt_id: attempt,
            occupied: self.queue.len() + usize::from(self.running.is_some()),
            queued: self.queue.len(),
            running: usize::from(self.running.is_some()),
        });
        self.verify();
    }
    pub fn manifest(&self) -> &Manifest {
        &self.manifest
    }
    pub fn event_seq(&self) -> u64 {
        self.seq
    }
    pub fn snapshot_event_full(&self) -> bool {
        self.events.len() == EVENTS
    }
    pub fn release_decode(&mut self) {
        self.reading = false;
    }
    pub fn client_done(&mut self, now: u64) -> Result<(), Error> {
        self.room()?;
        self.reading = false;
        self.event(now, "client_done", None, None);
        Ok(())
    }
    pub fn pop_event(&mut self) -> Option<Event> {
        self.events.pop_front()
    }
    pub fn note(&mut self, now: u64) -> Result<(), Error> {
        self.room()?;
        self.event(now, "test_barrier", None, None);
        Ok(())
    }
    fn immediate_occupied(&self) -> usize {
        self.immediate.len()
            + self
                .attempts
                .iter()
                .flatten()
                .filter(|a| a.immediate_reservation)
                .count()
    }
    pub fn begin_decode(&mut self, now: u64) -> Result<(), Error> {
        self.room()?;
        if self.failed.is_some() || self.eof {
            return Err(Error::Closed);
        }
        if self.reading || self.staging.is_some() || self.immediate_occupied() == BUDGET {
            return Err(Error::Blocked);
        }
        self.reading = true;
        self.event(now, "decode_reserved", None, None);
        Ok(())
    }
    pub fn end_input(&mut self, now: u64) -> Result<(), Error> {
        self.room()?;
        self.reading = false;
        self.eof = true;
        self.event(now, "half_close", None, None);
        Ok(())
    }
    fn validate_work(&self, work: &Work) -> Result<usize, Error> {
        let id =
            usize::try_from(work.message_id).map_err(|_| Error::Protocol("INVALID_MESSAGE_ID"))?;
        let expected = self
            .manifest
            .originals
            .get(id)
            .ok_or(Error::Protocol("INVALID_MESSAGE_ID"))?;
        if work.run_id != self.manifest.run_id
            || !(1..=3).contains(&work.attempt_number)
            || work.client_id != expected.client_id
            || work.scheduled_offset_ns != expected.scheduled_offset_ns
            || work.deadline_offset_ns != expected.deadline_offset_ns
            || work.expendable != expected.expendable
            || work.payload.len() != PAYLOAD
            || work.payload_sha256.as_slice() != expected.payload_sha256
            || Sha256::digest(&work.payload).as_slice() != expected.payload_sha256
        {
            return Err(Error::Protocol("IDENTITY_OR_PAYLOAD_MISMATCH"));
        }
        Ok(id)
    }
    fn frame(&self, index: usize, replay: bool) -> ServerFrame {
        let attempt = self.attempts[index].as_ref().unwrap();
        let result = attempt.terminal.as_ref().unwrap();
        ServerFrame {
            frame: Some(server_frame::Frame::TerminalOutcome(TerminalOutcome {
                run_id: self.manifest.run_id.clone(),
                message_id: attempt.message_id,
                attempt_id: attempt.attempt_id,
                outcome: if replay || attempt.duplicate {
                    Outcome::DuplicateResult as i32
                } else {
                    result.outcome
                },
                server_event_seq: result.event_seq,
                server_event_offset_ns: result.offset_ns,
                worker_service_ns: result.worker_service_ns,
                detail_code: result.detail_code.into(),
                referenced_terminal: (replay || attempt.duplicate).then(|| TerminalReference {
                    outcome: result.outcome,
                    server_event_seq: result.event_seq,
                    server_event_offset_ns: result.offset_ns,
                    worker_service_ns: result.worker_service_ns,
                    detail_code: result.detail_code.into(),
                }),
            })),
        }
    }
    // Caller holds exactly one decoded-stage reservation. New identities are
    // registered atomically; duplicates store only bounded attempt metadata.
    pub fn offer(&mut self, work: Work, now: u64) -> Result<(), Error> {
        self.room()?;
        if !self.reading || self.staging.is_some() {
            return Err(Error::Protocol("NO_DECODE_RESERVATION"));
        }
        let id = self.validate_work(&work)?;
        if let Some(i) = self
            .attempts
            .iter()
            .position(|a| a.as_ref().is_some_and(|a| a.attempt_id == work.attempt_id))
        {
            let old = self.attempts[i].as_ref().unwrap();
            if old.message_id != work.message_id || old.attempt_number != work.attempt_number {
                return Err(Error::Protocol("ATTEMPT_ID_REUSED"));
            }
            self.reading = false;
            self.decoded += 1;
            if old.terminal.is_some() {
                self.immediate.push_back(self.frame(i, true));
            }
            self.event(now, "attempt_replay", Some(id), Some(work.attempt_id));
            return Ok(());
        }
        if self
            .attempts
            .iter()
            .filter(|a| a.as_ref().is_some_and(|a| a.message_id == work.message_id))
            .count()
            == 3
        {
            return Err(Error::Protocol("ATTEMPT_LIMIT"));
        }
        let logical_entries = self.originals.iter().flatten().count();
        let i = self
            .attempts
            .iter()
            .position(Option::is_none)
            .ok_or(Error::Capacity)?;
        if i >= self.attempt_limit
            || (self.originals[id].is_none() && logical_entries >= self.logical_limit)
        {
            self.failed = Some("METADATA_CAPACITY_EXHAUSTED");
            self.event(
                now,
                "metadata_capacity_exhausted",
                Some(id),
                Some(work.attempt_id),
            );
            return Err(Error::Capacity);
        }
        let duplicate = self.originals[id].is_some();
        let terminal = self.originals[id].as_ref().and_then(|o| o.terminal.clone());
        self.attempts[i] = Some(Attempt {
            attempt_id: work.attempt_id,
            message_id: work.message_id,
            attempt_number: work.attempt_number,
            duplicate,
            terminal,
            response_generated: false,
            write_accepted: false,
            undelivered: false,
            immediate_reservation: duplicate,
        });
        self.reading = false;
        self.decoded += 1;
        if !duplicate {
            self.originals[id] = Some(Original {
                message_id: id as u64,
                phase: Phase::Staged,
                first_attempt: i,
                starts: 0,
                start_ns: None,
                exit_ns: None,
                cancellation_requested_ns: None,
                cancellation_observed_ns: None,
                cancellation_reason: None,
                terminal: None,
            });
            self.staging = Some(work);
        }
        self.event(
            now,
            if duplicate {
                "duplicate_linked"
            } else {
                "decoded"
            },
            Some(id),
            self.attempts[i].as_ref().map(|a| a.attempt_id),
        );
        Ok(())
    }
    fn finish(
        &mut self,
        id: usize,
        outcome: Outcome,
        time: u64,
        detail: &'static str,
        service: u64,
    ) {
        let result = ResultRecord {
            outcome: outcome as i32,
            event_seq: self.seq + 1,
            offset_ns: time,
            worker_service_ns: service,
            detail_code: detail,
        };
        let original = self.originals[id].as_mut().unwrap();
        original.phase = Phase::Terminal;
        original.terminal = Some(result.clone());
        for a in self
            .attempts
            .iter_mut()
            .flatten()
            .filter(|a| a.message_id == id as u64)
        {
            a.terminal = Some(result.clone());
            a.undelivered = self.failed.is_some();
        }
    }
    pub fn progress_stage(&mut self, now: u64) -> Result<(), Error> {
        self.room()?;
        let Some(work) = self.staging.as_ref() else {
            return Ok(());
        };
        let id = work.message_id as usize;
        if now >= work.deadline_offset_ns || self.failed.is_some() {
            let failed = self.failed.is_some();
            self.finish(
                id,
                if failed {
                    Outcome::Cancelled
                } else {
                    Outcome::Expired
                },
                now,
                if failed {
                    "STREAM_CANCELLED"
                } else {
                    "EXPIRED_WAITING"
                },
                0,
            );
            let original = self.originals[id].as_mut().unwrap();
            original.cancellation_requested_ns.get_or_insert(now);
            original.cancellation_observed_ns = Some(now);
            original.exit_ns = Some(now);
            original.cancellation_reason = Some(if failed {
                "STREAM_CANCELLED"
            } else {
                "DEADLINE"
            });
            let first = original.first_attempt;
            self.attempts[first].as_mut().unwrap().immediate_reservation = !failed;
            self.staging.take();
            self.event(now, "staging_terminal", Some(id), None);
            return Ok(());
        }
        if self.queue.len() + usize::from(self.running.is_some()) == BUDGET {
            return Err(Error::Blocked);
        }
        let slot = self
            .terminal_slots
            .iter()
            .position(|s| matches!(s, TerminalSlot::Free))
            .ok_or(Error::Blocked)?;
        let work = self.staging.take().unwrap();
        self.terminal_slots[slot] = TerminalSlot::Reserved(id);
        self.queue.push_back(Job {
            work,
            terminal_slot: slot,
        });
        self.acquired += 1;
        self.originals[id].as_mut().unwrap().phase = Phase::Queued;
        self.event(now, "admitted", Some(id), None);
        Ok(())
    }
    pub fn start(&mut self, now: u64) -> Result<Option<(usize, u64, u64)>, Error> {
        self.room()?;
        if self.running.is_some() || self.failed.is_some() {
            return Ok(None);
        }
        let Some(front) = self.queue.front() else {
            return Ok(None);
        };
        if now >= front.work.deadline_offset_ns {
            return Ok(None);
        } // independent expiry sweep removes it
        let job = self.queue.pop_front().unwrap();
        let id = job.work.message_id as usize;
        let o = self.originals[id].as_mut().unwrap();
        assert_eq!(o.starts, 0);
        o.starts += 1;
        o.start_ns = Some(now);
        o.phase = Phase::Running;
        let deadline = job.work.deadline_offset_ns;
        self.running = Some(job);
        self.event(now, "worker_start", Some(id), None);
        Ok(Some((
            id,
            deadline,
            if (12_000_000_000..24_000_000_000).contains(&now) {
                40
            } else {
                10
            },
        )))
    }
    pub fn request_cancel(
        &mut self,
        id: usize,
        now: u64,
        reason: &'static str,
    ) -> Result<(), Error> {
        self.room()?;
        let Some(o) = self.originals.get_mut(id).and_then(Option::as_mut) else {
            return Err(Error::Protocol("UNKNOWN_ORIGINAL"));
        };
        if o.phase != Phase::Terminal && o.cancellation_requested_ns.is_none() {
            o.cancellation_requested_ns = Some(now);
            o.cancellation_reason = Some(reason);
        }
        self.event(now, "cancellation_requested", Some(id), None);
        Ok(())
    }
    pub fn observe_cancel(&mut self, id: usize, now: u64) -> Result<(), Error> {
        self.room()?;
        let o = self.originals[id].as_mut().unwrap();
        if o.cancellation_requested_ns.is_some() && o.phase == Phase::Running {
            o.cancellation_observed_ns = Some(now);
        }
        self.event(now, "cancellation_observed", Some(id), None);
        Ok(())
    }
    pub fn cancelled(&self, id: usize) -> bool {
        self.originals[id]
            .as_ref()
            .unwrap()
            .cancellation_requested_ns
            .is_some()
    }
    pub fn exit(
        &mut self,
        id: usize,
        finished: u64,
        exited: u64,
        completed: bool,
    ) -> Result<(), Error> {
        self.room()?;
        let job = self
            .running
            .take()
            .ok_or(Error::Protocol("NO_RUNNING_WORKER"))?;
        assert_eq!(job.work.message_id, id as u64);
        let original = self.originals[id].as_mut().unwrap();
        original.exit_ns = Some(exited);
        let elapsed = exited - original.start_ns.unwrap();
        let (outcome, detail) = if completed && original.cancellation_observed_ns.is_none() {
            (Outcome::Completed, "COMPLETED")
        } else if original.cancellation_reason == Some("DEADLINE") {
            (Outcome::Expired, "EXPIRED_PROCESSING")
        } else {
            (Outcome::Cancelled, "CANCELLED_PROCESSING")
        };
        self.finish(
            id,
            outcome,
            if outcome == Outcome::Completed {
                finished
            } else {
                exited
            },
            detail,
            elapsed,
        );
        self.released += 1;
        let index = self.originals[id].as_ref().unwrap().first_attempt;
        if self.failed.is_none() {
            self.terminal_slots[job.terminal_slot] = TerminalSlot::Ready(self.frame(index, false));
            self.attempts[index].as_mut().unwrap().response_generated = true;
        } else {
            self.terminal_slots[job.terminal_slot] = TerminalSlot::Free;
        }
        self.event(exited, "worker_exit", Some(id), None);
        Ok(())
    }
    pub fn sweep(&mut self, now: u64) -> Result<bool, Error> {
        self.room()?;
        if self
            .staging
            .as_ref()
            .is_some_and(|w| now >= w.deadline_offset_ns || self.failed.is_some())
        {
            self.progress_stage(now)?;
            return Ok(true);
        }
        if let Some(position) = self.queue.iter().position(|j| {
            now >= j.work.deadline_offset_ns
                || self.cancelled(j.work.message_id as usize)
                || self.failed.is_some()
        }) {
            let job = self.queue.remove(position).unwrap();
            let id = job.work.message_id as usize;
            let expired = now >= job.work.deadline_offset_ns;
            let o = self.originals[id].as_mut().unwrap();
            o.cancellation_requested_ns.get_or_insert(now);
            o.cancellation_observed_ns = Some(now);
            o.exit_ns = Some(now);
            o.cancellation_reason = Some(if expired { "DEADLINE" } else { "CANCELLED" });
            self.finish(
                id,
                if expired {
                    Outcome::Expired
                } else {
                    Outcome::Cancelled
                },
                now,
                if expired {
                    "EXPIRED_QUEUED"
                } else {
                    "CANCELLED_QUEUED"
                },
                0,
            );
            self.released += 1;
            let first = self.originals[id].as_ref().unwrap().first_attempt;
            if self.failed.is_none() {
                self.terminal_slots[job.terminal_slot] =
                    TerminalSlot::Ready(self.frame(first, false));
                self.attempts[first].as_mut().unwrap().response_generated = true;
            } else {
                self.terminal_slots[job.terminal_slot] = TerminalSlot::Free;
            }
            self.event(now, "queued_removed", Some(id), None);
            return Ok(true);
        }
        Ok(false)
    }
    pub fn fail(&mut self, now: u64, reason: &'static str) -> Result<(), Error> {
        self.room()?;
        self.failed.get_or_insert(reason);
        self.reading = false;
        for o in self
            .originals
            .iter_mut()
            .flatten()
            .filter(|o| o.phase != Phase::Terminal)
        {
            o.cancellation_requested_ns.get_or_insert(now);
            o.cancellation_reason.get_or_insert("STREAM_CANCELLED");
        }
        for slot in &mut self.terminal_slots {
            if matches!(slot, TerminalSlot::Ready(_)) {
                *slot = TerminalSlot::Free;
            }
        }
        self.immediate.clear();
        for attempt in self.attempts.iter_mut().flatten() {
            attempt.immediate_reservation = false;
            if !attempt.write_accepted {
                attempt.undelivered = true;
            }
        }
        self.event(now, "stream_failed", None, None);
        Ok(())
    }
    pub fn response(&mut self, now: u64) -> Result<Option<ServerFrame>, Error> {
        self.room()?;
        if self.failed.is_some() {
            return Ok(self.protocol_error.take());
        }
        let mut frame = None;
        if let Some(i) = self
            .terminal_slots
            .iter()
            .position(|s| matches!(s, TerminalSlot::Ready(_)))
        {
            if let TerminalSlot::Ready(f) =
                std::mem::replace(&mut self.terminal_slots[i], TerminalSlot::Free)
            {
                frame = Some(f);
            }
        } else if let Some(f) = self.immediate.pop_front() {
            frame = Some(f);
        } else if let Some(i) = self.attempts.iter().position(|a| {
            a.as_ref()
                .is_some_and(|a| a.terminal.is_some() && !a.response_generated)
        }) {
            let a = self.attempts[i].as_mut().unwrap();
            a.response_generated = true;
            a.immediate_reservation = false;
            frame = Some(self.frame(i, false)); // writer accepts directly, one in-flight frame
        }
        if frame.is_some() {
            self.event(now, "response_taken_by_writer", None, None);
        }
        Ok(frame)
    }
    pub fn accepted_write(&mut self, frame: &ServerFrame, now: u64) -> Result<(), Error> {
        self.room()?;
        if let Some(server_frame::Frame::TerminalOutcome(t)) = &frame.frame {
            let a = self
                .attempts
                .iter_mut()
                .flatten()
                .find(|a| a.attempt_id == t.attempt_id)
                .unwrap();
            a.write_accepted = true;
        }
        self.event(now, "local_write_accepted", None, None);
        Ok(())
    }
    pub fn protocol_failure(
        &mut self,
        code: &'static str,
        id: Option<u64>,
        attempt: Option<u64>,
        now: u64,
    ) -> Result<(), Error> {
        self.fail(now, code)?;
        self.protocol_error = Some(ServerFrame {
            frame: Some(server_frame::Frame::ProtocolError(
                crate::protocol::ProtocolError {
                    run_id: self.manifest.run_id.clone(),
                    message_id: id,
                    attempt_id: attempt,
                    code: code.into(),
                },
            )),
        });
        Ok(())
    }
    pub fn next_deadline(&self) -> Option<u64> {
        self.queue
            .iter()
            .map(|j| j.work.deadline_offset_ns)
            .chain(self.staging.iter().map(|w| w.deadline_offset_ns))
            .min()
    }
    // Only after supervised tasks have actually exited. A failed logger cannot
    // produce a valid run: retain explicit unresolved records, never completion.
    pub fn force_unresolved_after_task_exit(&mut self, now: u64) {
        self.failed = Some("UNRESOLVED_SHUTDOWN");
        self.queue.clear();
        self.running.take();
        self.staging.take();
        self.reading = false;
        self.released = self.acquired;
        for slot in &mut self.terminal_slots {
            *slot = TerminalSlot::Free;
        }
        self.immediate.clear();
        for a in self.attempts.iter_mut().flatten() {
            a.immediate_reservation = false;
            if !a.write_accepted {
                a.undelivered = true;
            }
        }
        for o in self
            .originals
            .iter_mut()
            .flatten()
            .filter(|o| o.phase != Phase::Terminal)
        {
            o.phase = Phase::Terminal;
            o.exit_ns = Some(now);
        }
        self.verify();
    }
    pub fn drained(&self) -> bool {
        self.eof
            && self.staging.is_none()
            && self.queue.is_empty()
            && self.running.is_none()
            && self
                .terminal_slots
                .iter()
                .all(|s| matches!(s, TerminalSlot::Free))
            && self.immediate.is_empty()
            && self
                .attempts
                .iter()
                .flatten()
                .all(|a| a.response_generated || a.undelivered)
    }
    pub fn idle(&self) -> bool {
        self.queue.is_empty() && self.running.is_none() && self.staging.is_none()
    }
    pub fn staged(&self) -> bool {
        self.staging.is_some()
    }
    pub fn running_id(&self) -> Option<usize> {
        self.running.as_ref().map(|j| j.work.message_id as usize)
    }
    pub fn verify(&self) {
        let occupied = self.queue.len() + usize::from(self.running.is_some());
        assert!(usize::from(self.reading) + usize::from(self.staging.is_some()) <= 1);
        assert!(
            occupied <= BUDGET
                && self.immediate_occupied() + usize::from(self.reading || self.staging.is_some())
                    <= BUDGET
        );
        assert_eq!(self.acquired - self.released, occupied as u64);
        assert!(self.originals.iter().flatten().count() <= self.logical_limit);
        assert!(self.attempts.iter().flatten().count() <= self.attempt_limit);
        assert!(self.events.len() <= EVENTS);
        for o in self.originals.iter().flatten() {
            assert!(o.starts <= 1);
        }
        let reserved = self
            .terminal_slots
            .iter()
            .filter(|s| matches!(s, TerminalSlot::Reserved(_)))
            .count();
        assert_eq!(reserved, occupied);
        for slot in &self.terminal_slots {
            if let TerminalSlot::Reserved(id) = slot {
                assert!(self.originals[*id].is_some());
            }
        }
    }
    pub fn snapshot(&self) -> Snapshot {
        self.verify();
        Snapshot {
            run_id: self.manifest.run_id.clone(),
            logical_capacity: self.logical_limit,
            attempt_capacity: self.attempt_limit,
            logical_entries: self.originals.iter().flatten().count(),
            attempt_entries: self.attempts.iter().flatten().count(),
            allocated_ledger_bytes: self.originals.capacity() * size_of::<Option<Original>>()
                + self.attempts.capacity() * size_of::<Option<Attempt>>()
                + self.manifest.originals.capacity() * size_of::<Identity>()
                + self.manifest.run_id.capacity(),
            queued: self.queue.len(),
            running: usize::from(self.running.is_some()),
            cancellation_pending_subset: usize::from(
                self.running_id().is_some_and(|id| self.cancelled(id)),
            ),
            occupied: self.queue.len() + usize::from(self.running.is_some()),
            decoded_staging: usize::from(self.staging.is_some()),
            receive_stage_reservation: usize::from(self.reading),
            queued_payload_bytes: self.queue.iter().map(|j| j.work.payload.len()).sum(),
            worker_payload_bytes: self.running.as_ref().map_or(0, |j| j.work.payload.len()),
            staging_payload_bytes: self.staging.as_ref().map_or(0, |w| w.payload.len()),
            terminal_responses_reserved: self
                .terminal_slots
                .iter()
                .filter(|s| !matches!(s, TerminalSlot::Free))
                .count(),
            immediate_responses: self.immediate_occupied(),
            event_writer_queue: self.events.len(),
            permits_acquired: self.acquired,
            permits_released: self.released,
            decoded_frames: self.decoded,
            decoded_attempts: self.attempts.iter().flatten().count(),
            failed: self.failed,
            event_seq: self.seq,
            originals: self.originals.iter().flatten().cloned().collect(),
            attempts: self.attempts.iter().flatten().cloned().collect(),
        }
    }
}
