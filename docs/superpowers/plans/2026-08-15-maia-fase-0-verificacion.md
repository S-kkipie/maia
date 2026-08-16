# Maia — Fase 0: Verificación de Riesgos — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verificar mediante spikes desechables que las 5 suposiciones de riesgo del diseño de Maia se cumplen en Windows nativo, antes de escribir una sola línea de v1.

**Architecture:** Cada riesgo es un script aislado en `spikes/fase0/` que se ejecuta y produce un veredicto PASS/FALLA + métricas registradas en `spikes/fase0/FINDINGS.md`. El cerebro es Claude Code vía `claude-agent-sdk` (cliente persistente, auth por suscripción); la voz es Pipecat 1.7.0 (audio local, AssemblyAI STT, ElevenLabs TTS). Nada de esto es código de producción: es medición de viabilidad.

**Tech Stack:** Python 3.12, gestor `uv`, `claude-agent-sdk`, `pipecat-ai==1.7.0` (extras `local,assemblyai,elevenlabs,silero`), AssemblyAI (STT), ElevenLabs Flash v2.5 (TTS), PyAudio/WASAPI (audio), Playwright MCP local (integraciones).

**Spec:** `docs/superpowers/specs/2026-08-15-maia-voice-assistant-design.md`

## Global Constraints

Aplican a TODAS las tareas. Valores exactos, copiar literal.

- **Plataforma:** Windows nativo. Python **3.12** (instalado: 3.12.10). Gestor de dependencias **`uv`** (instalado: 0.12.3) — NUNCA `pip`/`requirements.txt` a mano.
- **Auth del cerebro:** suscripción vía `~/.claude/.credentials.json` (`claudeAiOauth`). **Prohibido** setear `ANTHROPIC_API_KEY` en el entorno o en `.env`. `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`) es solo fallback documentado para always-on.
- **MCP:** SOLO servidores **locales configurados** en `mcp_servers`, cada uno con su propio OAuth/credenciales. **Prohibido** usar los connectors nativos de la cuenta claude.ai.
- **STT:** **AssemblyAI** (`AssemblyAISTTService`), español vía `language_codes=[Language.ES]`, modelo `universal-3-5-pro`. **No Deepgram.**
- **TTS:** ElevenLabs **`eleven_flash_v2_5`** (`ElevenLabsTTSService`).
- **Pipecat pineado a `==1.7.0`** (APIs cambiaron en la línea 1.x; `PipelineTask`/`PipelineRunner` deprecados pero funcionan; VAD ya NO es param del transport). Ignorar tutoriales viejos.
- **Modelos del cerebro:** default `claude-haiku-4-5-20251001`; escala a `claude-sonnet-5`. Reasoning bajo.
- **Objetivo de latencia:** TTFA (query → primer audio) **< 1.5 s**.
- **Todo el código de Fase 0** vive en `spikes/fase0/` y es **desechable**. Resultados en `spikes/fase0/FINDINGS.md`.
- **Idioma:** mensajes al usuario y prompts de prueba en español.

**Cambios sobre el spec** (el spec queda desactualizado en estos puntos; sincronizar tras Fase 0): STT Deepgram→**AssemblyAI**; MCP connectors nativos→**locales configurados**; "wake word Pipecat nativo"→**Pipecat NO trae wake-word** (decisión abierta, §Task 5 nota); gestor de deps→**uv**.

