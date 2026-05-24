# hello_agent

The smallest possible agentkit host. Two tools (`echo`, `add`), one WebSocket endpoint.

## Run

```bash
pip install -e ..             # from repo root: pip install -e .
export ANTHROPIC_API_KEY=...  # or OPENAI_API_KEY
export AGENTKIT_MODEL=claude-sonnet-4-6     # optional; defaults to gpt-4o-mini
python examples/hello_agent/main.py
```

Server starts on `ws://127.0.0.1:8765/agent`.

## Talk to it

```python
import asyncio, json, websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:8765/agent") as ws:
        print(json.loads(await ws.recv()))           # thread_started
        await ws.send(json.dumps({
            "type": "user_message",
            "content": "add 2 and 40, then echo the result",
        }))
        while True:
            evt = json.loads(await ws.recv())
            print(evt)
            if evt["type"] == "turn_finished":
                break

asyncio.run(main())
```

## Health check (no key needed)

```bash
curl http://127.0.0.1:8765/healthz
# {"ok": true, "tools": ["echo", "add"]}
```
