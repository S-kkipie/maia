from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.fish.tts import FishAudioTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

from maia.vad import Silero16k
from maia.whisper_stt import WhisperCppSTT

IN_SR = 48000    # mic WASAPI nativo (AssemblyAI a 48k)
OUT_SR = 48000   # speaker Realtek nativo (solo acepta 48000 con índice explícito)
FISH_SR = 24000  # Fish genera a 24k -> transport resamplea 24000->48000 (2x exacto, limpio)


def build_transport(cfg) -> LocalAudioTransport:
    return LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=IN_SR,
            audio_out_sample_rate=OUT_SR,
            input_device_index=cfg.input_device_index,
            output_device_index=cfg.output_device_index,
        )
    )


def build_stt(cfg) -> AssemblyAISTTService:
    return AssemblyAISTTService(
        api_key=cfg.assemblyai_key,
        sample_rate=IN_SR,  # debe igualar el transport de entrada (input NO auto-resamplea)
        vad_force_turn_endpoint=False,  # AssemblyAI maneja turnos + barge-in server-side
        settings=AssemblyAISTTService.Settings(
            model="universal-3-5-pro",
            language_codes=[Language.ES],
            format_turns=True,
            keyterms_prompt=["Maia"],
        ),
    )


def build_vad() -> VADProcessor:
    """VAD local (Silero) que segmenta el habla para whisper.cpp. Corre a 48k->16k."""
    return VADProcessor(vad_analyzer=Silero16k(input_rate=IN_SR))


def build_whisper(cfg) -> WhisperCppSTT:
    """STT local whisper.cpp. En 'auto' arranca en standby; en 'whisper' se activa."""
    return WhisperCppSTT(
        model_name=cfg.whisper_model,
        models_dir="models/whisper",
        language=Language.ES,
    )


def build_tts(cfg) -> FishAudioTTSService:
    return FishAudioTTSService(
        api_key=cfg.fish_key,
        sample_rate=FISH_SR,
        settings=FishAudioTTSService.Settings(
            model="s2.1-pro-free",  # se envía como header WS -> tier gratis
            voice=cfg.fish_reference_id,
            latency="balanced",
        ),
    )
