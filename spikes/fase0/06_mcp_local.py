import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
)


async def main():
    options = ClaudeAgentOptions(
        model="claude-haiku-4-5-20251001",
        include_partial_messages=True,
        mcp_servers={  # <-- LOCAL configurado, no connector de cuenta
            "playwright": {
                "command": "npx",
                "args": ["-y", "@playwright/mcp@latest"],
            }
        },
        allowed_tools=["mcp__playwright__*"],
        permission_mode="bypassPermissions",
    )
    tools = []
    chunks = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            "Con la herramienta de navegador (Playwright), abre https://example.com "
            "y dime el título exacto de la página."
        )
        async for m in client.receive_response():
            if isinstance(m, StreamEvent):
                ev = m.event
                if ev.get("type") == "content_block_start":
                    cb = ev.get("content_block", {})
                    if cb.get("type") == "tool_use":
                        tools.append(cb.get("name"))
                elif ev.get("type") == "content_block_delta":
                    d = ev.get("delta", {})
                    if d.get("type") == "text_delta":
                        chunks.append(d.get("text", ""))
            elif isinstance(m, ResultMessage):
                break
    print("tools MCP usadas:", tools)
    print("respuesta:", "".join(chunks)[:400])


asyncio.run(main())
