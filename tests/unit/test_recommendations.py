from datetime import date, datetime, timedelta, timezone

from couchflix_app.domain.criteria import Criteria
from couchflix_app.infrastructure.providers.fake import CONTROL


def test_first_run_personal_session_only_has_subscribed_platform_content(core):
    out = core.personal()
    assert out["items"]
    netflix = next(p for p in core.platforms.all() if p["name"] == "Netflix")["id"]
    for card in out["items"]:
        offers = core.contents.get(card["id"]).availability
        assert any(a.platform_id == netflix and a.mode == "subscription" for a in offers)


def test_sessions_are_persisted_and_not_regenerated_on_access(core):
    first, themes = core.personal(), core.discovery()["themes"]
    CONTROL["fail"] = True  # any new provider query would now fail
    again = core.personal()
    assert [c["id"] for c in first["items"]] == [c["id"] for c in again["items"]] and not again.get("warnings")
    assert core.discovery()["themes"] == themes


def test_session_expiry_and_explicit_refresh(core):
    first = core.personal()
    core.db.run("UPDATE sessions SET expires_at=?", ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),))
    CONTROL["fail"] = True
    degraded = core.personal()  # expired + providers down → persisted catalog, flagged, never an empty screen
    assert degraded["items"] and degraded["warnings"]
    assert [p["id"] for p in core.sessions.latest("personal")["results"]["picks"]] == [c["id"] for c in first["items"]]  # not overwritten
    CONTROL["fail"] = False
    assert core.personal(refresh=True)["items"]


def test_profile_changes_recommendations_and_watched_are_excluded(core):
    horror = core.catalog.search(Criteria(genres=["horror"]))[0][0]
    core.interact(horror.id, rating="love")
    core.interact(horror.id, watched=True)
    picks, _ = core.recommender.personalized()
    ids = [p.id for p in picks]
    assert horror.id not in ids
    genres = [g for c in core.contents.get_many(ids) for g in c.genres[:1]]
    assert "horror" in genres


def test_search_respects_criteria_and_is_persisted(core):
    out = core.search("una película de ciencia ficción de menos de dos horas")
    assert out["items"] and out["agent"] == "rules"
    for card in out["items"]:
        c = core.contents.get(card["id"])
        assert "scifi" in c.genres and c.type == "movie"
    assert core.users.last_search()["query"].startswith("una película")
    assert core.discovery()["last_search"]["items"]


def test_searching_a_genre_nudges_but_does_not_define_profile(core):
    core.search("terror")
    view = core.profile.view()
    horror = next(d for d in view["dimensions"] if d["key"] == "horror")["value"]
    assert 50 < horror < 62


def test_refinements_exclude_previous_results(core):
    first = core.search("algo de aventuras")
    again = core.search(None, refine_key="more", search_id=first["id"])
    assert not {c["id"] for c in first["items"]} & {c["id"] for c in again["items"]}


def test_similar_to_uses_catalog(core):
    out = core.search("algo parecido a Horizonte Cuántico")
    assert out["items"] and all(c["title"] != "Horizonte Cuántico" for c in out["items"])


def test_discovery_has_themes_and_seasonal_content(core):
    themes, _ = core.recommender.discovery(today=date(2026, 7, 10))
    assert 1 <= len(themes) <= 3 and all(t["picks"] for t in themes)
    assert core.recommender.themes(date(2026, 10, 20))[0][0] == "Noche de Halloween"


def test_changing_platforms_changes_scope_and_all_off_means_unfiltered(core):
    mine = {p["name"]: p["id"] for p in core.platforms.all()}
    core.personal()
    core.update_settings({"platforms": [{"id": mine["Netflix"], "subscribed": False},
                                        {"id": mine["Disney+"], "subscribed": True}]})
    disney = core.personal()["items"]
    assert disney and all(any(p["name"] == "Disney+" for p in c["platforms"]) for c in disney)
    core.update_settings({"platforms": [{"id": mine["Disney+"], "subscribed": False}]})
    assert core.platforms.subscribed() == [] and core.personal()["items"]  # not silently falling back to Netflix


def test_credentials_are_masked_and_export_contains_history(core):
    core.update_settings({"tmdb_api_key": "abcdef123456"})
    assert core.settings_view()["credentials"]["tmdb_api_key"].endswith("3456") and "abcdef" not in str(core.settings_view())
    c = core.catalog.search(Criteria())[0][0]
    core.interact(c.id, rating="like")
    assert core.export()["interactions"][0]["rating"] == "like"


def test_provider_down_still_serves_suggestions(core_with_down):
    out = core_with_down.personal()
    assert out["items"] and out["warnings"] == ["fake_down"]


def test_ranking_handles_contents_without_genres():
    import random
    from couchflix_app.domain.models import Content
    from couchflix_app.services.recommender import rank
    items = [Content(1, "movie", "A"), Content(2, "movie", "B", genres=["drama"]), Content(3, "movie", "C")]
    assert {c.id for c in rank(items, None, Criteria(), 2026, random.Random(1))} == {1, 2, 3}


def test_initial_suggestions_never_modify_the_profile(core):
    """Carousel + Random Couch Sessions are generated by the app, not by the user: no search, no signal."""
    core.personal()
    core.discovery()
    core.personal(refresh=True)
    core.discovery(refresh=True)
    assert core.users.searched_genres() == [] and core.users.last_search() is None
    assert core.users.snapshots() == [] and core.users.activity() == []
    view = core.profile.view()
    assert not view["known"] and [d["value"] for d in view["dimensions"]] == [50] * 6


def test_user_search_and_ratings_do_modify_it_but_refinements_do_not(core):
    first = core.search("terror")
    after_search = {d["key"]: d["value"] for d in core.profile.view()["dimensions"]}
    assert after_search["horror"] > 50
    core.search(None, refine_key="more", search_id=first["id"])
    core.search(None, refine_key="recent", search_id=first["id"])
    assert {d["key"]: d["value"] for d in core.profile.view()["dimensions"]} == after_search
    card = core.search("ciencia ficción")["items"][0]
    core.interact(card["id"], rating="dislike")
    assert next(d["value"] for d in core.profile.view()["dimensions"] if d["key"] == "scifi") < 50
