import asyncio

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.utils.string import match_endofsentence

from maia.voices import VOICES

SYSTEM_PROMPT = (
    "Eres Maia, asistente de voz mujer en español, cálida, natural y RESUELTA. "
    "Tu usuario es Adrián Issac (correo issacysofia@gmail.com); trátalo por su nombre cuando sea natural. "
    "Es una conversación HABLADA: sé breve y directo. "
    "REGLA CLAVE: NO hagas preguntas aclaratorias salvo que sea imprescindible. Si algo es "
    "ambiguo, ASUME lo más razonable y ACTÚA de inmediato (usa tus herramientas, busca, resuelve). "
    "El usuario quiere resultados y decisión, no un interrogatorio. Nunca respondas con una pregunta "
    "cuando puedes simplemente hacer la tarea. "
    "Responde con lo esencial. Otra capa reescribirá tu respuesta para hablarla, así que no te "
    "preocupes por el formato, pero sé conciso. No incluyas URLs ni fuentes con enlaces. "
    "Puedes cambiar tu voz entre 'chica' y 'joven' con set_voice si te lo piden. "
    "Puedes poner recordatorios/timers con set_timer (segundos + mensaje); convierte minutos a segundos. "
    "Tienes navegador (Playwright) además de Bash y web. Si el usuario te pide una capacidad que no tienes, "
    "puedes agregarte un MCP nuevo con agregar_mcp (aplica cuando te reinicien)."
)

HEARTBEAT_EVERY = 5.0  # s: aviso de progreso (dinámico, generado por Gemini) si Claude tarda


def make_timer_server(fire_cb):
    """Tool de timers/recordatorios in-process. fire_cb(message) se llama al vencer."""
    _tasks = set()

    @tool("set_timer", "Programa un recordatorio hablado dentro de N segundos.",
          {"seconds": float, "message": str})
    async def set_timer(args):
        secs = float(args.get("seconds", 0))
        msg = str(args.get("message", "")).strip() or "tu recordatorio"

        async def _fire():
            await asyncio.sleep(secs)
            await fire_cb(msg)

        t = asyncio.create_task(_fire())
        _tasks.add(t)
        t.add_done_callback(_tasks.discard)
        return {"content": [{"type": "text", "text": f"Listo, te aviso en {int(secs)} segundos: {msg}"}]}

    return create_sdk_mcp_server(name="timers", version="1.0.0", tools=[set_timer])


def make_config_server():
    """Tool para que Maia se agregue MCPs nuevos (auto-extensión). Aplica al reiniciar."""
    import shlex

    @tool(
        "agregar_mcp",
        "Agrega un servidor MCP local nuevo a Maia. nombre: identificador corto; "
        "comando: ejecutable (por ejemplo 'npx'); args: argumentos separados por espacios.",
        {"nombre": str, "comando": str, "args": str},
    )
    async def agregar_mcp(a):
        from maia import mcps

        name = str(a.get("nombre", "")).strip()
        cmd = str(a.get("comando", "")).strip()
        arglist = shlex.split(str(a.get("args", "")))
        if not name or not cmd:
            return {"content": [{"type": "text", "text": "Necesito al menos nombre y comando."}],
                    "is_error": True}
        mcps.add_mcp(name, cmd, arglist)
        return {"content": [{"type": "text",
                             "text": f"Listo, agregué el MCP {name}. Lo tendré disponible la próxima vez que me reinicies."}]}

    return create_sdk_mcp_server(name="config", version="1.0.0", tools=[agregar_mcp])


def make_voice_server(switch_cb):
    """Tool para que Maia cambie su voz en vivo. switch_cb(reference_id) -> None."""

    @tool("set_voice", "Cambia la voz de Maia. El parámetro voice debe ser 'chica' o 'joven'.",
          {"voice": str})
    async def set_voice(args):
        name = str(args.get("voice", "")).strip().lower()
        if name not in VOICES:
            return {"content": [{"type": "text",
                                 "text": f"Voz no válida. Opciones: {', '.join(VOICES)}."}],
                    "is_error": True}
        await switch_cb(VOICES[name])
        return {"content": [{"type": "text", "text": f"Voz cambiada a {name}."}]}

    return create_sdk_mcp_server(name="voz", version="1.0.0", tools=[set_voice])


def _delta_text(message) -> str:
    if isinstance(message, StreamEvent):
        ev = message.event
        if ev.get("type") == "content_block_delta":
            d = ev.get("delta", {})
            if d.get("type") == "text_delta":
                return d.get("text", "")
    return ""


def _short(value, n: int = 160) -> str:
    """Compacta el input/output de una tool a una línea corta para el log."""
    import json

    try:
        s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    except Exception:
        s = str(value)
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "..."


def _log_tools(message) -> None:
    """Muestra en consola qué herramientas ejecuta Claude y sus resultados."""
    if isinstance(message, AssistantMessage):
        for b in message.content:
            if isinstance(b, ToolUseBlock):
                name = b.name.replace("mcp__", "").replace("__", ".")
                print(f"[TOOL >] {name}  {_short(b.input)}", flush=True)
    elif isinstance(message, UserMessage):
        content = getattr(message, "content", None)
        if isinstance(content, list):
            for b in content:
                if isinstance(b, ToolResultBlock):
                    mark = "ERR" if b.is_error else "OK"
                    print(f"[TOOL {mark}] {_short(b.content)}", flush=True)


