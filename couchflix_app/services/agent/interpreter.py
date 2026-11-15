"""Turns a natural-language request into Criteria. Rules engine by default; an LLM is optional."""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from ...domain.criteria import Criteria
from ...domain.models import GENRES, unaccent
from .llm import LLMClient

log = logging.getLogger("couchflix.agent")

GENRE_WORDS = {
    "horror": ["terror", "miedo", "horror", "susto"], "scifi": ["ciencia ficcion", "ciencia-ficcion", "sci-fi", "scifi", "espacial", "futurista"],
    "drama": ["drama"], "romance": ["romance", "romantic", "amor"], "adventure": ["aventura"],
    "family": ["familia", "ninos", "infantil", "peques"], "comedy": ["comedia", "gracios", "divertid", "risa"],
    "action": ["accion", "action"], "animation": ["animacion", "animad", "dibujos"], "documentary": ["documental"],
    "thriller": ["thriller", "suspense", "tension"], "fantasy": ["fantasia", "fantastic"], "mystery": ["misterio"],
    "crime": ["crimen", "policiaca", "mafia"], "war": ["belic", "guerra"], "western": ["western"], "history": ["historic"],
}
NUMBERS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "diez": 10}


def _num(token: str) -> int | None:
    return int(token) if token.isdigit() else NUMBERS.get(token)


def interpret_rules(text: str, platform_names: list[str], today: date | None = None) -> Criteria:
    today = today or date.today()
    t = " " + unaccent(text.lower()) + " "
    c = Criteria()
    c.genres = [g for g, words in GENRE_WORDS.items() if any(w in t for w in words)]
    if re.search(r"\b(series?|serial(es)?)\b", t):
        c.kind = "tv"
    elif re.search(r"\b(pelicula|peliculas|film|movie|cine)\b", t):
        c.kind = "movie"
    if m := re.search(r"(?:mas de|menos de|maximo|max|como mucho|no (?:dure|dura|pase)\w* (?:de|mas de))\s+(\w+)\s*(horas?|h\b|min)", t):
        n = _num(m.group(1))
        if n:
            c.max_runtime = n * 60 if m.group(2).startswith(("h")) else n
    if "hora y media" in t:
        c.max_runtime = 90
    elif re.search(r"\bcorta\b", t) and c.kind != "tv" and not c.max_runtime:
        c.max_runtime = 100
    if re.search(r"\bserie corta\b|\bserie breve\b", t):
        c.kind, c.max_seasons = "tv", 2
    if m := re.search(r"ultimos?\s+(\w+)\s+anos?", t):
        if n := _num(m.group(1)):
            c.year_from = today.year - n
    elif re.search(r"reciente|nuevo|actual|este ano|estreno", t):
        c.year_from = today.year - 2
    if "clasic" in t:
        c.year_to = 2000
    if re.search(r"bien valorad|buena nota|mejor valorad|aclamad|alta puntuacion|buenas criticas", t):
        c.min_rating = 7.5
    c.platforms = [n for n in platform_names if unaccent(n.lower()).rstrip("+ ") in t]
    if m := re.search(r"(?:parecid[oa]s? a|similar(?:es)? a|del estilo de|tipo|como)\s+(.+?)(?:[,.;?!]| pero | que | y |$)", t.strip()):
        title = m.group(1).strip()
        if title and not re.match(r"(un|una|algo|el|la|lo|los|las)\b", title):
            c.similar_to = _original_case(text, title)
    if re.search(r"sorprend|aleatori|lo que sea|cualquier cosa", t):
        c.surprise = True
    if re.search(r"diferente|distinto|salir de|fuera de mi", t):
        c.novelty = True
    if re.search(r"poco conocid|menos conocid|joya|oculta|desconocid", t):
        c.hidden = True
    if re.search(r"en familia|familiar|con ninos|con los ninos", t) and "family" not in c.genres:
        c.genres.append("family")
    if c.is_empty() and len(text.strip()) > 1:
        c.query = text.strip()
    c.genre_any = False
    return c


def _original_case(original: str, lowered_unaccented: str) -> str:
    """Recover the user's casing/accents for a captured title (matching on the unaccented text)."""
    plain = unaccent(original.lower())
    i = plain.find(lowered_unaccented)
    return original[i:i + len(lowered_unaccented)].strip() if i >= 0 else lowered_unaccented


SYSTEM = f"""Eres el intérprete de peticiones de COUCHFLIX, una app de recomendación de películas y series.
Convierte la petición del usuario en un objeto JSON (sin texto adicional) con estas claves opcionales:
kind ("movie"|"tv"), genres (lista de: {", ".join(GENRES)}), year_from, year_to (enteros), min_rating (0-10),
max_runtime (minutos), max_seasons (entero), platforms (nombres de plataformas), similar_to (título),
query (título buscado), surprise, novelty, hidden (booleanos). Omite lo que no se mencione. Año actual: {date.today().year}."""


def interpret(text: str, platform_names: list[str], llm: LLMClient | None) -> tuple[Criteria, str]:
    """Returns (criteria, agent) where agent is 'llm' or 'rules' — never presents rules as an LLM."""
    if llm:
        try:
            raw = llm.complete(SYSTEM, text)
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            return Criteria.from_dict(data), "llm"
        except Exception as exc:
            log.warning("LLM interpretation failed, using rules: %s", exc)
    return interpret_rules(text, platform_names), "rules"
