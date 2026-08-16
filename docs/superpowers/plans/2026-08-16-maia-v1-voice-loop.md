# Maia v1 — Loop de Voz Conversacional — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir Maia v1: un asistente de voz en español que despierta con la wake word "Maia", conversa usando Claude Code como cerebro (cliente persistente), habla con baja latencia percibida (relleno hablado), se deja interrumpir (barge-in), y puede poner timers con confirmación por voz.

**Architecture:** Un proceso Python asyncio. La wake word (Porcupine) escucha en un stream propio a 16 kHz; al detectar "Maia" arranca un pipeline de Pipecat 1.7.0: `mic (WASAPI 48k, device explícito) → AssemblyAI STT (español, turnos server-side) → MaiaBrain (FrameProcessor con ClaudeSDKClient persistente) → Fish TTS (44.1k→48k) → speaker`. El cerebro autentica por la suscripción (sin API key), expone un tool de timers in-process, y un hook `PreToolUse` verbaliza la confirmación antes de acciones que cambian estado.

**Tech Stack:** Python 3.12 (uv), `pipecat-ai[local,assemblyai,fish,silero]==1.7.0`, `claude-agent-sdk` 0.2.139, `pvporcupine`+`pvrecorder` (wake word), Fish Audio `s2.1-pro-free` (TTS), AssemblyAI `universal-3-5-pro` (STT), PyAudio/WASAPI.

**Spec:** `docs/superpowers/specs/2026-08-15-maia-voice-assistant-design.md` (diseño) + `spikes/fase0/FINDINGS.md` (hallazgos de Fase 0, autoridad sobre valores concretos).

## Global Constraints

Aplican a TODAS las tareas. Valores exactos, verificados en Fase 0.

- **Plataforma:** Windows nativo. Python **3.12**. Gestor **`uv`**. Pinnear **`pipecat-ai==1.7.0`**.
- **Auth cerebro:** suscripción vía `~/.claude/.credentials.json`. **Prohibido** `ANTHROPIC_API_KEY` en entorno/.env. Modelo default `claude-haiku-4-5-20251001`, `include_partial_messages=True`, `permission_mode="bypassPermissions"` (el gate real es el hook `PreToolUse`).
- **Audio:** transport a **48000 Hz** con `input_device_index`/`output_device_index` **explícitos** (el default mandó el audio al device equivocado en Fase 0). Consola: **`PYTHONUTF8=1`**.
- **STT:** `AssemblyAISTTService(sample_rate=48000, vad_force_turn_endpoint=False, settings=Settings(model="universal-3-5-pro", language_codes=[Language.ES]))`. Turnos + barge-in server-side (sin VAD local).
- **TTS:** `FishAudioTTSService(sample_rate=44100, settings=Settings(model="s2.1-pro-free", voice=<reference_id ES>, latency="balanced"))`. Fish **no** acepta 48000 en pcm (máx 44100); el output transport a 48000 resamplea. Fallback documentado: ElevenLabs (`eleven_flash_v2_5`, sample_rate=48000).
- **Wake word:** `pvporcupine` con un `.ppn` custom "Maia" entrenado para **Windows** en Picovoice Console; capturado por `pvrecorder` a `porcupine.frame_length`/`porcupine.sample_rate` (16k) **sin** pinear device index.
- **MCP:** solo local/in-process. v1 tool = **timers** (`@tool` + `create_sdk_mcp_server`). Nada de connectors claude.ai.
- **Idioma:** español en prompts, TTS y mensajes.
- **Latencia:** cold-start del SDK ~19 s → el `ClaudeSDKClient` se abre UNA vez y se mantiene warm. TTFA de respuesta warm ~2.7 s → enmascarar con **relleno hablado** inmediato.

