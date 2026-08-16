import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Carga .env desde la raíz del repo (dos niveles arriba de este archivo)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

if os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit(
        "ANTHROPIC_API_KEY está seteada. Fase 0 exige auth por suscripción; "
        "quítala del entorno y de .env."
    )


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Falta variable de entorno requerida: {name}")
    return value
