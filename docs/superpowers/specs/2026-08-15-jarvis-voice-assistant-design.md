# Jarvis — Voice Assistant Harness

**Fecha:** 2026-08-15
**Estado:** Diseño aprobado, pendiente de plan de implementación
**Plataforma objetivo:** Windows nativo

## 1. Objetivo

Asistente de IA por voz ("Jarvis") que se sienta como un asistente inteligente real capaz de
ayudar a manejar la vida/trabajo del usuario. Habla y entiende **español nativo**. El cerebro es
**el harness completo de Claude Code** (no una app recortada), con acceso a shell/OS, web, y
servicios personales vía tool calling + MCP. Autentica con la **suscripción Claude Pro Max**
existente. Prioridad #1: **experiencia de usuario** — baja latencia percibida, interrupción
natural, seguridad ante acciones destructivas.

**No-objetivos (v1):** cobertura total de "toda mi vida"; multi-dispositivo/remoto; voz offline;
GUI computer-use (clic en apps de escritorio) — se pospone; el modelo CSM de Sesame (descartado,
§9).

## 2. Decisión central: el cerebro ES Claude Code

**El "cerebro" es el harness interno de Claude Code, manejado por código vía el Claude Agent
SDK (`claude-agent-sdk`, Python).** Verificado como autoritativo (ago 2026): el Agent SDK expone
el **mismo motor** que Claude Code interactivo — idénticas tools built-in (Bash, Read/Write/Edit,
Grep, Glob, WebSearch, WebFetch, subagentes), soporte MCP completo, y hooks (PreToolUse, etc.).
No es una versión reducida; es Claude Code como librería.

- **Auth por suscripción, sin API key.** Confirmado en la máquina: `~/.claude/.credentials.json`
  contiene `claudeAiOauth` (`subscriptionType`, `rateLimitTier`). Si `ANTHROPIC_API_KEY` no está
  seteada, el SDK usa la suscripción Pro Max. Para always-on: `claude setup-token` →
  `CLAUDE_CODE_OAUTH_TOKEN`. **Costo marginal de cerebro = $0.**
