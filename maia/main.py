import asyncio

from claude_agent_sdk import ClaudeSDKClient, ResultMessage
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

from maia import config, services
from maia.audio_out import ResampleOut
from maia.brain import MaiaBrain, build_claude_options


async def _warmup(claude: ClaudeSDKClient):
    """Elimina el cold-start del SDK (~19s) antes del primer turno real."""
    await claude.query("Di: lista.")
    async for m in claude.receive_response():
        if isinstance(m, ResultMessage):
            break


async def main():
    cfg = config.load()
    transport = services.build_transport(cfg)
    async with ClaudeSDKClient(options=build_claude_options()) as claude:
        print("Calentando el cerebro…")
        await _warmup(claude)
        pipeline = Pipeline([
            transport.input(),
            services.build_stt(cfg),
            MaiaBrain(claude),
            services.build_tts(cfg),
            ResampleOut(),  # Fish 24k -> 48k antes del transport (fix del chipmunk)
            transport.output(),
        ])
        task = PipelineTask(pipeline, params=PipelineParams(
            audio_in_sample_rate=48000, audio_out_sample_rate=48000, enable_metrics=True))
        print("Maia lista. Habla en español. Ctrl-C para salir.")
        await PipelineRunner(handle_sigint=False).run(task)


if __name__ == "__main__":
    asyncio.run(main())
