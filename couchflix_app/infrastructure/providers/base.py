"""Common contract for every catalog provider (TMDB, JustWatch, OMDb, …)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ...domain.criteria import Criteria
from ...domain.models import Offer, ProviderItem


class ProviderUnavailable(Exception):
    """The provider cannot be used right now (no credentials, no network, not permitted…)."""


class ICatalogProvider(ABC):
    @abstractmethod
    def get_provider_name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap local check (credentials configured, enabled…). Must not hit the network."""

    @abstractmethod
    def search(self, criteria: Criteria) -> list[ProviderItem]: ...

    @abstractmethod
    def get_details(self, external_id: str) -> ProviderItem: ...

    @abstractmethod
    def get_availability(self, external_id: str, country: str) -> list[Offer]: ...