**Estructura de archivos** (paquete `maia/` en la raíz; `pyproject.toml` está en modo `[tool.uv] package = false`, se corre con `uv run python -m maia.main`):
- `maia/__init__.py` — vacío.
- `maia/config.py` — carga `.env`, guard anti-API-key, selección de devices de audio.
- `maia/services.py` — construye STT (AssemblyAI) y TTS (Fish/ElevenLabs) desde config.
- `maia/brain.py` — `MaiaBrain` FrameProcessor + setup del `ClaudeSDKClient` + tool de timers + hook de gate.
- `maia/wake.py` — gate de wake word Porcupine.
- `maia/main.py` — entrypoint: wake → pipeline → loop.

**Precondiciones manuales:**
- `.env` con `ASSEMBLYAI_API_KEY`, `FISHAUDIO_API_KEY`, `FISHAUDIO_REFERENCE_ID` (ya está en Fase 0). Añadir `PICOVOICE_ACCESS_KEY` (de Picovoice Console) y `MAIA_WAKE_PPN` (ruta al `.ppn`). Opcional `MAIA_INPUT_DEVICE`/`MAIA_OUTPUT_DEVICE` (índices o substring del nombre).
- Entrenar el `.ppn` "Maia" (Windows) en console.picovoice.ai (necesario para M3, no antes).

---

### Task 1 (M1): Config + selección de device + loop de eco (mic → STT → TTS)

**Meta demostrable:** "Maia repite lo que digo" — valida el stack de audio+STT+TTS en tu hardware real, con el device correcto.

**Files:**
- Create: `maia/__init__.py` (vacío)
- Create: `maia/config.py`
- Create: `maia/services.py`
- Create: `maia/echo.py` (entrypoint temporal de M1)

**Interfaces:**
- Produce: `config.load()` → objeto con `input_device_index`, `output_device_index`, claves. Consumido por M2-M5.
- Produce: `services.build_stt(cfg)`, `services.build_tts(cfg)` → servicios Pipecat. Consumido por M2-M5.

- [ ] **Step 1: `maia/config.py`** (carga .env, guard, selección de device WASAPI)

```python
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
        # sin hint: usa el default WASAPI
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


def load() -> Config:
    return Config(
        assemblyai_key=_require("ASSEMBLYAI_API_KEY"),
        fish_key=_require("FISHAUDIO_API_KEY"),
        fish_reference_id=os.getenv("FISHAUDIO_REFERENCE_ID") or None,
        input_device_index=_pick_wasapi_device(True, os.getenv("MAIA_INPUT_DEVICE")),
        output_device_index=_pick_wasapi_device(False, os.getenv("MAIA_OUTPUT_DEVICE")),
        picovoice_key=os.getenv("PICOVOICE_ACCESS_KEY") or None,
        wake_ppn=os.getenv("MAIA_WAKE_PPN") or None,
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
```

- [ ] **Step 2: Elegir devices** — `uv run python -m maia.config` lista los devices WASAPI. Anotar el índice del **micrófono** (tu headset) y del **altavoz/auriculares donde escuchas** en `.env`:
```dotenv
MAIA_INPUT_DEVICE=Headset Microphone
MAIA_OUTPUT_DEVICE=<nombre o índice de tus auriculares>
```
Expected: la lista muestra los devices; en Fase 0 el mic era idx 36, el output default (Realtek idx 26) era el equivocado → aquí lo fijas explícito.

- [ ] **Step 3: `maia/services.py`** (STT AssemblyAI + TTS Fish, con fallback ElevenLabs)

```python
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.fish.tts import FishAudioTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

TRANSPORT_SR = 48000
FISH_SR = 44100  # Fish máx en pcm; el output transport resamplea 44100->48000


def build_transport(cfg) -> LocalAudioTransport:
    return LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=TRANSPORT_SR,
            audio_out_sample_rate=TRANSPORT_SR,
            input_device_index=cfg.input_device_index,
            output_device_index=cfg.output_device_index,
        )
    )


def build_stt(cfg) -> AssemblyAISTTService:
    return AssemblyAISTTService(
        api_key=cfg.assemblyai_key,
        sample_rate=TRANSPORT_SR,  # debe igualar el transport (input NO auto-resamplea)
        vad_force_turn_endpoint=False,  # AssemblyAI maneja turnos + barge-in server-side
        settings=AssemblyAISTTService.Settings(
            model="universal-3-5-pro",
            language_codes=[Language.ES],
            format_turns=True,
            keyterms_prompt=["Maia"],
        ),
    )


def build_tts(cfg) -> FishAudioTTSService:
    return FishAudioTTSService(
        api_key=cfg.fish_key,
        sample_rate=FISH_SR,
        settings=FishAudioTTSService.Settings(
            model="s2.1-pro-free",  # se envía como header WS -> tier gratis
            voice=cfg.fish_reference_id,
            latency="balanced",
        ),
    )
```

