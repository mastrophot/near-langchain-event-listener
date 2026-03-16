from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from .errors import NEAREventListenerError
from .listener import NEAREventListener


def _safe_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _wrap_error(exc: Exception) -> str:
    if isinstance(exc, NEAREventListenerError):
        return _safe_json(exc.to_dict())
    return _safe_json({"error": "internal_error", "message": str(exc)})


class SubscribeInput(BaseModel):
    account_id: str = Field(description="NEAR account to monitor")
    event_types: List[str] = Field(default_factory=list, description="Filter by event types, e.g. transfer,function_call,event_json")
    callback_url: Optional[str] = Field(default=None, description="Optional HTTP callback URL")
    callback_headers: Dict[str, str] = Field(default_factory=dict)


class UnsubscribeInput(BaseModel):
    subscription_id: str


class PollInput(BaseModel):
    network: str = "mainnet"
    finality: str = "final"
    max_blocks: int = 20
    max_events: int = 200


class NEAREventListenerToolkit:
    def __init__(self, listener: Optional[NEAREventListener] = None):
        self.listener = listener or NEAREventListener()

    def get_tools(self) -> list[StructuredTool]:
        return [
            StructuredTool.from_function(
                name="near_event_subscribe_account",
                description="Subscribe to NEAR account events with optional event-type filtering and callbacks.",
                args_schema=SubscribeInput,
                func=self._subscribe,
            ),
            StructuredTool.from_function(
                name="near_event_unsubscribe",
                description="Remove an existing account event subscription.",
                args_schema=UnsubscribeInput,
                func=self._unsubscribe,
            ),
            StructuredTool.from_function(
                name="near_event_list_subscriptions",
                description="List active account event subscriptions.",
                func=self._list_subscriptions,
            ),
            StructuredTool.from_function(
                name="near_event_listener_status",
                description="Get listener runtime status (subscriptions count and last processed block heights).",
                func=self._status,
            ),
            StructuredTool.from_function(
                name="near_event_poll",
                description="Poll NEAR blocks, parse events, apply filters, and trigger callbacks.",
                args_schema=PollInput,
                func=self._poll,
            ),
        ]

    def _subscribe(self, **kwargs: Any) -> str:
        try:
            return _safe_json(self.listener.subscribe(**kwargs))
        except Exception as exc:
            return _wrap_error(exc)

    def _unsubscribe(self, **kwargs: Any) -> str:
        try:
            return _safe_json(self.listener.unsubscribe(**kwargs))
        except Exception as exc:
            return _wrap_error(exc)

    def _list_subscriptions(self) -> str:
        try:
            return _safe_json(self.listener.list_subscriptions())
        except Exception as exc:
            return _wrap_error(exc)

    def _status(self) -> str:
        try:
            return _safe_json(self.listener.status())
        except Exception as exc:
            return _wrap_error(exc)

    def _poll(self, **kwargs: Any) -> str:
        try:
            return _safe_json(self.listener.poll_once(**kwargs))
        except Exception as exc:
            return _wrap_error(exc)


def get_near_event_listener_tools() -> list[StructuredTool]:
    return NEAREventListenerToolkit().get_tools()
