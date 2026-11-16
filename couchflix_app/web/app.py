"""FastAPI app: thin HTTP layer over the application facade, plus the static single-page UI."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..application.couchflix import Couchflix
from ..infrastructure.db import Db
from ..infrastructure.providers.justwatch import JustWatchProvider
from ..infrastructure.providers.tmdb import TMDBProvider

STATIC = Path(__file__).parent / "static"


class InteractionIn(BaseModel):
    watched: bool | None = None
    rating: str | None = None   # like | love | dislike | null (clears)
    comment: str | None = None


class ProfileIn(BaseModel):
    name: str
    avatar: str


class SearchIn(BaseModel):
    text: str | None = None
    refine: str | None = None
    search_id: int | None = None


def build_providers(app_settings, names: list[str]) -> dict:
    registry = {}
    for name in names:
        if name == "tmdb":
            registry[name] = TMDBProvider(lambda: app_settings.get("tmdb_api_key"))
        elif name == "justwatch":
            registry[name] = JustWatchProvider()
        elif name in ("fake", "fake_down"):  # test-only providers, never enabled by default
            from ..infrastructure.providers.fake import FakeDownProvider, FakeProvider
            registry[name] = FakeProvider() if name == "fake" else FakeDownProvider()
    return registry


def create_app(db_path: str | None = None, provider_names: list[str] | None = None) -> FastAPI:
    db = Db(db_path or os.environ.get("COUCHFLIX_DB", "data/couchflix.db"))
    names = provider_names or [n.strip() for n in os.environ.get("COUCHFLIX_PROVIDERS", "tmdb").split(",") if n.strip()]
    from ..infrastructure.repositories import AVATARS, MAX_PROFILES, ProfileError, Settings, current_user
    core = Couchflix(db, build_providers(Settings(db), names))

    async def active_profile(request: Request):
        """Every /api call except the profile picker's own runs as the profile named in X-Profile (async: the
        ContextVar must be set in the request task so the threadpool-run endpoint inherits it)."""
        path = request.url.path
        if not path.startswith("/api/") or path.startswith("/api/profiles"):
            return
        header = request.headers.get("x-profile", "")
        if not header.isdigit() or not core.profiles.get(int(header)):
            raise HTTPException(401, "Selecciona un perfil")
        current_user.set(int(header))

    app = FastAPI(title="COUCHFLIX", docs_url=None, redoc_url=None, dependencies=[Depends(active_profile)])

    def profile_call(fn, *args):
        try:
            return fn(*args)
        except ProfileError as err:
            raise HTTPException(409 if "Máximo" in str(err) or "último" in str(err) else 422, str(err))

    @app.get("/api/profiles")
    def list_profiles():
        return {"profiles": core.profiles.all(), "max": MAX_PROFILES, "avatars": list(AVATARS)}

    @app.post("/api/profiles")
    def create_profile(body: ProfileIn):
        return profile_call(core.profiles.create, body.name, body.avatar)

    @app.put("/api/profiles/{profile_id}")
    def update_profile(profile_id: int, body: ProfileIn):
        return found(profile_call(core.profiles.update, profile_id, body.name, body.avatar))

    @app.delete("/api/profiles/{profile_id}")
    def delete_profile(profile_id: int):
        found(profile_call(core.profiles.delete, profile_id) or None)
        return {"deleted": profile_id}

    def found(value):
        if value is None:
            raise HTTPException(404, "No encontrado")
        return value

    @app.get("/api/suggestions/personal")
    def personal():
        return core.personal()

    @app.post("/api/suggestions/personal/refresh")
    def personal_refresh():
        return core.personal(refresh=True)

    @app.get("/api/suggestions/discovery")
    def discovery():
        return core.discovery()

    @app.post("/api/suggestions/discovery/refresh")
    def discovery_refresh():
        return core.discovery(refresh=True)

    @app.post("/api/search")
    def search(body: SearchIn):
        if not (body.text or body.refine):
            raise HTTPException(422, "Escribe qué te apetece ver")
        return core.search(body.text, body.refine, body.search_id)

    @app.get("/api/search/last")
    def last_search():
        return core.last_search() or {}

    @app.get("/api/content/{content_id}")
    def content(content_id: int):
        return found(core.content(content_id))

    @app.post("/api/content/{content_id}/refresh")
    def content_refresh(content_id: int):
        return found(core.content(content_id, refresh=True))

    @app.put("/api/content/{content_id}/interaction")
    def interaction(content_id: int, body: InteractionIn):
        fields = {k: getattr(body, k) for k in body.model_fields_set}
        if fields.get("rating") not in (None, "like", "love", "dislike"):
            raise HTTPException(422, "Valoración no válida")
        return found(core.interact(content_id, **fields))

    @app.get("/api/profile")
    def profile():
        return core.profile.view()

    @app.post("/api/profile/recalculate")
    def recalc():
        core.profile.recalculate()
        return core.profile.view()

    @app.get("/api/activity")
    def activity():
        return core.activity()

    @app.get("/api/settings")
    def get_settings():
        return core.settings_view()

    @app.put("/api/settings")
    def put_settings(data: dict = Body(...)):
        return core.update_settings(data)

    @app.get("/api/export")
    def export():
        return JSONResponse(core.export(), headers={"Content-Disposition": 'attachment; filename="couchflix-export.json"'})

    if any(n.startswith("fake") for n in names):
        _mount_test_endpoints(app, core)

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="ui")

    @app.middleware("http")
    async def no_cache(request, call_next):  # local app: always serve the latest UI
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    app.state.core = core
    return app


def _mount_test_endpoints(app: FastAPI, core: Couchflix) -> None:
    """Only exists when the fake (test) provider is registered: posters for the fictional fixtures + a control knob."""
    from ..infrastructure.providers.fake import CONTROL, FakeProvider

    @app.get("/__fixtures__/poster/{item_id}.svg")
    def poster(item_id: int):
        item = FakeProvider().items.get(str(item_id))
        h = int(hashlib.md5(str(item_id).encode()).hexdigest()[:6], 16)
        a, b = h % 360, (h // 360 + 90) % 360
        title = (item or {"title": "?"})["title"]
        words = title.split()
        lines = "".join(f'<text x="150" y="{190 + i * 34}" font-size="28" font-weight="700" text-anchor="middle" fill="#fff" '
                        f'font-family="system-ui,sans-serif">{w}</text>' for i, w in enumerate(words[:3]))
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 450"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
               f'<stop offset="0" stop-color="hsl({a},55%,28%)"/><stop offset="1" stop-color="hsl({b},60%,14%)"/></linearGradient></defs>'
               f'<rect width="300" height="450" fill="url(#g)"/><circle cx="220" cy="90" r="46" fill="hsla({a},80%,70%,.25)"/>{lines}</svg>')
        return Response(svg, media_type="image/svg+xml")

    @app.get("/__fixtures__/icon/{pid}.svg")
    def icon(pid: int):
        names = {8: "N", 119: "P", 1899: "M", 337: "D", 350: "A"}
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" rx="9" fill="hsl({pid * 47 % 360},55%,38%)"/>'
               f'<text x="20" y="27" font-size="20" font-weight="700" text-anchor="middle" fill="#fff" font-family="system-ui">{names.get(pid, "?")}</text></svg>')
        return Response(svg, media_type="image/svg+xml")

    @app.post("/__test__/control")
    def control(data: dict = Body(...)):
        CONTROL.update({k: data[k] for k in ("delay", "fail") if k in data})
        return CONTROL