- [ ] **Step 4: `maia/echo.py`** (loop de eco: STT → habla lo transcrito)

```python
import asyncio

from pipecat.frames.frames import TranscriptionFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from maia import config, services


class EchoBrain(FrameProcessor):
    """Placeholder de M1: repite por TTS lo que el STT transcriba."""

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            print(f"ESCUCHÉ: {frame.text}")
            await self.push_frame(TTSSpeakFrame(f"Dijiste: {frame.text}"))
        else:
            await self.push_frame(frame, direction)


async def main():
    cfg = config.load()
    transport = services.build_transport(cfg)
    pipeline = Pipeline([
        transport.input(),
        services.build_stt(cfg),
        EchoBrain(),
        services.build_tts(cfg),
        transport.output(),
    ])
    task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=True))
    print("Habla en español; Maia repetirá. Ctrl-C para salir.")
    await PipelineRunner(handle_sigint=False).run(task)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Correr y validar (usuario habla/escucha)**

Run: `$env:PYTHONUTF8=1; uv run python -m maia.echo`
Expected (criterio de PASS): hablas una frase en español → aparece `ESCUCHÉ: ...` y **escuchas** a Maia repetirla por tus auriculares (device correcto). Valida mic→STT→TTS(Fish)→speaker end-to-end en hardware real.
Si no escuchas: reajustar `MAIA_OUTPUT_DEVICE`. Si el STT no capta: revisar `MAIA_INPUT_DEVICE`.

- [ ] **Step 6: Commit**
```bash
git add maia/__init__.py maia/config.py maia/services.py maia/echo.py
git commit -m "feat(v1): M1 loop de eco (config + device selection + STT + TTS)"
```

---

### Task 2 (M2): Cerebro conversacional (ClaudeSDKClient persistente) + relleno hablado

**Meta demostrable:** "Maia conversa" — reemplaza el eco por Claude, con relleno hablado y streaming por frase.

**Files:**
- Create: `maia/brain.py`
- Create: `maia/main.py` (entrypoint real, reemplaza echo.py como principal)

**Interfaces:**
- Consume: `config.load()`, `services.build_*`.
- Produce: `MaiaBrain(FrameProcessor)` con un `ClaudeSDKClient` persistente inyectado; consumido por M4/M5.

- [ ] **Step 1: `maia/brain.py`** (MaiaBrain + apertura del cliente persistente)

```python
import asyncio

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
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

SYSTEM_PROMPT = (
    "Eres Maia, una asistente de voz en español. Responde SIEMPRE en español, "
    "de forma breve y natural para ser hablada en voz alta (sin markdown, sin listas largas). "
)


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
            await self.push_frame(TTSSpeakFrame("Dame un segundo."))  # relleno inmediato
            self._gen_task = self.create_task(self._run_brain(frame.text))
        else:
            await self.push_frame(frame, direction)

    async def _abort(self):
        if self._gen_task:
            await self.cancel_task(self._gen_task)
            self._gen_task = None
        try:
            await self._claude.interrupt()  # detiene generación server-side (SDK)
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


def build_claude_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model="claude-haiku-4-5-20251001",
        include_partial_messages=True,
        permission_mode="bypassPermissions",
        system_prompt=SYSTEM_PROMPT,
    )
```

- [ ] **Step 2: `maia/main.py`** (abre el cliente persistente una vez, arma el pipeline)

```python
import asyncio

