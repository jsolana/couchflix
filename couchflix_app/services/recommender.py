"""Filtering, ranking and explaining. The pure functions at the top are the testable core; `Recommender`
orchestrates them on top of the normalized catalog (it never talks to providers directly)."""
from __future__ import annotations

import random
from datetime import date

from ..domain.criteria import Criteria
from ..domain.models import GENRES, STREAM_MODES, Content, Pick
from ..domain.profile import BASELINE, DIM_GENRES, DIM_META, KNOWN_AT
from ..infrastructure.repositories import PlatformRepo, Settings, UserRepo
from .catalog_service import CatalogService
from .profile_service import ProfileService


# ---------------------------------------------------------------- pure functions
def filter_unseen(contents: list[Content], seen_ids: set[int]) -> list[Content]:
    return [c for c in contents if c.id not in seen_ids]


def filter_platforms(contents: list[Content], platform_ids: list[int] | None) -> list[Content]:
    """Keep contents streamable on one of the platforms. No filter → everything. Availability still
    unknown (never fetched, e.g. provider down) → kept, so a failing provider doesn't empty the screen."""
    if not platform_ids:
        return contents
    return [c for c in contents if c.availability_updated_at is None
            or any(a.platform_id in platform_ids and a.mode in STREAM_MODES for a in c.availability)]


def affinity(c: Content, dims: dict[str, int] | None) -> float | None:
    """0..1 match between a content's genres and the profile; None while the profile is unknown."""
    if not dims:
        return None
    vals = [dims[k] / 100 for k, genres in DIM_GENRES.items() if set(c.genres) & set(genres)]
    return max(vals) if vals else 0.35  # genres outside the six dimensions are neutral-ish


def score(c: Content, dims: dict[str, int] | None, crit: Criteria, year: int, rng: random.Random) -> float:
    aff = affinity(c, dims)
    s = 0.5 * (0.5 if aff is None else aff) + 0.3 * ((c.best_rating or 6) / 10)
    s += 0.15 * max(0.0, 1 - (year - (c.year or year - 15)) / 15)
    s += 0.3 * sum(g in c.genres for g in crit.genres) / max(len(crit.genres), 1) if crit.genres else 0
    if crit.hidden:
        s += 0.3 / (1 + (c.popularity or 0) / 50)
    return s + 0.08 * rng.random()  # a little noise → variety between refreshes


def rank(contents: list[Content], dims, crit: Criteria, year: int, rng: random.Random) -> list[Content]:
    """Score, then greedily pick penalizing repeated primary genres (variety)."""
    scores = {c.id: score(c, dims, crit, year, rng) for c in contents}
    primary = lambda c: c.genres[0] if c.genres else ""   # providers may return contents without genres
    pool, out, used = list(contents), [], {}
    while pool:
        best = max(pool, key=lambda c: scores[c.id] - 0.06 * used.get(primary(c), 0))
        pool.remove(best)
        out.append(best)
        used[primary(best)] = used.get(primary(best), 0) + 1
    return out


def explain(c: Content, aff: float | None, crit: Criteria, platform_names: list[str], year: int) -> str:
    parts = []
    asked = [GENRES[g] for g in crit.genres if g in c.genres]
    if crit.similar_to:
        parts.append(f"Parecida a {crit.similar_to}")
    elif asked:
        parts.append("Encaja con tu petición: " + ", ".join(asked))
    if aff is not None and aff >= 0.5:
        parts.append(f"Va con tus gustos ({round(aff * 100)} %)")
    elif aff is None and not asked and not crit.hidden:
        parts.append("Popular ahora")
    if crit.hidden:
        parts.append("Joya poco conocida")
    if platform_names:
        parts.append("En " + platform_names[0])
    if c.best_rating and c.best_rating >= 7.5:
        parts.append(f"Muy bien valorada ({c.best_rating:g})")
    if c.year and c.year >= year - 1:
        parts.append("Estreno reciente")
    return " · ".join(parts[:3]) or "Una apuesta del agente"


