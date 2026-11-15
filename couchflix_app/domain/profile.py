"""Audiovisual profile: six dimensions, 0–100, learned from persisted signals."""
from __future__ import annotations

import math

# key, label, tagline, genres that feed the dimension
DIMENSIONS = [
    ("horror", "Terror", "Adicto a los sustos", ("horror",)),
    ("scifi", "Ciencia ficción", "Explorador galáctico", ("scifi",)),
    ("drama", "Drama", "Corazón de lágrima fácil", ("drama",)),
    ("romance", "Romance", "Romántico incurable", ("romance",)),
    ("adventure", "Aventuras", "Espíritu aventurero", ("adventure",)),
    ("family", "Familiar", "Modo manta y palomitas", ("family", "animation")),
]
DIM_GENRES = {key: genres for key, _, _, genres in DIMENSIONS}
DIM_META = {key: (label, tag) for key, label, tag, _ in DIMENSIONS}

RATING_WEIGHTS = {"love": 3.0, "like": 2.0, "dislike": -3.0}  # watched without rating is neutral (0)
SEARCH_WEIGHT, SEARCH_CAP = 0.3, 1.0   # a genre search is a weak signal and can never dominate
SATURATION = 4.0                       # raw score at which a dimension moves ~76 % of the way to 0 / 100
BASELINE = 50                          # every dimension starts neutral: likes push it up, dislikes pull it down
KNOWN_AT = 60                          # a dimension above this counts as a real preference


def compute_profile(rated: list[tuple[list[str], str]], searched: list[list[str]]) -> dict[str, int] | None:
    """rated: [(genres, rating)]; searched: [genres of each *user* search]. None when there are no signals yet
    (the profile is then shown at the neutral baseline). Each dimension is BASELINE ± signals, within 0..100."""
    raw = {key: 0.0 for key in DIM_GENRES}
    from_search = {key: 0.0 for key in DIM_GENRES}
    signals = 0
    for genres, rating in rated:
        weight = RATING_WEIGHTS.get(rating)
        if weight is None:
            continue
        signals += 1
        for key, dim_genres in DIM_GENRES.items():
            if set(genres) & set(dim_genres):
                raw[key] += weight
    for genres in searched:
        for key, dim_genres in DIM_GENRES.items():
            if set(genres) & set(dim_genres):
                from_search[key] = min(SEARCH_CAP, from_search[key] + SEARCH_WEIGHT)
                signals += 1
    if not signals:
        return None
    return {k: round(BASELINE + 50 * math.tanh((raw[k] + from_search[k]) / SATURATION)) for k in raw}


def describe(values: dict[str, int] | None) -> str:
    if not values or max(values.values()) < KNOWN_AT:
        return "Tu personalidad audiovisual está por descubrir. Valora algunos títulos y el radar cobrará vida."
    top = sorted(values, key=values.get, reverse=True)
    first, second = DIM_META[top[0]][1], DIM_META[top[1]][1]
    if values[top[1]] < KNOWN_AT:
        return f"{first}. Y todavía quedan muchas historias por descubrir."
    return f"{first}, con un toque de «{second.lower()}»."
