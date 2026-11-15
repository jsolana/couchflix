from datetime import date

from couchflix_app.domain.criteria import Criteria, matches, refine
from couchflix_app.domain.models import Availability, Content, norm_title, platform_key
from couchflix_app.domain.profile import compute_profile, describe
from couchflix_app.services.agent.interpreter import interpret, interpret_rules
from couchflix_app.services.recommender import affinity, explain, filter_platforms, filter_unseen

PLATFORMS = ["Netflix", "Amazon Prime Video", "Disney+"]


# ---- profile weights
def test_no_signals_means_unknown_profile_shown_at_neutral_50():
    assert compute_profile([], []) is None
    assert describe(None).startswith("Tu personalidad audiovisual está por descubrir")


def test_rating_weights_love_gt_like_above_baseline_and_dislike_below():
    love = compute_profile([(["horror"], "love")], [])["horror"]
    like = compute_profile([(["horror"], "like")], [])["horror"]
    dislike = compute_profile([(["horror"], "dislike")], [])["horror"]
    assert love > like > 50 > dislike


def test_dimensions_without_signals_stay_at_50():
    dims = compute_profile([(["horror"], "love")], [])
    assert dims["horror"] > 50 and all(v == 50 for k, v in dims.items() if k != "horror")


def test_dislike_outweighs_a_like():   # strong negative signal (-3) vs moderate positive (+2)
    assert compute_profile([(["drama"], "like"), (["drama"], "dislike")], [])["drama"] < 50


def test_values_stay_within_0_100():
    assert compute_profile([(["drama"], "love")] * 100, [])["drama"] <= 100
    assert compute_profile([(["drama"], "dislike")] * 100, [])["drama"] >= 0


def test_watched_without_rating_is_neutral():
    assert compute_profile([(["drama"], "watched")], []) is None


def test_one_search_cannot_distort_the_profile():
    many = compute_profile([], [["horror"]] * 50)["horror"]
    assert 50 < many <= 62 and many < compute_profile([(["horror"], "like")], [])["horror"]


# ---- agent interpretation
def test_interprets_genre_runtime_rating_platform():
    c = interpret_rules("Quiero una película de aventuras que no dure más de dos horas, bien valorada y en Netflix", PLATFORMS)
    assert c.kind == "movie" and c.genres == ["adventure"] and c.max_runtime == 120
    assert c.min_rating == 7.5 and c.platforms == ["Netflix"]


def test_interprets_recency_similarity_and_flags():
    today = date(2026, 11, 15)
    assert interpret_rules("una película de los últimos dos años", PLATFORMS, today).year_from == 2024
    assert interpret_rules("Algo parecido a Interstellar", PLATFORMS).similar_to == "Interstellar"
    assert interpret_rules("algo que me sorprenda", PLATFORMS).surprise
    assert interpret_rules("algo diferente a lo que suelo ver", PLATFORMS).novelty
    assert interpret_rules("una serie corta", PLATFORMS).max_seasons == 2
    assert "family" in interpret_rules("algo para ver en familia", PLATFORMS).genres
    assert interpret_rules("terror que dé mucho miedo", PLATFORMS).genres == ["horror"]


def test_unrecognized_text_becomes_title_query_and_agent_is_labelled_rules():
    crit, agent = interpret("Blade Runner", PLATFORMS, llm=None)
    assert crit.query == "Blade Runner" and agent == "rules"


def test_llm_failure_falls_back_to_rules_honestly():
    class Broken:
        def complete(self, *_):
            raise RuntimeError("down")
    assert interpret("ciencia ficción", PLATFORMS, Broken())[1] == "rules"


def test_llm_json_is_sanitized():
    class Fine:
        def complete(self, *_):
            return 'claro: {"genres": ["scifi", "nonsense"], "max_runtime": 90, "evil": 1}'
    crit, agent = interpret("x", PLATFORMS, Fine())
    assert agent == "llm" and crit.genres == ["scifi"] and crit.max_runtime == 90


def test_refinements():
    base = Criteria(genres=["scifi"])
    assert refine(base, "recent", 2026, []).year_from == 2023
    assert refine(base, "action", 2026, []).genres == ["scifi", "action"]
    assert refine(base, "different", 2026, [1, 2]).exclude_ids == [1, 2]


# ---- filtering
def content(i, genres=("drama",), **kw):
    return Content(id=i, type="movie", title=f"T{i}", genres=list(genres), year=2024, **kw)


def test_excludes_seen_contents():
    assert [c.id for c in filter_unseen([content(1), content(2), content(3)], {2})] == [1, 3]


def test_platform_filter_keeps_only_streamable_on_my_platforms():
    on = content(1, availability_updated_at="x", availability=[Availability(8, "Netflix", None, "subscription", None)])
    rent = content(2, availability_updated_at="x", availability=[Availability(8, "Netflix", None, "rental", None)])
    other = content(3, availability_updated_at="x", availability=[Availability(9, "Max", None, "subscription", None)])
    unknown = content(4)  # availability never fetched
    assert [c.id for c in filter_platforms([on, rent, other, unknown], [8])] == [1, 4]
    assert len(filter_platforms([on, rent, other], [])) == 3  # no filter → everything


def test_matches_and_normalization_helpers():
    c = content(1, genres=("scifi", "drama"), runtime=100, ratings={"imdb": 8.0})
    assert matches(c, Criteria(genres=["scifi"], max_runtime=120, min_rating=7.5))
    assert not matches(c, Criteria(genres=["horror"])) and not matches(c, Criteria(max_runtime=90))
    assert norm_title("Amélie: Le Fabuleux!") == "amelie le fabuleux"
    assert platform_key("Amazon Prime Video") == platform_key("prime video") and platform_key("Disney+") == "disney plus"


def test_affinity_and_explanation():
    c = content(1, genres=("horror",), ratings={"imdb": 8.0})
    assert affinity(c, None) is None and affinity(c, {"horror": 80, "scifi": 0, "drama": 0, "romance": 0, "adventure": 0, "family": 0}) == 0.8
    assert "Netflix" in explain(c, 0.8, Criteria(genres=["horror"]), ["Netflix"], 2026)