**Precondiciones manuales (no scriptables — verificar antes de la Tarea 1):**
- `claude /login` (Pro Max) ya hecho → `~/.claude/.credentials.json` presente. La Tarea 3 confirma vigencia.
- Node ≥ 22 (instalado: v24) para MCP stdio vía `npx`.
- Git for Windows recomendado para la tool Bash (si falta, Claude Code usa PowerShell; setear `CLAUDE_CODE_GIT_BASH_PATH` si es necesario).
- Claves en `.env` (ver `.env.example`): `ASSEMBLYAI_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (una voz española de tu cuenta ElevenLabs).

---

### Task 1: Entorno reproducible con `uv` + esqueleto de spikes

**Files:**
- Create: `pyproject.toml` (vía `uv init`)
- Create: `.python-version`, `.gitignore`, `.env.example`
- Create: `spikes/fase0/_env.py`
- Create: `spikes/fase0/FINDINGS.md`
- Create: `spikes/fase0/00_smoke.py`

**Interfaces:**
- Produce: módulo `_env` con `require(name: str) -> str` (lee `.env`, aborta si `ANTHROPIC_API_KEY` está seteada). Todas las tareas siguientes lo importan con el boilerplate de `sys.path`.
- Produce: `FINDINGS.md` con una sección por tarea.

- [ ] **Step 1: Inicializar proyecto con uv (Python 3.12)**

Run:
```powershell
uv init --python 3.12 --no-workspace
```
Expected: crea `pyproject.toml` y `.python-version` con `3.12`.

- [ ] **Step 2: Agregar dependencias con uv**

Run:
```powershell
uv add claude-agent-sdk python-dotenv "pipecat-ai[local,assemblyai,elevenlabs,silero]==1.7.0"
```
Expected: resuelve e instala; crea/actualiza `uv.lock`. PyAudio entra por el extra `local` (wheel Windows con PortAudio incluido, sin build manual).

- [ ] **Step 3: Escribir `.gitignore`**

```gitignore
.venv/
.env
__pycache__/
*.pyc
```

- [ ] **Step 4: Escribir `.env.example`**

```dotenv
# Claves de voz (NO poner ANTHROPIC_API_KEY: el cerebro usa la suscripción)
ASSEMBLYAI_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
```

- [ ] **Step 5: Escribir `spikes/fase0/_env.py`**

```python
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
```

- [ ] **Step 6: Escribir `spikes/fase0/FINDINGS.md` (esqueleto)**

```markdown
# Fase 0 — Hallazgos

Cada tarea registra: fecha, veredicto (PASS/FALLA/PARCIAL), métricas y notas.

## Task 2 — SDK persistente + streaming + Bash
- Veredicto:
- TTFT (s):
- ¿Bash ejecutó? ¿Git Bash o PowerShell?:
- ¿Contexto persistió (turno 2)?:
- Notas:

## Task 3 — Auth suscripción + límites
- Veredicto:
- subscriptionType / expiresAt vigente:
- Turnos OK de 20 / errores:
- Latencia media (s):
- Notas (rate-limit observado):

## Task 4 — Audio WASAPI
- Veredicto:
- Host API elegido / device in/out:
- ¿Echo audible sin XRuns?:
- Notas:

## Task 5 — STT AssemblyAI español
- Veredicto:
- Modelo / language_codes:
- ¿Español transcrito con precisión en streaming?:
- Latencia final aprox (s):
- Notas:

## Task 6 — Latencia E2E (TTFA)
- Veredicto:
- TTFA total (query→primer audio) (s):
- Pipecat TTFA(TTS) / TTFB (s):
- ¿< 1.5 s?:
- Notas:

## Task 7 — MCP local configurado
- Veredicto:
- ¿Playwright MCP corrió headless vía npx?:
- Título de example.com devuelto:
- Decisión OAuth-MCP (Calendar) para v1:
- Notas:
```

- [ ] **Step 7: Escribir `spikes/fase0/00_smoke.py`**

```python
import importlib.metadata as md
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401  (el import dispara el guard de API key)

for pkg in ("claude-agent-sdk", "pipecat-ai", "python-dotenv"):
    try:
        print(f"{pkg}: {md.version(pkg)}")
    except md.PackageNotFoundError:
        sys.exit(f"Paquete no instalado: {pkg}")

cred = pathlib.Path.home() / ".claude" / ".credentials.json"
if not cred.exists():
    sys.exit(f"No hay credentials.json en {cred} — corre `claude /login`.")
print("credentials.json: OK")
print("Smoke OK")
```

- [ ] **Step 8: Ejecutar el smoke**

Run: `uv run python spikes/fase0/00_smoke.py`
Expected: imprime versiones de los 3 paquetes, `credentials.json: OK`, `Smoke OK`. Confirma que `pipecat-ai` es `1.7.0`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock .python-version .gitignore .env.example spikes/fase0/
git commit -m "chore: entorno uv + esqueleto de spikes Fase 0"
```

---

### Task 2: Cliente persistente + streaming token-a-token + tool Bash (Windows)

**Files:**
- Create: `spikes/fase0/01_sdk_stream.py`
- Modify: `spikes/fase0/FINDINGS.md` (sección Task 2)

**Interfaces:**
- Consume: `_env` (Task 1).
- Verifica riesgo §8b.1 del spec.

