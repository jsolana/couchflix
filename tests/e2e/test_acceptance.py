"""Acceptance tests (numbered after section 18.2 of the spec). Real browser, real app, fictional fixture catalog."""
import re
import time

import pytest
from playwright.sync_api import expect

PERSONAL = "[data-testid=personal]"
REAL_CARD = f"{PERSONAL} .card:not(.sk)"


def home(page, app):
    page.goto(app.url)
    expect(page.locator(REAL_CARD).first).to_be_visible(timeout=15000)


def open_first_card(page):
    page.locator(REAL_CARD).first.click()
    expect(page.get_by_test_id("detail-title")).to_be_visible()


def card_ids(page, section=PERSONAL):
    return page.evaluate("(s) => [...document.querySelectorAll(s + ' .card[data-id]')].map(c => c.dataset.id)", section)


# 1 ------------------------------------------------------------------------------------------------------------
def test_01_app_starts_with_three_sections(page, app):
    page.goto(app.url)
    expect(page).to_have_title(re.compile("COUCHFLIX"))
    expect(page.locator(".nav-item[data-route]")).to_have_text(["Sugerencias", "Buscar", "Perfil"])


# 2 ------------------------------------------------------------------------------------------------------------
def test_02_first_run_has_no_data_and_unknown_profile(page, app):
    assert app.api("GET", "/api/activity") == []
    page.goto(app.url + "/#/profile")
    expect(page.get_by_test_id("radar")).to_have_attribute("data-state", "done", timeout=5000)
    assert page.locator(".dim .num").all_inner_texts() == ["50"] * 6          # neutral baseline for a new user
    expect(page.get_by_test_id("description")).to_contain_text("por descubrir")
    expect(page.get_by_test_id("empty")).to_contain_text("Aquí aparecerá tu historial")
    assert app.api("GET", "/api/activity") == []                               # loading the app logged nothing


# 3 + 4 --------------------------------------------------------------------------------------------------------
def test_03_04_placeholders_then_progressive_reveal(page, app):
    app.control(delay=0.8)  # slow catalog → the skeleton phase is observable
    page.goto(app.url)
    track = page.locator(f"{PERSONAL} .track")
    skeletons = track.locator(".card.sk")
    expect(skeletons.first).to_be_visible()
    assert skeletons.count() >= 6 and track.locator(".card:not(.sk)").count() == 0
    size = "e => [e.offsetWidth, e.offsetHeight]"   # layout size (ignores in-flight transform animations)
    before = skeletons.first.evaluate(size)
    track_h = track.bounding_box()["height"]
    expect(page.locator(REAL_CARD).first).to_be_visible(timeout=20000)    # real cards replace placeholders
    assert page.locator(REAL_CARD).first.evaluate(size) == before                    # identical footprint
    assert abs(track.bounding_box()["height"] - track_h) <= 2                         # no layout jump
    expect(page.locator(f"{REAL_CARD} img.cover.loaded").first).to_be_attached()      # image faded in
    expect(page.locator(f"{PERSONAL} .carousel")).to_have_attribute("data-state", "ready")
    assert page.locator(".notice").is_hidden()


# 5 ------------------------------------------------------------------------------------------------------------
def test_05_carousel_navigation_arrows_keyboard_and_drag(page, app):
    home(page, app)
    track = page.locator(f"{PERSONAL} .track")
    page.locator(f"{PERSONAL} .carousel").hover()
    scroll = lambda: track.evaluate("t => t.scrollLeft")
    assert scroll() == 0
    page.locator(f"{PERSONAL} .car-arrow.r").click()
    page.wait_for_function("t => t.scrollLeft > 100", arg=track.element_handle())
    # keyboard
    first = page.locator(REAL_CARD).first
    first.focus()
    page.keyboard.press("ArrowRight")
    focused = page.evaluate("document.activeElement.dataset.id")
    assert focused and focused != first.get_attribute("data-id")
    # mouse drag
    start = scroll()
    box = track.bounding_box()
    page.mouse.move(box["x"] + 400, box["y"] + 120)
    page.mouse.down()
    page.mouse.move(box["x"] + 150, box["y"] + 120, steps=8)
    page.mouse.up()
    assert scroll() != start
    expect(page.get_by_test_id("detail")).to_have_count(0)  # a drag must not open a card


