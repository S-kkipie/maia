"""Capa de reflejo instantáneo (Gemini Flash-Lite).

Decide en ~0.5s si responde directo (charla simple) o delega al cerebro agéntico
(Claude). Reemplaza el relleno canned: para 'Hola' responde 'Hola', y para tareas
que requieren pasos/herramientas dice un relleno corto y marca delegación.
"""
from google import genai

PERSONA = (
    "Eres Maia, una asistente de voz mujer en español: cálida, natural, breve, tuteas. "
    "Tus respuestas se van a ESCUCHAR, así que: una sola frase corta, sin markdown, sin listas, sin emojis."
)

INSTRUCCION = (
    PERSONA
    + "\n\nDecide sobre el mensaje del usuario:\n"
    "- SOLO si es pura charla o algo que sabes de memoria al instante (saludo, gracias, cómo estás, "
    "una opinión breve, un dato general que ya conoces): respóndelo directo y termina con [FIN].\n"
    "- Si el usuario te pide HACER algo o requiere buscar/datos actuales — por ejemplo: poner un timer o "
    "recordatorio, cambiar tu voz, buscar en internet, la hora/clima/noticias, abrir, enviar, ejecutar, "
    "calcular, o cualquier acción con herramientas o varios pasos: NUNCA digas que ya lo hiciste (tú NO "
    "puedes ejecutar acciones). Responde SOLO un relleno corto y natural ('Déjame ver.', 'Un momento.', "
    "'Claro, un segundo.') y termina con [CLAUDE].\n"
    "Ante la MÍNIMA duda usa [CLAUDE]. No inventes datos. Responde SIEMPRE en español."
)


class Reflex:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite"):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def respond(self, user_text: str) -> tuple[str, bool]:
        """Devuelve (texto_a_hablar, needs_claude)."""
        try:
            r = await self._client.aio.models.generate_content(
                model=self._model,
                contents=f"{INSTRUCCION}\n\nUsuario: {user_text}\nMaia:",
            )
            txt = (r.text or "").strip()
        except Exception:
            return ("Déjame ver.", True)  # ante fallo del reflejo, delega a Claude
        needs_claude = "[CLAUDE]" in txt
        txt = txt.replace("[CLAUDE]", "").replace("[FIN]", "").strip()
        if not txt:
            txt = "Déjame ver."
            needs_claude = True
        return (txt, needs_claude)
