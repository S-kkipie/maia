"""Memoria persistente de Maia entre conversaciones.

Maia corre aislada (setting_sources=[]), así que no hereda la memoria de Claude Code.
Aquí guardamos hechos del usuario en un archivo markdown que se CARGA en el system
prompt al arrancar (siempre en contexto) y que Maia amplía con la tool 'recordar'.
"""
import datetime
import pathlib

from claude_agent_sdk import create_sdk_mcp_server, tool

MEMORY_FILE = pathlib.Path(__file__).resolve().parents[1] / "maia_memory.md"


def load_memory() -> str:
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text(encoding="utf-8").strip()
    return ""


def append_memory(nota: str) -> None:
    nota = " ".join(nota.split()).strip()
    if not nota:
        return
    today = datetime.date.today().isoformat()
    with MEMORY_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- {nota}  ({today})\n")


def forget(texto: str) -> int:
    """Borra las líneas de memoria que contengan `texto`. Devuelve cuántas quitó."""
    if not MEMORY_FILE.exists():
        return 0
    lines = MEMORY_FILE.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if texto.lower() not in ln.lower()]
    MEMORY_FILE.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return len(lines) - len(kept)


def make_memory_server():
    """MCP local de memoria: recordar / ver_memoria / olvidar."""

    @tool("recordar", "Guarda un dato importante del usuario en tu memoria persistente "
          "(preferencias, nombres, gustos, rutinas, decisiones) para recordarlo en futuras "
          "conversaciones. nota: el hecho a recordar, en una frase corta.", {"nota": str})
    async def recordar(a):
        nota = str(a.get("nota", "")).strip()
        if not nota:
            return {"content": [{"type": "text", "text": "¿Qué quieres que recuerde?"}],
                    "is_error": True}
        append_memory(nota)
        return {"content": [{"type": "text", "text": f"Guardado en memoria: {nota}"}]}

    @tool("ver_memoria", "Muestra todo lo que tienes guardado en la memoria persistente.", {})
    async def ver_memoria(a):
        mem = load_memory() or "(memoria vacía)"
        return {"content": [{"type": "text", "text": mem}]}

    @tool("olvidar", "Borra de la memoria las notas que contengan cierto texto.",
          {"texto": str})
    async def olvidar(a):
        texto = str(a.get("texto", "")).strip()
        if not texto:
            return {"content": [{"type": "text", "text": "¿Qué quieres que olvide?"}],
                    "is_error": True}
        n = forget(texto)
        return {"content": [{"type": "text", "text": f"Olvidé {n} nota(s) sobre '{texto}'."}]}

    return create_sdk_mcp_server(name="memoria", version="1.0.0",
                                 tools=[recordar, ver_memoria, olvidar])
