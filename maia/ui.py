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


def run_window() -> None:
    """Abre la ventana (bloquea el hilo principal). Requiere pywebview + WebView2."""
    import webview

    html = (pathlib.Path(__file__).parent / "ui" / "index.html").read_text(encoding="utf-8")
    webview.create_window("Maia", html=html, width=1120, height=740,
                          background_color="#0e1016", min_size=(820, 560))
    webview.start()