- [ ] **Step 1: Escribir `spikes/fase0/01_sdk_stream.py`**

```python
import asyncio
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401  (guard de API key)

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
)


async def run_turn(client, prompt):
    t0 = time.perf_counter()
    first_token = None
    tools = []
    chunks = []
    await client.query(prompt)
    async for message in client.receive_response():
        if isinstance(message, StreamEvent):
            ev = message.event
            et = ev.get("type")
            if et == "content_block_start":
                cb = ev.get("content_block", {})
                if cb.get("type") == "tool_use":
                    tools.append(cb.get("name"))
            elif et == "content_block_delta":
                d = ev.get("delta", {})
                if d.get("type") == "text_delta":
                    if first_token is None:
                        first_token = time.perf_counter() - t0
                    chunks.append(d.get("text", ""))
        elif isinstance(message, ResultMessage):
            break
    return {"ttft": first_token, "tools": tools, "text": "".join(chunks)}


async def main():
    options = ClaudeAgentOptions(
        model="claude-haiku-4-5-20251001",
        include_partial_messages=True,
        allowed_tools=["Bash"],
        # bypassPermissions: spike headless sin gate (el gate real es de v1).
        # Si el nombre del campo/valor difiere, registrar el real en FINDINGS.
        permission_mode="bypassPermissions",
    )
    async with ClaudeSDKClient(options=options) as client:
        r1 = await run_turn(
            client,
            "Ejecuta el comando de shell `echo hola-maia` y dime exactamente su salida.",
        )
        print(f"TURNO 1 — TTFT: {r1['ttft']:.3f}s  tools: {r1['tools']}")
        print("TURNO 1 — texto:", r1["text"][:300])
        r2 = await run_turn(
            client, "¿Qué comando de shell te acabo de pedir que ejecutara?"
        )
        print("TURNO 2 — (prueba de contexto):", r2["text"][:300])


asyncio.run(main())
```

- [ ] **Step 2: Ejecutar**

Run: `uv run python spikes/fase0/01_sdk_stream.py`
Expected (criterios de PASS):
- Conecta **sin** `ANTHROPIC_API_KEY` (usa la suscripción).
- `TTFT` se imprime (hay streaming incremental, no espera-todo).
- `tools` incluye `Bash` y el texto del turno 1 contiene `hola-maia`.
- El turno 2 menciona `echo`/`hola-maia` → el contexto persistió en el mismo cliente.

Si el turno 1 no ejecuta Bash o el proceso queda bloqueado pidiendo permiso: registrar que `permission_mode="bypassPermissions"` no aplicó y anotar el nombre/valor real del campo.

- [ ] **Step 3: Registrar hallazgo en FINDINGS.md**

Rellenar la sección Task 2 con: veredicto, TTFT, si Bash usó Git Bash o PowerShell (observar en la salida), y si el turno 2 retuvo contexto.

- [ ] **Step 4: Commit**

```bash
git add spikes/fase0/01_sdk_stream.py spikes/fase0/FINDINGS.md
git commit -m "spike(fase0): SDK persistente + streaming + Bash en Windows"
```

---

### Task 3: Auth por suscripción (`credentials.json`) + sondeo de límites Pro Max

**Files:**
- Create: `spikes/fase0/02_auth_limits.py`
- Modify: `spikes/fase0/FINDINGS.md` (sección Task 3)

**Interfaces:**
- Consume: `_env` (Task 1).
- Verifica riesgo §8b.2 (auth headless + límites always-on).

- [ ] **Step 1: Escribir `spikes/fase0/02_auth_limits.py`**

```python
import asyncio
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401  (guard: aborta si hay API key)

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

CRED = pathlib.Path.home() / ".claude" / ".credentials.json"
oauth = json.loads(CRED.read_text())["claudeAiOauth"]
vigente = oauth.get("expiresAt", 0) / 1000 > time.time()
print("subscriptionType:", oauth.get("subscriptionType"))
print("rateLimitTier:", oauth.get("rateLimitTier"))
print("accessToken vigente:", vigente)
if not vigente:
    print("AVISO: accessToken expirado; el SDK debería refrescar con refreshToken.")


async def main():
    options = ClaudeAgentOptions(model="claude-haiku-4-5-20251001")
    latencias = []
    errores = []
    async with ClaudeSDKClient(options=options) as client:
        for i in range(20):
            t0 = time.perf_counter()
            try:
                await client.query(f"Responde solo con el número {i}, nada más.")
                async for m in client.receive_response():
                    if isinstance(m, ResultMessage):
                        break
                latencias.append(time.perf_counter() - t0)
            except Exception as e:  # noqa: BLE001
                errores.append(repr(e))
                print(f"ERROR en turno {i}: {e}")
                break
    print(f"Turnos OK: {len(latencias)}/20  errores: {len(errores)}")
    if latencias:
        print(f"Latencia media: {sum(latencias) / len(latencias):.3f}s")


asyncio.run(main())
```

