"""Computer use local para Maia: ojos (screenshots) y manos (mouse/teclado) en Windows.

MCP in-process (como voz/timers). Claude ve la pantalla y actúa sobre el escritorio,
no solo el navegador. Para que NO se pierda: casi toda acción devuelve una captura
nueva, así Claude siempre ve el resultado antes del siguiente paso.

Coordenadas: las capturas se reescalan a ~1280 de ancho para no gastar tokens. Claude
da coordenadas EN ESA captura y aquí las reescalamos a los píxeles reales de la pantalla.
"""
import base64
import io

import pyautogui
import pyperclip
from mss import mss
from PIL import Image

from claude_agent_sdk import create_sdk_mcp_server, tool

pyautogui.FAILSAFE = True  # mover el mouse a una esquina aborta (freno de emergencia)
pyautogui.PAUSE = 0.05

SHOT_WIDTH = 1280  # ancho al que reescalamos la captura enviada a Claude


def _capture(state: dict):
    """Captura la pantalla primaria, la reescala y actualiza el factor de escala."""
    with mss() as sct:
        mon = sct.monitors[1]  # monitor primario
        raw = sct.grab(mon)
        real_w, real_h = raw.width, raw.height
        img = Image.frombytes("RGB", (real_w, real_h), raw.rgb)
    tw = min(SHOT_WIDTH, real_w)
    th = int(real_h * tw / real_w)
    small = img.resize((tw, th), Image.LANCZOS)
    state["sx"] = real_w / tw
    state["sy"] = real_h / th
    state["real"] = (real_w, real_h)
    state["shot"] = (tw, th)
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode(), tw, th, real_w, real_h


def _shot_result(state: dict, note: str = ""):
    b64, tw, th, rw, rh = _capture(state)
    text = f"Captura {tw}x{th} (pantalla real {rw}x{rh}). Da coordenadas en {tw}x{th}."
    if note:
        text = note + " " + text
    return {"content": [
        {"type": "image", "data": b64, "mimeType": "image/png"},
        {"type": "text", "text": text},
    ]}


def _to_real(state: dict, x, y):
    return int(float(x) * state.get("sx", 1)), int(float(y) * state.get("sy", 1))


def make_computer_server():
    """MCP de computer use. Devuelve capturas tras cada acción para no perderse."""
    state = {"sx": 1.0, "sy": 1.0}

    @tool("screenshot", "Toma una captura de la pantalla para ver qué hay. Úsala SIEMPRE "
          "antes de actuar y cuando dudes dónde estás.", {})
    async def screenshot(a):
        return _shot_result(state)

    @tool("click", "Haz clic en (x, y) EN COORDENADAS DE LA ÚLTIMA CAPTURA. "
          "button: left|right|middle. clicks: 1 o 2 (doble clic). Devuelve una captura nueva.",
          {"x": float, "y": float, "button": str, "clicks": float})
    async def click(a):
        rx, ry = _to_real(state, a.get("x", 0), a.get("y", 0))
        button = str(a.get("button", "left")).lower() or "left"
        clicks = int(a.get("clicks", 1) or 1)
        pyautogui.click(rx, ry, clicks=clicks, button=button)
        return _shot_result(state, f"Clic {button} x{clicks} en real ({rx},{ry}).")

    @tool("type_text", "Escribe texto en el campo enfocado (pega vía portapapeles, soporta "
          "acentos y ñ). Haz clic primero en el campo. Devuelve una captura nueva.",
          {"text": str})
    async def type_text(a):
        text = str(a.get("text", ""))
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        return _shot_result(state, "Texto escrito.")

    @tool("press_keys", "Presiona una tecla o combinación. Ejemplos: 'enter', 'tab', 'esc', "
          "'win', 'ctrl+c', 'ctrl+v', 'alt+tab', 'ctrl+shift+t'. Devuelve una captura nueva.",
          {"keys": str})
    async def press_keys(a):
        combo = str(a.get("keys", "")).strip().lower()
        if not combo:
            return {"content": [{"type": "text", "text": "Falta keys."}], "is_error": True}
        parts = [p.strip() for p in combo.replace(" ", "").split("+") if p.strip()]
        if len(parts) > 1:
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(parts[0])
        return _shot_result(state, f"Tecla(s) {combo}.")

    @tool("scroll", "Desplaza la rueda. amount positivo sube, negativo baja (ej. -500). "
          "Devuelve una captura nueva.", {"amount": float})
    async def scroll(a):
        pyautogui.scroll(int(a.get("amount", 0)))
        return _shot_result(state, "Scroll hecho.")

    @tool("move", "Mueve el mouse a (x, y) EN COORDENADAS DE LA ÚLTIMA CAPTURA, sin hacer clic.",
          {"x": float, "y": float})
    async def move(a):
        rx, ry = _to_real(state, a.get("x", 0), a.get("y", 0))
        pyautogui.moveTo(rx, ry)
        return {"content": [{"type": "text", "text": f"Mouse en real ({rx},{ry})."}]}

    @tool("drag", "Arrastra desde (x1,y1) hasta (x2,y2), coordenadas de la última captura. "
          "Devuelve una captura nueva.",
          {"x1": float, "y1": float, "x2": float, "y2": float})
    async def drag(a):
        x1, y1 = _to_real(state, a.get("x1", 0), a.get("y1", 0))
        x2, y2 = _to_real(state, a.get("x2", 0), a.get("y2", 0))
        pyautogui.moveTo(x1, y1)
        pyautogui.dragTo(x2, y2, duration=0.3, button="left")
        return _shot_result(state, f"Arrastre ({x1},{y1})->({x2},{y2}).")

    return create_sdk_mcp_server(
        name="pc", version="1.0.0",
        tools=[screenshot, click, type_text, press_keys, scroll, move, drag],
    )
