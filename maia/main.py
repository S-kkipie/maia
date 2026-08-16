import argparse
import asyncio

from claude_agent_sdk import ClaudeSDKClient, ResultMessage
from pipecat.frames.frames import TTSSpeakFrame, TTSUpdateSettingsFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.fish.tts import FishAudioTTSService

import pathlib

from maia import config, mcps, memory, services
from maia.audio_out import ResampleOut
from maia.brain import (
    MaiaBrain,
    build_claude_options,
    make_config_server,
    make_timer_server,
    make_voice_server,
)
from maia.computer import make_computer_server
from maia.clean import SpeechCleaner
from maia.reflex import Reflex
from maia.stt_fallback import STTFallbackGate, TagAAI


def build_stt_stages(cfg):
    """Devuelve la lista de procesadores STT según cfg.stt_engine.

    - 'assemblyai': sólo AssemblyAI (nube), sin VAD ni whisper.
    - 'whisper':    sólo whisper.cpp local (con VAD), activo desde el arranque.
    - 'auto':       AssemblyAI + whisper.cpp en standby + gate que cae a whisper si falla.
    """
    engine = cfg.stt_engine
    if engine == "assemblyai":
        print("[STT] Motor: AssemblyAI (nube, sin fallback)", flush=True)
        return [services.build_stt(cfg)]
    if engine == "whisper":
        print(f"[STT] Motor: whisper.cpp local ({cfg.whisper_model}, sin nube)", flush=True)
        whisper = services.build_whisper(cfg)
        whisper.active = True
        return [services.build_vad(), whisper]
    # auto (default)
    print(f"[STT] Motor: auto — AssemblyAI + fallback whisper.cpp ({cfg.whisper_model})", flush=True)
    whisper = services.build_whisper(cfg)
    return [
        services.build_stt(cfg),
        TagAAI(),
        services.build_vad(),
        whisper,
        STTFallbackGate(whisper),
    ]


async def _warmup(claude: ClaudeSDKClient):
    """Elimina el cold-start del SDK (~19s) antes del primer turno real."""
    await claude.query("Di: lista.")
    async for m in claude.receive_response():
        if isinstance(m, ResultMessage):
            break


async def main(stt_engine: str | None = None):
    cfg = config.load()
    if stt_engine:
        cfg.stt_engine = stt_engine
    transport = services.build_transport(cfg)
    reflex = Reflex(cfg.gemini_key, cfg.reflex_model) if cfg.gemini_key else None

    # Callback para cambiar la voz en vivo: empuja un TTSUpdateSettingsFrame al pipeline.
    holder = {"task": None}

    async def switch_voice(reference_id):
        if holder["task"] is not None:
            await holder["task"].queue_frame(
                TTSUpdateSettingsFrame(delta=FishAudioTTSService.Settings(voice=reference_id))
            )

    async def fire_timer(message):
        if holder["task"] is not None:
            await holder["task"].queue_frame(TTSSpeakFrame(f"Oye, recordatorio: {message}"))

    voice_server = make_voice_server(switch_voice)
    timer_server = make_timer_server(fire_timer)
    # in-process (voz, timers) + MCPs externos del registro (playwright/browser, etc.)
    servers = {
        "voz": voice_server,
        "timers": timer_server,
        "config": make_config_server(),
        "pc": make_computer_server(),  # computer use: ojos + manos en el escritorio
        "memoria": memory.make_memory_server(),  # memoria persistente entre sesiones
        **mcps.load_registry(),
    }
    mem = memory.load_memory()
    if mem:
        print(f"[MEMORIA] {len(mem.splitlines())} nota(s) cargada(s).", flush=True)
    plugin_dir = pathlib.Path(__file__).resolve().parents[1] / "maia_plugin"
    options = build_claude_options(
        mcp_servers=servers,
        allowed_tools=mcps.allowed_tools_for(servers.keys()),
        plugins=[{"type": "local", "path": str(plugin_dir)}],  # skill computer-use
        enable_skills=True,
        memory=mem,  # se inyecta en el system prompt (siempre en contexto)
    )

    async with ClaudeSDKClient(options=options) as claude:
        print("Calentando el cerebro…")
        await _warmup(claude)
        pipeline = Pipeline([
            transport.input(),
            *build_stt_stages(cfg),
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
    parser = argparse.ArgumentParser(description="Maia — asistente de voz")
    parser.add_argument(
        "--stt",
        choices=["auto", "assemblyai", "whisper"],
        default=None,
        help="Motor STT: auto (default, AssemblyAI + fallback whisper), "
             "assemblyai (sólo nube), whisper (sólo local). Override de MAIA_STT.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.stt))
