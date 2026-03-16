import json

import httpx

from near_langchain_event_listener.langchain_tools import NEAREventListenerToolkit, get_near_event_listener_tools
from near_langchain_event_listener.listener import NEAREventListener
from near_langchain_event_listener.rpc import NEARRPCClient


class FakeRPC:
    def __init__(self):
        self.block_data = {
            "header": {"height": 42, "hash": "block_hash_42"},
            "chunks": [{"chunk_hash": "chunk_42"}],
        }
        self.chunk_data = {
            "transactions": [
                {
                    "hash": "tx_42",
                    "signer_id": "alice.near",
                    "receiver_id": "contract.near",
                    "actions": [{"FunctionCall": {"method_name": "ping"}}],
                }
            ],
            "receipts_outcome": [],
        }

    def block(self, network: str, *, finality: str = "final") -> dict:
        return self.block_data

    def block_by_height(self, network: str, height: int) -> dict:
        return self.block_data

    def chunk(self, network: str, chunk_id: str) -> dict:
        return self.chunk_data


def test_listener_poll_matches_subscription_without_callback() -> None:
    listener = NEAREventListener(rpc_client=FakeRPC())
    sub = listener.subscribe(account_id="alice.near", event_types=["function_call"])
    assert sub["account_id"] == "alice.near"

    result = listener.poll_once(network="mainnet", max_blocks=5)
    assert result["matched_events"] == 1
    event = result["events"][0]["event"]
    assert event["event_type"] == "function_call"


def test_listener_triggers_callback_for_matched_event() -> None:
    callback_calls = []

    def callback_handler(request: httpx.Request) -> httpx.Response:
        callback_calls.append(request)
        return httpx.Response(200, json={"ok": True})

    listener = NEAREventListener(
        rpc_client=FakeRPC(),
        callback_transport=httpx.MockTransport(callback_handler),
        callback_retries=1,
    )
    listener.subscribe(
        account_id="alice.near",
        event_types=["function_call"],
        callback_url="https://callback.example/hook",
        callback_headers={"X-Test": "1"},
    )

    result = listener.poll_once(network="mainnet", max_blocks=1)
    assert result["matched_events"] == 1
    assert result["callbacks_sent"] == 1
    assert len(callback_calls) == 1


def test_langchain_tools_return_json() -> None:
    listener = NEAREventListener(rpc_client=FakeRPC())
    tools = {tool.name: tool for tool in NEAREventListenerToolkit(listener=listener).get_tools()}

    subscribe_out = json.loads(
        tools["near_event_subscribe_account"].invoke(
            {"account_id": "alice.near", "event_types": ["function_call"]}
        )
    )
    assert subscribe_out["account_id"] == "alice.near"

    poll_out = json.loads(tools["near_event_poll"].invoke({"network": "mainnet", "max_blocks": 1}))
    assert poll_out["matched_events"] == 1


def test_rpc_reconnect_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "rpc1.invalid" in str(request.url):
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": "x", "result": {"ok": True}})

    transport = httpx.MockTransport(handler)
    client = NEARRPCClient(
        rpc_by_network={"mainnet": ["https://rpc1.invalid", "https://rpc2.valid"]},
        max_retries=2,
        backoff_seconds=0,
        transport=transport,
    )

    result = client.rpc("mainnet", "status", [])
    assert result["ok"] is True


def test_default_tool_factory_exposes_expected_tools() -> None:
    tools = {tool.name for tool in get_near_event_listener_tools()}
    assert "near_event_subscribe_account" in tools
    assert "near_event_poll" in tools
