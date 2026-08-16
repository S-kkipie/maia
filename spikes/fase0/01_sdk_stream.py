import asyncio
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401  (guard de API key)

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
)


async def run_turn(client, prompt):
    t0 = time.perf_counter()
    first_token = None
    tools = []
    chunks = []
    await client.query(prompt)
    async for message in client.receive_response():
        if isinstance(message, StreamEvent):
            ev = message.event
            et = ev.get("type")
            if et == "content_block_start":
                cb = ev.get("content_block", {})
                if cb.get("type") == "tool_use":
                    tools.append(cb.get("name"))
            elif et == "content_block_delta":
                d = ev.get("delta", {})
                if d.get("type") == "text_delta":
                    if first_token is None:
                        first_token = time.perf_counter() - t0
                    chunks.append(d.get("text", ""))
        elif isinstance(message, ResultMessage):
            break
    return {"ttft": first_token, "tools": tools, "text": "".join(chunks)}


async def main():
    options = ClaudeAgentOptions(
        model="claude-haiku-4-5-20251001",
        include_partial_messages=True,
        allowed_tools=["Bash"],
        # bypassPermissions: spike headless sin gate (el gate real es de v1).
        # Si el nombre del campo/valor difiere, registrar el real en FINDINGS.
        permission_mode="bypassPermissions",
    )
    async with ClaudeSDKClient(options=options) as client:
        r1 = await run_turn(
            client,
            "Ejecuta el comando de shell `echo hola-maia` y dime exactamente su salida.",
        )
        print(f"TURNO 1 — TTFT: {r1['ttft']:.3f}s  tools: {r1['tools']}")
        print("TURNO 1 — texto:", r1["text"][:300])
        r2 = await run_turn(
            client, "¿Qué comando de shell te acabo de pedir que ejecutara?"
        )
        print("TURNO 2 — (prueba de contexto):", r2["text"][:300])


asyncio.run(main())
