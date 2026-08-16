import asyncio

from pipecat.frames.frames import TranscriptionFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from maia import config, services
from maia.audio_out import ResampleOut
from maia.clean import SpeechCleaner


class EchoBrain(FrameProcessor):
    """Placeholder de M1: repite por TTS lo que el STT transcriba."""

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            print(f"ESCUCHE: {frame.text}")
            await self.push_frame(TTSSpeakFrame(f"Dijiste: {frame.text}"))
        else:
            await self.push_frame(frame, direction)


async def main():
    cfg = config.load()
    transport = services.build_transport(cfg)
    pipeline = Pipeline([
        transport.input(),
        services.build_stt(cfg),
        EchoBrain(),
        SpeechCleaner(),
        services.build_tts(cfg),
        ResampleOut(),
        transport.output(),
    ])
    task = PipelineTask(pipeline, params=PipelineParams(
        audio_in_sample_rate=48000, audio_out_sample_rate=48000, enable_metrics=True))
    print("Habla en espanol; Maia repetira. Ctrl-C para salir.")
    await PipelineRunner(handle_sigint=False).run(task)


if __name__ == "__main__":
    asyncio.run(main())