# 6 + 7 --------------------------------------------------------------------------------------------------------
def test_06_07_detail_opens_and_shows_update_dates(page, app):
    home(page, app)
    title = page.locator(REAL_CARD).first.locator("h3").inner_text()
    open_first_card(page)
    expect(page.get_by_test_id("detail-title")).to_have_text(title)
    expect(page).to_have_url(re.compile(r"#/c/\d+"))
    expect(page.get_by_test_id("synopsis")).not_to_be_empty()
    expect(page.get_by_test_id("offers")).to_contain_text("Netflix")
    pattern = re.compile(r"\d{1,2} \w{3,4} 2026 · \d{2}:\d{2}")
    expect(page.get_by_test_id("meta-updated")).to_have_text(pattern)
    expect(page.get_by_test_id("avail-updated")).to_have_text(pattern)
    expect(page.get_by_test_id("updated")).to_contain_text("Información actualizada el")
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("detail")).to_have_count(0)


# 8..11 --------------------------------------------------------------------------------------------------------
def pressed(page, act):
    return page.get_by_test_id(f"act-{act}").get_attribute("aria-pressed")


def test_08_mark_watched_is_independent_of_ratings(page, app):
    home(page, app)
    open_first_card(page)
    cid = page.url.split("/c/")[1]
    page.get_by_test_id("act-watched").click()
    expect(page.get_by_test_id("act-watched")).to_have_attribute("aria-pressed", "true")
    assert [pressed(page, a) for a in ("like", "love", "dislike")] == ["false"] * 3
    assert app.api("GET", f"/api/content/{cid}")["content"]["interaction"]["watched"] is True
    page.get_by_test_id("act-watched").click()   # reversible
    expect(page.get_by_test_id("act-watched")).to_have_attribute("aria-pressed", "false")


def test_09_10_11_like_love_dislike_are_exclusive_and_toggle(page, app):
    home(page, app)
    open_first_card(page)
    cid = page.url.split("/c/")[1]
    state = lambda: app.api("GET", f"/api/content/{cid}")["content"]["interaction"]["rating"]
    page.get_by_test_id("act-like").click()
    expect(page.get_by_test_id("act-like")).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("act-like")).to_have_class(re.compile("pop-like"))     # microinteraction fired
    assert state() == "like"
    page.get_by_test_id("act-love").click()
    expect(page.get_by_test_id("act-love")).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("act-like")).to_have_attribute("aria-pressed", "false")
    assert state() == "love"
    page.get_by_test_id("act-dislike").click()
    expect(page.get_by_test_id("act-dislike")).to_have_attribute("aria-pressed", "true")
    assert state() == "dislike"
    page.get_by_test_id("act-dislike").click()
    expect(page.get_by_test_id("act-dislike")).to_have_attribute("aria-pressed", "false")
    assert state() is None
    for act in ("watched", "like", "love", "dislike", "comment", "refresh"):  # accessible names + tooltips
        assert page.get_by_test_id(f"act-{act}").get_attribute("aria-label") == page.get_by_test_id(f"act-{act}").get_attribute("data-tip")


# 12 -----------------------------------------------------------------------------------------------------------
def test_12_comment(page, app):
    home(page, app)
    open_first_card(page)
    cid = page.url.split("/c/")[1]
    page.get_by_test_id("act-comment").click()
    expect(page.get_by_test_id("comment-pop")).to_be_visible()
    page.get_by_test_id("comment-text").fill("Un final que no esperaba")
    page.get_by_test_id("save-comment").click()
    expect(page.locator(".toast")).to_contain_text("Comentario guardado")
    expect(page.get_by_test_id("comment-pop")).to_be_hidden()
    expect(page.get_by_test_id("act-comment")).to_have_attribute("aria-pressed", "true")
    assert app.api("GET", f"/api/content/{cid}")["content"]["interaction"]["comment"] == "Un final que no esperaba"


