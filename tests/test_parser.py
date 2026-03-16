from near_langchain_event_listener.parser import parse_chunk_events


def test_parse_chunk_events_extracts_transfer_and_event_json() -> None:
    block = {"header": {"height": 100, "hash": "block_hash_100"}}
    chunk = {
        "transactions": [
            {
                "hash": "tx_hash_1",
                "signer_id": "alice.near",
                "receiver_id": "bob.near",
                "actions": [{"Transfer": {"deposit": "1"}}],
            }
        ],
        "receipts_outcome": [
            {
                "id": "receipt_1",
                "outcome": {
                    "executor_id": "bob.near",
                    "logs": ['EVENT_JSON:{"standard":"nep141","event":"ft_transfer","data":[]}'],
                },
            }
        ],
    }

    events = parse_chunk_events(block, chunk)
    event_types = [e.event_type for e in events]

    assert "transfer" in event_types
    assert "event_json" in event_types
    assert any("alice.near" in e.account_ids for e in events)
