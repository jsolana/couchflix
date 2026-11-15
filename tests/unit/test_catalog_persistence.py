from datetime import datetime, timedelta, timezone

from couchflix_app.application.couchflix import Couchflix
from couchflix_app.domain.criteria import Criteria
from couchflix_app.domain.models import ProviderItem
from couchflix_app.infrastructure.db import Db
from couchflix_app.infrastructure.providers.fake import CONTROL, FakeProvider


def item(provider, ext, title="Dune", year=2021, **kw):
    return ProviderItem(provider=provider, external_id=ext, type="movie", title=title, year=year, **kw)


def test_same_content_from_two_providers_has_one_identity(core):
    a, _ = core.catalog.merge(item("tmdb", "movie:1", synopsis="from tmdb"))
    b, _ = core.catalog.merge(item("omdb", "tt1", original_title="DUNE", synopsis="from omdb"))
    assert a == b and len(core.contents.all()) == 1
    assert core.contents.sources(a) == {"tmdb": "movie:1", "omdb": "tt1"}


def test_different_year_or_type_is_not_the_same_content(core):
    a, _ = core.catalog.merge(item("tmdb", "1", year=1984))
    b, _ = core.catalog.merge(item("tmdb", "2", year=2021))
    assert a != b


def test_discrepancies_resolved_by_priority_and_provenance_kept(core):
    core.settings.set("provider_priority", ["tmdb", "omdb"])
    cid, _ = core.catalog.merge(item("omdb", "tt1", synopsis="omdb text"))
    core.catalog.merge(item("tmdb", "movie:1", synopsis="tmdb text"))    # higher priority wins
    core.catalog.merge(item("omdb", "tt1", synopsis="omdb text again"))  # lower priority can't overwrite
    assert core.contents.get(cid).synopsis == "tmdb text"
    assert core.contents.provenance(cid)["synopsis"] == "tmdb"


def test_ratings_from_each_source_are_aggregated(core):
    cid, _ = core.catalog.merge(item("tmdb", "1", ratings={"tmdb": 7.9}))
    core.catalog.merge(item("omdb", "tt1", ratings={"imdb": 8.0}))
    assert core.contents.get(cid).ratings == {"tmdb": 7.9, "imdb": 8.0}


def test_search_aggregates_and_never_duplicates(core):
    first, _ = core.catalog.search(Criteria(genres=["scifi"]))
    again, _ = core.catalog.search(Criteria(genres=["scifi"]))
    assert {c.id for c in first} == {c.id for c in again}
    assert len(core.contents.all()) == len(first) > 0


def test_failing_provider_is_isolated_and_reported(core_with_down):
    contents, errors = core_with_down.catalog.search(Criteria(genres=["horror"]))
    assert contents and errors == ["fake_down"]


def test_falls_back_to_persisted_catalog_when_all_providers_fail(core):
    core.catalog.search(Criteria(genres=["horror"]))
    CONTROL["fail"] = True
    contents, errors = core.catalog.search(Criteria(genres=["horror"]))
    assert contents and errors == ["fake"]


def test_details_and_availability_cache_with_independent_policies(core):
    c = core.catalog.search(Criteria(genres=["scifi"]))[0][0]
    first = core.catalog.get(c.id)
    assert first.content.detailed and first.content.availability and first.content.runtime
    stamp_meta, stamp_av = first.content.metadata_updated_at, first.content.availability_updated_at
    CONTROL["fail"] = True  # fresh data → provider must not even be needed
    cached = core.catalog.get(c.id)
    assert cached.errors == [] and cached.content.metadata_updated_at == stamp_meta
    # availability goes stale (24h) while metadata (30d) stays valid
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    core.db.run("UPDATE contents SET availability_updated_at=? WHERE id=?", (old, c.id))
    assert core.catalog.avail_stale(core.contents.get(c.id)) and not core.catalog.meta_stale(core.contents.get(c.id))
    degraded = core.catalog.get(c.id)
    assert degraded.errors == ["fake"] and degraded.content.availability  # old data kept
    assert stamp_av  # (was set)


def test_forced_refresh_hits_providers_and_updates_dates(core):
    c = core.catalog.search(Criteria(genres=["drama"]))[0][0]
    before = core.catalog.get(c.id).content
    after = core.catalog.get(c.id, force=True)
    assert after.content.availability_updated_at >= before.availability_updated_at and not after.changed


def test_availability_is_per_country(core):
    c = core.catalog.search(Criteria(genres=["drama"]))[0][0]
    core.catalog.get(c.id)
    assert core.contents.get(c.id, "ES").availability and not core.contents.get(c.id, "FR").availability


def test_new_platforms_are_added_dynamically(core):
    from couchflix_app.domain.models import Offer
    pid = core.platforms.resolve(9999, "SkyShowtime")
    assert pid == core.platforms.resolve(9999, "SkyShowtime") and any(p["name"] == "SkyShowtime" for p in core.platforms.all())


def test_persistence_survives_reopening_the_database(tmp_path):
    path = tmp_path / "c.db"
    one = Couchflix(Db(path), {"fake": FakeProvider()})
    c = one.catalog.search(Criteria(genres=["scifi"]))[0][0]
    one.interact(c.id, rating="love", comment="obra maestra")
    two = Couchflix(Db(path), {"fake": FakeProvider()})
    assert two.contents.get(c.id).title == c.title
    assert two.users.state(c.id) == {"watched": False, "rating": "love", "comment": "obra maestra"}


def test_interactions_are_independent_and_reversible(core):
    c = core.catalog.search(Criteria())[0][0]
    core.interact(c.id, watched=True)
    assert core.users.state(c.id)["rating"] is None            # watched does not imply like/dislike
    core.interact(c.id, rating="like")
    core.interact(c.id, rating="dislike")
    core.interact(c.id, rating=None)
    state = core.users.state(c.id)
    assert state["watched"] and state["rating"] is None
    kinds = [a["kind"] for a in core.users.activity()]
    assert kinds[:4] == ["unrate", "dislike", "like", "watched"]


def test_concurrent_requests_never_duplicate_contents(core):
    """Two screens loading at once (carousel + discovery) must resolve the same title to one identity."""
    import threading
    threads = [threading.Thread(target=core.catalog.search, args=(Criteria(),)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    titles = [c.title for c in core.contents.all()]
    assert len(titles) == len(set(titles)) == 30
