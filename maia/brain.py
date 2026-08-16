import asyncio

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    create_sdk_mcp_server,
    tool,
)
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.utils.string import match_endofsentence

from maia.voices import VOICES

SYSTEM_PROMPT = (
    "Eres Maia, una asistente de voz mujer, en español. Hablas de forma cálida, "
    "cercana y natural, como una persona real conversando, no como un robot. "
    "Responde SIEMPRE en español, breve y para ser escuchada en voz alta: frases "
    "cortas, sin markdown, sin listas ni emojis. Si no sabes algo, dilo con naturalidad. "
    "Tuteas al usuario y suenas amable y con un toque de personalidad. "
    "Puedes cambiar tu propia voz entre 'chica' y 'joven' con la herramienta set_voice "
    "cuando el usuario te lo pida (por ejemplo: 'cambia a la voz joven')."
)


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


class MaiaBrain(FrameProcessor):
    def __init__(self, claude: ClaudeSDKClient, **kwargs):
        super().__init__(**kwargs)
        self._claude = claude
        self._gen_task = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            await self._abort()
            await self.push_frame(frame, direction)
        elif isinstance(frame, TranscriptionFrame) and frame.text.strip():
            await self._abort()
            await self.push_frame(TTSSpeakFrame("Mmm, dame un segundo."))  # relleno inmediato
            self._gen_task = self.create_task(self._run_brain(frame.text))
        else:
            await self.push_frame(frame, direction)

    async def _abort(self):
        if self._gen_task:
            await self.cancel_task(self._gen_task)
            self._gen_task = None
        try:
            await self._claude.interrupt()
        except Exception:
            pass

    async def _run_brain(self, user_text: str):
        await self.push_frame(LLMFullResponseStartFrame())
        buf = ""
        await self._claude.query(user_text)
        async for message in self._claude.receive_response():
            buf += _delta_text(message)
            idx = match_endofsentence(buf)
            while idx:
                await self.push_frame(LLMTextFrame(buf[:idx]))
                buf = buf[idx:]
                idx = match_endofsentence(buf)
            if isinstance(message, ResultMessage):
                break
        if buf.strip():
            await self.push_frame(LLMTextFrame(buf))
        await self.push_frame(LLMFullResponseEndFrame())


def build_claude_options(mcp_servers=None, allowed_tools=None) -> ClaudeAgentOptions:
    kwargs = dict(
        model="claude-haiku-4-5-20251001",
        include_partial_messages=True,
        permission_mode="bypassPermissions",
        system_prompt=SYSTEM_PROMPT,
    )
    if mcp_servers:
        kwargs["mcp_servers"] = mcp_servers
    if allowed_tools:
        kwargs["allowed_tools"] = allowed_tools
    return ClaudeAgentOptions(**kwargs)
