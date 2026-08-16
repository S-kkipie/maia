"""Fallback de STT: AssemblyAI (nube) -> whisper.cpp (local), con recuperación.

Va DESPUÉS de los dos STT en el pipeline:
    input(vad) -> AssemblyAI -> TagAAI -> WhisperCppSTT(standby) -> STTFallbackGate -> brain

- TagAAI marca las transcripciones de AssemblyAI. En el gate, lo NO marcado es whisper.
- Normal: reenvía AssemblyAI, descarta whisper (que está en standby).
- Señal de "AssemblyAI VIVO" en tiempo real = CUALQUIER frame suyo, interim (parcial)
  o final. Mientras lleguen interims, NO hay fallback (aunque hables minutos y el final
  tarde). Esto evita el fallback falso.
- Cae a whisper solo si: (1) ErrorFrame de AssemblyAI, o (2) hiciste MISS_LIMIT turnos
  completos sin que AssemblyAI emitiera absolutamente NADA (ni interims) — señal real de
  que murió.
- RECUPERACIÓN: si ya cayó a whisper y AssemblyAI vuelve a emitir, regresa solo a la nube.
"""
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

MISS_TIMEOUT = 8.0  # s tras dejar de hablar sin NINGÚN frame de AssemblyAI = 1 miss
MISS_LIMIT = 3      # misses seguidos antes de caer a whisper (conservador)


class TagAAI(FrameProcessor):
    """Marca las transcripciones que vienen de AssemblyAI (para distinguirlas de whisper)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
            frame._maia_src = "aai"
        await self.push_frame(frame, direction)


class STTFallbackGate(FrameProcessor):
    """Enruta transcripciones y decide cuándo caer a whisper y cuándo volver."""

    def __init__(self, whisper, **kwargs):
        super().__init__(**kwargs)
        self._whisper = whisper  # WhisperCppSTT en standby
        self._fallback = False
        self._misses = 0
        self._miss_task = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, ErrorFrame):
            self._to_whisper("AssemblyAI reportó error irrecuperable")
            await self.push_frame(frame, direction)  # no la tragamos (es no-fatal)
            return

        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._cancel_miss_timer()  # turno nuevo: no penalices lo anterior
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            if not self._fallback:
                self._arm_miss_timer()  # vigila si AssemblyAI no dio NADA en este turno
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
            src = getattr(frame, "_maia_src", "whisper")
            if src == "aai":
                # CUALQUIER frame de AssemblyAI (interim o final) => está VIVO ahora mismo.
                self._misses = 0
                self._cancel_miss_timer()
                if self._fallback:
                    self._to_aai("AssemblyAI volvió a responder")  # recuperación
                await self.push_frame(frame, direction)
            else:  # whisper
                if self._fallback:
                    await self.push_frame(frame, direction)
                # en modo nube whisper está en standby y no emite; si emitiera, se ignora
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
            self._to_whisper("AssemblyAI dejó de transcribir")

    def _to_whisper(self, reason: str):
        if self._fallback:
            return
        self._fallback = True
        print(f"[STT] Fallback -> whisper.cpp local: {reason}", flush=True)
        self._whisper.activate()

    def _to_aai(self, reason: str):
        if not self._fallback:
            return
        self._fallback = False
        self._misses = 0
        print(f"[STT] Recuperado -> AssemblyAI (nube): {reason}", flush=True)
        self._whisper.deactivate()