# 13 -----------------------------------------------------------------------------------------------------------
def test_13_manual_refresh_updates_dates_and_reports_no_changes(page, app):
    home(page, app)
    open_first_card(page)
    stamp = page.get_by_test_id("avail-updated").get_attribute("datetime")
    time.sleep(1.2)
    page.get_by_test_id("act-refresh").click()
    expect(page.get_by_test_id("act-refresh")).to_have_class(re.compile("spin"))     # visible refreshing state
    expect(page.locator(".toast")).to_contain_text("sin cambios", timeout=10000)
    assert page.get_by_test_id("avail-updated").get_attribute("datetime") > stamp


def test_13b_refresh_error_keeps_previous_data(page, app):
    home(page, app)
    open_first_card(page)
    synopsis = page.get_by_test_id("synopsis").inner_text()
    app.control(fail=True)
    page.get_by_test_id("act-refresh").click()
    expect(page.locator(".toast.err")).to_contain_text("No se pudo actualizar", timeout=10000)
    expect(page.get_by_test_id("synopsis")).to_have_text(synopsis)
    expect(page.get_by_test_id("offers")).to_contain_text("Netflix")


# 14 + 15 ------------------------------------------------------------------------------------------------------
def seed_ratings(app, n=5):
    ids = [c["id"] for c in app.api("GET", "/api/suggestions/personal")["items"]][:n]
    for i, cid in enumerate(ids):
        app.api("PUT", f"/api/content/{cid}/interaction", json={"rating": "love" if i % 2 else "like"})
    return ids


def test_14_15_profile_radar_builds_from_the_centre(page, app):
    seed_ratings(app)
    home(page, app)
    page.get_by_role("link", name="Perfil").click()
    radar = page.get_by_test_id("radar")
    expect(radar).to_be_visible()
    t0 = time.monotonic()
    shape = page.locator("[data-testid=radar-shape]")
    assert radar.get_attribute("data-state") == "building"
    points = lambda: shape.get_attribute("points")
    assert set(points().split()) == {"230.0,230.0"}                        # every point starts at the origin
    cx = lambda: [float(d.get_attribute("cx")) for d in page.locator("svg.radar .dot").all()]
    assert set(cx()) == {230.0}
    expect(radar).to_have_attribute("data-state", "done", timeout=5000)
    elapsed = time.monotonic() - t0
    assert 0.6 < elapsed < 2.5, elapsed                                       # smooth, not abrupt, not endless
    assert set(points().split()) != {"230.0,230.0"} and len(set(cx())) > 1  # polygon reached its values
    expect(page.get_by_test_id("legend")).to_have_class(re.compile("show"))
    values = [int(v) for v in page.locator(".dim .num").all_inner_texts() if v.isdigit()]
    assert len(values) == 6 and max(values) > 0
    expect(page.get_by_test_id("description")).not_to_contain_text("por descubrir")


def test_15b_reduced_motion_skips_the_animation(browser, app):
    seed_ratings(app)
    page = browser.new_context(reduced_motion="reduce", viewport={"width": 1280, "height": 800}).new_page()
    page.goto(app.url + "/#/profile")
    expect(page.get_by_test_id("radar")).to_have_attribute("data-state", "done", timeout=1500)
    cx = page.locator("svg.radar .dot").evaluate_all("dots => dots.map(d => d.getAttribute('cx'))")
    assert set(cx) != {"230"}


# 16 -----------------------------------------------------------------------------------------------------------
def test_16_history_lists_activity_and_opens_detail(page, app):
    ids = seed_ratings(app, 2)
    app.api("PUT", f"/api/content/{ids[0]}/interaction", json={"watched": True, "comment": "Muy buena"})
    app.api("POST", "/api/search", json={"text": "algo de terror"})
    page.goto(app.url + "/#/profile")
    kinds = page.locator("[data-testid=timeline] .event")
    expect(kinds.first).to_be_visible()
    seen = {k for k in page.locator("[data-testid=timeline] .event").evaluate_all("els => els.map(e => e.dataset.kind)")}
    assert {"search", "watched", "comment", "like", "love"} <= seen
    page.locator("[data-testid=timeline] a.event").first.click()
    expect(page.get_by_test_id("detail")).to_be_visible()


