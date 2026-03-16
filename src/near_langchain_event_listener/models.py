from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class Subscription:
    subscription_id: str
    account_id: str
    event_types: Set[str] = field(default_factory=set)
    callback_url: Optional[str] = None
    callback_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedEvent:
    event_id: str
    block_height: int
    block_hash: str
    tx_hash: Optional[str]
    event_type: str
    account_ids: List[str]
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "block_height": self.block_height,
            "block_hash": self.block_hash,
            "tx_hash": self.tx_hash,
            "event_type": self.event_type,
            "account_ids": self.account_ids,
            "payload": self.payload,
        }
