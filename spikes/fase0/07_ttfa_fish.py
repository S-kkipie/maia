"""TTFA con Fish Audio (modelo gratis s2.1-pro-free) para comparar contra ElevenLabs (05)."""
import asyncio
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402

require("FISHAUDIO_API_KEY")
REFERENCE_ID = os.getenv("FISHAUDIO_REFERENCE_ID") or None  # voz espanola (opcional)

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
)
from pipecat.frames.frames import (  # noqa: E402
    EndFrame,
    MetricsFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
)
from pipecat.metrics.metrics import TTFAMetricsData  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402
from pipecat.services.fish.tts import FishAudioTTSService  # noqa: E402
from pipecat.transports.local.audio import (  # noqa: E402
    LocalAudioTransport,
    LocalAudioTransportParams,
)

SR = 48000  # rate nativo WASAPI
state = {"t0": None, "first_audio": None}


class AudioTap(FrameProcessor):
    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if (
            isinstance(frame, TTSAudioRawFrame)
            and state["first_audio"] is None
            and state["t0"] is not None
        ):
            state["first_audio"] = time.perf_counter()
            print(f"TTFA total (query -> primer audio): {state['first_audio'] - state['t0']:.3f}s")
        if isinstance(frame, MetricsFrame):
            for d in frame.data:
                if isinstance(d, TTFAMetricsData):
                    print(f"Pipecat TTFA(TTS)={d.ttfa:.3f}s TTFB={d.ttfb:.3f}s")
        await self.push_frame(frame, direction)


async def drain(client):
    async for m in client.receive_response():
        if isinstance(m, ResultMessage):
            return


async def brain_stream(client, task, prompt):
    buf = ""
    state["t0"] = time.perf_counter()
    await client.query(prompt)
    async for message in client.receive_response():
        if isinstance(message, StreamEvent):
            ev = message.event
            if ev.get("type") == "content_block_delta":
                d = ev.get("delta", {})
                if d.get("type") == "text_delta":
                    buf += d.get("text", "")
                    m = re.search(r"[.!?]\s", buf)
                    if m:  # primera frase completa -> hablar YA
                        await task.queue_frame(TTSSpeakFrame(buf[: m.end()].strip()))
                        return
        elif isinstance(message, ResultMessage):
            if buf.strip():
                await task.queue_frame(TTSSpeakFrame(buf.strip()))
            return


async def main():
    tts = FishAudioTTSService(
        api_key=os.getenv("FISHAUDIO_API_KEY"),
        sample_rate=SR,
        settings=FishAudioTTSService.Settings(
            model="s2.1-pro-free",  # se envia como header WS -> tier gratis
            voice=REFERENCE_ID,     # reference_id de una voz espanola (o None = default)
            latency="balanced",
        ),
    )
    transport = LocalAudioTransport(
        LocalAudioTransportParams(audio_out_enabled=True, audio_out_sample_rate=SR)
    )
    pipeline = Pipeline([tts, AudioTap(), transport.output()])
    task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=True))
    runner = PipelineRunner(handle_sigint=False)

    async def drive():
        opts = ClaudeAgentOptions(
            model="claude-haiku-4-5-20251001", include_partial_messages=True
        )
        async with ClaudeSDKClient(options=opts) as client:
            # Warmup: elimina el cold-start del SDK (mide cliente WARM persistente).
            await client.query("Responde solo con la palabra: listo.")
            await drain(client)
            await brain_stream(
                client, task, "En una sola frase corta y natural, saludame como asistente de voz."
            )
        await asyncio.sleep(4)
        await task.queue_frame(EndFrame())

    await asyncio.gather(runner.run(task), drive())


asyncio.run(main())