- [ ] **Step 2: Ejecutar**

Run: `uv run python spikes/fase0/02_auth_limits.py`
Expected (criterios de PASS):
- Imprime `subscriptionType`/`rateLimitTier` y `accessToken vigente: True`.
- Completa los 20 turnos **sin** ninguna clave de API, usando la suscripción.
- No hay error de auth. Si aparece un error de rate-limit/uso, registrarlo textual (es un dato valioso para always-on).

- [ ] **Step 3: (Opcional) documentar fallback de token**

En FINDINGS anotar, sin ejecutar: para always-on headless, `claude setup-token` genera un `CLAUDE_CODE_OAUTH_TOKEN` (1 año) que se exporta en el entorno como precedencia sobre el login interactivo. Marcar como "pendiente de probar en despliegue always-on".

- [ ] **Step 4: Registrar hallazgo + Commit**

```bash
git add spikes/fase0/02_auth_limits.py spikes/fase0/FINDINGS.md
git commit -m "spike(fase0): auth por suscripcion (credentials.json) + sondeo de limites"
```

---

### Task 4: Audio WASAPI — loopback con Pipecat (forzando host-API WASAPI)

**Files:**
- Create: `spikes/fase0/03_audio_wasapi.py`
- Modify: `spikes/fase0/FINDINGS.md` (sección Task 4)

**Interfaces:**
- Consume: `_env` (Task 1).
- Produce: los índices de device WASAPI que la Tarea 5 reutilizará como referencia.
- Verifica riesgo §8b.3. Nota: Pipecat abre el device por defecto (suele ser MME); aquí forzamos WASAPI enumerando con PyAudio y pasando `input_device_index`/`output_device_index`.

- [ ] **Step 1: Escribir `spikes/fase0/03_audio_wasapi.py`**

```python
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401

import pyaudio  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.transports.local.audio import (  # noqa: E402
    LocalAudioTransport,
    LocalAudioTransportParams,
)


def wasapi_devices():
    pa = pyaudio.PyAudio()
    try:
        info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        pa.terminate()
        sys.exit("WASAPI no disponible en esta build de PortAudio.")
    in_idx = info.get("defaultInputDevice", -1)
    out_idx = info.get("defaultOutputDevice", -1)
    print(f"WASAPI: host_api={info['index']} in={in_idx} out={out_idx}")
    pa.terminate()
    if in_idx < 0 or out_idx < 0:
        sys.exit("WASAPI sin device in/out por defecto — registrar y elegir device manual.")
    return int(in_idx), int(out_idx)


async def main():
    in_idx, out_idx = wasapi_devices()
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            input_device_index=in_idx,
            output_device_index=out_idx,
        )
    )
    pipeline = Pipeline([transport.input(), transport.output()])  # mic -> speaker
    task = PipelineTask(pipeline, params=PipelineParams())
    runner = PipelineRunner(handle_sigint=False)  # loop Proactor de Windows
    print("Loopback 8s: habla y escúchate (usa auriculares para evitar acople).")
    try:
        await asyncio.wait_for(runner.run(task), timeout=8.0)
    except asyncio.TimeoutError:
        print("Fin del loopback (8s).")


asyncio.run(main())
```

- [ ] **Step 2: Ejecutar (manual: hablar al micrófono)**

Run: `uv run python spikes/fase0/03_audio_wasapi.py`
Expected (criterios de PASS):
- Imprime la línea `WASAPI: host_api=... in=... out=...` (WASAPI existe y tiene devices).
- Durante 8 s se escucha el eco de la propia voz por los altavoces/auriculares, sin errores de XRun ni excepciones.