class MaiaBrain(FrameProcessor):
    def __init__(self, claude: ClaudeSDKClient, reflex=None, **kwargs):
        super().__init__(**kwargs)
        self._claude = claude
        self._reflex = reflex  # capa Gemini rápida; si None, todo va a Claude
        self._gen_task = None
        self._claude_running = False   # True mientras Claude procesa un turno
        self._interrupt_task = None    # interrupt() en 2do plano (nunca bloquea el pipeline)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            await self._abort()
            await self.push_frame(frame, direction)
        elif isinstance(frame, TranscriptionFrame) and frame.text.strip():
            print(f"[TÚ] {frame.text}", flush=True)
            await self._abort()
            self._gen_task = self.create_task(self._handle_turn(frame.text))
        else:
            await self.push_frame(frame, direction)

    async def _abort(self):
        was_running = self._claude_running
        # Cancela la generación local en curso (acotado y rápido).
        if self._gen_task:
            await self.cancel_task(self._gen_task)
            self._gen_task = None
        # Interrumpe a Claude SÓLO si había un turno activo, y SIEMPRE en segundo
        # plano: interrupt() espera el ack del CLI hasta 60s, y hacerlo aquí en
        # medio de una tool larga (p.ej. navegador) congelaba TODO el pipeline
        # (dejaba de transcribir y de responder). Nunca lo esperamos en el hilo
        # de frames.
        if was_running and self._interrupt_task is None:
            self._interrupt_task = self.create_task(self._interrupt_claude())

    async def _interrupt_claude(self):
        try:
            await asyncio.wait_for(self._claude.interrupt(), timeout=5.0)
        except Exception:
            pass
        finally:
            self._interrupt_task = None

    async def _handle_turn(self, user_text: str):
        needs_claude = True
        if self._reflex is not None:
            # Reflejo instantáneo (~0.5s): responde directo o da un relleno + delega.
            reply, needs_claude = await self._reflex.respond(user_text)
            if reply.strip():
                await self.push_frame(TTSSpeakFrame(reply))
        if needs_claude:
            await self._run_claude(user_text)

    async def _run_claude(self, user_text: str):
        # Recolecta la respuesta completa de Claude (con heartbeat basado en su progreso real),
        # luego Gemini la humaniza (corta, sin URLs/markdown/siglas) y la hablamos.
        done = {"v": False}
        progress = {"buf": ""}  # progreso parcial de Claude, para avisos contextuales

        async def heartbeat():
            try:
                while not done["v"]:
                    await asyncio.sleep(HEARTBEAT_EVERY)
                    if done["v"]:
                        break
                    phrase = (
                        await self._reflex.progress_update(user_text, progress["buf"])
                        if self._reflex is not None
                        else "Sigo en ello."
                    )
                    if not done["v"]:
                        await self.push_frame(TTSSpeakFrame(phrase))
            except asyncio.CancelledError:
                pass

        hb = self.create_task(heartbeat())
        buf = ""
        pending = ""  # para loguear a Claude en tiempo real, frase por frase
        claude_failed = False
        self._claude_running = True
        try:
            # Si quedó un interrupt del turno anterior en vuelo, deja que aterrice
            # antes de lanzar esta query (evita solapar turnos en el CLI).
            if self._interrupt_task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(self._interrupt_task), timeout=5.0)
                except Exception:
                    pass
            await self._claude.query(user_text)
            async for message in self._claude.receive_response():
                _log_tools(message)  # [TOOL→]/[TOOL✓]: qué ejecuta Claude
                delta = _delta_text(message)
                if delta:
                    buf += delta
                    progress["buf"] = buf  # expone el progreso al heartbeat
                    pending += delta
                    idx = match_endofsentence(pending)
                    while idx:
                        frag = pending[:idx].strip()
                        if frag:
                            print(f"[CLAUDE] {frag}", flush=True)
                        pending = pending[idx:]
                        idx = match_endofsentence(pending)
                if isinstance(message, ResultMessage):
                    break
        except asyncio.CancelledError:
            raise  # turno cancelado por barge-in: propaga limpio (no hables)
        except Exception as e:  # Claude no disponible -> fallback a Gemini
            print(f"[FALLBACK] Claude no disponible: {e}", flush=True)
            claude_failed = True
        finally:
            done["v"] = True
            self._claude_running = False
            await self.cancel_task(hb)
        if pending.strip():
            print(f"[CLAUDE] {pending.strip()}", flush=True)

        if claude_failed:
            spoken = (
                await self._reflex.full_answer(user_text)
                if self._reflex is not None
                else "Perdona, ahora mismo no puedo responder."
            )
        else:
            raw = buf.strip()
            if not raw:
                return
            spoken = await self._reflex.humanize(raw) if self._reflex is not None else raw
        rest = spoken
        idx = match_endofsentence(rest)
        while idx:
            frag = rest[:idx].strip()
            if frag:
                await self.push_frame(TTSSpeakFrame(frag))
            rest = rest[idx:]
            idx = match_endofsentence(rest)
        if rest.strip():
            await self.push_frame(TTSSpeakFrame(rest.strip()))


def build_claude_options(mcp_servers=None, allowed_tools=None) -> ClaudeAgentOptions:
    kwargs = dict(
        model="claude-haiku-4-5-20251001",
        include_partial_messages=True,
        permission_mode="bypassPermissions",
        system_prompt=SYSTEM_PROMPT,
        strict_mcp_config=True,   # SOLO nuestros mcp_servers; ignora connectors claude.ai + config global
        setting_sources=[],       # modo aislado: no hereda ~/.claude ni proyecto
    )
    if mcp_servers:
        kwargs["mcp_servers"] = mcp_servers
    if allowed_tools:
        kwargs["allowed_tools"] = allowed_tools
    return ClaudeAgentOptions(**kwargs)
