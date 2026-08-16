"""VAD Silero que acepta el audio 48k del pipeline resampleándolo a 16k.

Silero sólo trabaja a 16000/8000 Hz, pero nuestro transport corre a 48000 (rate
nativo del device WASAPI). El VADController no resamplea, así que este wrapper
resamplea cada bloque 48k->16k antes de analizarlo. Necesario para segmentar el
STT local de whisper.cpp.
"""
from pipecat.audio.resamplers.soxr_resampler import SOXRAudioResampler
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams


class Silero16k(SileroVADAnalyzer):
    """SileroVAD forzado a 16k, resampleando el audio de entrada (p.ej. 48k)."""

    def __init__(self, input_rate: int, params: VADParams | None = None):
        super().__init__(sample_rate=16000, params=params)
        self._input_rate = input_rate
        self._rs = SOXRAudioResampler()

    def set_sample_rate(self, sample_rate: int):
        # El pipeline pasa 48000; lo ignoramos y mantenemos el modelo a 16000.
        super().set_sample_rate(16000)

    async def analyze_audio(self, buffer: bytes):
        if self._input_rate != 16000:
            buffer = await self._rs.resample(buffer, self._input_rate, 16000)
        return await super().analyze_audio(buffer)
