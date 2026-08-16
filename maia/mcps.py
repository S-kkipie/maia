"""Registro de MCPs locales configurables + defaults.

Maia puede tener MCPs externos (stdio/npx) además de sus tools in-process (voz, timers).
El registro vive en mcp_registry.json (editable por ti o por Maia con agregar_mcp).
"""
import json
import pathlib

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "mcp_registry.json"

# MCPs externos por defecto. Maia puede agregar más al registro.
DEFAULT_MCPS = {
    "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp@latest"]},
}


def load_registry() -> dict:
    if REGISTRY.exists():
        try:
            data = json.loads(REGISTRY.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return dict(DEFAULT_MCPS)


def save_registry(mcps: dict) -> None:
    REGISTRY.write_text(json.dumps(mcps, ensure_ascii=False, indent=2), encoding="utf-8")


def add_mcp(name: str, command: str, args: list) -> None:
    reg = load_registry()
    reg[name] = {"command": command, "args": args}
    save_registry(reg)


def allowed_tools_for(server_names) -> list:
    """Wildcards para permitir todas las tools de cada MCP."""
    return [f"mcp__{name}__*" for name in server_names]
