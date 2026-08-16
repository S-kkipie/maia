"""UI opcional de Maia: ventana ligera (pywebview / WebView2) con eventos en vivo.

No es Electron: usa el WebView2 nativo de Windows (poca RAM, ya instalado). El
pipeline (en un hilo aparte) emite eventos por un WebSocket local; la página los
pinta: transcripciones, salida de Claude en vivo y las herramientas que ejecuta.
"""
import asyncio
import json
import pathlib

import websockets

_clients: set = set()
_enabled = False
_state = {"meta": None, "status": "listening"}  # se reenvía a clientes nuevos


def enable() -> None:
    global _enabled
    _enabled = True


def enabled() -> bool:
    return _enabled


async def _handler(ws):
    _clients.add(ws)
    try:
        # reenvía el estado actual al cliente recién conectado
        if _state["meta"]:
            await ws.send(json.dumps(_state["meta"]))
        await ws.send(json.dumps({"kind": "status", "state": _state["status"]}))
        async for _ in ws:  # no esperamos mensajes del cliente; mantenemos abierto
            pass
    except Exception:
        pass
    finally:
        _clients.discard(ws)


async def start_server(port: int = 8760) -> None:
    await websockets.serve(_handler, "127.0.0.1", port)


async def emit(kind: str, **fields) -> None:
    """Envía un evento a la UI. No-op si la UI está apagada. Nunca rompe el pipeline."""
    if not _enabled:
        return
    if kind == "meta":
        _state["meta"] = {"kind": "meta", **fields}
    elif kind == "status":
        _state["status"] = fields.get("state", "listening")
    if not _clients:
        return
    msg = json.dumps({"kind": kind, **fields})
    for ws in list(_clients):
        try:
            await ws.send(msg)
        except Exception:
            _clients.discard(ws)


def open_ui() -> None:
    """Abre la página en el navegador (se conecta al WebSocket para los eventos).

    Navegador y no ventana Electron/pywebview a propósito: así el pipeline (audio +
    el subproceso del CLI de Claude) se queda en el HILO PRINCIPAL, único lugar donde
    asyncio puede lanzar subprocesos en Windows. La página pesa lo de una pestaña.
    """
    import webbrowser

    page = pathlib.Path(__file__).parent / "ui" / "index.html"
    webbrowser.open(page.as_uri())
