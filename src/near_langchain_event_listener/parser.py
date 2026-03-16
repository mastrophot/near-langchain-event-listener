from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from .models import ParsedEvent


def _event_id(block_height: int, tx_hash: Optional[str], idx: int) -> str:
    return f"{block_height}:{tx_hash or 'no_tx'}:{idx}"


def _parse_log_payload(log_line: str) -> Tuple[str, Dict[str, Any]]:
    prefix = "EVENT_JSON:"
    if log_line.startswith(prefix):
        raw = log_line[len(prefix) :].strip()
        try:
            data = json.loads(raw)
            return "event_json", {"raw": log_line, "event": data}
        except json.JSONDecodeError:
            return "receipt_log", {"raw": log_line, "parse_error": "invalid_event_json"}
    return "receipt_log", {"raw": log_line}


def parse_chunk_events(block: dict[str, Any], chunk: dict[str, Any]) -> list[ParsedEvent]:
    header = block.get("header", {})
    block_height = int(header.get("height", 0))
    block_hash = str(header.get("hash", ""))

    events: list[ParsedEvent] = []
    idx = 0

    for tx in chunk.get("transactions", []):
        tx_hash = tx.get("hash")
        signer_id = tx.get("signer_id")
        receiver_id = tx.get("receiver_id")

        for action in tx.get("actions", []):
            if "Transfer" in action:
                payload = {
                    "kind": "transfer",
                    "transaction": tx,
                    "action": action,
                }
                events.append(
                    ParsedEvent(
                        event_id=_event_id(block_height, tx_hash, idx),
                        block_height=block_height,
                        block_hash=block_hash,
                        tx_hash=tx_hash,
                        event_type="transfer",
                        account_ids=[x for x in [signer_id, receiver_id] if isinstance(x, str)],
                        payload=payload,
                    )
                )
                idx += 1
            if "FunctionCall" in action:
                payload = {
                    "kind": "function_call",
                    "transaction": tx,
                    "action": action,
                }
                events.append(
                    ParsedEvent(
                        event_id=_event_id(block_height, tx_hash, idx),
                        block_height=block_height,
                        block_hash=block_hash,
                        tx_hash=tx_hash,
                        event_type="function_call",
                        account_ids=[x for x in [signer_id, receiver_id] if isinstance(x, str)],
                        payload=payload,
                    )
                )
                idx += 1

    for outcome in chunk.get("receipts_outcome", []):
        tx_hash = outcome.get("id")
        outcome_data = outcome.get("outcome", {})
        executor_id = outcome_data.get("executor_id")
        logs = outcome_data.get("logs", [])
        for line in logs:
            event_type, payload = _parse_log_payload(str(line))
            payload["executor_id"] = executor_id
            events.append(
                ParsedEvent(
                    event_id=_event_id(block_height, tx_hash, idx),
                    block_height=block_height,
                    block_hash=block_hash,
                    tx_hash=tx_hash,
                    event_type=event_type,
                    account_ids=[executor_id] if isinstance(executor_id, str) else [],
                    payload=payload,
                )
            )
            idx += 1

    return events
