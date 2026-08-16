"""STT local con whisper.cpp (pywhispercpp) — fallback offline de AssemblyAI.

Corre el modelo ggml de whisper.cpp EN PROCESO (sin API, sin nube). Segmenta por
VAD (SegmentedSTTService): acumula audio mientras hablas y transcribe el segmento
completo cuando dejas de hablar. Arranca en "standby frío" (active=False): no gasta
CPU en inferencia hasta que el gate lo activa porque AssemblyAI cayó.
"""
import asyncio
import re

import numpy as np
from pipecat.audio.resamplers.soxr_resampler import SOXRAudioResampler
from pipecat.frames.frames import Frame, StartFrame, TranscriptionFrame
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601

WHISPER_SR = 16000  # whisper.cpp espera 16 kHz mono float32

# whisper alucina "sonidos" en silencio/ruido: [Música], (risas), [BLANK_AUDIO]...
# Si el texto es SOLO uno de esos tokens entre corchetes/paréntesis, lo descartamos.
_ARTIFACT = re.compile(r"^[\[\(\*][^\]\)]*[\]\)\*]?$")


class WhisperCppSTT(SegmentedSTTService):
    """whisper.cpp local como STT segmentado. Standby frío hasta activate()."""

    def __init__(self, model_name: str = "base", models_dir: str = "models/whisper",
                 language: Language = Language.ES, n_threads: int = 4, **kwargs):
        super().__init__(**kwargs)
        self._model_name = model_name
        self._models_dir = models_dir
        self._lang = language
        self._n_threads = n_threads
        self._model = None
        self._resampler = SOXRAudioResampler()
        self.active = False  # el gate lo pone True cuando AssemblyAI falla

    @property
    def wants_wav_segments(self) -> bool:
        # Modelo local: queremos PCM16 crudo, no un contenedor WAV.
        return False

    async def start(self, frame: StartFrame):
        await super().start(frame)
        if self._model is None:
            # La carga del ggml bloquea ~7s: la hacemos en un hilo para no
            # congelar el event loop del pipeline.
            self._model = await asyncio.to_thread(self._load_model)

    def _load_model(self):
        from pywhispercpp.model import Model

        return Model(
            self._model_name,
            models_dir=self._models_dir,
            redirect_whispercpp_logs_to=False,
            print_realtime=False,
            print_progress=False,
        )

    def activate(self):
        """Enciende la inferencia local (lo llama el gate al caer AssemblyAI)."""
        if not self.active:
            self.active = True
            print(f"[STT] whisper.cpp ACTIVO (modelo {self._model_name})", flush=True)

    async def run_stt(self, audio: bytes):
        # Standby frío: bufferea (barato) pero no gasta CPU en inferencia.
        if not self.active or self._model is None or not audio:
            return

        # PCM16 @ sample_rate del pipeline (48k) -> 16k float32 mono para whisper.
        if self.sample_rate != WHISPER_SR:
            audio = await self._resampler.resample(audio, self.sample_rate, WHISPER_SR)
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size < WHISPER_SR // 4:  # <0.25s: ruido, ignora
            return

        segments = await asyncio.to_thread(self._transcribe, samples)
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text or _ARTIFACT.match(text):
            return
        print(f"[TÚ·whisper] {text}", flush=True)
        yield TranscriptionFrame(text, self._user_id, time_now_iso8601(), self._lang)

    def _transcribe(self, samples):
        lang = self._lang.value.split("-")[0] if hasattr(self._lang, "value") else "es"
        return self._model.transcribe(
            samples, language=lang, n_threads=self._n_threads,
            print_realtime=False, print_progress=False, translate=False,
        )
