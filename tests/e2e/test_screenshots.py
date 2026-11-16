"""Regenerates docs/screenshots/*.png for the README. Opt-in:  ./couchflix test -m screenshots
Screenshots use the fictional TEST catalog (fixtures) so they can be produced offline and without API keys."""
from pathlib import Path

import pytest
from playwright.sync_api import expect

OUT = Path(__file__).resolve().parents[2] / "docs" / "screenshots"
pytestmark = pytest.mark.screenshots


@pytest.fixture
def lived_in(app):
    """A user with some history, so the profile and the carousels look like a real session."""
    for query, rating, how_many in [("terror", "love", 1), ("ciencia ficción", "love", 1), ("ciencia ficción", "like", 1),
                                    ("drama", "like", 1), ("romance", "like", 1), ("aventuras", "love", 1)]:
        for card in app.api("POST", "/api/search", json={"text": query})["items"][:how_many]:
            app.api("PUT", f"/api/content/{card['id']}/interaction", json={"rating": rating})
    app.api("POST", "/api/suggestions/personal/refresh")
    app.api("POST", "/api/suggestions/discovery/refresh")
    return app


def test_screenshots(page, app, lived_in):
    OUT.mkdir(parents=True, exist_ok=True)
    shot = lambda name, **kw: page.screenshot(path=str(OUT / f"{name}.png"), **kw)

    # 1. initial state with placeholders (fresh first run: nothing persisted, slow catalog)
    from tests.e2e.conftest import App
    (app.dir / "first-run").mkdir()
    first = App(app.dir / "first-run").start()
    try:
        first.control(delay=1.5)
        page.goto(first.url)
        expect(page.locator("[data-testid=personal] .card.sk").first).to_be_visible()
        page.wait_for_timeout(900)
        shot("initial-placeholders")
    finally:
        first.stop()

    # 2. home + 3. carousel
    page.goto(lived_in.url)
    expect(page.locator("[data-testid=personal] .card:not(.sk)").first).to_be_visible(timeout=15000)
    expect(page.locator("[data-testid=discovery] .card:not(.sk)").first).to_be_visible(timeout=15000)
    page.wait_for_timeout(1200)
    shot("home")
    page.locator("[data-testid=personal] .carousel").hover()
    shot("carousel", clip={"x": 232, "y": 150, "width": 1208, "height": 420})

    # 4. detail
    page.locator("[data-testid=personal] .card:not(.sk)").first.click()
    expect(page.get_by_test_id("detail-title")).to_be_visible()
    page.get_by_test_id("act-love").click()
    page.wait_for_timeout(1300)
    page.get_by_test_id("act-love").hover()
    shot("detail")
    page.keyboard.press("Escape")

    # 5. profile with radar
    page.get_by_role("link", name="Perfil").click()
    expect(page.get_by_test_id("radar")).to_have_attribute("data-state", "done", timeout=5000)
    page.wait_for_timeout(1200)
    shot("profile")

    # 6. search + 7. agent results
    page.get_by_role("link", name="Buscar").click()
    page.wait_for_timeout(500)
    page.get_by_test_id("ask-input").fill("")
    shot("search")
    page.get_by_test_id("ask-input").fill("Quiero una película de aventuras que no dure más de dos horas, bien valorada y en Netflix")
    page.get_by_test_id("ask-submit").click()
    expect(page.locator("[data-testid=search-results] .card:not(.sk)").first).to_be_visible(timeout=15000)
    page.wait_for_timeout(1500)
    shot("agent-results")

    # 8. session profiles: picker, manage mode and the create/edit panel (a small family, built-in avatars)
    for name, avatar in [("Lucía", "a7"), ("Marcos", "a2"), ("Peque", "a9")]:
        lived_in.api("POST", "/api/profiles", json={"name": name, "avatar": avatar})
    lived_in.api("PUT", "/api/profiles/1", json={"name": "Javi", "avatar": "a10"})
    page.evaluate("sessionStorage.clear()")          # forget the preselected profile
    page.goto(lived_in.url + "/?picker")
    expect(page.locator(".pf-card:not(.add)")).to_have_count(4)
    page.wait_for_timeout(900)
    shot("profile-picker")
    page.get_by_test_id("manage-profiles").click()
    page.wait_for_timeout(300)
    page.get_by_test_id("profile-3").click()
    expect(page.get_by_test_id("profile-editor")).to_be_visible()
    page.wait_for_timeout(700)
    shot("profile-manage")
