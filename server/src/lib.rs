//! Experiment 001 protocol foundation. Runtime scenarios are not implemented yet.
pub mod protocol {
    tonic::include_proto!("pressure.v1");
}

#[cfg(test)]
mod tests {
    use super::protocol::{Payload, Summary};
    use prost::Message;

    #[test]
    fn payload_round_trip_preserves_sequence_and_owned_bytes() {
        let original = Payload {
            sequence: 42,
            data: (0..=255).cycle().take(16384).collect(),
        };
        let encoded = original.encode_to_vec();
        let decoded = Payload::decode(encoded.as_slice()).unwrap();
        assert_eq!(decoded.sequence, 42);
        assert_eq!(decoded.data.len(), 16384);
        assert_eq!(decoded.data, original.data);
        assert_ne!(decoded.data.as_ptr(), original.data.as_ptr());
    }

    #[test]
    fn summary_round_trip_keeps_admission_distinct_from_completion() {
        let summary = Summary {
            accepted: 10,
            processed: 7,
        };
        assert_eq!(
            Summary::decode(summary.encode_to_vec().as_slice()).unwrap(),
            summary
        );
    }
}

#[cfg(test)]
mod channel_contract_tests {
    use tokio::sync::mpsc;

    #[tokio::test]
    async fn reservation_blocks_read_ahead_and_drop_releases_eof_slot() {
        let (tx, mut rx) = mpsc::channel(1);
        tx.send(vec![1u8; 16]).await.unwrap();
        assert!(tx.try_reserve().is_err());
        assert_eq!(rx.recv().await.unwrap().len(), 16);
        let eof_permit = tx.reserve().await.unwrap();
        assert_eq!(tx.capacity(), 0);
        drop(eof_permit); // receive returned EOF: no message handed off
        assert_eq!(tx.capacity(), 1);
        drop(tx);
        assert!(rx.recv().await.is_none());
    }

    #[tokio::test]
    async fn owned_payloads_survive_handoff_and_drain_exactly_once() {
        let (tx, mut rx) = mpsc::unbounded_channel();
        for sequence in 0..3 {
            tx.send(super::protocol::Payload {
                sequence,
                data: vec![sequence as u8; 16],
            })
            .unwrap();
        }
        drop(tx);
        let mut bytes = 0;
        for sequence in 0..3 {
            let item = rx.recv().await.unwrap();
            assert_eq!(item.sequence, sequence);
            assert_eq!(item.data, vec![sequence as u8; 16]);
            bytes += item.data.len();
        }
        assert_eq!(bytes, 48);
        assert!(rx.recv().await.is_none());
    }
}
