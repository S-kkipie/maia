"""Limpiador de texto para voz + logging de la conversación.

Quita marcas de markdown que Maia narraría literal (**, [ ], `, #, listas), y
loguea en consola lo que Maia va a decir ([MAIA]).
"""
import re

from pipecat.frames.frames import TextFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")       # [texto](url) -> texto
_PAREN_URL = re.compile(r"\s*\(\s*https?://[^)]+\)")  # texto(https://...) -> texto
_URL = re.compile(r"https?://\S+")                  # url suelta -> fuera
_MD = re.compile(r"(\*\*|\*|__|_|`+|~~|#+\s*|>+\s*)")
_BRACKETS = re.compile(r"[\[\]]")
_BULLET = re.compile(r"(?m)^\s*[-•*]\s+")


def clean_for_speech(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = _PAREN_URL.sub("", text)
    text = _URL.sub("", text)
    text = _BULLET.sub("", text)
    text = _MD.sub("", text)
    text = _BRACKETS.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


class SpeechCleaner(FrameProcessor):
    """Limpia el texto de los frames de voz antes del TTS y loguea [MAIA]."""

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, (TextFrame, TTSSpeakFrame)) and getattr(frame, "text", None):
            cleaned = clean_for_speech(frame.text)
            frame.text = cleaned
            if cleaned.strip():
                print(f"[MAIA] {cleaned}", flush=True)
        await self.push_frame(frame, direction)
