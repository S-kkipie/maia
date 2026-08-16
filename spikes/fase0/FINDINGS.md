# Fase 0 — Hallazgos

Cada tarea registra: fecha, veredicto (PASS/FALLA/PARCIAL), métricas y notas.

## Task 2 — SDK persistente + streaming + Bash
- Veredicto: PASS
- TTFT (s): 8.115s (turno 1; incremental por content_block_delta, confirma streaming real, no espera-todo)
- ¿Bash ejecutó? ¿Git Bash o PowerShell?: Sí, tools=['Bash'] y el texto del turno 1 contiene `hola-maia`. El script (verbatim del brief) sólo captura el nombre de la tool, no su input, por lo que el shell exacto no es observable directamente en la salida capturada. Inferencia de alta confianza: Claude Code (el proceso `claude` que el SDK spawnea) usa Git Bash en Windows (no WSL, no PowerShell) para la tool Bash; Git for Windows está instalado en este equipo (`C:\Program Files\Git\bin\bash.exe` existe), por lo que es la ruta usada.
- ¿Contexto persistió (turno 2)?: Sí. Turno 2 respondió "Me pediste que ejecutara el comando: `echo hola-maia`" sin repetir el prompt — contexto retenido en el mismo `ClaudeSDKClient`.
- Notas: `permission_mode="bypassPermissions"` funcionó tal cual está escrito en el brief — no lanzó excepción y el turno 1 no se bloqueó pidiendo permiso interactivo (corrió headless dentro del timeout acotado de 120s, terminó en ~8s). Conectó sin `ANTHROPIC_API_KEY` (guard de `_env.py` confirma que no está seteada), usando la suscripción vía `~/.claude/.credentials.json`. Esto resuelve el riesgo §8b.1: el SDK sí puede correr Bash no interactivo en Windows con `bypassPermissions`; el gate de confirmación real de v1 deberá construirse aparte (no viene gratis de un permission_mode distinto).

## Task 3 — Auth suscripción + límites
- Veredicto: PASS
- subscriptionType: `max` / rateLimitTier: `default_claude_max_5x` / accessToken vigente: `True`
- Turnos OK de 20 / errores: 20/20 OK, 0 errores
- Latencia media (s): 1.698s
- Notas (rate-limit observado): Sin errores de auth ni de rate-limit en las 20 llamadas secuenciales (ráfaga corta, modelo `claude-haiku-4-5-20251001`). El SDK corrió headless enteramente por suscripción (`~/.claude/.credentials.json`), sin `ANTHROPIC_API_KEY` seteada (guard de `_env.py` lo confirma). Resuelve §8b.2 para el caso de ráfaga corta: no se observó throttling con `default_claude_max_5x`. Queda pendiente un sondeo de uso sostenido/prolongado (always-on real) para confirmar límites diarios/horarios, que esta prueba de 20 turnos cortos no cubre.
- Fallback de token para always-on (documentado, no ejecutado): para despliegue headless sin login interactivo, `claude setup-token` genera un `CLAUDE_CODE_OAUTH_TOKEN` de larga duración (1 año) que se exporta en el entorno y tiene precedencia sobre el login interactivo vía `credentials.json`. Marcado como "pendiente de probar en despliegue always-on".

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