Si `handle_sigint` provoca `NotImplementedError`, ya está en `False`; si aun así falla el runner en Windows, registrar el traceback. Si el eco tiene glitches, anotar sample_rate/latencia.

- [ ] **Step 3: Registrar hallazgo + Commit**

```bash
git add spikes/fase0/03_audio_wasapi.py spikes/fase0/FINDINGS.md
git commit -m "spike(fase0): audio WASAPI loopback con Pipecat"
```

---

### Task 5: STT AssemblyAI — transcripción de español en streaming

**Files:**
- Create: `spikes/fase0/04_stt_assemblyai.py`
- Modify: `spikes/fase0/FINDINGS.md` (sección Task 5)

**Interfaces:**
- Consume: `_env` (Task 1); `ASSEMBLYAI_API_KEY`.
- Verifica el cambio de vendor a AssemblyAI y el riesgo real de **español en streaming**.
- Nota de diseño: usamos `vad_force_turn_endpoint=False` → AssemblyAI maneja el fin de turno server-side (requiere modelo U3 Pro; `universal-3-5-pro` califica), así el spike no necesita VAD local. Wake-word "Maia" NO existe en Pipecat: aquí se sondea como `keyterms_prompt=["Maia"]` para reforzarla, pero la estrategia de wake-word queda como decisión abierta de v1 (engine externo tipo openWakeWord/Porcupine, o match de "Maia" en el transcript).

- [ ] **Step 1: Escribir `spikes/fase0/04_stt_assemblyai.py`**

```python
import asyncio
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402

API_KEY = require("ASSEMBLYAI_API_KEY")

import pyaudio  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    InterimTranscriptionFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402
from pipecat.services.assemblyai.stt import AssemblyAISTTService  # noqa: E402
from pipecat.transcriptions.language import Language  # noqa: E402
from pipecat.transports.local.audio import (  # noqa: E402
    LocalAudioTransport,
    LocalAudioTransportParams,
)


class Printer(FrameProcessor):
    def __init__(self):
        super().__init__()
        self._last_speech = time.perf_counter()

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame):
            print("…", frame.text)
            self._last_speech = time.perf_counter()
        elif isinstance(frame, TranscriptionFrame):
            print(f"FINAL [{getattr(frame, 'language', '?')}]: {frame.text}")
        await self.push_frame(frame, direction)


def wasapi_in():
    pa = pyaudio.PyAudio()
    info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    idx = int(info.get("defaultInputDevice", -1))
    pa.terminate()
    return idx if idx >= 0 else None


async def main():
    stt = AssemblyAISTTService(
        api_key=API_KEY,
        sample_rate=16000,
        vad_force_turn_endpoint=False,  # AssemblyAI maneja turnos (U3 Pro)
        settings=AssemblyAISTTService.Settings(
            model="universal-3-5-pro",
            language_codes=[Language.ES],  # español (steering U3 Pro)
            format_turns=True,
            keyterms_prompt=["Maia"],
        ),
    )
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_in_sample_rate=16000,
            input_device_index=wasapi_in(),
        )
    )
    pipeline = Pipeline([transport.input(), stt, Printer()])
    task = PipelineTask(pipeline, params=PipelineParams())
    runner = PipelineRunner(handle_sigint=False)
    print("20s: di varias frases en español (incluye 'Maia'). Ctrl-C para cortar.")
    try:
        await asyncio.wait_for(runner.run(task), timeout=20.0)
    except asyncio.TimeoutError:
        print("Fin (20s).")


asyncio.run(main())
```

- [ ] **Step 2: Ejecutar (manual: hablar en español)**

Run: `uv run python spikes/fase0/04_stt_assemblyai.py`
Expected (criterios de PASS):
- Aparecen transcripciones interinas (`…`) y `FINAL [es]: ...` con el texto español correcto.
- La precisión en español es aceptable (registrar impresión + ejemplos).

**Criterio de FALLA / hallazgo crítico:** si el español no se transcribe (o solo funciona en inglés, o el modelo `universal-3-5-pro` es rechazado por la cuenta), registrarlo como bloqueante — implica revisar plan/vendor de STT. Si el rechazo es por entitlement del modelo, probar `model="universal-streaming-multilingual"` (sin steering por `language_codes`).

- [ ] **Step 3: Registrar hallazgo + Commit**

