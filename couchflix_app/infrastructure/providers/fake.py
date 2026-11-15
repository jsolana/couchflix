"""TEST-ONLY providers. Registered solely when COUCHFLIX_PROVIDERS contains 'fake' / 'fake_down'.

They serve a fictional catalog (fixtures/test_catalog.json) so tests, demos and screenshots run offline.
They are never enabled by default and never used as real information in production.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ...domain.criteria import Criteria, matches
from ...domain.models import Content, Offer, ProviderItem, norm_title
from .base import ICatalogProvider, ProviderUnavailable

FIXTURE = Path(__file__).parent / "fixtures" / "test_catalog.json"
PLATFORM_IDS = {"Netflix": 8, "Amazon Prime Video": 119, "Max": 1899, "Disney+": 337, "Apple TV+": 350}
CONTROL = {"delay": 0.0, "fail": False}  # tweaked by the test-only control endpoint


class FakeProvider(ICatalogProvider):
    def __init__(self):
        self.items = {str(i["id"]): i for i in json.loads(FIXTURE.read_text())["items"]}

    def get_provider_name(self) -> str:
        return "fake"

    def is_available(self) -> bool:
        return True

    def _gate(self):
        time.sleep(CONTROL["delay"])
        if CONTROL["fail"]:
            raise ProviderUnavailable("fake provider forced to fail")

    def _item(self, d: dict, detailed: bool) -> ProviderItem:
        return ProviderItem(
            provider="fake", external_id=str(d["id"]), type=d["type"], title=d["title"],
            original_title=d["original_title"], synopsis=d["synopsis"], year=d["year"],
            poster=f"/__fixtures__/poster/{d['id']}.svg", genres=d["genres"], ratings={"imdb": d["rating"]},
            popularity=d["popularity"], runtime=d.get("runtime") if detailed else None,
            seasons=d.get("seasons") if detailed else None, detailed=detailed)

    def search(self, c: Criteria) -> list[ProviderItem]:
        self._gate()
        if c.similar_to:
            seed = next((d for d in self.items.values() if norm_title(c.similar_to) in norm_title(d["title"])), None)
            pool = [d for d in self.items.values() if seed and d is not seed and set(d["genres"]) & set(seed["genres"])]
        else:
            pool = list(self.items.values())
        out = []
        for d in pool:
            probe = Content(0, d["type"], d["title"], d["original_title"], year=d["year"], genres=d["genres"],
                            ratings={"imdb": d["rating"]}, runtime=d.get("runtime"), seasons=d.get("seasons"))
            query_ok = not c.query or norm_title(c.query) in norm_title(d["title"]) or c.query.lower() in d["synopsis"].lower()
            plat_ok = not c.platform_ids or any(PLATFORM_IDS.get(n) in c.platform_ids for n, m in d["platforms"] if m != "rental")
            hidden_ok = not c.hidden or d["popularity"] < 30
            if query_ok and plat_ok and hidden_ok and matches(probe, Criteria(**{**c.to_dict(), "query": None, "exclude_ids": []})):
                out.append(d)
        out.sort(key=lambda d: (d["rating"] if c.hidden or (c.min_rating or 0) >= 8 else d["popularity"]), reverse=True)
        return [self._item(d, False) for d in out]

    def get_details(self, external_id: str) -> ProviderItem:
        self._gate()
        return self._item(self.items[external_id], True)

    def get_availability(self, external_id: str, country: str) -> list[Offer]:
        self._gate()
        if country != "ES":
            return []
        return [Offer(PLATFORM_IDS.get(n), n, m, f"https://example.test/watch/{external_id}", f"/__fixtures__/icon/{PLATFORM_IDS.get(n)}.svg")
                for n, m in self.items[external_id]["platforms"]]


class FakeDownProvider(ICatalogProvider):
    """Always fails — lets acceptance tests check graceful degradation."""

    def get_provider_name(self) -> str:
        return "fake_down"

    def is_available(self) -> bool:
        return True

    def _boom(self, *_):
        raise ProviderUnavailable("fake_down is down on purpose")

    search = get_details = get_availability = _boom
