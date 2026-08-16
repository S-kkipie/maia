---
name: computer-use
description: Usar cuando controles la computadora (escritorio Windows) con las tools de 'pc' (screenshot, click, type_text, press_keys, scroll, drag). Enseña a actuar en pasos pequeños, verificando cada acción, para no perderte.
---

# Computer use disciplinado

Controlas una PC Windows real con las tools `mcp__pc__*`. El riesgo es actuar a ciegas y perderte. Sigue SIEMPRE este ciclo: **ver → planear → un paso → verificar**.

## Ciclo obligatorio

1. **Ver primero.** Toma `screenshot` antes de cualquier acción. Lee la pantalla: ventana activa, campos, botones, dónde está el foco.
2. **Un paso a la vez.** Haz UNA acción (un clic, un texto, una tecla). No encadenes 5 acciones sin mirar.
3. **Verifica.** Cada acción (`click`, `type_text`, `press_keys`, `scroll`, `drag`) te devuelve una captura nueva: MÍRALA. ¿Pasó lo que esperabas? Si no, reevalúa; no sigas al siguiente paso a ciegas.
4. **Coordenadas.** Da x,y en la escala de la ÚLTIMA captura (el texto de cada captura te dice su tamaño). Apunta al CENTRO del elemento.

## Reglas

- **Escribir:** primero `click` en el campo para enfocarlo, luego `type_text`. Nunca escribas sin haber enfocado el campo.
- **Atajos:** usa `press_keys` para 'enter', 'tab', 'esc', 'win', 'alt+tab', 'ctrl+c', etc. Abrir el menú Inicio = `press_keys` 'win' y luego escribir el nombre de la app.
- **Web:** para tareas de navegador prefiere las tools de Playwright (más fiables que clic a ciegas). Usa `pc` para apps de escritorio, o cuando el navegador no baste.
- **Si te pierdes:** toma `screenshot`, ubícate, y si hace falta `press_keys` 'esc' o 'alt+tab' para volver a un estado conocido. Di en voz alta (respuesta corta) qué estás viendo y qué harás.
- **Freno:** si algo se ve mal o peligroso (borrar, pagar, enviar), detente y confirma con el usuario antes de actuar.
- **Paciencia:** tras abrir una app o cargar una página, toma otra `screenshot` para dar tiempo a que aparezca antes de seguir.

## Ejemplo (abrir Bloc de notas y escribir)

1. `screenshot` — veo el escritorio.
2. `press_keys` 'win' — se abre Inicio (verifico en la captura).
3. `type_text` "bloc de notas" — aparece el resultado.
4. `press_keys` 'enter' — abre la app (verifico que se abrió).
5. `click` en el área de texto — enfoco.
6. `type_text` "Hola" — verifico que se escribió.