from claude_agent_sdk import ClaudeSDKClient
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

from maia import config, services
from maia.brain import MaiaBrain, build_claude_options


async def main():
    cfg = config.load()
    transport = services.build_transport(cfg)
    async with ClaudeSDKClient(options=build_claude_options()) as claude:
        # warmup: elimina el cold-start (~19s) antes del primer turno real
        await claude.query("Di: lista.")
        async for m in claude.receive_response():
            from claude_agent_sdk import ResultMessage
            if isinstance(m, ResultMessage):
                break
        pipeline = Pipeline([
            transport.input(),
            services.build_stt(cfg),
            MaiaBrain(claude),
            services.build_tts(cfg),
            transport.output(),
        ])
        task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=True))
        print("Maia lista. Habla en español. Ctrl-C para salir.")
        await PipelineRunner(handle_sigint=False).run(task)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Correr y validar (usuario conversa)**

Run: `$env:PYTHONUTF8=1; uv run python -m maia.main`
Expected: hablas una pregunta → Maia dice "Dame un segundo" al instante → luego responde en español con voz (frase por frase). Conversación multi-turno mantiene contexto (cliente persistente).
Si el relleno y la respuesta se pisan raro o la primera frase tarda mucho: registrar tiempos; es esperado ~2.7 s a la respuesta real tras el relleno.

- [ ] **Step 4: Commit**
```bash
git add maia/brain.py maia/main.py
git commit -m "feat(v1): M2 cerebro conversacional persistente + relleno hablado"
```

---

### Task 3 (M3): Wake word "Maia" (Porcupine)

**Meta demostrable:** "Maia despierta al llamarla" — el pipeline sólo arranca tras detectar "Maia".

**Files:**
- Create: `maia/wake.py`
- Modify: `maia/main.py` (esperar la wake word antes del pipeline)

**Interfaces:**
- Consume: `cfg.picovoice_key`, `cfg.wake_ppn`.
- Produce: `WakeWord.wait()` async que retorna al detectar "Maia".

- [ ] **Step 1: Precondición** — entrenar el `.ppn` "Maia" (Windows) en console.picovoice.ai; poner `PICOVOICE_ACCESS_KEY` y `MAIA_WAKE_PPN=<ruta al .ppn>` en `.env`. `uv add pvporcupine pvrecorder`.

- [ ] **Step 2: `maia/wake.py`**

```python
import asyncio

import pvporcupine
from pvrecorder import PvRecorder


class WakeWord:
    def __init__(self, access_key: str, ppn_path: str):
        self._porcupine = pvporcupine.create(access_key=access_key, keyword_paths=[ppn_path])
        # pvrecorder captura a porcupine.sample_rate (16k) SIN pinear device WASAPI 48k
        self._recorder = PvRecorder(frame_length=self._porcupine.frame_length, device_index=-1)

    async def wait(self) -> None:
        loop = asyncio.get_running_loop()

        def _listen():
            self._recorder.start()
            try:
                while True:
                    if self._porcupine.process(self._recorder.read()) >= 0:
                        return
            finally:
                self._recorder.stop()

        await loop.run_in_executor(None, _listen)

    def close(self):
        self._recorder.delete()
        self._porcupine.delete()
```

- [ ] **Step 3: Modificar `maia/main.py`** — envolver el pipeline en un bucle que espera la wake word. Reemplazar el bloque del pipeline por:

```python
    from maia.wake import WakeWord

    wake = WakeWord(cfg.picovoice_key, cfg.wake_ppn) if cfg.picovoice_key and cfg.wake_ppn else None
    async with ClaudeSDKClient(options=build_claude_options()) as claude:
        # (warmup igual que M2)
        while True:
            if wake:
                print("Esperando 'Maia'…")
                await wake.wait()
                print("¡Activada!")
            pipeline = Pipeline([
                transport.input(), services.build_stt(cfg), MaiaBrain(claude),
                services.build_tts(cfg), transport.output(),
            ])
            task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=True))
            await PipelineRunner(handle_sigint=False).run(task)
            if not wake:
                break
```

