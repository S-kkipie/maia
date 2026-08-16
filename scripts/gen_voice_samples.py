"""Genera muestras MP3 de voces femeninas de Fish para elegir por oído. Uso: uv run python scripts/gen_voice_samples.py"""
import json
import os
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "maia"))
from config import _require  # noqa: E402  (reusa la carga de .env + guard)

KEY = _require("FISHAUDIO_API_KEY")
OUT = pathlib.Path(__file__).resolve().parents[1] / "voces_muestra"
OUT.mkdir(exist_ok=True)

TEXT = ("Hola, soy Maia, tu asistente de voz. Puedo ayudarte con tu dia, poner "
        "recordatorios y responder tus preguntas. Cuentame, en que te echo una mano?")

VOCES = {
    # Destacadas por la comunidad (búsqueda web / páginas de Fish)
    "1_MuyReal_NoArtificial": "edbe850c6b7d40f195edd8c043b18748",
    "2_VozFem_EspLatino": "c32a6108bd0741a0824a9a5a31cedd00",
    "3_VozFem_Espanola": "2a9fb1586f6347be9099f3ac983ef362",
    "4_VozFem_Joven": "86c10378b06a4858abf9bb4553aaa89c",
    # Top del ranking por API (naturales para asistente)
    "5_Chica": "35929683c49c4ec0bf779dc07d22620b",
    "6_Reze": "3f56a67897df4d218eac6494ff88337f",
}


def synth(name, ref_id):
    body = json.dumps({
        "text": TEXT, "reference_id": ref_id, "format": "mp3", "latency": "normal",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.fish.audio/v1/tts", data=body, method="POST",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
                 "model": "s2.1-pro-free"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        path = OUT / f"{name}.mp3"
        path.write_bytes(data)
        print(f"OK  {name:16} {len(data):>7} bytes -> {path}")
    except Exception as e:
        print(f"ERR {name:16} {e}")


if __name__ == "__main__":
    for name, ref in VOCES.items():
        synth(name, ref)
    print(f"\nAbre la carpeta y reproduce: {OUT}")
