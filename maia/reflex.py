"""Capa de reflejo instantáneo (Gemini Flash-Lite).

Decide en ~0.5s si responde directo (charla simple) o delega al cerebro agéntico
(Claude). Reemplaza el relleno canned: para 'Hola' responde 'Hola', y para tareas
que requieren pasos/herramientas dice un relleno corto y marca delegación.
"""
from google import genai

PERSONA = (
    "Eres Maia, una asistente de voz mujer en español: cálida, natural, breve, tuteas. "
    "Tu usuario es Adrián Issac (correo issacysofia@gmail.com). "
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


HUMANIZAR = (
    PERSONA
    + "\n\nAbajo va el resultado CRUDO del cerebro (puede tener markdown, URLs, listas, siglas, "
    "y ser largo). Reescríbelo como lo diría Maia HABLANDO: español, natural, cálido y CORTO "
    "(máximo 3 o 4 frases, lo esencial). Reglas estrictas:\n"
    "- Sin URLs ni enlaces. Si hay fuentes, di solo el nombre del sitio ('según Improvado', 'lo vi en MNTN').\n"
    "- Sin markdown, sin listas, sin viñetas, sin corchetes.\n"
    "- No deletrees siglas: exprésalas de forma pronunciable o cámbialas por su significado "
    "(por ejemplo 'A/B' -> 'pruebas comparativas', 'SEO' -> 'posicionamiento en buscadores').\n"
    "- Ve al grano; si el tema es amplio, resume lo clave y ofrece contar más si quiere."
)


class Reflex:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite"):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def heartbeat_phrase(self, user_text: str) -> str:
        """Frase de progreso dinámica y variada mientras Claude trabaja."""
        try:
            r = await self._client.aio.models.generate_content(
                model=self._model,
                contents=(
                    f'Eres Maia, asistente de voz en español, cálida. El usuario pidió: "{user_text}". '
                    "Sigues trabajando en ello y AÚN no terminas. Di UNA sola frase muy corta, natural y "
                    "VARIADA para avisar que sigues en ello (puedes referirte a lo que buscas). "
                    "No repitas siempre lo mismo ni uses 'un momento' genérico. Solo la frase, sin comillas."
                ),
            )
            return (r.text or "").strip().strip('"') or "Sigo en ello."
        except Exception:
            return "Sigo en ello."

    async def progress_update(self, user_text: str, claude_so_far: str) -> str:
        """Aviso de progreso basado en lo que Claude lleva hecho (no genérico)."""
        if not claude_so_far.strip():
            return await self.heartbeat_phrase(user_text)
        try:
            r = await self._client.aio.models.generate_content(
                model=self._model,
                contents=(
                    f'Eres Maia, asistente de voz en español, cálida. El usuario pidió: "{user_text}". '
                    "Estás trabajando y AÚN no terminas. Esto es tu progreso REAL hasta ahora "
                    f"(lo que has visto/hecho):\n---\n{claude_so_far[-1500:]}\n---\n"
                    "Da UNA sola frase MUY corta y natural avisando cómo vas, BASADA en ese progreso real "
                    "(menciona brevemente lo último que viste o hiciste). Varía, no repitas 'un momento' "
                    "genérico. Solo la frase, sin comillas."
                ),
            )
            return (r.text or "").strip().strip('"') or "Sigo en ello."
        except Exception:
            return "Sigo en ello."

    async def full_answer(self, user_text: str) -> str:
        """Respuesta completa por Gemini (fallback si Claude no está disponible)."""
        try:
            r = await self._client.aio.models.generate_content(
                model=self._model,
                contents=(
                    f"{PERSONA}\n\nResponde de forma útil y natural, en español, breve y hablada, "
                    f"a esto: {user_text}\nMaia:"
                ),
            )
            return (r.text or "").strip() or "Perdona, ahora no puedo responder eso."
        except Exception:
            return "Perdona, ahora mismo no puedo responder."

    async def speak_result(self, user_text: str, claude_text: str, activity: str) -> str:
        """Narra el RESULTADO de un turno agéntico interpretando texto + acciones de tools.

        Clave cuando Claude casi no escribe texto y solo ejecuta herramientas: en vez de
        quedarse callada, Maia dice qué hizo y qué encontró/pasó.
        """
        try:
            r = await self._client.aio.models.generate_content(
                model=self._model,
                contents=(
                    PERSONA
                    + f'\n\nEl usuario pidió: "{user_text}".\n'
                    "Esto es TODO lo que hiciste en este turno: tus frases y las herramientas "
                    "que ejecutaste con sus resultados (en orden). Las capturas de pantalla se "
                    "marcan como '(captura de pantalla)'.\n---\n"
                    f"{activity[-3500:]}\n---\n"
                    f'Texto final que redactaste (puede estar vacío o incompleto): "{claude_text[-800:]}"\n\n'
                    "Dile al usuario, HABLANDO en español, en 1 a 3 frases cortas, el RESULTADO: "
                    "qué hiciste y qué encontraste o pasó. Si completaste la acción, dilo natural "
                    "('Listo, ya…', 'Hecho', 'Encontré…'). Si el texto final ya lo resume, básate "
                    "en él. Usa SOLO lo que aparece arriba, no inventes. Sin markdown, sin URLs, "
                    "sin deletrear siglas. Solo la respuesta hablada."
                ),
            )
            txt = (r.text or "").strip()
            return txt or (claude_text.strip() or "Listo.")
        except Exception:
            return claude_text.strip() or "Listo, ya lo hice."

    async def humanize(self, raw: str) -> str:
        """Reescribe la salida cruda de Claude en una respuesta hablada, corta y limpia."""
        try:
            r = await self._client.aio.models.generate_content(
                model=self._model,
                contents=f"{HUMANIZAR}\n\nResultado crudo:\n{raw}\n\nMaia (hablando):",
            )
            return (r.text or "").strip() or raw
        except Exception:
            return raw

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
