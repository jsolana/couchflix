"""Core entities. Plain dataclasses, no I/O."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

# canonical genre key -> Spanish label (providers map their own genres onto these keys)
GENRES = {
    "action": "Acción", "adventure": "Aventuras", "animation": "Animación", "comedy": "Comedia",
    "crime": "Crimen", "documentary": "Documental", "drama": "Drama", "family": "Familiar",
    "fantasy": "Fantasía", "history": "Historia", "horror": "Terror", "music": "Música",
    "mystery": "Misterio", "romance": "Romance", "scifi": "Ciencia ficción", "thriller": "Suspense",
    "war": "Bélica", "western": "Western",
}
MODES = ("subscription", "free", "free_ads", "rental", "purchase")  # availability modalities
STREAM_MODES = ("subscription", "free", "free_ads")  # "included" modalities


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def unaccent(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def norm_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", unaccent(title or "").lower()).strip()


def platform_key(name: str) -> str:
    """Canonical key so 'Amazon Prime Video', 'Prime Video' and 'prime video' are one platform."""
    n = re.sub(r"\s+", " ", unaccent(name).lower().replace("+", " plus")).strip()
    aliases = {"amazon prime video": "prime video", "amazon video": "prime video", "apple tv": "apple tv plus",
               "atres player": "atresplayer", "movistar": "movistar plus", "disney": "disney plus"}
    return aliases.get(n, n)


@dataclass
class Offer:
    """An availability entry as reported by a provider."""
    platform_id: int | None
    platform_name: str
    mode: str
    url: str | None = None
    icon: str | None = None


@dataclass
class ProviderItem:
    """Raw content as returned by a provider (before normalization)."""
    provider: str
    external_id: str
    type: str  # movie | tv
    title: str
    original_title: str | None = None
    synopsis: str | None = None
    year: int | None = None
    poster: str | None = None
    runtime: int | None = None
    seasons: int | None = None
    genres: list[str] = field(default_factory=list)
    ratings: dict[str, float] = field(default_factory=dict)
    popularity: float | None = None
    detailed: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class Availability:
    platform_id: int
    platform_name: str
    icon: str | None
    mode: str
    url: str | None
    updated_at: str | None = None


@dataclass
class Content:
    id: int
    type: str
    title: str
    original_title: str | None = None
    synopsis: str | None = None
    year: int | None = None
    poster: str | None = None
    runtime: int | None = None
    seasons: int | None = None
    genres: list[str] = field(default_factory=list)
    ratings: dict[str, float] = field(default_factory=dict)
    popularity: float | None = None
    detailed: bool = False
    metadata_updated_at: str | None = None
    availability_updated_at: str | None = None
    availability: list[Availability] = field(default_factory=list)

    @property
    def best_rating(self) -> float | None:
        for src in ("imdb", "tmdb"):
            if self.ratings.get(src):
                return self.ratings[src]
        return max(self.ratings.values(), default=None)


@dataclass
class Pick:
    """A recommended content with its justification."""
    id: int
    reason: str = ""
    affinity: int | None = None
