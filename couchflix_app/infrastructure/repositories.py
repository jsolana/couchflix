"""Repositories: the only place that knows SQL. Swap this module to move to another database."""
from __future__ import annotations

import json
import os
import re
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from ..domain.models import Availability, Content, norm_title, now_iso, platform_key
from .db import Db

# Active session profile. The web layer sets it per request (X-Profile header); 1 = the default profile (tests, CLI).
current_user: ContextVar[int] = ContextVar("current_user", default=1)
MAX_PROFILES = 8
AVATARS = tuple(f"a{i}" for i in range(1, 13))
IMAGE_AVATAR = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")
MAX_AVATAR_BYTES = 150_000


class ProfileError(ValueError):
    """Invalid profile data (the web layer maps it to HTTP 422/409)."""


class Settings:
    """Key/value settings. Secrets fall back to environment variables."""
    DEFAULTS = {
        "country": "ES", "platforms_configured": False, "providers": None,
        "discovery_interval_hours": 12, "personal_interval_hours": 24,
        "metadata_ttl_days": 30, "availability_ttl_hours": 24,
        "provider_priority": ["tmdb", "omdb", "justwatch", "fake"],
        "llm_provider": "none", "llm_model": "", "llm_base_url": "",
        "tmdb_api_key": "", "anthropic_api_key": "", "openai_api_key": "",
    }
    ENV = {"tmdb_api_key": "TMDB_API_KEY", "anthropic_api_key": "ANTHROPIC_API_KEY",
           "openai_api_key": "OPENAI_API_KEY", "llm_provider": "COUCHFLIX_LLM", "llm_base_url": "OPENAI_BASE_URL"}

    def __init__(self, db: Db):
        self.db = db

    def get(self, key: str):
        row = self.db.one("SELECT value FROM settings WHERE key=?", (key,))
        if row:
            value = json.loads(row["value"])
            if value not in ("", None):
                return value
        return os.environ.get(self.ENV.get(key, ""), "") or self.DEFAULTS[key]

    def set(self, key: str, value) -> None:
        if key not in self.DEFAULTS:
            raise KeyError(key)
        self.db.run("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value)))
        if key == "country":
            self.db.run("UPDATE users SET country=?", (value,))  # country is global


class PlatformRepo:
    def __init__(self, db: Db):
        self.db = db

    def all(self) -> list[dict]:
        return [dict(r) for r in self.db.all("SELECT * FROM platforms ORDER BY id")]

    def subscribed(self) -> list[dict]:
        return [dict(r) for r in self.db.all("SELECT * FROM platforms WHERE subscribed=1")]

    def set_subscribed(self, platform_id: int, value: bool) -> None:
        self.db.run("UPDATE platforms SET subscribed=? WHERE id=?", (int(value), platform_id))

    def by_names(self, names: list[str]) -> list[dict]:
        keys = {platform_key(n) for n in names}
        return [p for p in self.all() if p["key"] in keys]

    def resolve(self, external_id: int | None, name: str, icon: str | None = None) -> int:
        """Find (or dynamically create) the platform an offer refers to."""
        with self.db.lock:
            return self._resolve(external_id, name, icon)

    def _resolve(self, external_id: int | None, name: str, icon: str | None) -> int:
        key = platform_key(name)
        row = (external_id and self.db.one("SELECT * FROM platforms WHERE external_id=?", (external_id,))) \
            or self.db.one("SELECT * FROM platforms WHERE key=?", (key,))
        if row:
            self.db.run("UPDATE platforms SET external_id=COALESCE(external_id,?), icon=COALESCE(icon,?) WHERE id=?",
                        (external_id, icon, row["id"]))
            return row["id"]
        return self.db.run("INSERT INTO platforms (name,key,external_id,icon) VALUES (?,?,?,?)",
                           (name, key, external_id, icon)).lastrowid


class ContentRepo:
    JSON_FIELDS = ("genres", "ratings")

    def __init__(self, db: Db):
        self.db = db

    # ---- reading
    def _build(self, row, availability=None) -> Content:
        d = dict(row)
        return Content(
            id=d["id"], type=d["type"], title=d["title"], original_title=d["original_title"],
            synopsis=d["synopsis"], year=d["year"], poster=d["poster"], runtime=d["runtime"],
            seasons=d["seasons"], genres=json.loads(d["genres"]), ratings=json.loads(d["ratings"]),
            popularity=d["popularity"], detailed=bool(d["detailed"]),
            metadata_updated_at=d["metadata_updated_at"], availability_updated_at=d["availability_updated_at"],
            availability=availability or [])

    def _availability(self, ids: list[int], country: str) -> dict[int, list[Availability]]:
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self.db.all(
            f"SELECT a.*, p.name, p.icon FROM availability a JOIN platforms p ON p.id=a.platform_id "
            f"WHERE a.content_id IN ({marks}) AND a.country=? ORDER BY p.id", (*ids, country))
        out: dict[int, list[Availability]] = {}
        for r in rows:
            out.setdefault(r["content_id"], []).append(
                Availability(r["platform_id"], r["name"], r["icon"], r["mode"], r["url"], r["updated_at"]))
        return out

    def get_many(self, ids: list[int], country: str = "ES") -> list[Content]:
        ids = list(dict.fromkeys(ids))
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = {r["id"]: r for r in self.db.all(f"SELECT * FROM contents WHERE id IN ({marks})", tuple(ids))}
        av = self._availability(ids, country)
        return [self._build(rows[i], av.get(i)) for i in ids if i in rows]

    def get(self, content_id: int, country: str = "ES") -> Content | None:
        found = self.get_many([content_id], country)
        return found[0] if found else None

    def all(self, country: str = "ES") -> list[Content]:
        return self.get_many([r["id"] for r in self.db.all("SELECT id FROM contents")], country)

    def sources(self, content_id: int) -> dict[str, str]:
        return {r["provider"]: r["external_id"]
                for r in self.db.all("SELECT provider, external_id FROM content_sources WHERE content_id=?",
                                     (content_id,))}

    def provenance(self, content_id: int) -> dict[str, str]:
        return {r["attribute"]: r["provider"]
                for r in self.db.all("SELECT attribute, provider FROM provenance WHERE content_id=?", (content_id,))}

    # ---- identity / matching
    def find_by_source(self, provider: str, external_id: str) -> int | None:
        row = self.db.one("SELECT content_id FROM content_sources WHERE provider=? AND external_id=?",
                          (provider, external_id))
        return row["content_id"] if row else None

    def find_by_match(self, titles: list[str | None], year: int | None, kind: str) -> int | None:
        norms = [n for n in {norm_title(t) for t in titles} if n]
        if not norms:
            return None
        marks = ",".join("?" * len(norms))
        row = self.db.one(
            f"SELECT id FROM contents WHERE type=? AND (norm_title IN ({marks}) OR norm_original IN ({marks})) "
            f"AND (year IS NULL OR ? IS NULL OR ABS(year-?)<=1)", (kind, *norms, *norms, year, year))
        return row["id"] if row else None

    # ---- writing
    def create(self, kind: str, title: str) -> int:
        return self.db.run("INSERT INTO contents (type,title,norm_title,created_at) VALUES (?,?,?,?)",
                           (kind, title, norm_title(title), now_iso())).lastrowid

    def update(self, content_id: int, **fields) -> None:
        if not fields:
            return
        for key in self.JSON_FIELDS:
            if key in fields:
                fields[key] = json.dumps(fields[key], ensure_ascii=False)
        if "title" in fields:
            fields["norm_title"] = norm_title(fields["title"])
        if "original_title" in fields:
            fields["norm_original"] = norm_title(fields["original_title"])
        sets = ",".join(f"{k}=?" for k in fields)
        self.db.run(f"UPDATE contents SET {sets} WHERE id=?", (*fields.values(), content_id))

    def save_source(self, content_id: int, provider: str, external_id: str, raw: dict) -> None:
        self.db.run("INSERT INTO content_sources VALUES (?,?,?,?,?) ON CONFLICT(provider, external_id) "
                    "DO UPDATE SET raw=excluded.raw, fetched_at=excluded.fetched_at",
                    (provider, external_id, content_id, json.dumps(raw, ensure_ascii=False), now_iso()))

    def set_provenance(self, content_id: int, attribute: str, provider: str) -> None:
        self.db.run("INSERT INTO provenance VALUES (?,?,?,?) ON CONFLICT(content_id, attribute) "
                    "DO UPDATE SET provider=excluded.provider, updated_at=excluded.updated_at",
                    (content_id, attribute, provider, now_iso()))

    def replace_availability(self, content_id: int, country: str, source: str,
                             rows: list[tuple[int, str, str | None]]) -> bool:
        """Replace what one provider said about a content in a country. Returns True if anything changed."""
        before = {(r["platform_id"], r["mode"]) for r in self.db.all(
            "SELECT platform_id, mode FROM availability WHERE content_id=? AND country=? AND source=?",
            (content_id, country, source))}
        now = now_iso()
        with self.db.lock:
            self.db.conn.execute("DELETE FROM availability WHERE content_id=? AND country=? AND source=?",
                                 (content_id, country, source))
            self.db.conn.executemany(
                "INSERT OR REPLACE INTO availability VALUES (?,?,?,?,?,?,?)",
                [(content_id, pid, mode, country, url, source, now) for pid, mode, url in rows])
            self.db.conn.execute("UPDATE contents SET availability_updated_at=? WHERE id=?", (now, content_id))
            self.db.conn.commit()
        return before != {(pid, mode) for pid, mode, _ in rows}


class UserRepo:
    """Interactions, activity, searches and profile snapshots of the ACTIVE session profile (never of another one)."""

    def __init__(self, db: Db):
        self.db = db

    @property
    def uid(self) -> int:
        return current_user.get()

    def state(self, content_id: int) -> dict:
        return self.states([content_id])[content_id]

    def states(self, ids: list[int]) -> dict[int, dict]:
        out = {i: {"watched": False, "rating": None, "comment": None} for i in ids}
        if ids:
            marks = ",".join("?" * len(ids))
            for r in self.db.all(f"SELECT * FROM interactions WHERE user_id=? AND content_id IN ({marks})",
                                 (self.uid, *ids)):
                out[r["content_id"]] = {"watched": bool(r["watched"]), "rating": r["rating"], "comment": r["comment"]}
        return out

    def update_state(self, content_id: int, origin: str = "detail", **fields) -> dict:
        """fields ⊆ {watched, rating, comment}; each change is also logged in the activity feed."""
        cur = self.state(content_id)
        new = {**cur, **fields}
        self.db.run(
            "INSERT INTO interactions VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id, content_id) DO UPDATE SET "
            "watched=excluded.watched, rating=excluded.rating, comment=excluded.comment, "
            "origin=excluded.origin, updated_at=excluded.updated_at",
            (self.uid, content_id, int(new["watched"]), new["rating"], new["comment"], origin, now_iso()))
        if "watched" in fields and fields["watched"] != cur["watched"]:
            self.log("watched" if fields["watched"] else "unwatched", content_id)
        if "rating" in fields and fields["rating"] != cur["rating"]:
            self.log(fields["rating"] or "unrate", content_id)
        if "comment" in fields and fields["comment"] != cur["comment"] and fields["comment"]:
            self.log("comment", content_id, fields["comment"])
        return new

    def seen_ids(self) -> set[int]:
        return {r["content_id"] for r in self.db.all(
            "SELECT content_id FROM interactions WHERE user_id=? AND (watched=1 OR rating IS NOT NULL)", (self.uid,))}

    def rated(self) -> list[tuple[list[str], str]]:
        return [(json.loads(r["genres"]), r["rating"]) for r in self.db.all(
            "SELECT c.genres, i.rating FROM interactions i JOIN contents c ON c.id=i.content_id "
            "WHERE i.user_id=? AND i.rating IS NOT NULL", (self.uid,))]

    def log(self, kind: str, content_id: int | None = None, detail: str | None = None) -> None:
        self.db.run("INSERT INTO activity (user_id,kind,content_id,detail,created_at) VALUES (?,?,?,?,?)",
                    (self.uid, kind, content_id, detail, now_iso()))

    def activity(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.db.all(
            "SELECT * FROM activity WHERE user_id=? ORDER BY id DESC LIMIT ?", (self.uid, limit))]

    # searches
    def add_search(self, query: str, criteria: dict, results: list[dict], origin: str, refined: bool = False) -> int:
        """Only searches typed/chosen by the user reach this table (initial suggestions never do)."""
        sid = self.db.run("INSERT INTO searches (user_id,query,criteria,results,origin,created_at,refined) VALUES (?,?,?,?,?,?,?)",
                          (self.uid, query, json.dumps(criteria), json.dumps(results), origin, now_iso(), int(refined))).lastrowid
        self.log("search", None, query)
        return sid

    def _search(self, row) -> dict | None:
        return row and {**dict(row), "criteria": json.loads(row["criteria"]), "results": json.loads(row["results"])}

    def last_search(self) -> dict | None:
        return self._search(self.db.one("SELECT * FROM searches WHERE user_id=? ORDER BY id DESC LIMIT 1", (self.uid,)))

    def get_search(self, search_id: int) -> dict | None:
        return self._search(self.db.one("SELECT * FROM searches WHERE id=? AND user_id=?", (search_id, self.uid)))

    def searched_genres(self) -> list[list[str]]:
        return [json.loads(r["criteria"]).get("genres", []) for r in self.db.all(
            "SELECT criteria FROM searches WHERE user_id=? AND refined=0", (self.uid,))]

    # profile snapshots (evolution)
    def snapshots(self, limit: int = 12) -> list[dict]:
        rows = self.db.all("SELECT * FROM profile_snapshots WHERE user_id=? ORDER BY id DESC LIMIT ?", (self.uid, limit))
        return [{"dims": json.loads(r["dims"]), "computed_at": r["computed_at"]} for r in reversed(rows)]

    def add_snapshot(self, dims: dict) -> None:
        self.db.run("INSERT INTO profile_snapshots (user_id,dims,computed_at) VALUES (?,?,?)",
                    (self.uid, json.dumps(dims), now_iso()))

    def export(self) -> dict:
        tables = ("interactions", "activity", "searches", "profile_snapshots")
        return {t: [dict(r) for r in self.db.all(f"SELECT * FROM {t} WHERE user_id=?", (self.uid,))] for t in tables}


class SessionRepo:
    """Persisted recommendation sessions (personal carousel, Random Couch Sessions)."""

    def __init__(self, db: Db):
        self.db = db

    def latest(self, kind: str) -> dict | None:
        row = self.db.one("SELECT * FROM sessions WHERE kind=? AND user_id=? ORDER BY id DESC LIMIT 1",
                          (kind, current_user.get()))
        return row and {**dict(row), "results": json.loads(row["results"])}

    def save(self, kind: str, results: dict, ttl_hours: float, criteria: dict | None = None) -> None:
        now = datetime.now(timezone.utc)
        self.db.run("INSERT INTO sessions (kind,criteria,results,created_at,expires_at,user_id) VALUES (?,?,?,?,?,?)",
                    (kind, json.dumps(criteria or {}), json.dumps(results),
                     now.isoformat(timespec="seconds"), (now + timedelta(hours=ttl_hours)).isoformat(timespec="seconds"),
                     current_user.get()))

    def expire_all(self) -> None:
        self.db.run("UPDATE sessions SET expires_at=?", ("1970-01-01T00:00:00+00:00",))


class ProfileRepo:
    """Session profiles (family members): name + avatar. Each owns a private data space keyed by users.id."""
    TABLES = ("interactions", "activity", "searches", "profile_snapshots", "sessions")

    def __init__(self, db: Db):
        self.db = db

    @staticmethod
    def _clean(name: str, avatar: str) -> tuple[str, str]:
        name = " ".join((name or "").split())
        if not 1 <= len(name) <= 24:
            raise ProfileError("El nombre debe tener entre 1 y 24 caracteres")
        if avatar not in AVATARS and not (len(avatar or "") <= MAX_AVATAR_BYTES and IMAGE_AVATAR.match(avatar or "")):
            raise ProfileError("Avatar no válido")
        return name, avatar

    @staticmethod
    def _view(row) -> dict:
        return {"id": row["id"], "name": row["alias"], "avatar": row["avatar"] or AVATARS[0]}

    def all(self) -> list[dict]:
        return [self._view(r) for r in self.db.all("SELECT id, alias, avatar FROM users ORDER BY id")]

    def get(self, profile_id: int) -> dict | None:
        row = self.db.one("SELECT id, alias, avatar FROM users WHERE id=?", (profile_id,))
        return row and self._view(row)

    def create(self, name: str, avatar: str) -> dict:
        name, avatar = self._clean(name, avatar)
        with self.db.lock:
            if self.db.one("SELECT COUNT(*) n FROM users")["n"] >= MAX_PROFILES:
                raise ProfileError(f"Máximo {MAX_PROFILES} perfiles")
            country = Settings(self.db).get("country")
            pid = self.db.run("INSERT INTO users (alias, avatar, country, created_at) VALUES (?,?,?,?)",
                              (name, avatar, country, now_iso())).lastrowid
        return self.get(pid)

    def update(self, profile_id: int, name: str, avatar: str) -> dict | None:
        name, avatar = self._clean(name, avatar)
        self.db.run("UPDATE users SET alias=?, avatar=? WHERE id=?", (name, avatar, profile_id))
        return self.get(profile_id)

    def delete(self, profile_id: int) -> bool:
        """Removes the profile and everything it owns (history, searches, taste profile, cached suggestions)."""
        with self.db.lock:
            if not self.get(profile_id):
                return False
            if self.db.one("SELECT COUNT(*) n FROM users")["n"] <= 1:
                raise ProfileError("No se puede eliminar el último perfil")
            for table in self.TABLES:
                self.db.conn.execute(f"DELETE FROM {table} WHERE user_id=?", (profile_id,))
            self.db.conn.execute("DELETE FROM users WHERE id=?", (profile_id,))
            self.db.conn.commit()
        return True
