import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401

import pyaudio  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.transports.local.audio import (  # noqa: E402
    LocalAudioTransport,
    LocalAudioTransportParams,
)


def wasapi_devices():
    pa = pyaudio.PyAudio()
    try:
        info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        pa.terminate()
        sys.exit("WASAPI no disponible en esta build de PortAudio.")
    in_idx = info.get("defaultInputDevice", -1)
    out_idx = info.get("defaultOutputDevice", -1)
    print(f"WASAPI: host_api={info['index']} in={in_idx} out={out_idx}")
    pa.terminate()
    if in_idx < 0 or out_idx < 0:
        sys.exit("WASAPI sin device in/out por defecto — registrar y elegir device manual.")
    return int(in_idx), int(out_idx)


async def main():
    in_idx, out_idx = wasapi_devices()
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=48000,
            audio_out_sample_rate=48000,
            input_device_index=in_idx,
            output_device_index=out_idx,
        )
    )
    pipeline = Pipeline([transport.input(), transport.output()])  # mic -> speaker
    task = PipelineTask(pipeline, params=PipelineParams())
    runner = PipelineRunner(handle_sigint=False)  # loop Proactor de Windows
    print("Loopback 8s: habla y escúchate (usa auriculares para evitar acople).")
    try:
        await asyncio.wait_for(runner.run(task), timeout=8.0)
    except asyncio.TimeoutError:
        print("Fin del loopback (8s).")


asyncio.run(main())
