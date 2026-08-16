"""Prueba de calidad de TTS aislada. Uso: uv run python -m maia.say [texto opcional]"""
import asyncio
import sys

from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

from maia import config, services
from maia.audio_out import ResampleOut


async def main():
    text = " ".join(sys.argv[1:]) or (
        "Hola, soy Maia. ¿Se me escucha limpia y natural, sin ruido ni tono agudo?"
    )
    cfg = config.load()
    transport = services.build_transport(cfg)
    task = PipelineTask(
        Pipeline([services.build_tts(cfg), ResampleOut(), transport.output()]),
        params=PipelineParams(audio_in_sample_rate=48000, audio_out_sample_rate=48000),
    )

    async def drive():
        await asyncio.sleep(0.5)
        await task.queue_frame(TTSSpeakFrame(text))
        await asyncio.sleep(8.0)
        await task.queue_frame(EndFrame())

    await asyncio.gather(PipelineRunner(handle_sigint=False).run(task), drive())


if __name__ == "__main__":
    asyncio.run(main())
