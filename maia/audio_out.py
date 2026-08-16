"""Resampleo de salida propio: Fish (24k) -> 48k ANTES del transport.

El resample interno de LocalAudioTransport de Pipecat 1.7.0 no aplica bien el
rate al reproducir (produce audio acelerado/agudo, tipo chipmunk). Resampleando
los TTSAudioRawFrame al rate nativo del device ANTES de transport.output(), el
transport sólo hace passthrough y reproduce correcto.
"""
from pipecat.audio.resamplers.soxr_resampler import SOXRAudioResampler
from pipecat.frames.frames import TTSAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

OUT_SR = 48000  # rate nativo del device de salida (Realtek WASAPI)


class ResampleOut(FrameProcessor):
    """Resamplea cada TTSAudioRawFrame a OUT_SR con soxr (alta calidad)."""

    def __init__(self, rate: int = OUT_SR, **kwargs):
        super().__init__(**kwargs)
        self._rate = rate
        self._resampler = SOXRAudioResampler()

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame) and frame.sample_rate != self._rate:
            audio = await self._resampler.resample(frame.audio, frame.sample_rate, self._rate)
            frame = TTSAudioRawFrame(
                audio=audio, sample_rate=self._rate, num_channels=frame.num_channels
            )
        await self.push_frame(frame, direction)
