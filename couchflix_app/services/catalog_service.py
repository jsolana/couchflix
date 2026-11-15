"""CatalogService: the only door to providers. Merges, normalizes, deduplicates and persists their data."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..domain.criteria import Criteria, matches
from ..domain.models import Content, ProviderItem, norm_title, now_iso
from ..infrastructure.providers.base import ICatalogProvider
from ..infrastructure.repositories import ContentRepo, PlatformRepo, Settings

log = logging.getLogger("couchflix.catalog")
ATTRS = ("type", "title", "original_title", "synopsis", "year", "poster", "runtime", "seasons", "genres", "popularity")


@dataclass
class Refreshed:
    content: Content
    changed: bool = False
    errors: list[str] = field(default_factory=list)


def _older_than(stamp: str | None, delta: timedelta) -> bool:
    return not stamp or datetime.now(timezone.utc) - datetime.fromisoformat(stamp) > delta


class CatalogService:
    def __init__(self, contents: ContentRepo, platforms: PlatformRepo, settings: Settings,
                 providers: dict[str, ICatalogProvider]):
        self.contents, self.platforms, self.settings, self.providers = contents, platforms, settings, providers
        self._identity = threading.RLock()  # find-or-create must be atomic, or concurrent requests duplicate contents

    # ---- providers
    def active_providers(self) -> list[ICatalogProvider]:
        enabled = self.settings.get("providers")
        return [p for name, p in self.providers.items()
                if (enabled is None or name in enabled) and p.is_available()]

    def _rank(self, provider: str) -> int:
        order = self.settings.get("provider_priority")
        return order.index(provider) if provider in order else len(order)

    @staticmethod
    def _run(jobs: list[tuple]) -> list[tuple]:
        """Run (key, fn, *args) jobs in parallel; return (key, result, error) so one failure never hides the rest."""
        if not jobs:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
            futures = [(job[0], pool.submit(job[1], *job[2:])) for job in jobs]
        out = []
        for key, fut in futures:
            try:
                out.append((key, fut.result(), None))
            except Exception as exc:  # provider down, network, quota…
                log.warning("provider call failed (%s): %s", key, exc)
                out.append((key, None, exc))
        return out

    # ---- normalization & identity
    def merge(self, item: ProviderItem) -> tuple[int, bool]:
        """Fold a provider item into the normalized catalog. Returns (content id, anything changed)."""
        with self._identity:
            return self._merge(item)

    def _merge(self, item: ProviderItem) -> tuple[int, bool]:
        cid = self.contents.find_by_source(item.provider, item.external_id) \
            or self.contents.find_by_match([item.title, item.original_title], item.year, item.type)
        created = cid is None
        if created:
            cid = self.contents.create(item.type, item.title)
        current, provenance = self.contents.get(cid), self.contents.provenance(cid)
        updates: dict = {}
        for attr in ATTRS:
            value = getattr(item, attr)
            if value in (None, "", []):
                continue
            owner = provenance.get(attr)
            if owner is None or self._rank(item.provider) <= self._rank(owner):  # priority decides discrepancies
                if getattr(current, attr) != value:
                    updates[attr] = value
                self.contents.set_provenance(cid, attr, item.provider)
        ratings = {**current.ratings, **item.ratings}
        if ratings != current.ratings:
            updates["ratings"] = ratings
        if item.detailed and not current.detailed:
            updates["detailed"] = 1
        if created or updates or item.detailed:
            updates["metadata_updated_at"] = now_iso()
        self.contents.update(cid, **updates)
        self.contents.save_source(cid, item.provider, item.external_id, item.extra)
        return cid, created or bool({k for k in updates} - {"metadata_updated_at", "detailed"})

    # ---- search
    def search(self, criteria: Criteria, min_provider_results: int = 5) -> tuple[list[Content], list[str]]:
        """Query active providers; falls back to / completes with the persisted catalog when they fail."""
        providers = self.active_providers()
        results = self._run([(p.get_provider_name(), p.search, criteria) for p in providers])
        errors = [name for name, _, err in results if err]
        ids: list[int] = []
        for _, items, err in results:
            ids += [self.merge(i)[0] for i in (items or [])]
        if errors or len(ids) < min_provider_results:
            ids += [c.id for c in self.contents.all(criteria.country) if matches(c, criteria)]
        ids = [i for i in dict.fromkeys(ids) if i not in criteria.exclude_ids]
        return self.contents.get_many(ids, criteria.country), errors

    # ---- freshness policies (metadata and availability are independent)
    def meta_stale(self, c: Content) -> bool:
        return not c.detailed or _older_than(c.metadata_updated_at, timedelta(days=self.settings.get("metadata_ttl_days")))

    def avail_stale(self, c: Content) -> bool:
        return _older_than(c.availability_updated_at, timedelta(hours=self.settings.get("availability_ttl_hours")))

    def refresh_availability(self, contents: list[Content], force: bool = False) -> list[str]:
        """Bring availability up to date for many contents at once (parallel provider calls)."""
        country, errors, jobs = self.settings.get("country"), [], []
        for c in contents:
            if force or self.avail_stale(c):
                for provider in self.active_providers():
                    ext = self.contents.sources(c.id).get(provider.get_provider_name())
                    if ext:
                        jobs.append(((c.id, provider.get_provider_name()), provider.get_availability, ext, country))
        for (cid, name), offers, err in self._run(jobs):
            if err:
                errors.append(name)
                continue
            rows = [(self.platforms.resolve(o.platform_id, o.platform_name, o.icon), o.mode, o.url) for o in offers]
            self.contents.replace_availability(cid, country, name, rows)
        return sorted(set(errors))

    def get(self, content_id: int, force: bool = False) -> Refreshed | None:
        """Content with fresh-enough data. `force` hits every provider (manual refresh)."""
        country = self.settings.get("country")
        before = self.contents.get(content_id, country)
        if not before:
            return None
        errors: list[str] = []
        snapshot = {(a.platform_id, a.mode) for a in before.availability}
        changed = False
        if force or self.meta_stale(before):
            known = self.contents.sources(content_id)
            jobs = [(p.get_provider_name(), p.get_details, known[p.get_provider_name()])
                    for p in self.active_providers() if p.get_provider_name() in known]
            # enrich: providers that don't know this content yet get a title lookup
            jobs += [(p.get_provider_name(), self._lookup, p, before)
                     for p in self.active_providers() if p.get_provider_name() not in known]
            for name, item, err in self._run(jobs):
                if err:
                    errors.append(name)
                elif item:
                    changed |= self.merge(item)[1]
            if not errors:  # a verified, error-free pass counts as an effective update even if nothing changed
                self.contents.update(content_id, metadata_updated_at=now_iso())
        errors += self.refresh_availability([before], force=force)
        after = self.contents.get(content_id, country)
        changed |= snapshot != {(a.platform_id, a.mode) for a in after.availability}
        return Refreshed(after, changed, sorted(set(errors)))

    @staticmethod
    def _lookup(provider: ICatalogProvider, c: Content) -> ProviderItem | None:
        """Find the same content in another provider by title + year + type (never by assuming ids match)."""
        for hit in provider.search(Criteria(query=c.title)):
            if hit.type == c.type and norm_title(hit.title) == norm_title(c.title) \
                    and (not hit.year or not c.year or abs(hit.year - c.year) <= 1):
                return provider.get_details(hit.external_id)
        return None
