"""Session profiles: CRUD, limits, migration of the pre-existing profile and — above all — data isolation."""
import pytest
from fastapi.testclient import TestClient

from couchflix_app.infrastructure.repositories import AVATARS, MAX_PROFILES, ProfileError
from couchflix_app.web.app import create_app


@pytest.fixture
def api(tmp_path):
    client = TestClient(create_app(str(tmp_path / "t.db"), ["fake"]))
    client.as_ = lambda pid: {"X-Profile": str(pid)}
    return client


def new(api, name="Ana", avatar="a3"):
    return api.post("/api/profiles", json={"name": name, "avatar": avatar}).json()


def test_default_profile_exists_with_a_builtin_avatar(api):
    profiles = api.get("/api/profiles").json()["profiles"]
    assert len(profiles) == 1 and profiles[0]["id"] == 1 and profiles[0]["avatar"] in AVATARS
    assert len(AVATARS) >= 10


def test_crud_and_validation(api):
    ana = new(api)
    assert api.put(f"/api/profiles/{ana['id']}", json={"name": "Ana M", "avatar": "a5"}).json()["name"] == "Ana M"
    assert api.post("/api/profiles", json={"name": "  ", "avatar": "a1"}).status_code == 422
    assert api.post("/api/profiles", json={"name": "X", "avatar": "nope"}).status_code == 422
    assert api.post("/api/profiles", json={"name": "X", "avatar": "data:text/html;base64,AAAA"}).status_code == 422
    img = "data:image/png;base64,iVBORw0KGgo="
    assert api.post("/api/profiles", json={"name": "Foto", "avatar": img}).json()["avatar"] == img
    assert api.delete("/api/profiles/999").status_code == 404


def test_limit_and_last_profile_protected(api):
    for i in range(MAX_PROFILES - 1):
        new(api, f"P{i}")
    assert api.post("/api/profiles", json={"name": "Extra", "avatar": "a1"}).status_code == 409
    solo = TestClient(create_app(":memory:", ["fake"]))
    assert solo.delete("/api/profiles/1").status_code == 409


def test_api_requires_a_valid_profile(api):
    assert api.get("/api/profile").status_code == 401
    assert api.get("/api/profile", headers=api.as_(42)).status_code == 401
    assert api.get("/api/profile", headers=api.as_(1)).status_code == 200


def test_data_never_crosses_between_profiles(api):
    ana = new(api)["id"]
    cid = api.post("/api/search", json={"text": "una comedia"}, headers=api.as_(1)).json()["items"][0]["id"]
    sid = api.get("/api/search/last", headers=api.as_(1)).json()["id"]
    api.put(f"/api/content/{cid}/interaction", json={"rating": "love", "watched": True}, headers=api.as_(1))
    api.get("/api/suggestions/personal", headers=api.as_(1))

    # Ana sees none of it
    assert api.get("/api/activity", headers=api.as_(ana)).json() == []
    assert api.get("/api/search/last", headers=api.as_(ana)).json() == {}
    assert api.get("/api/profile", headers=api.as_(ana)).json()["known"] is False
    assert api.get(f"/api/content/{cid}", headers=api.as_(ana)).json()["content"]["interaction"]["rating"] is None
    export = api.get("/api/export", headers=api.as_(ana)).json()
    assert export["user_id"] == ana and not any(export[t] for t in ("interactions", "activity", "searches"))
    # refining someone else's search id must not reach it
    r = api.post("/api/search", json={"refine": "more_recent", "search_id": sid}, headers=api.as_(ana))
    assert r.status_code != 200 or r.json()["query"] != "una comedia"
    # her own suggestions are her own session, and Javi's history is intact
    assert api.get("/api/activity", headers=api.as_(1)).json()


def test_deleting_a_profile_removes_everything_it_owned(api):
    ana = new(api)["id"]
    cid = api.post("/api/search", json={"text": "una comedia"}, headers=api.as_(ana)).json()["items"][0]["id"]
    api.put(f"/api/content/{cid}/interaction", json={"rating": "like"}, headers=api.as_(ana))
    api.get("/api/suggestions/personal", headers=api.as_(ana))
    assert api.delete(f"/api/profiles/{ana}").status_code == 200
    db = api.app.state.core.db
    for table in ("interactions", "activity", "searches", "profile_snapshots", "sessions"):
        assert db.one(f"SELECT COUNT(*) n FROM {table} WHERE user_id=?", (ana,))["n"] == 0, table
    assert api.get("/api/profile", headers=api.as_(ana)).status_code == 401
