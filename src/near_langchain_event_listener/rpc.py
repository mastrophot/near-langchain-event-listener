from __future__ import annotations

import itertools
import time
from typing import Any, Dict, List, Optional

import httpx

from .errors import NEAREventListenerError

DEFAULT_RPC_BY_NETWORK = {
    "mainnet": [
        "https://rpc.mainnet.near.org",
        "https://free.rpc.fastnear.com",
    ],
    "testnet": [
        "https://rpc.testnet.near.org",
        "https://test.rpc.fastnear.com",
    ],
}


class NEARRPCClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        rpc_by_network: Optional[Dict[str, List[str]]] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.rpc_by_network = rpc_by_network or DEFAULT_RPC_BY_NETWORK
        self.transport = transport

    def _endpoints(self, network: str) -> List[str]:
        endpoints = self.rpc_by_network.get(network)
        if not endpoints:
            raise NEAREventListenerError(
                "invalid_network",
                "network must be mainnet or testnet",
                {"network": network},
            )
        return endpoints

    def rpc(self, network: str, method: str, params: Any) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": "near-langchain-event-listener",
            "method": method,
            "params": params,
        }

        errors: list[str] = []
        endpoints = self._endpoints(network)
        cycle = itertools.cycle(endpoints)
        attempts = max(1, self.max_retries)

        for attempt in range(attempts):
            url = next(cycle)
            try:
                with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                    response = client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
            except httpx.HTTPError as exc:
                errors.append(f"{url}: {exc}")
                if attempt < attempts - 1:
                    time.sleep(self.backoff_seconds * (attempt + 1))
                continue

            if "error" in data:
                err = data["error"]
                errors.append(f"{url}: {err.get('message', 'rpc error')}")
                if attempt < attempts - 1:
                    time.sleep(self.backoff_seconds * (attempt + 1))
                continue

            return data.get("result", {})

        raise NEAREventListenerError(
            "rpc_error",
            "all RPC attempts failed",
            {"network": network, "attempts": attempts, "errors": errors},
        )

    def block(self, network: str, *, finality: str = "final") -> dict[str, Any]:
        return self.rpc(network, "block", {"finality": finality})

    def block_by_height(self, network: str, height: int) -> dict[str, Any]:
        return self.rpc(network, "block", {"block_id": height})

    def chunk(self, network: str, chunk_id: str) -> dict[str, Any]:
        return self.rpc(network, "chunk", {"chunk_id": chunk_id})
