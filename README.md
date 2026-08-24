# Maia

Asistente de IA por voz, en español, cuyo cerebro es el **harness completo de Claude Code**
(vía Claude Agent SDK, autenticado con suscripción Claude Pro Max — sin API key). Acceso real a
la vida del usuario mediante tool calling: shell/OS (Bash), web (Playwright MCP + WebSearch/
WebFetch) y servicios personales (Calendar, Gmail, …) por MCP.

**Estado:** diseño aprobado. Implementación arranca en Windows nativo por Fase 0.

## Stack

| Capa | Elección |
|---|---|
| Plataforma | Windows nativo |
| Orquestación de voz | [Pipecat](https://github.com/pipecat-ai/pipecat) |
| STT | Deepgram Flux (español) |
| TTS | ElevenLabs Flash v2.5 (español) |
| Wake word / VAD / barge-in | Pipecat nativo (wake word: "Maia") |
| Cerebro | Claude Code harness vía `claude-agent-sdk` (`ClaudeSDKClient` persistente) |
| Auth cerebro | Suscripción Claude Pro Max (`CLAUDE_CODE_OAUTH_TOKEN`) |
| Tools | Bash, WebSearch/WebFetch, MCP (Playwright, Calendar, Gmail, timers) |
| Confirmación | Hook `PreToolUse` / `canUseTool` — "sí" hablado antes de acciones que cambian estado |

## Diseño

Spec completo: [`docs/superpowers/specs/2026-08-15-maia-voice-assistant-design.md`](docs/superpowers/specs/2026-08-15-maia-voice-assistant-design.md)

## Objetivo de latencia

Primera sílaba hablada **<1.5s** por turno (streaming por frase + relleno hablado + sesión
persistente sin cold-start).

## Licencia

[GNU AGPL-3.0-or-later](LICENSE) — © S-kippie.