Nota: el recorder de Porcupine (16k, device default) y el transport de Pipecat (48k, device explícito) NO corren a la vez — Porcupine cierra su stream al detectar, antes de abrir el pipeline. (Si en runtime hay conflicto de device, registrar y considerar cerrar/abrir explícito.)

- [ ] **Step 4: Correr y validar** — `$env:PYTHONUTF8=1; uv run python -m maia.main` → dices "Maia" → "¡Activada!" → conversas. Criterio: el pipeline no escucha hasta la wake word.

- [ ] **Step 5: Commit**
```bash
git add maia/wake.py maia/main.py pyproject.toml uv.lock
git commit -m "feat(v1): M3 wake word Maia (Porcupine)"
```

---

### Task 4 (M4): Barge-in (interrupción por voz)

**Meta demostrable:** "Maia se calla si la interrumpo" — hablar encima corta el TTS y la generación del cerebro.

**Files:**
- Modify: `maia/main.py` (habilitar interrupciones en `PipelineParams`)
- Verify: `maia/brain.py` (ya maneja `InterruptionFrame` en `_abort`)

**Interfaces:** Consume el `InterruptionFrame` que AssemblyAI (server-turn) emite en `SpeechStarted`.

- [ ] **Step 1: Habilitar interrupciones** — en `main.py`, `PipelineParams(enable_metrics=True, allow_interruptions=True)`. (Confirmar el nombre exacto del flag en Pipecat 1.7.0 al correr; si difiere, registrar el real.)

- [ ] **Step 2: Verificar el abort del cerebro** — `MaiaBrain.process_frame` ya llama `_abort()` en `InterruptionFrame` (M2), que cancela el task de generación y llama `claude.interrupt()`. Sin cambios de código salvo que el runtime muestre que `interrupt()` no existe/da error → en ese caso, quitar esa llamada y confiar en `cancel_task` (registrar en FINDINGS).

- [ ] **Step 3: Correr y validar** — mientras Maia habla una respuesta larga, hablas encima: el audio de Maia se corta de inmediato y atiende tu nuevo turno. Criterio de PASS: sin solapamiento; la generación previa se aborta.

- [ ] **Step 4: Commit**
```bash
git add maia/main.py maia/brain.py
git commit -m "feat(v1): M4 barge-in (interrupción por voz)"
```

---

### Task 5 (M5): Tool de timers + gate de confirmación por voz

**Meta demostrable:** "Maia, recuérdame en 10 segundos X" → confirma por voz → al vencer, lo dice.

**Files:**
- Modify: `maia/brain.py` (tool `set_timer`, `create_sdk_mcp_server`, hook `PreToolUse`, `VoiceBridge`)
- Modify: `maia/main.py` (cablear `VoiceBridge` al transcript + pasar el frame de recordatorio al task)

**Interfaces:**
- Produce: `VoiceBridge.on_transcript(text)` (lo llama el brain con cada transcript) y `VoiceBridge.listen()` (lo usa el hook).
- Produce: `make_timer_server(speak_cb)` y `make_gate_hook(bridge, speak_cb)`.

- [ ] **Step 1: Añadir a `maia/brain.py`** el tool de timers, el bridge y el hook