# 17 + 18 ------------------------------------------------------------------------------------------------------
def test_17_18_agent_search_and_visual_results(page, app):
    page.goto(app.url + "/#/search")
    page.get_by_test_id("ask-input").fill("Quiero una película de ciencia ficción de menos de dos horas, bien valorada y en Netflix")
    page.get_by_test_id("ask-submit").click()
    results = page.locator("[data-testid=search-results] .card:not(.sk)")
    expect(results.first).to_be_visible(timeout=15000)
    chips = page.locator("#understood .pill").all_inner_texts()
    assert {"Ciencia ficción", "Película", "≤ 120 min", "★ 7.5+", "Netflix"} <= set(chips)
    expect(page.get_by_test_id("agent-tag")).to_have_text("Reglas")               # honest: rules, not an LLM
    expect(page.get_by_test_id("why").first).not_to_be_empty()                   # short justification
    ids = card_ids(page, "[data-testid=search-results]")
    for cid in ids:                                                              # every result honours the request
        c = app.api("GET", f"/api/content/{cid}")["content"]
        assert "Ciencia ficción" in c["genres"] and c["type"] == "movie" and c["runtime"] <= 120
        assert any(o["name"] == "Netflix" and o["mode"] == "subscription" for o in c["offers"])


def test_17b_refinements_and_last_search_in_suggestions(page, app):
    page.goto(app.url + "/#/search")
    page.get_by_test_id("ask-input").fill("una película")
    page.keyboard.press("Enter")
    expect(page.locator("[data-testid=search-results] .card:not(.sk)").first).to_be_visible(timeout=15000)
    first_ids = card_ids(page, "[data-testid=search-results]")
    page.get_by_test_id("refine-more").click()
    expect(page.locator("[data-testid=search-results] .card:not(.sk)").first).to_be_visible(timeout=15000)
    assert not set(first_ids) & set(card_ids(page, "[data-testid=search-results]"))   # "otras opciones"
    page.get_by_test_id("refine-recent").click()
    expect(page.locator("#understood")).to_contain_text("Desde", timeout=15000)
    page.get_by_role("link", name="Sugerencias").click()
    expect(page.get_by_test_id("last-search")).to_be_visible()     # kept apart from the personalized carousel
    assert page.locator(f"{PERSONAL} [data-testid=last-search]").count() == 0


def test_18b_no_results_state(page, app):
    page.goto(app.url + "/#/search")
    page.get_by_test_id("ask-input").fill("una película del oeste de menos de 30 minutos")
    page.get_by_test_id("ask-submit").click()
    expect(page.get_by_test_id("empty")).to_contain_text("Nada encaja", timeout=10000)


# 19 -----------------------------------------------------------------------------------------------------------
def test_19_new_random_couch_sessions(page, app):
    home(page, app)
    disc = page.locator("[data-testid=discovery]")
    expect(disc.locator("[data-testid=theme] .card:not(.sk)").first).to_be_visible(timeout=15000)
    gen = app.api("GET", "/api/suggestions/discovery")["generated_at"]
    time.sleep(1.1)
    with page.expect_response(lambda r: r.url.endswith("/api/suggestions/discovery/refresh") and r.ok):
        page.get_by_test_id("refresh-discovery").click()
    expect(disc.locator("[data-testid=theme] .card:not(.sk)").first).to_be_visible(timeout=15000)
    assert app.api("GET", "/api/suggestions/discovery")["generated_at"] > gen
    expect(page.get_by_role("heading", name="Random Couch Sessions")).to_be_visible()


def test_19b_navigation_never_triggers_new_searches(page, app):
    home(page, app)
    calls = []
    page.on("request", lambda r: calls.append(r.url) if "/api/suggestions" in r.url else None)
    for route in ("Buscar", "Perfil", "Sugerencias"):
        page.get_by_role("link", name=route).click()
    page.wait_for_timeout(500)
    assert calls == []


