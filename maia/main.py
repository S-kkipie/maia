import asyncio

from claude_agent_sdk import ClaudeSDKClient, ResultMessage
from pipecat.frames.frames import TTSUpdateSettingsFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.fish.tts import FishAudioTTSService

from maia import config, services
from maia.audio_out import ResampleOut
from maia.brain import MaiaBrain, build_claude_options, make_voice_server
from maia.clean import SpeechCleaner
from maia.reflex import Reflex


async def _warmup(claude: ClaudeSDKClient):
    """Elimina el cold-start del SDK (~19s) antes del primer turno real."""
    await claude.query("Di: lista.")
    async for m in claude.receive_response():
        if isinstance(m, ResultMessage):
            break


async def main():
    cfg = config.load()
    transport = services.build_transport(cfg)
    reflex = Reflex(cfg.gemini_key, cfg.reflex_model) if cfg.gemini_key else None

    # Callback para cambiar la voz en vivo: empuja un TTSUpdateSettingsFrame al pipeline.
    holder = {"task": None}

    async def switch_voice(reference_id):
        if holder["task"] is not None:
            await holder["task"].queue_frame(
                TTSUpdateSettingsFrame(delta=FishAudioTTSService.Settings(voice=reference_id))
            )

    voice_server = make_voice_server(switch_voice)
    options = build_claude_options(
        mcp_servers={"voz": voice_server},
        allowed_tools=["mcp__voz__set_voice"],
    )

    async with ClaudeSDKClient(options=options) as claude:
        print("Calentando el cerebro…")
        await _warmup(claude)
        pipeline = Pipeline([
            transport.input(),
            services.build_stt(cfg),
            MaiaBrain(claude, reflex),
            SpeechCleaner(),  # quita markdown (**, [ ]) y loguea [MAIA]
            services.build_tts(cfg),
            ResampleOut(),  # Fish 24k -> 48k antes del transport (fix del chipmunk)
            transport.output(),
        ])
        task = PipelineTask(pipeline, params=PipelineParams(
            audio_in_sample_rate=48000, audio_out_sample_rate=48000, enable_metrics=True))
        holder["task"] = task
        print("Maia lista. Habla en español. Ctrl-C para salir.")
        await PipelineRunner(handle_sigint=False).run(task)


if __name__ == "__main__":
    asyncio.run(main())