```python
from claude_agent_sdk import HookMatcher, create_sdk_mcp_server, tool


class VoiceBridge:
    def __init__(self):
        self._answers: asyncio.Queue[str] = asyncio.Queue()

    def on_transcript(self, text: str) -> None:
        self._answers.put_nowait(text)

    async def listen(self, timeout: float = 15.0) -> str:
        return await asyncio.wait_for(self._answers.get(), timeout=timeout)


def make_timer_server(speak_cb):
    """speak_cb(message: str) -> None : empuja un TTSSpeakFrame al pipeline."""
    _tasks: set = set()

    @tool("set_timer", "Programa un recordatorio hablado dentro de N segundos",
          {"seconds": float, "message": str})
    async def set_timer(args):
        async def _fire():
            await asyncio.sleep(float(args["seconds"]))
            await speak_cb(f"Recordatorio: {args['message']}")
        t = asyncio.create_task(_fire())
        _tasks.add(t)
        t.add_done_callback(_tasks.discard)
        return {"content": [{"type": "text",
                             "text": f"Timer puesto: {args['seconds']}s -> {args['message']}"}]}

    return create_sdk_mcp_server(name="timers", version="1.0.0", tools=[set_timer])


def make_gate_hook(bridge: VoiceBridge, speak_cb):
    async def pre_tool_use(input_data, tool_use_id, context):
        name = input_data["tool_name"]
        await speak_cb(f"¿Confirmas {name}? Di sí o no.")
        try:
            answer = await bridge.listen(timeout=15.0)
        except asyncio.TimeoutError:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                    "permissionDecision": "deny", "permissionDecisionReason": "Sin respuesta."}}
        if answer.strip().lower().rstrip(".").rstrip("!") in ("si", "sí", "claro", "dale", "confirmo"):
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "permissionDecision": "deny", "permissionDecisionReason": "El usuario dijo que no."}}

    return HookMatcher(matcher="mcp__timers__set_timer", hooks=[pre_tool_use], timeout=30.0)
```

- [ ] **Step 2: Cablear en `build_claude_options`** — que acepte el server de timers y el hook, y registrar `mcp_servers` + `allowed_tools` + `hooks`:

```python
def build_claude_options(timer_server=None, gate_hook=None) -> ClaudeAgentOptions:
    kwargs = dict(
        model="claude-haiku-4-5-20251001",
        include_partial_messages=True,
        permission_mode="bypassPermissions",
        system_prompt=SYSTEM_PROMPT,
    )
    if timer_server is not None:
        kwargs["mcp_servers"] = {"timers": timer_server}
        kwargs["allowed_tools"] = ["mcp__timers__set_timer"]  # confirmar naming al correr (log tool_name)
    if gate_hook is not None:
        kwargs["hooks"] = {"PreToolUse": [gate_hook]}
    return ClaudeAgentOptions(**kwargs)
```

- [ ] **Step 3: En `maia/main.py`** — crear `bridge = VoiceBridge()`, un `speak_cb` que haga `await task.queue_frames([TTSSpeakFrame(msg)])`, construir `timer_server`/`gate_hook`, pasarlos a `build_claude_options(...)`, y en `MaiaBrain` llamar `bridge.on_transcript(frame.text)` en cada `TranscriptionFrame` (para que el hook reciba el "sí"). Nota: `speak_cb` necesita el `task`, que se crea después de las options → crear el `task` primero con un `speak_cb` que capture el task por referencia diferida (o un pequeño holder mutable). Registrar el patrón exacto al implementar.

- [ ] **Step 4: Correr y validar** — "Maia, pon un timer de 10 segundos que diga hola" → Maia pregunta "¿Confirmas set_timer? Di sí o no" → dices "sí" → a los 10 s Maia dice "Recordatorio: hola". Si dices "no" → no lo pone. Criterio: el gate intercepta y respeta tu voz; el timer dispara out-of-band.

- [ ] **Step 5: Commit**
```bash
git add maia/brain.py maia/main.py
git commit -m "feat(v1): M5 tool de timers + gate de confirmación por voz"
```

---

## Cierre v1

Al completar M1-M5, Maia v1 está funcional: wake word → conversación en español con cerebro persistente → relleno + streaming → barge-in → timers con confirmación por voz. Riesgos a vigilar en runtime (registrar en un FINDINGS de v1): nombre exacto del flag de interrupciones y de `allowed_tools` para el tool in-process; existencia de `ClaudeSDKClient.interrupt()`; conflicto de device entre Porcupine (16k) y el transport (48k); y la latencia percibida real con el relleno. v2: Calendar/Gmail (MCP local con OAuth), envío de correos (doble confirmación), multi-tool.
