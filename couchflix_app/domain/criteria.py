"""Search criteria: the common language between the agent, the catalog and the providers."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields

from .models import GENRES, Content


@dataclass
class Criteria:
    query: str | None = None          # free-text title search
    kind: str | None = None           # movie | tv
    genres: list[str] = field(default_factory=list)
    genre_any: bool = False           # True: any genre matches; False: all of them
    year_from: int | None = None
    year_to: int | None = None
    min_rating: float | None = None
    max_runtime: int | None = None    # minutes
    max_seasons: int | None = None
    platforms: list[str] = field(default_factory=list)   # names asked for explicitly
    similar_to: str | None = None
    surprise: bool = False
    novelty: bool = False             # outside the user's comfort zone
    hidden: bool = False              # hidden gems / lesser known
    exclude_ids: list[int] = field(default_factory=list)
    # filled by the recommender right before querying providers
    country: str = "ES"
    platform_ids: list[int] = field(default_factory=list)  # external ids for provider-side filtering
    page: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Criteria":
        known = {f.name: f for f in fields(cls)}
        clean = {k: v for k, v in (data or {}).items() if k in known and v is not None}
        clean["genres"] = [g for g in clean.get("genres", []) if g in GENRES]
        return cls(**clean)

    def is_empty(self) -> bool:
        return not (self.query or self.kind or self.genres or self.year_from or self.year_to or self.min_rating
                    or self.max_runtime or self.max_seasons or self.platforms or self.similar_to
                    or self.surprise or self.novelty or self.hidden)

    def chips(self) -> list[str]:
        """Human readable summary of what the agent understood."""
        out = [GENRES[g] for g in self.genres]
        if self.kind:
            out.append("Película" if self.kind == "movie" else "Serie")
        if self.similar_to:
            out.append(f"Como {self.similar_to}")
        if self.query and not self.similar_to:
            out.append(f"“{self.query}”")
        if self.max_runtime:
            out.append(f"≤ {self.max_runtime} min")
        if self.max_seasons:
            out.append(f"≤ {self.max_seasons} temporadas")
        if self.year_from:
            out.append(f"Desde {self.year_from}")
        if self.year_to:
            out.append(f"Hasta {self.year_to}")
        if self.min_rating:
            out.append(f"★ {self.min_rating:g}+")
        out += self.platforms
        out += [t for flag, t in ((self.surprise, "Sorpresa"), (self.novelty, "Algo diferente"),
                                  (self.hidden, "Menos conocido")) if flag]
        return out


def matches(c: Content, crit: Criteria) -> bool:
    """Does an already-catalogued content satisfy the criteria? (used for the local/offline catalog)"""
    if crit.kind and c.type != crit.kind:
        return False
    if crit.genres:
        found = [g in c.genres for g in crit.genres]
        if not (any(found) if crit.genre_any else all(found)):
            return False
    if crit.year_from and (c.year or 0) < crit.year_from:
        return False
    if crit.year_to and (c.year or 9999) > crit.year_to:
        return False
    if crit.min_rating and (c.best_rating or 0) < crit.min_rating:
        return False
    if crit.max_runtime and c.type == "movie" and c.runtime and c.runtime > crit.max_runtime:
        return False
    if crit.max_seasons and c.seasons and c.seasons > crit.max_seasons:
        return False
    if crit.query and crit.query.lower() not in (c.title + " " + (c.original_title or "")).lower():
        return False
    return c.id not in crit.exclude_ids


def refine(crit: Criteria, key: str, now_year: int, previous_ids: list[int]) -> Criteria:
    """Apply a refinement chip ('más reciente', 'más acción', …) on top of previous criteria."""
    new = Criteria.from_dict(crit.to_dict())
    if key == "recent":
        new.year_from = max(new.year_from or 0, now_year - 3)
    elif key == "action":
        new.genres = list(dict.fromkeys(new.genres + ["action"]))
    elif key == "less_known":
        new.hidden = True
    elif key == "different":
        new.novelty, new.genres, new.query, new.similar_to = True, [], None, None
        new.exclude_ids = previous_ids
    elif key == "more":
        new.page, new.exclude_ids = new.page + 1, previous_ids
    return new
