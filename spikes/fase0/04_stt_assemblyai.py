import asyncio
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402

API_KEY = require("ASSEMBLYAI_API_KEY")

import pyaudio  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    InterimTranscriptionFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402
from pipecat.services.assemblyai.stt import AssemblyAISTTService  # noqa: E402
from pipecat.transcriptions.language import Language  # noqa: E402
from pipecat.transports.local.audio import (  # noqa: E402
    LocalAudioTransport,
    LocalAudioTransportParams,
)


class Printer(FrameProcessor):
    def __init__(self):
        super().__init__()
        self._last_speech = time.perf_counter()

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame):
            print("…", frame.text)
            self._last_speech = time.perf_counter()
        elif isinstance(frame, TranscriptionFrame):
            print(f"FINAL [{getattr(frame, 'language', '?')}]: {frame.text}")
        await self.push_frame(frame, direction)


def wasapi_in():
    pa = pyaudio.PyAudio()
    info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    idx = int(info.get("defaultInputDevice", -1))
    pa.terminate()
    return idx if idx >= 0 else None


async def main():
    stt = AssemblyAISTTService(
        api_key=API_KEY,
        sample_rate=48000,
        vad_force_turn_endpoint=False,  # AssemblyAI maneja turnos (U3 Pro)
        settings=AssemblyAISTTService.Settings(
            model="universal-3-5-pro",
            language_codes=[Language.ES],  # español (steering U3 Pro)
            format_turns=True,
            keyterms_prompt=["Maia"],
        ),
    )
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_in_sample_rate=48000,
            input_device_index=wasapi_in(),
        )
    )
    pipeline = Pipeline([transport.input(), stt, Printer()])
    task = PipelineTask(pipeline, params=PipelineParams())
    runner = PipelineRunner(handle_sigint=False)
    print("20s: di varias frases en español (incluye 'Maia'). Ctrl-C para cortar.")
    try:
        await asyncio.wait_for(runner.run(task), timeout=20.0)
    except asyncio.TimeoutError:
        print("Fin (20s).")


asyncio.run(main())
