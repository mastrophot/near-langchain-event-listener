# near-langchain-event-listener

LangChain tools for monitoring NEAR blockchain events with account subscriptions, event-type filtering, parsed event payloads, callback triggering, and reliable RPC reconnection.

## Features

- Subscribe to account-level events
- Filter by event type (`transfer`, `function_call`, `event_json`, `receipt_log`)
- Parse event data from transactions and `EVENT_JSON` logs
- Trigger HTTP callbacks for matched events
- Retry and endpoint failover for resilient RPC access

## Installation

```bash
pip install near-langchain-event-listener
```

## Quick Start (LangChain)

```python
import json
from near_langchain_event_listener import get_near_event_listener_tools

tools = {tool.name: tool for tool in get_near_event_listener_tools()}

sub = json.loads(tools["near_event_subscribe_account"].invoke({
    "account_id": "example.near",
    "event_types": ["transfer", "function_call"],
    "callback_url": "https://example.com/callback"
}))

print(sub["subscription_id"])

poll = json.loads(tools["near_event_poll"].invoke({
    "network": "mainnet",
    "max_blocks": 10,
    "max_events": 100
}))

print(poll["matched_events"])
```

## Tool Names

- `near_event_subscribe_account`
- `near_event_unsubscribe`
- `near_event_list_subscriptions`
- `near_event_poll`

## API Notes

- Subscriptions are in-memory state by default.
- First poll starts at current head block to avoid large historical backfill.
- Callback delivery uses HTTP POST and retries on failure.
- RPC reconnection uses multiple endpoints and retry backoff.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest -q
```

## License

MIT