```bash
git add spikes/fase0/04_stt_assemblyai.py spikes/fase0/FINDINGS.md
git commit -m "spike(fase0): STT AssemblyAI espanol en streaming"
```

---

### Task 6: Latencia end-to-end (TTFA) — cerebro (SDK) → ElevenLabs Flash

**Files:**
- Create: `spikes/fase0/05_ttfa.py`
- Modify: `spikes/fase0/FINDINGS.md` (sección Task 6)

**Interfaces:**
- Consume: `_env`; `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`.
- Verifica riesgo §8b.4 (TTFA < 1.5 s). Mide desde el envío del turno al cerebro hasta el **primer audio** hablado, usando corte por primera frase + TTS por streaming. La latencia de STT (Task 5, endpointing de AssemblyAI) se suma aparte para estimar el turno completo.

- [ ] **Step 1: Escribir `spikes/fase0/05_ttfa.py`**

```python
import asyncio
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402

require("ELEVENLABS_API_KEY")
VOICE_ID = require("ELEVENLABS_VOICE_ID")

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
)
from pipecat.frames.frames import (  # noqa: E402
    EndFrame,
    MetricsFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
)
from pipecat.metrics.metrics import TTFAMetricsData  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService  # noqa: E402
from pipecat.transports.local.audio import (  # noqa: E402
    LocalAudioTransport,
    LocalAudioTransportParams,
)

state = {"t0": None, "first_audio": None}


class AudioTap(FrameProcessor):
    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if (
            isinstance(frame, TTSAudioRawFrame)
            and state["first_audio"] is None
            and state["t0"] is not None
        ):
            state["first_audio"] = time.perf_counter()
            print(f"TTFA total (query→primer audio): {state['first_audio'] - state['t0']:.3f}s")
        if isinstance(frame, MetricsFrame):
            for d in frame.data:
                if isinstance(d, TTFAMetricsData):
                    print(f"Pipecat TTFA(TTS)={d.ttfa:.3f}s TTFB={d.ttfb:.3f}s")
        await self.push_frame(frame, direction)


async def brain_stream(client, task, prompt):
    buf = ""
    state["t0"] = time.perf_counter()
    await client.query(prompt)
    async for message in client.receive_response():
        if isinstance(message, StreamEvent):
            ev = message.event
            if ev.get("type") == "content_block_delta":
                d = ev.get("delta", {})
                if d.get("type") == "text_delta":
                    buf += d.get("text", "")
                    m = re.search(r"[.!?]\s", buf)
                    if m:  # primera frase completa -> hablar YA
                        await task.queue_frame(TTSSpeakFrame(buf[: m.end()].strip()))
                        return
        elif isinstance(message, ResultMessage):
            if buf.strip():
                await task.queue_frame(TTSSpeakFrame(buf.strip()))
            return


async def main():
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        sample_rate=16000,
        settings=ElevenLabsTTSService.Settings(voice=VOICE_ID, model="eleven_flash_v2_5"),
    )
    transport = LocalAudioTransport(
        LocalAudioTransportParams(audio_out_enabled=True, audio_out_sample_rate=16000)
    )
    pipeline = Pipeline([tts, AudioTap(), transport.output()])
    task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=True))
    runner = PipelineRunner(handle_sigint=False)

    async def drive():
        opts = ClaudeAgentOptions(
            model="claude-haiku-4-5-20251001", include_partial_messages=True
        )
        async with ClaudeSDKClient(options=opts) as client:
            await brain_stream(
                client, task, "En una sola frase corta y natural, salúdame como asistente de voz."
            )
        await asyncio.sleep(4)  # dejar sonar el audio
        await task.queue_frame(EndFrame())

    await asyncio.gather(runner.run(task), drive())


asyncio.run(main())
```

- [ ] **Step 2: Ejecutar**

Run: `uv run python spikes/fase0/05_ttfa.py`
Expected (criterios de PASS):
- Se escucha el saludo hablado.
- Se imprime `TTFA total (query→primer audio): X.XXXs` con **X < 1.5**.
- Se imprime el desglose `Pipecat TTFA(TTS)/TTFB`.

Si `TTFAMetricsData` no aparece (según el vendor puede emitir solo TTFB), basta el `TTFA total` por timestamp del primer `TTSAudioRawFrame` (registrar cuál se obtuvo). Si `queue_frame`/`EndFrame` no cortan limpio, registrar y cerrar por timeout.

