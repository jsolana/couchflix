"""TMDB adapter: metadata, posters and per-country watch providers (availability data is powered by JustWatch)."""
from __future__ import annotations

from typing import Callable

import httpx

from ...domain.criteria import Criteria
from ...domain.models import Offer, ProviderItem
from .base import ICatalogProvider, ProviderUnavailable

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"
GENRE_IDS = {28: "action", 12: "adventure", 16: "animation", 35: "comedy", 80: "crime", 99: "documentary",
             18: "drama", 10751: "family", 14: "fantasy", 36: "history", 27: "horror", 10402: "music",
             9648: "mystery", 10749: "romance", 878: "scifi", 53: "thriller", 10752: "war", 37: "western",
             10759: ["action", "adventure"], 10765: ["scifi", "fantasy"], 10762: "family", 10768: "war"}
MODES = {"flatrate": "subscription", "free": "free", "ads": "free_ads", "rent": "rental", "buy": "purchase"}


def _genre_keys(ids: list[int]) -> list[str]:
    keys: list[str] = []
    for i in ids:
        v = GENRE_IDS.get(i)
        keys += v if isinstance(v, list) else [v] if v else []
    return list(dict.fromkeys(keys))


def _tmdb_genre_ids(keys: list[str], kind: str) -> list[int]:
    out = []
    for gid, v in GENRE_IDS.items():
        if (kind == "movie" and gid in (10759, 10765, 10762, 10768)) or (kind == "tv" and gid in (28, 12, 878, 14, 10751, 10752)):
            continue
        if any(k in (v if isinstance(v, list) else [v]) for k in keys):
            out.append(gid)
    return out


class TMDBProvider(ICatalogProvider):
    def __init__(self, api_key: Callable[[], str], language: str = "es-ES"):
        self._key, self.language = api_key, language
        self.http = httpx.Client(timeout=10)

    def get_provider_name(self) -> str:
        return "tmdb"

    def is_available(self) -> bool:
        return bool(self._key())

    def _get(self, path: str, **params) -> dict:
        key = self._key()
        if not key:
            raise ProviderUnavailable("TMDB_API_KEY no configurada")
        headers = {"Authorization": f"Bearer {key}"} if len(key) > 40 else {}
        if not headers:
            params["api_key"] = key
        r = self.http.get(f"{API}{path}", params={"language": self.language, **params}, headers=headers)
        r.raise_for_status()
        return r.json()

    # ---- mapping
    @staticmethod
    def _item(d: dict, kind: str, detailed: bool = False) -> ProviderItem:
        date = d.get("release_date") or d.get("first_air_date") or ""
        genres = _genre_keys(d.get("genre_ids") or [g["id"] for g in d.get("genres", [])])
        runtime = d.get("runtime") or (d.get("episode_run_time") or [None])[0]
        return ProviderItem(
            provider="tmdb", external_id=f"{kind}:{d['id']}", type=kind,
            title=d.get("title") or d.get("name") or "", original_title=d.get("original_title") or d.get("original_name"),
            synopsis=d.get("overview") or None, year=int(date[:4]) if date[:4].isdigit() else None,
            poster=f"{IMG}/w500{d['poster_path']}" if d.get("poster_path") else None,
            runtime=runtime, seasons=d.get("number_of_seasons"), genres=genres,
            ratings={"tmdb": round(d["vote_average"], 1)} if d.get("vote_count") else {},
            popularity=d.get("popularity"), detailed=detailed,
            extra={"imdb_id": (d.get("external_ids") or {}).get("imdb_id")})

    # ---- ICatalogProvider
    def search(self, c: Criteria) -> list[ProviderItem]:
        if c.similar_to:
            return self._similar(c)
        if c.query:
            data = self._get("/search/multi", query=c.query, page=c.page)
            return [self._item(d, d["media_type"]) for d in data["results"] if d.get("media_type") in ("movie", "tv")]
        items: list[ProviderItem] = []
        for kind in ([c.kind] if c.kind else ["movie", "tv"]):
            items += self._discover(c, kind)
        return items

    def _discover(self, c: Criteria, kind: str) -> list[ProviderItem]:
        date_field = "primary_release_date" if kind == "movie" else "first_air_date"
        p: dict = {"sort_by": "vote_average.desc" if c.hidden or c.min_rating and c.min_rating >= 8 else "popularity.desc",
                   "page": c.page, "vote_count.gte": 200 if c.hidden else 100 if c.min_rating else 30}
        if c.genres:
            p["with_genres"] = ("|" if c.genre_any else ",").join(map(str, _tmdb_genre_ids(c.genres, kind)))
        if c.year_from:
            p[f"{date_field}.gte"] = f"{c.year_from}-01-01"
        if c.year_to:
            p[f"{date_field}.lte"] = f"{c.year_to}-12-31"
        if c.min_rating or c.hidden:
            p["vote_average.gte"] = c.min_rating or 7.3
        if c.hidden:
            p["vote_count.lte"] = 2500
        if c.max_runtime and kind == "movie":
            p["with_runtime.lte"] = c.max_runtime
        if c.platform_ids:
            p.update(with_watch_providers="|".join(map(str, c.platform_ids)), watch_region=c.country,
                     with_watch_monetization_types="flatrate|free|ads")
        return [self._item(d, kind) for d in self._get(f"/discover/{kind}", **p)["results"]]

    def _similar(self, c: Criteria) -> list[ProviderItem]:
        hits = [d for d in self._get("/search/multi", query=c.similar_to)["results"] if d.get("media_type") in ("movie", "tv")]
        if not hits:
            return []
        seed = hits[0]
        data = self._get(f"/{seed['media_type']}/{seed['id']}/recommendations", page=c.page)
        return [self._item(d, seed["media_type"]) for d in data["results"]]

    def get_details(self, external_id: str) -> ProviderItem:
        kind, tid = external_id.split(":")
        return self._item(self._get(f"/{kind}/{tid}", append_to_response="external_ids"), kind, detailed=True)

    def get_availability(self, external_id: str, country: str) -> list[Offer]:
        kind, tid = external_id.split(":")
        region = self._get(f"/{kind}/{tid}/watch/providers").get("results", {}).get(country, {})
        return [Offer(p["provider_id"], p["provider_name"], MODES[mode], region.get("link"),
                      f"{IMG}/w92{p['logo_path']}" if p.get("logo_path") else None)
                for mode in MODES for p in region.get(mode, [])]
