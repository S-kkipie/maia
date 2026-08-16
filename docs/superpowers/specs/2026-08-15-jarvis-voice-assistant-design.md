# Jarvis — Voice Assistant Harness

**Fecha:** 2026-08-15
**Estado:** Diseño aprobado, pendiente de plan de implementación

## 1. Objetivo

Asistente de IA por voz ("Jarvis") que se sienta como un asistente inteligente real capaz de
ayudar a manejar la vida/trabajo del usuario. Habla y entiende **español nativo**. Usa
**tool calling** vía MCP para operar sobre servicios reales (calendario, email, etc.). El
cerebro es Claude, autenticado con la suscripción **Claude Pro Max** existente. La prioridad
número uno es la **experiencia de usuario**: baja latencia percibida, interrupción natural, y
seguridad ante acciones destructivas.

**No-objetivos (v1):** cobertura total de "toda mi vida"; multi-dispositivo/remoto; voz
offline; el modelo CSM de Sesame (descartado, ver §9).

## 2. Contexto y decisiones clave

- **Cerebro = Claude Agent SDK (Python).** Envuelve el mismo loop agéntico de Claude Code:
  MCP nativo, hooks de ciclo de vida, sesión persistente, gestión de contexto. Autentica con
  `~/.claude/.credentials.json` (suscripción Pro Max) — **sin API key, sin costo marginal de
  cerebro**. No construimos el harness de agente; lo envolvemos.
- **Capa de voz = Pipecat.** Framework de voz por pipeline (Daily). Resuelve VAD, turn
  detection, barge-in a nivel de frame, y streaming de TTS — el trabajo que a implementaciones
  a mano les cuesta semanas.
- **STT = Deepgram Flux.** Streaming, hecho para agentes conversacionales, interrupción
  natural, español nativo.
- **TTS = ElevenLabs Flash v2.5**, plan mensual de pago. ~75ms TTFB, español nativo. Un solo
  backend TTS.
- **Un solo proceso Python asyncio**, dos módulos con frontera limpia: `voice` (Pipecat I/O) y
  `brain` (Agent SDK). El stack API-only elimina la GPU, así que no hace falta separar procesos
  ni sockets.

## 3. Arquitectura

```
┌─ proceso jarvis (asyncio) ─────────────────────────────────┐
│                                                            │
│  módulo voice (Pipecat pipeline)                           │
│    mic → wake word "Jarvis" → VAD/turn detection           │
│        → Deepgram Flux (STT, español)                      │
│    spk ← ElevenLabs Flash (TTS, español)                   │
│    barge-in / endpointing: nativos del framework           │
│                     ↕  (frames de texto + eventos)         │
│  módulo brain (custom Pipecat LLM service)                 │
│    → sesión persistente del Claude Agent SDK               │
│    → hook PreToolUse: gate de confirmación                 │
│    → MCP servers: Calendar, Gmail, timers…                 │
│    → auth: suscripción Pro Max (credentials.json)          │
└────────────────────────────────────────────────────────────┘
```

**Frontera de módulos:** `voice` solo mueve audio↔texto y emite eventos (wake, transcript,
barge_in, speech_done). `brain` solo consume texto y produce texto/decisiones de tool. El
`brain` no importa nada de audio → se testea entero con transcripts de entrada y un MCP mock.

## 4. Flujo de un turno

