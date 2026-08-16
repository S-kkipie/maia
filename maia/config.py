import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

if os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("ANTHROPIC_API_KEY seteada: Maia usa la suscripción. Quítala.")


def _require(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"Falta variable de entorno: {name}")
    return v


def _pick_wasapi_device(want_input: bool, hint: str | None) -> int:
    """Elige un device WASAPI (input u output). hint = substring del nombre o índice."""
    import pyaudio

    pa = pyaudio.PyAudio()
    try:
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        candidates = []
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            if d["hostApi"] != wasapi:
                continue
            chans = d["maxInputChannels"] if want_input else d["maxOutputChannels"]
            if chans > 0:
                candidates.append((i, d["name"]))
        if hint and hint.strip():
            if hint.strip().isdigit():
                return int(hint.strip())
            for i, name in candidates:
                if hint.lower() in name.lower():
                    return i
            sys.exit(f"No hay device WASAPI que matchee '{hint}'. Opciones: {candidates}")
        key = "defaultInputDevice" if want_input else "defaultOutputDevice"
        idx = int(pa.get_host_api_info_by_type(pyaudio.paWASAPI).get(key, -1))
        if idx < 0:
            sys.exit(f"Sin device WASAPI por defecto ({'in' if want_input else 'out'}). Opciones: {candidates}")
        return idx
    finally:
        pa.terminate()


@dataclass
class Config:
    assemblyai_key: str
    fish_key: str
    fish_reference_id: str | None
    input_device_index: int
    output_device_index: int
    picovoice_key: str | None
    wake_ppn: str | None
    gemini_key: str | None
    reflex_model: str
    stt_engine: str      # 'auto' (AssemblyAI + fallback whisper) | 'assemblyai' | 'whisper'
    whisper_model: str   # modelo ggml: base | small | medium ...


def load() -> Config:
    return Config(
        assemblyai_key=_require("ASSEMBLYAI_API_KEY"),
        fish_key=_require("FISHAUDIO_API_KEY"),
        fish_reference_id=os.getenv("FISHAUDIO_REFERENCE_ID") or None,
        input_device_index=_pick_wasapi_device(True, os.getenv("MAIA_INPUT_DEVICE")),
        output_device_index=_pick_wasapi_device(False, os.getenv("MAIA_OUTPUT_DEVICE")),
        picovoice_key=os.getenv("PICOVOICE_ACCESS_KEY") or None,
        wake_ppn=os.getenv("MAIA_WAKE_PPN") or None,
        gemini_key=os.getenv("GEMINI_API_KEY") or None,
        reflex_model=os.getenv("MAIA_REFLEX_MODEL") or "gemini-2.5-flash-lite",
        stt_engine=(os.getenv("MAIA_STT") or "auto").strip().lower(),
        whisper_model=os.getenv("MAIA_WHISPER_MODEL") or "medium-q5_0",
    )


def list_devices() -> None:
    """Utilidad: imprime devices WASAPI in/out para elegir MAIA_INPUT/OUTPUT_DEVICE."""
    import pyaudio

    pa = pyaudio.PyAudio()
    wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if d["hostApi"] == wasapi:
            print(f"[{i}] {d['name']} | in={d['maxInputChannels']} out={d['maxOutputChannels']} "
                  f"| {int(d['defaultSampleRate'])}Hz")
    pa.terminate()


if __name__ == "__main__":
    list_devices()
