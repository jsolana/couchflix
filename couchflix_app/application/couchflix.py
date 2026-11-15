"""Application facade: the use cases the web layer calls. Persists sessions, searches and interactions."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from ..domain.criteria import Criteria, refine
from ..domain.models import GENRES, STREAM_MODES, Content, Pick, now_iso
from ..infrastructure.db import Db
from ..infrastructure.providers.base import ICatalogProvider
from ..infrastructure.repositories import (ContentRepo, PlatformRepo, SessionRepo, Settings, UserRepo, USER_ID)
from ..services.agent.interpreter import interpret
from ..services.agent.llm import build_llm
from ..services.catalog_service import CatalogService
from ..services.profile_service import ProfileService
from ..services.recommender import Recommender

SECRETS = ("tmdb_api_key", "anthropic_api_key", "openai_api_key")


class Couchflix:
    def __init__(self, db: Db, providers: dict[str, ICatalogProvider]):
        self.db, self.settings = db, Settings(db)
        self.contents, self.platforms = ContentRepo(db), PlatformRepo(db)
        self.users, self.sessions = UserRepo(db), SessionRepo(db)
        self.catalog = CatalogService(self.contents, self.platforms, self.settings, providers)
        self.profile = ProfileService(self.users)
        self.recommender = Recommender(self.catalog, self.users, self.platforms, self.profile, self.settings)
        self._locks = {"personal": threading.Lock(), "discovery": threading.Lock()}

    # ------------------------------------------------------------- serialization
    def card(self, c: Content, state: dict, pick: Pick | None = None) -> dict:
        mine = {p["id"] for p in self.platforms.subscribed()}
        included = [a for a in c.availability if a.mode in STREAM_MODES]
        included.sort(key=lambda a: a.platform_id not in mine)
        return {
            "id": c.id, "title": c.title, "year": c.year, "type": c.type, "poster": c.poster,
            "genres": [GENRES[g] for g in c.genres[:2] if g in GENRES], "rating": c.best_rating,
            "platforms": [{"name": a.platform_name, "icon": a.icon, "mine": a.platform_id in mine} for a in included[:3]],
            "availability_known": c.availability_updated_at is not None,
            "affinity": pick.affinity if pick else None, "reason": pick.reason if pick else None,
            "watched": state["watched"], "rating_state": state["rating"],
        }

    def cards(self, picks: list[dict], hide_seen: bool = True) -> list[dict]:
        """Hydrate persisted picks into cards with current state (and drop what was watched since)."""
        by_id = {c.id: c for c in self.contents.get_many([p["id"] for p in picks], self.settings.get("country"))}
        states = self.users.states(list(by_id))
        return [self.card(by_id[p["id"]], states[p["id"]], Pick(**p)) for p in picks
                if p["id"] in by_id and not (hide_seen and (states[p["id"]]["watched"] or states[p["id"]]["rating"]))]

    def detail(self, c: Content) -> dict:
        mine = {p["id"] for p in self.platforms.subscribed()}
        return {
            **self.card(c, self.users.state(c.id)),
            "original_title": c.original_title, "synopsis": c.synopsis, "runtime": c.runtime, "seasons": c.seasons,
            "ratings": c.ratings, "country": self.settings.get("country"),
            "offers": [{"name": a.platform_name, "icon": a.icon, "mode": a.mode, "url": a.url, "mine": a.platform_id in mine}
                       for a in c.availability],
            "metadata_updated_at": c.metadata_updated_at, "availability_updated_at": c.availability_updated_at,
            "sources": sorted(set(self.contents.provenance(c.id).values())),
            "interaction": self.users.state(c.id),
        }

    # ------------------------------------------------------------- persisted sessions
    def _setup(self) -> dict | None:
        return None if self.catalog.active_providers() else {"setup": "providers"}

    def _session(self, kind: str, build, ttl_key: str, refresh: bool) -> dict:
        if setup := self._setup():
            if not self.sessions.latest(kind):
                return setup
        with self._locks[kind]:
            current = self.sessions.latest(kind)
            fresh = current and current["expires_at"] > datetime.now(timezone.utc).isoformat()
            if current and fresh and not refresh:
                return {**current["results"], "generated_at": current["created_at"]}
            results, errors = build()
            if not results:  # nothing found (provider failures?): keep what we had and don't persist emptiness
                old = {**current["results"], "generated_at": current["created_at"]} if current else {}
                return {**old, "warnings": errors or ["empty"]}
            if not errors:  # degraded results (a provider failed) are served but not frozen into the session
                self.sessions.save(kind, results, self.settings.get(ttl_key))
            return {**results, "generated_at": now_iso(), "warnings": errors}

    def personal(self, refresh: bool = False) -> dict:
        def build():
            picks, errors = self.recommender.personalized()
            return ({"picks": [vars(p) for p in picks]} if picks else {}), errors
        out = self._session("personal", build, "personal_interval_hours", refresh)
        if "setup" not in out:
            out["items"] = self.cards(out.pop("picks", []))
        return out

    def discovery(self, refresh: bool = False) -> dict:
        def build():
            themes, errors = self.recommender.discovery()
            return ({"themes": [{"title": t["title"], "picks": [vars(p) for p in t["picks"]]} for t in themes]}
                    if themes else {}), errors
        out = self._session("discovery", build, "discovery_interval_hours", refresh)
        if "setup" not in out:
            themes = [{"title": t["title"], "items": self.cards(t["picks"])} for t in out.get("themes", [])]
            out["themes"] = [t for t in themes if t["items"]]
            last = self.users.last_search()
            out["last_search"] = last and {"id": last["id"], "query": last["query"], "items": self.cards(last["results"])}
        return out

    def invalidate_sessions(self) -> None:
        self.sessions.expire_all()

    # ------------------------------------------------------------- agent search
    def search(self, text: str | None, refine_key: str | None = None, search_id: int | None = None) -> dict:
        previous = self.users.get_search(search_id) if search_id else self.users.last_search() if refine_key else None
        if refine_key and previous:
            crit = refine(Criteria.from_dict(previous["criteria"]), refine_key, datetime.now().year,
                          [r["id"] for r in previous["results"]])
            text, agent = previous["query"], previous["origin"]
        else:
            names = [p["name"] for p in self.platforms.all()]
            crit, agent = interpret(text or "", names, build_llm(self.settings))
        picks, errors = self.recommender.search(crit)
        saved = [vars(p) for p in picks]
        sid = self.users.add_search(text or "", crit.to_dict(), saved, agent, refined=bool(refine_key and previous))
        self.profile.recalculate()
        return {"id": sid, "query": text, "agent": agent, "chips": crit.chips(), "items": self.cards(saved),
                "warnings": errors, "setup": self._setup() and "providers"}

    def last_search(self) -> dict | None:
        s = self.users.last_search()
        return s and {"id": s["id"], "query": s["query"], "agent": s["origin"],
                      "chips": Criteria.from_dict(s["criteria"]).chips(), "items": self.cards(s["results"]), "warnings": []}

    # ------------------------------------------------------------- content & interactions
    def content(self, content_id: int, refresh: bool = False) -> dict | None:
        result = self.catalog.get(content_id, force=refresh)
        if not result:
            return None
        status = "error" if result.errors and not result.changed else "updated" if result.changed else "unchanged"
        return {"content": self.detail(result.content), "status": status, "errors": result.errors}

    def interact(self, content_id: int, **fields) -> dict | None:
        if not self.contents.get(content_id):
            return None
        state = self.users.update_state(content_id, **fields)
        if "rating" in fields:
            self.profile.recalculate()
        return state

    # ------------------------------------------------------------- profile, activity, settings
    def activity(self, limit: int = 100) -> list[dict]:
        events = self.users.activity(limit)
        by_id = {c.id: c for c in self.contents.get_many([e["content_id"] for e in events if e["content_id"]])}
        return [{**e, "title": by_id[e["content_id"]].title if e["content_id"] in by_id else None,
                 "poster": by_id[e["content_id"]].poster if e["content_id"] in by_id else None} for e in events]

    def settings_view(self) -> dict:
        s, enabled = self.settings, self.settings.get("providers")
        mask = lambda v: ("•" * 6 + v[-4:]) if v else ""
        return {
            "country": s.get("country"), "platforms": self.platforms.all(), "platforms_configured": s.get("platforms_configured"),
            "discovery_interval_hours": s.get("discovery_interval_hours"),
            "providers": [{"name": n, "enabled": enabled is None or n in enabled, "available": p.is_available()}
                          for n, p in self.catalog.providers.items()],
            "credentials": {k: mask(s.get(k)) for k in SECRETS},
            "llm": {"provider": s.get("llm_provider"), "model": s.get("llm_model"), "base_url": s.get("llm_base_url"),
                    "active": build_llm(s) is not None},
        }

    def update_settings(self, data: dict) -> dict:
        s = self.settings
        for p in data.get("platforms", []):
            self.platforms.set_subscribed(p["id"], bool(p["subscribed"]))
            s.set("platforms_configured", True)
        for key in ("country", "discovery_interval_hours", "providers", "llm_provider", "llm_model", "llm_base_url"):
            if key in data:
                s.set(key, data[key])
        for key in SECRETS:
            if data.get(key) and "•" not in data[key]:
                s.set(key, data[key].strip())
        if {"platforms", "country", "providers"} & set(data):
            self.invalidate_sessions()  # next visit rebuilds with the new scope — no eager refetch
        return self.settings_view()

    def export(self) -> dict:
        contents = {c.id: c.title for c in self.contents.all()}
        data = self.users.export()
        for rows in data.values():
            for row in rows:
                if row.get("content_id") in contents:
                    row["title"] = contents[row["content_id"]]
        return {"exported_at": now_iso(), "user_id": USER_ID, **data}