1. Usuario dice "Jarvis" → wake word activa la escucha.
2. Usuario habla → Deepgram transcribe en streaming; VAD/turn detection marca fin de turno.
3. `brain` entrega el texto a la sesión persistente del Agent SDK.
4. Apenas Claude decide usar una tool, `brain` emite un **relleno hablado** ("dame un segundo,
   reviso tu calendario") → ElevenLabs empieza a hablar de inmediato.
5. Claude hace stream de tokens → `brain` corta por frase → ElevenLabs habla frase por frase
   mientras Claude sigue generando.
6. Si la tool cambia estado, el **gate de confirmación** (§6) interrumpe antes de ejecutar.
7. Usuario puede hablar encima en cualquier momento → barge-in corta el TTS y reinicia el turno.

## 5. Camino único al cerebro

**Todos los turnos van a Claude** (decisión del usuario: sin router/clasificador que se
equivoque). Optimización de latencia y cuota por configuración, no por bifurcación:

- Modelo por defecto **Haiku** para conversación; se escala a Sonnet solo cuando la tarea lo
  requiere (lo decide el propio agente / política de sistema).
- Reasoning bajo por defecto.
- Sesión **persistente** (no cold-start por turno) — el error de latencia #1 en el prior art.
- Streaming por frase + relleno hablado → primera sílaba objetivo **<1.5s** (vs 5-12s del
  prior art de referencia).

## 6. Gate de confirmación (seguridad)

Sin pantalla, la voz no puede ejecutar acciones destructivas por error o por mala transcripción.
Implementado como **hook `PreToolUse` determinístico del Agent SDK** (no depende del prompt):

- Tool clasificada **solo-lectura** (leer agenda, buscar/resumir email) → ejecuta directo.
- Tool que **cambia estado** (enviar, borrar, crear, agendar, modificar) → el hook pausa,
  Jarvis verbaliza la acción concreta ("voy a enviar este correo a X con asunto Y, ¿confirmas?")
  y espera un "sí" hablado antes de ejecutar.

La clasificación read-only vs state-changing es una tabla explícita por tool, no inferida.

## 7. Alcance v1 y tools

v1 = **loop de voz funcionando + cerebro persistente + gate + 3 tools reales**. La arquitectura
permite enchufar tools nuevas sin tocar el core.

Tools candidatas v1:
- **Calendar**: leer agenda (read-only) + crear evento (con confirmación).
- **Gmail**: leer/resumir (read-only) + redactar borrador (con confirmación; enviar queda v2 o
  detrás de doble confirmación).
- **Timers/recordatorios** locales.

Todo lo demás (Slack, Notion, CRM, control de OS, etc.) = v2+.

## 8. Fase 0 — verificación de riesgos (antes de construir v1)

Riesgos que se prueban primero porque pueden cambiar decisiones:

1. **Auth de MCP headless.** Los MCP de claude.ai (Gmail, Calendar) están atados al login
   interactivo de claude.ai. Verificar si el Agent SDK los usa headless. Si no → MCP locales con
   OAuth propio (Google Calendar/Gmail API). Define qué tools entran realmente a v1.
2. **Audio en WSL2.** WSLg + PulseAudio (`PULSE_SERVER=unix:/mnt/wslg/PulseServer`) con
   `PulseAudioRDPSource`/`Sink` disponibles. Probar captura + reproducción de baja latencia con
   `sounddevice`/Pipecat. Fallback: capa de audio como proceso nativo Windows.
3. **Latencia real end-to-end.** Medir TTFA de un turno completo con la sesión persistente antes
   de invertir en features. Confirmar que <1.5s es alcanzable con este stack.
4. **Agent SDK + suscripción headless.** Confirmar que `claude-agent-sdk` en Python autentica
   con `credentials.json` sin API key y que el uso intenso no revienta límites de Pro Max.

## 8b. Selección de frameworks por adopción (jul 2026)

Elección anclada en estrellas/actividad de GitHub, no en preferencia:

| Repo | Stars | Veredicto |
|---|---|---|
| `pipecat-ai/pipecat` | ~13.4k | **Elegido** (capa de voz). El más estrellado y activo, Python-first, mayor librería de integraciones. |
| `livekit/agents` | ~11.4k | Alternativa para remoto/telefonía/multi-device. Overkill para desktop single-user. |
| `TEN-framework` | ~10.9k | Orquestación multimodal en grafo; complejidad innecesaria. |
| `openinterpreter/01` | alto (turnkey) | Cerebro = Open Interpreter, no la suscripción Claude → no encaja. |
| `mcp-use-voice-assistant` | 34 | Claude solo por API key. Referencia. |
| `Kevthetech143/claude-voice` | 2 | Arquitectura idéntica a la nuestra pero demo sin licencia/incompleto → leer para ideas, **no forkear**. |

El cerebro (Agent SDK) no tiene alternativa: es el único camino que autentica con la
suscripción Pro Max en vez de API por token.

## 9. Descartado: CSM (Sesame)

Petición original. Descartado tras análisis: CSM-1B es **solo TTS contextual en inglés**, no
conversacional; el modelo bueno de las demos de Sesame no se liberó; requiere finetune para
español; y con presupuesto para API de voz, ElevenLabs da mejor voz, en español, más rápido. Lo
único que CSM aportaba (prosodia condicionada al turno previo) no compensa inglés + finetune +
GPU. Puede volver como backend opcional si algún día se finetunea a español.

## 10. Testing

- **`brain` sin voz ni GPU:** unit tests con transcripts de entrada + MCP mock. Toda la lógica de
  gate, clasificación read/write, chunking por frase y política de relleno corre en CI en ms.
- **`voice` integración:** pipeline de Pipecat con STT/TTS reales, prueba de barge-in y
  wake word.
- **Métrica desde día 1:** time-to-first-audio (TTFA) por turno, registrada y monitoreada.

## 11. Costos

- Claude (cerebro): **$0 marginal** — cubierto por Pro Max existente. Riesgo: límites de uso en
  operación siempre-activa (mitigado por Haiku + reasoning bajo).
- ElevenLabs Flash: **plan mensual de pago** (Starter/Creator según volumen; ~1000 créditos ≈
  1 min de voz; Flash = 0.5 créditos/carácter).
- Deepgram Flux STT: uso por minuto, aparte.

## 12. Stack

| Capa | Elección |
|---|---|
| Orquestación de voz | Pipecat |
| STT | Deepgram Flux (español) |
| TTS | ElevenLabs Flash v2.5 (español, plan de pago) |
| Wake word / VAD / barge-in | Pipecat nativo |
| Cerebro | Claude Agent SDK (Python), sesión persistente |
| Auth cerebro | Suscripción Pro Max (`~/.claude/.credentials.json`) |
| Tools | MCP (Calendar, Gmail, timers en v1) |
| Runtime | Un proceso Python 3.12 asyncio |
| Confirmación | Hook `PreToolUse` del Agent SDK |