# ---------------------------------------------------------------- orchestration
class Recommender:
    def __init__(self, catalog: CatalogService, users: UserRepo, platforms: PlatformRepo, profile: ProfileService,
                 settings: Settings, rng: random.Random | None = None):
        self.catalog, self.users, self.platforms = catalog, users, platforms
        self.profile, self.settings, self.rng = profile, settings, rng or random.Random()

    def scope(self, crit: Criteria) -> list[dict]:
        """Platforms the results must be available on: the ones asked for, else the subscribed ones."""
        return (self.platforms.by_names(crit.platforms) if crit.platforms else []) or self.platforms.subscribed()

    def _prepare(self, crit: Criteria) -> list[dict]:
        crit.country = self.settings.get("country")
        scope = self.scope(crit)
        ids = [p["external_id"] for p in scope]
        crit.platform_ids = ids if scope and all(ids) else []  # provider-side filter only if every id is known
        return scope

    def gather(self, criteria: list[Criteria]) -> tuple[list[Content], list[str], list[dict]]:
        scope, found, errors = [], {}, []
        for crit in criteria:
            scope = self._prepare(crit)
            contents, errs = self.catalog.search(crit)
            found.update({c.id: c for c in contents})
            errors += errs
        return list(found.values()), sorted(set(errors)), scope

    def finalize(self, contents: list[Content], crit: Criteria, scope: list[dict], limit: int,
                 dims, personal: bool = True) -> list[Pick]:
        """unseen → rank → ensure availability → platform filter → explain."""
        year = date.today().year
        pool = filter_unseen(contents, self.users.seen_ids() | set(crit.exclude_ids))
        if crit.novelty and dims:  # step outside the comfort zone: avoid the user's strongest dimensions
            strong = {g for k, v in dims.items() if v >= KNOWN_AT for g in DIM_GENRES[k]}
            pool = [c for c in pool if not strong & set(c.genres)] or pool
        ranked = rank(pool, dims if personal else None, crit, year, self.rng)[: limit * 2]
        self.catalog.refresh_availability(ranked)
        country = self.settings.get("country")
        fresh = {c.id: c for c in self.catalog.contents.get_many([c.id for c in ranked], country)}
        kept = filter_platforms([fresh[c.id] for c in ranked if c.id in fresh], [p["id"] for p in scope])
        if crit.surprise:
            self.rng.shuffle(kept)
        picks = []
        for c in kept[:limit]:
            aff = affinity(c, dims)
            names = [a.platform_name for a in c.availability if a.mode in STREAM_MODES
                     and (not scope or a.platform_id in {p["id"] for p in scope})]
            picks.append(Pick(c.id, explain(c, aff, crit, names, year), None if aff is None else round(aff * 100)))
        return picks

    # ---- the three products
    def personalized(self, limit: int = 20) -> tuple[list[Pick], list[str]]:
        dims = self.profile.compute()
        top = [k for k, v in sorted((dims or {}).items(), key=lambda kv: -kv[1]) if v > BASELINE][:3]
        if top:
            crits = [Criteria(genres=list(DIM_GENRES[k]), genre_any=True, min_rating=6.5, page=self.rng.randint(1, 2))
                     for k in top]
        else:  # no preference yet (neutral profile): what is popular and well rated right now
            crits = [Criteria(), Criteria(kind="movie", min_rating=7), Criteria(kind="tv", min_rating=7)]
        contents, errors, scope = self.gather(crits)
        return self.finalize(contents, Criteria(), scope, limit, dims), errors

    def themes(self, today: date) -> list[tuple[str, Criteria]]:
        month, year = today.month, today.year
        seasonal = {10: ("Noche de Halloween", Criteria(query="Halloween")), 12: ("Sesión navideña", Criteria(query="Navidad")),
                    1: ("Sesión navideña", Criteria(query="Navidad")), 7: ("Verano en familia", Criteria(genres=["family"])),
                    8: ("Verano en familia", Criteria(genres=["family"])), 2: ("Para San Valentín", Criteria(genres=["romance"]))}
        pool = [("Joyas ocultas", Criteria(hidden=True)), ("Muy bien valoradas", Criteria(min_rating=8)),
                ("Lo más actual", Criteria(year_from=year - 1)), ("Algo que no sueles ver", Criteria(novelty=True)),
                ("Sorpréndeme", Criteria(surprise=True, page=self.rng.randint(1, 3)))]
        self.rng.shuffle(pool)
        return ([seasonal[month]] if month in seasonal else []) + pool

    def discovery(self, today: date | None = None, themes: int = 3, limit: int = 10) -> tuple[list[dict], list[str]]:
        dims, out, errors = self.profile.compute(), [], []
        for title, crit in self.themes(today or date.today()):
            if len(out) >= themes:
                break
            if crit.novelty and dims:
                weak = [k for k, v in sorted(dims.items(), key=lambda kv: kv[1])][:2]
                crit.genres, crit.genre_any = [g for k in weak for g in DIM_GENRES[k]], True
                title = f"Fuera de tu zona de confort · {DIM_META[weak[0]][0]}"
            contents, errs, scope = self.gather([crit])
            errors += errs
            picks = self.finalize(contents, crit, scope, limit, dims, personal=False)
            if picks:
                out.append({"title": title, "picks": picks})
        return out, sorted(set(errors))

    def search(self, crit: Criteria, limit: int = 12) -> tuple[list[Pick], list[str]]:
        dims = self.profile.compute()
        contents, errors, scope = self.gather([crit])
        return self.finalize(contents, crit, scope, limit, dims), errors
