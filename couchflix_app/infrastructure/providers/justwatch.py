"""JustWatch adapter — intentionally NOT active.

Research summary (see README → "Proveedores"): JustWatch does not offer a public, documented API.
Its GraphQL endpoint is internal, unstable and its terms of use do not allow automated access without a
partnership agreement. COUCHFLIX therefore does not scrape it. Availability data from JustWatch reaches the
app legitimately through TMDB's watch-providers endpoint (attribution: "powered by JustWatch").

If you obtain an authorized JustWatch partner API, implement the three methods below and set
COUCHFLIX_PROVIDERS=tmdb,justwatch — no other code needs to change.
"""
from __future__ import annotations

from ...domain.criteria import Criteria
from ...domain.models import Offer, ProviderItem
from .base import ICatalogProvider, ProviderUnavailable


class JustWatchProvider(ICatalogProvider):
    def get_provider_name(self) -> str:
        return "justwatch"

    def is_available(self) -> bool:
        return False  # no authorized access available

    def _no_access(self):
        raise ProviderUnavailable("JustWatch no ofrece una API pública autorizada")

    def search(self, criteria: Criteria) -> list[ProviderItem]:
        self._no_access()

    def get_details(self, external_id: str) -> ProviderItem:
        self._no_access()

    def get_availability(self, external_id: str, country: str) -> list[Offer]:
        self._no_access()
