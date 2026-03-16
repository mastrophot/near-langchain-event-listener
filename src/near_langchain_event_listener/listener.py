from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import httpx

from .errors import NEAREventListenerError
from .models import ParsedEvent, Subscription
from .parser import parse_chunk_events
from .rpc import NEARRPCClient


class NEAREventListener:
    def __init__(
        self,
        *,
        rpc_client: Optional[NEARRPCClient] = None,
        callback_timeout_seconds: float = 10.0,
        callback_retries: int = 2,
        callback_transport: Optional[httpx.BaseTransport] = None,
    ):
        self.rpc = rpc_client or NEARRPCClient()
        self.callback_timeout_seconds = callback_timeout_seconds
        self.callback_retries = callback_retries
        self.callback_transport = callback_transport
        self.subscriptions: dict[str, Subscription] = {}
        self.last_processed_height: dict[str, int] = {}

    def subscribe(
        self,
        *,
        account_id: str,
        event_types: Optional[List[str]] = None,
        callback_url: Optional[str] = None,
        callback_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        if not account_id:
            raise NEAREventListenerError("invalid_account", "account_id is required")
        if callback_url and not callback_url.startswith(("http://", "https://")):
            raise NEAREventListenerError(
                "invalid_callback_url",
                "callback_url must start with http:// or https://",
                {"callback_url": callback_url},
            )

        sub_id = str(uuid.uuid4())
        normalized_event_types = {
            self._normalize_event_filter(x)
            for x in (event_types or [])
            if x and self._normalize_event_filter(x)
        }

        self.subscriptions[sub_id] = Subscription(
            subscription_id=sub_id,
            account_id=account_id,
            event_types=normalized_event_types,
            callback_url=callback_url,
            callback_headers=callback_headers or {},
        )
        return self._subscription_to_dict(self.subscriptions[sub_id])

    def unsubscribe(self, subscription_id: str) -> Dict[str, Any]:
        removed = self.subscriptions.pop(subscription_id, None)
        return {
            "subscription_id": subscription_id,
            "removed": removed is not None,
        }

    def list_subscriptions(self) -> Dict[str, Any]:
        return {
            "subscriptions": [self._subscription_to_dict(s) for s in self.subscriptions.values()],
            "count": len(self.subscriptions),
        }

    def status(self) -> Dict[str, Any]:
        return {
            "subscriptions_count": len(self.subscriptions),
            "last_processed_height": dict(self.last_processed_height),
        }

    def poll_once(
        self,
        *,
        network: str = "mainnet",
        finality: str = "final",
        max_blocks: int = 20,
        max_events: int = 200,
    ) -> Dict[str, Any]:
        latest_block = self.rpc.block(network, finality=finality)
        latest_height = int(latest_block.get("header", {}).get("height", 0))

        previous_height = self.last_processed_height.get(network)
        if previous_height is None:
            start_height = latest_height
        else:
            start_height = previous_height + 1

        if latest_height - start_height + 1 > max_blocks:
            start_height = latest_height - max_blocks + 1

        if start_height > latest_height:
            start_height = latest_height

        matched_events: List[Dict[str, Any]] = []
        callbacks_sent = 0

        for height in range(start_height, latest_height + 1):
            block = self.rpc.block_by_height(network, height)
            chunks = block.get("chunks", [])
            for chunk_meta in chunks:
                chunk_hash = chunk_meta.get("chunk_hash")
                if not chunk_hash:
                    continue
                chunk = self.rpc.chunk(network, chunk_hash)
                events = parse_chunk_events(block, chunk)
                for event in events:
                    for sub in self.subscriptions.values():
                        if not self._matches_subscription(event, sub):
                            continue
                        payload = {
                            "subscription_id": sub.subscription_id,
                            "account_id": sub.account_id,
                            "event": event.to_dict(),
                        }
                        dispatch = self._dispatch_callback(sub, payload)
                        payload["callback"] = dispatch
                        matched_events.append(payload)
                        if dispatch.get("triggered"):
                            callbacks_sent += 1
                        if len(matched_events) >= max_events:
                            self.last_processed_height[network] = height
                            return {
                                "network": network,
                                "from_height": start_height,
                                "to_height": height,
                                "subscriptions": len(self.subscriptions),
                                "matched_events": len(matched_events),
                                "callbacks_sent": callbacks_sent,
                                "events": matched_events,
                                "truncated": True,
                            }

        self.last_processed_height[network] = latest_height
        return {
            "network": network,
            "from_height": start_height,
            "to_height": latest_height,
            "subscriptions": len(self.subscriptions),
            "matched_events": len(matched_events),
            "callbacks_sent": callbacks_sent,
            "events": matched_events,
            "truncated": False,
        }

    def _matches_subscription(self, event: ParsedEvent, sub: Subscription) -> bool:
        if sub.account_id not in event.account_ids:
            return False
        if sub.event_types and not any(self._event_filter_matches(event, x) for x in sub.event_types):
            return False
        return True

    @staticmethod
    def _normalize_event_filter(token: str) -> str:
        return token.strip().lower()

    @staticmethod
    def _event_filter_matches(event: ParsedEvent, token: str) -> bool:
        event_type = event.event_type.lower()
        if token == event_type:
            return True

        if event_type != "event_json":
            return False
        if not token.startswith("event_json"):
            return False

        event_payload = event.payload.get("event", {})
        event_name = str(event_payload.get("event", "")).lower()
        standard = str(event_payload.get("standard", "")).lower()

        # Supported filter formats:
        # - event_json
        # - event_json:ft_transfer
        # - event_json:nep141:ft_transfer
        parts = token.split(":")
        if len(parts) == 1:
            return token == "event_json"
        if len(parts) == 2:
            return event_name == parts[1]
        if len(parts) >= 3:
            return standard == parts[1] and event_name == parts[2]
        return False

    def _dispatch_callback(self, sub: Subscription, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not sub.callback_url:
            return {"triggered": False, "reason": "no_callback_url"}

        errors: list[str] = []
        for attempt in range(max(1, self.callback_retries)):
            try:
                with httpx.Client(timeout=self.callback_timeout_seconds, transport=self.callback_transport) as client:
                    response = client.post(sub.callback_url, json=payload, headers=sub.callback_headers)
                    response.raise_for_status()
                return {
                    "triggered": True,
                    "status_code": response.status_code,
                    "attempt": attempt + 1,
                }
            except httpx.HTTPError as exc:
                errors.append(str(exc))

        return {
            "triggered": False,
            "reason": "callback_failed",
            "errors": errors,
        }

    @staticmethod
    def _subscription_to_dict(sub: Subscription) -> Dict[str, Any]:
        return {
            "subscription_id": sub.subscription_id,
            "account_id": sub.account_id,
            "event_types": sorted(sub.event_types),
            "callback_url": sub.callback_url,
            "callback_headers": sub.callback_headers,
        }