- **Sesión persistente:** un `ClaudeSDKClient` abierto por toda la sesión de voz → sin cold-start,
  contexto vivo entre turnos (elimina el error de latencia #1 del prior art).
- **Streaming token a token:** `ClaudeAgentOptions(include_partial_messages=True)` → `StreamEvent`
  con `text_delta` en eventos `content_block_delta`.

## 3. Acceso a la vida del usuario (tools)

| Capacidad | Mecanismo | Estado |
|---|---|---|
| Shell / OS completo | Tool **Bash** (Git Bash/PowerShell en Windows) | ✅ built-in |
| Web use (navegar/automatizar) | **Playwright MCP** + `WebSearch`/`WebFetch` | ✅ (Playwright ya conectado en el entorno) |
| Servicios personales | MCP connectors (Calendar, Gmail, etc.) | ✅ v1 |
| GUI computer-use (clic en apps escritorio) | MCP Windows (pyautogui/screenshot) | ⏸ pospuesto; viable en Windows nativo a futuro |

El `computer-use` oficial de Anthropic es solo macOS/interactivo → no se usa. En Windows nativo,
si algún día se requiere GUI-clicking, entra un MCP de comunidad como fase aparte. Para v1, Bash
(todo el OS) + Playwright (toda la web) + MCP (servicios) cubren el acceso a la vida.

## 4. Arquitectura

```
┌─ proceso jarvis (Windows nativo, Python asyncio) ──────────┐
│                                                            │
│  módulo voice (Pipecat pipeline)                           │
│    mic → wake word "Jarvis" → VAD/turn detection           │
│        → Deepgram Flux (STT, español)                      │
│    spk ← ElevenLabs Flash (TTS, español)                   │
│    barge-in / endpointing: nativos del framework           │
│                     ↕  (texto + eventos)                   │
│  módulo brain (custom Pipecat LLM service)                 │
│    → ClaudeSDKClient persistente (harness de Claude Code)  │
│    → hook PreToolUse: gate de confirmación (§6)            │
│    → tools: Bash, WebSearch/WebFetch, MCP (Playwright,     │
│             Calendar, Gmail, timers…)                      │
│    → auth: Pro Max (CLAUDE_CODE_OAUTH_TOKEN / credentials) │
└────────────────────────────────────────────────────────────┘
```

**Un solo proceso** Python asyncio (el stack es API-only para voz → sin GPU → no hace falta
separar procesos). Dos módulos con frontera limpia: `voice` mueve audio↔texto y emite eventos
(wake, transcript, barge_in, speech_done); `brain` consume texto y produce texto/decisiones de
tool vía `ClaudeSDKClient`. `brain` no importa audio → se testea con transcripts + MCP mock.

## 5. Flujo de un turno

1. Usuario dice "Jarvis" → wake word activa la escucha.
2. Usuario habla → Deepgram transcribe en streaming; VAD/turn detection marca fin de turno.
3. `brain` inyecta el texto en el `ClaudeSDKClient` persistente.
4. Apenas Claude decide usar una tool, `brain` emite un **relleno hablado** ("dame un segundo,
   reviso tu calendario") → ElevenLabs habla de inmediato.
5. Claude hace stream de tokens → `brain` corta por frase → ElevenLabs habla frase por frase
   mientras Claude sigue generando.
6. Si la tool cambia estado, el **gate de confirmación** (§6) interrumpe antes de ejecutar.
7. Barge-in: el usuario habla encima → corta el TTS y reinicia el turno.

## 6. Camino único al cerebro

**Todos los turnos van a Claude** (sin router/clasificador que se equivoque). Optimización por
config, no por bifurcación: modelo por defecto rápido (Haiku) para conversación, escala a Sonnet
cuando la tarea lo pide; reasoning bajo por defecto; sesión persistente. Primera sílaba objetivo
**<1.5s** (vs 5-12s del prior art), vía streaming por frase + relleno hablado.

## 7. Gate de confirmación (seguridad)

Sin pantalla, la voz no puede ejecutar acciones destructivas por error o mala transcripción.
Mecanismo: **hook `PreToolUse` / callback `canUseTool` del Agent SDK** (determinístico, no
depende del prompt). El callback recibe `tool_name` + `tool_input`, y retorna
`hookSpecificOutput.permissionDecision = "allow" | "deny"`.

- Tool **solo-lectura** (leer agenda, buscar/resumir email, `WebFetch`) → allow directo.
- Tool que **cambia estado** (enviar, borrar, crear, agendar; `Bash` con comandos mutantes) → el
  hook pausa, llama al módulo `voice` para verbalizar la acción concreta ("voy a enviar este
  correo a X, ¿confirmas?"), espera "sí" hablado, y recién allow/deny.

La clasificación read-only vs state-changing es una tabla explícita por tool + patrón de comando
Bash, no inferida. (Nota: timeout por defecto del hook 600s — suficiente para confirmación por
voz.)

## 8. Alcance v1 y tools

v1 = **loop de voz funcionando + `ClaudeSDKClient` persistente + gate + 3 tools reales**. La
arquitectura permite enchufar tools sin tocar el core.

Tools candidatas v1:
- **Calendar**: leer agenda (read-only) + crear evento (con confirmación).
- **Gmail**: leer/resumir (read-only) + redactar borrador (con confirmación; enviar → v2 o doble
  confirmación).
- **Timers/recordatorios** locales.

Bash y WebSearch/WebFetch/Playwright están disponibles desde el inicio (son built-in/ya
conectados), sujetos al gate. Slack, Notion, CRM, GUI computer-use = v2+.

## 8b. Fase 0 — verificación de riesgos (antes de v1)

1. **Runtime Windows nativo.** Python 3.12 en Windows + `claude` CLI Windows autenticado
   (`claude /login` o `setup-token`) + `claude-agent-sdk` instalado + `ClaudeSDKClient` conecta y
   hace un turno con streaming. Verificar que la tool Bash funciona en Windows (Git Bash).
2. **Auth suscripción headless.** `ClaudeSDKClient` corre sin `ANTHROPIC_API_KEY`, usando la
   suscripción. Probar `CLAUDE_CODE_OAUTH_TOKEN` para always-on. Verificar límites de uso Pro Max
   en operación intensa.
3. **Audio Windows (WASAPI).** Captura mic + reproducción de baja latencia con
   `sounddevice`/Pipecat en Windows nativo. (Riesgo bajo — sin el problema RDP de WSL2.)
4. **Latencia real end-to-end.** Medir TTFA de un turno completo con sesión persistente. Confirmar
   <1.5s alcanzable.
5. **Auth MCP headless.** Que los MCP (Playwright, Calendar, Gmail) corran bajo el SDK sin login
   interactivo; si un connector no re-autentica headless → MCP local con OAuth propio.

## 8c. Selección de frameworks por adopción (jul 2026)

| Repo | Stars | Veredicto |
|---|---|---|
| `pipecat-ai/pipecat` | ~13.4k | **Elegido** (capa de voz). El más estrellado y activo, Python-first, mayor librería de integraciones. |
| `livekit/agents` | ~11.4k | Alternativa para remoto/telefonía/multi-device. Overkill para desktop single-user. |
| `TEN-framework` | ~10.9k | Orquestación multimodal en grafo; complejidad innecesaria. |
| `openinterpreter/01` | alto (turnkey) | Cerebro = Open Interpreter, no la suscripción Claude → no encaja. |
| `mcp-use-voice-assistant` | 34 | Claude solo por API key. Referencia. |
| `Kevthetech143/claude-voice` | 2 | Arquitectura idéntica a la nuestra pero demo sin licencia/incompleto → leer para ideas, **no forkear**. |

El cerebro (Claude Code vía Agent SDK) no tiene alternativa: es el único camino que autentica con
la suscripción Pro Max en vez de API por token.

## 9. Descartado: CSM (Sesame)

Petición original. Descartado tras análisis: CSM-1B es **solo TTS contextual en inglés**, no
conversacional; el modelo bueno de las demos de Sesame no se liberó; requiere finetune para
español; y con presupuesto para API de voz, ElevenLabs da mejor voz, en español, más rápido. Lo
único que aportaba (prosodia condicionada al turno previo) no compensa inglés + finetune + GPU.
Puede volver como backend opcional si se finetunea a español.

## 10. Testing

- **`brain` sin voz:** unit tests con transcripts de entrada + MCP mock. Toda la lógica de gate,
  clasificación read/write, chunking por frase y política de relleno corre en CI en ms.
- **`voice` integración:** pipeline Pipecat con STT/TTS reales; prueba de barge-in y wake word.
- **Métrica desde día 1:** time-to-first-audio (TTFA) por turno, registrada.

## 11. Costos

- Claude (cerebro): **$0 marginal** — cubierto por Pro Max existente. Riesgo: límites de uso en
  operación always-on (mitigado por Haiku + reasoning bajo).
- ElevenLabs Flash: **plan mensual de pago** (~1000 créditos ≈ 1 min; Flash = 0.5 créditos/char).
- Deepgram Flux STT: uso por minuto, aparte.

## 12. Stack

| Capa | Elección |
|---|---|
| Plataforma | Windows nativo |
| Orquestación de voz | Pipecat |
| STT | Deepgram Flux (español) |
| TTS | ElevenLabs Flash v2.5 (español, plan de pago) |
| Wake word / VAD / barge-in | Pipecat nativo |
| Audio I/O | sounddevice / WASAPI |
| Cerebro | Claude Code harness vía `claude-agent-sdk` (`ClaudeSDKClient` persistente) |
| Auth cerebro | Suscripción Pro Max (`CLAUDE_CODE_OAUTH_TOKEN` / `credentials.json`) |
| Tools | Bash, WebSearch/WebFetch, MCP (Playwright + Calendar, Gmail, timers en v1) |
| Runtime | Un proceso Python 3.12 asyncio |
| Confirmación | Hook `PreToolUse` / `canUseTool` del Agent SDK |
