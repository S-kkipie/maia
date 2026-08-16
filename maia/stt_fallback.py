"""Fallback de STT: AssemblyAI (nube) -> whisper.cpp (local) sin reiniciar.

Va DESPUÉS de los dos STT en el pipeline:
    input(vad) -> AssemblyAI -> TagAAI -> WhisperCppSTT(standby) -> STTFallbackGate -> brain

- TagAAI marca las transcripciones de AssemblyAI. En el gate, lo NO marcado es whisper.
- El gate normalmente reenvía las de AssemblyAI y descarta whisper (que está en standby).
- Cuando AssemblyAI falla, el gate enciende whisper y a partir de ahí reenvía whisper
  y descarta AssemblyAI. Dos disparadores:
    1) ErrorFrame de AssemblyAI (agota sus 3 reintentos de reconexión).
    2) Hablaste (VAD) pero AssemblyAI no transcribió nada en MISS_TIMEOUT, dos veces
       seguidas (cubre créditos agotados donde el WS sigue abierto pero mudo).
"""
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

MISS_TIMEOUT = 4.0  # s de espera de una transcripción de AssemblyAI tras dejar de hablar
MISS_LIMIT = 2      # misses seguidos antes de caer a whisper


class TagAAI(FrameProcessor):
    """Marca las transcripciones que vienen de AssemblyAI (para distinguirlas de whisper)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
            frame._maia_src = "aai"
        await self.push_frame(frame, direction)


class STTFallbackGate(FrameProcessor):
    """Enruta transcripciones y decide cuándo caer de AssemblyAI a whisper.cpp."""

    def __init__(self, whisper, **kwargs):
        super().__init__(**kwargs)
        self._whisper = whisper  # WhisperCppSTT en standby; le llamamos activate()
        self._fallback = False
        self._misses = 0
        self._miss_task = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, ErrorFrame):
            self._trigger("AssemblyAI reportó error irrecuperable")
            await self.push_frame(frame, direction)  # no la tragamos (es no-fatal)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            if not self._fallback:
                self._arm_miss_timer()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
            src = getattr(frame, "_maia_src", "whisper")
            if src == "aai":
                # AssemblyAI vivo: cancela el miss timer pendiente.
                if isinstance(frame, TranscriptionFrame) and frame.text.strip():
                    self._misses = 0
                    self._cancel_miss_timer()
                if self._fallback:
                    return  # ya estamos en whisper: descarta AssemblyAI
                await self.push_frame(frame, direction)
            else:  # whisper
                if self._fallback:
                    await self.push_frame(frame, direction)
                # en modo normal whisper está en standby y no emite; si emitiera, se ignora
            return

        await self.push_frame(frame, direction)

    def _arm_miss_timer(self):
        self._cancel_miss_timer()
        self._miss_task = self.create_task(self._miss_after_timeout())

    def _cancel_miss_timer(self):
        if self._miss_task is not None:
            task = self._miss_task
            self._miss_task = None
            self.create_task(self._safe_cancel(task))

    async def _safe_cancel(self, task):
        try:
            await self.cancel_task(task)
        except Exception:
            pass

    async def _miss_after_timeout(self):
        import asyncio

        try:
            await asyncio.sleep(MISS_TIMEOUT)
        except asyncio.CancelledError:
            return
        self._misses += 1
        print(f"[STT] AssemblyAI sin respuesta ({self._misses}/{MISS_LIMIT})", flush=True)
        if self._misses >= MISS_LIMIT:
            self._trigger("AssemblyAI dejó de transcribir")

    def _trigger(self, reason: str):
        if self._fallback:
            return
        self._fallback = True
        print(f"[STT] Fallback -> whisper.cpp local: {reason}", flush=True)
        self._whisper.activate()
