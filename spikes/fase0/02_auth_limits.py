import asyncio
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401  (guard: aborta si hay API key)

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

CRED = pathlib.Path.home() / ".claude" / ".credentials.json"
oauth = json.loads(CRED.read_text())["claudeAiOauth"]
vigente = oauth.get("expiresAt", 0) / 1000 > time.time()
print("subscriptionType:", oauth.get("subscriptionType"))
print("rateLimitTier:", oauth.get("rateLimitTier"))
print("accessToken vigente:", vigente)
if not vigente:
    print("AVISO: accessToken expirado; el SDK debería refrescar con refreshToken.")


async def main():
    options = ClaudeAgentOptions(model="claude-haiku-4-5-20251001")
    latencias = []
    errores = []
    async with ClaudeSDKClient(options=options) as client:
        for i in range(20):
            t0 = time.perf_counter()
            try:
                await client.query(f"Responde solo con el número {i}, nada más.")
                async for m in client.receive_response():
                    if isinstance(m, ResultMessage):
                        break
                latencias.append(time.perf_counter() - t0)
            except Exception as e:  # noqa: BLE001
                errores.append(repr(e))
                print(f"ERROR en turno {i}: {e}")
                break
    print(f"Turnos OK: {len(latencias)}/20  errores: {len(errores)}")
    if latencias:
        print(f"Latencia media: {sum(latencias) / len(latencias):.3f}s")


asyncio.run(main())