# 20 + 21 ------------------------------------------------------------------------------------------------------
def test_20_21_persistence_across_restart(page, app):
    home(page, app)
    shown = card_ids(page)
    themes = app.api("GET", "/api/suggestions/discovery")["themes"]
    open_first_card(page)
    cid = page.url.split("/c/")[1]
    page.get_by_test_id("act-love").click()
    page.get_by_test_id("act-comment").click()
    page.get_by_test_id("comment-text").fill("Para repetir")
    page.get_by_test_id("save-comment").click()
    expect(page.locator(".toast").last).to_contain_text("Comentario guardado")
    app.restart(providers="fake_down")      # providers can't answer any more: everything must come from SQLite
    page.goto(app.url + f"/#/c/{cid}")
    expect(page.get_by_test_id("act-love")).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("comment-text")).to_have_value("Para repetir")
    expect(page.get_by_test_id("meta-updated")).to_be_visible()
    page.goto(app.url + "/#/suggestions")
    page.reload()
    expect(page.locator(f"{PERSONAL} .card:not(.sk)").first).to_be_visible(timeout=15000)
    kept = [i for i in shown if i != cid]                                      # the loved one is no longer suggested
    assert card_ids(page) == kept                                              # same recommendations, not regenerated
    assert app.api("GET", "/api/suggestions/discovery")["themes"][0]["title"] == themes[0]["title"]
    page.goto(app.url + "/#/profile")
    expect(page.get_by_test_id("radar")).to_have_attribute("data-state", "done", timeout=5000)
    expect(page.locator("[data-testid=timeline] .event").first).to_be_visible()


# 22 -----------------------------------------------------------------------------------------------------------
def test_22_changing_platforms_changes_suggestions(page, app):
    home(page, app)
    assert page.locator(f"{PERSONAL} .card:not(.sk) .plats img[alt=Netflix]").count() > 0
    page.get_by_role("button", name="Configuración").click()
    expect(page.get_by_test_id("settings")).to_be_visible()
    page.get_by_test_id("platform-netflix").click()
    page.get_by_test_id("platform-disney-plus").click()
    expect(page.get_by_test_id("platform-disney-plus")).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("platform-netflix")).to_have_attribute("aria-pressed", "false")
    page.keyboard.press("Escape")
    cards = page.locator(f"{PERSONAL} .card:not(.sk)")
    expect(cards.first).to_be_visible(timeout=15000)
    page.wait_for_timeout(500)
    for card in cards.all():
        assert card.locator(".plats img[alt=Disney\\+]").count() == 1
    # everything off: no silent Netflix fallback, the user is told and results are unfiltered
    page.get_by_role("button", name="Configuración").click()
    page.get_by_test_id("platform-disney-plus").click()
    expect(page.get_by_text("Sin plataformas activas")).to_be_visible()


# 23 -----------------------------------------------------------------------------------------------------------
def test_23_works_with_an_unavailable_provider(page, app_factory):
    app = app_factory("fake,fake_down")
    home(page, app)
    expect(page.get_by_test_id("provider-notice")).to_be_visible()
    assert page.locator(f"{PERSONAL} .card:not(.sk)").count() >= 5
    page.get_by_role("link", name="Buscar").click()
    page.get_by_test_id("ask-input").fill("una película")
    page.keyboard.press("Enter")
    expect(page.locator("[data-testid=search-results] .card:not(.sk)").first).to_be_visible(timeout=15000)
    open_first = page.locator("[data-testid=search-results] .card").first
    open_first.click()
    expect(page.get_by_test_id("detail-title")).to_be_visible()
    expect(page.get_by_test_id("synopsis")).not_to_be_empty()


def test_23b_unconfigured_app_asks_for_a_provider(page, app_factory):
    app = app_factory("tmdb")            # real provider, no API key → graceful setup state, no fake data
    page.goto(app.url)
    expect(page.get_by_test_id("empty").first).to_contain_text("Conecta un catálogo")
    assert page.locator(".card:not(.sk)").count() == 0