- [ ] **Step 3: Registrar hallazgo + Commit**

```bash
git add spikes/fase0/05_ttfa.py spikes/fase0/FINDINGS.md
git commit -m "spike(fase0): latencia E2E (TTFA) cerebro -> ElevenLabs"
```

---

### Task 7: MCP local configurado, headless (Playwright) + decisión OAuth-MCP

**Files:**
- Create: `spikes/fase0/06_mcp_local.py`
- Modify: `spikes/fase0/FINDINGS.md` (sección Task 7)

**Interfaces:**
- Consume: `_env` (Task 1).
- Verifica riesgo §8b.5 reencuadrado: los MCP son **locales configurados** en `mcp_servers` (cero connectors nativos). Playwright (sin OAuth) prueba el mecanismo headless vía `npx`. La parte OAuth (Calendar) se documenta como decisión, no se ejecuta.

- [ ] **Step 1: (Precondición) instalar navegadores de Playwright**

Run: `npx -y playwright install chromium`
Expected: descarga Chromium (una vez). Evita que el primer uso del MCP falle por falta de navegador.

- [ ] **Step 2: Escribir `spikes/fase0/06_mcp_local.py`**

```python
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _env import require  # noqa: E402,F401

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
)


async def main():
    options = ClaudeAgentOptions(
        model="claude-haiku-4-5-20251001",
        include_partial_messages=True,
        mcp_servers={  # <-- LOCAL configurado, no connector de cuenta
            "playwright": {
                "command": "npx",
                "args": ["-y", "@playwright/mcp@latest"],
            }
        },
        allowed_tools=["mcp__playwright__*"],
        permission_mode="bypassPermissions",
    )
    tools = []
    chunks = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            "Con la herramienta de navegador (Playwright), abre https://example.com "
            "y dime el título exacto de la página."
        )
        async for m in client.receive_response():
            if isinstance(m, StreamEvent):
                ev = m.event
                if ev.get("type") == "content_block_start":
                    cb = ev.get("content_block", {})
                    if cb.get("type") == "tool_use":
                        tools.append(cb.get("name"))
                elif ev.get("type") == "content_block_delta":
                    d = ev.get("delta", {})
                    if d.get("type") == "text_delta":
                        chunks.append(d.get("text", ""))
            elif isinstance(m, ResultMessage):
                break
    print("tools MCP usadas:", tools)
    print("respuesta:", "".join(chunks)[:400])


asyncio.run(main())
```

- [ ] **Step 3: Ejecutar**

Run: `uv run python spikes/fase0/06_mcp_local.py`
Expected (criterios de PASS):
- `tools MCP usadas` contiene una tool `mcp__playwright__...` → el servidor MCP **local** arrancó vía `npx` **sin login interactivo**.
- La respuesta menciona el título `Example Domain`.

Si `allowed_tools=["mcp__playwright__*"]` (wildcard) no habilita las tools, registrar y probar sin wildcard o confiando solo en `bypassPermissions`.

- [ ] **Step 4: Documentar la decisión OAuth-MCP (Calendar) para v1**

En FINDINGS (sin ejecutar): un connector con OAuth propio (p. ej. un Google Calendar MCP local en `mcp_servers`) requiere completar el flujo OAuth **una vez** de forma interactiva; el servidor MCP cachea sus tokens en su propio store y luego corre headless. Registrar el paquete MCP de Calendar candidato para v1 y marcar "pendiente: verificar persistencia de token tras reinicio headless". Confirma la premisa: **cero dependencia de los connectors de la cuenta claude.ai.**

- [ ] **Step 5: Commit**

```bash
git add spikes/fase0/06_mcp_local.py spikes/fase0/FINDINGS.md
git commit -m "spike(fase0): MCP local configurado (Playwright) headless + decision OAuth-MCP"
```

---

## Cierre de Fase 0

Cuando las 7 tareas estén en PASS (o con hallazgos registrados), `spikes/fase0/FINDINGS.md` es el insumo para el plan de **v1**. Revisar especialmente: TTFA real vs 1.5 s, calidad de español de AssemblyAI, límites Pro Max observados, si WASAPI necesitó device manual, y la estrategia de wake-word (no nativa en Pipecat). Con esos datos se invoca de nuevo `superpowers:writing-plans` para el plan de v1.