# extras: shell, settings ---------------------------------------------------------------------------------------
def test_sidebar_collapses_and_remembers_state(page, app):
    page.goto(app.url)
    width = lambda: page.locator(".sidebar").bounding_box()["width"]
    expanded = width()
    page.get_by_role("button", name="Expandir o contraer el menú").click()
    page.wait_for_timeout(500)
    assert width() < expanded / 2
    page.reload()
    page.wait_for_timeout(500)
    assert width() < expanded / 2
    page.locator('.nav-item[data-route="search"]').hover()
    expect(page.locator('.nav-item[data-route="search"]')).to_have_attribute("data-tip", "Buscar")


def test_mobile_layout_has_no_horizontal_scroll(browser, app):
    page = browser.new_context(viewport={"width": 390, "height": 800}, has_touch=True).new_page()
    page.goto(app.url)
    expect(page.locator(REAL_CARD).first).to_be_visible(timeout=15000)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.locator(".sidebar").bounding_box()["y"] > 600      # bottom navigation on phones


def test_export_contains_user_history(page, app):
    seed_ratings(app, 2)
    data = app.api("GET", "/api/export")
    assert len(data["interactions"]) == 2 and data["activity"]


# session profiles ----------------------------------------------------------------------------------------------
def picker(page, app):
    page.goto(app.url + "/?picker")
    expect(page.get_by_test_id("picker")).to_be_visible()


def test_first_screen_is_the_profile_picker_with_the_existing_profile(page, app):
    picker(page, app)
    expect(page.get_by_role("heading", name="¿Quién está viendo?")).to_be_visible()
    expect(page.locator(".pf-card:not(.add) .pf-name")).to_have_text(["Javi"])
    expect(page.locator("#app")).to_be_hidden()
    page.get_by_test_id("profile-1").click()
    expect(page.locator(REAL_CARD).first).to_be_visible(timeout=15000)
    expect(page.get_by_test_id("switch-profile")).to_contain_text("Javi")


def test_create_profile_with_avatar_isolated_data_and_switching(page, app):
    seed_ratings(app, 2)                                      # the default profile has history
    picker(page, app)
    page.get_by_test_id("add-profile").click()
    expect(page.locator("[data-testid^=avatar-]")).to_have_count(12)
    page.get_by_test_id("profile-name").press_sequentially("Lucía")      # real key presses (fill() would hide a blocked keydown)
    expect(page.get_by_test_id("profile-name")).to_have_value("Lucía")
    page.get_by_test_id("avatar-a7").click()
    page.get_by_test_id("save-profile").click()
    page.get_by_test_id("profile-2").click()
    expect(page.get_by_test_id("switch-profile")).to_contain_text("Lucía")
    page.goto(app.url + "/?picker#/profile")
    expect(page.get_by_test_id("picker")).to_be_hidden()      # a reload keeps the chosen profile
    assert app.api("GET", "/api/activity", headers={"X-Profile": "2"}) == []
    assert app.api("GET", "/api/activity")                    # Perfil (1) keeps its own
    page.get_by_test_id("switch-profile").click()             # back to the picker
    expect(page.get_by_test_id("picker")).to_be_visible()


def test_edit_and_delete_profile_with_confirmation(page, app):
    app.api("POST", "/api/profiles", json={"name": "Tmp", "avatar": "a2"})
    picker(page, app)
    page.get_by_test_id("manage-profiles").click()
    page.get_by_test_id("profile-2").click()
    page.get_by_test_id("profile-name").fill("Peque")
    page.get_by_test_id("avatar-a9").click()
    page.get_by_test_id("save-profile").click()
    expect(page.get_by_test_id("profile-2")).to_contain_text("Peque")
    page.get_by_test_id("profile-2").click()
    page.get_by_test_id("delete-profile").click()
    expect(page.get_by_text("No se puede deshacer")).to_be_visible()
    page.get_by_test_id("confirm-delete").click()
    expect(page.get_by_test_id("profile-2")).to_have_count(0)


def test_api_rejects_unknown_profile(app):
    import httpx
    assert httpx.get(app.url + "/api/profile", headers={"X-Profile": "99"}).status_code == 401
