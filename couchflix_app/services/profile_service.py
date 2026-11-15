"""Builds the audiovisual profile from the persisted history (always recomputable)."""
from __future__ import annotations

from collections import Counter

from ..domain.models import GENRES
from ..domain.profile import BASELINE, DIMENSIONS, DIM_META, compute_profile, describe
from ..infrastructure.repositories import UserRepo


class ProfileService:
    def __init__(self, users: UserRepo):
        self.users = users

    def compute(self) -> dict[str, int] | None:
        return compute_profile(self.users.rated(), self.users.searched_genres())

    def recalculate(self) -> dict[str, int] | None:
        """Recompute from history and keep a snapshot whenever the profile changed (feeds 'evolution')."""
        dims = self.compute()
        snaps = self.users.snapshots(1)
        if dims and (not snaps or snaps[-1]["dims"] != dims):
            self.users.add_snapshot(dims)
        return dims

    def view(self) -> dict:
        dims = self.compute()
        snaps = self.users.snapshots(12)
        liked = Counter(g for genres, rating in self.users.rated() if rating in ("like", "love")
                        for g in genres for _ in range(2 if rating == "love" else 1))
        evolution = []
        if len(snaps) >= 2:
            first, last = snaps[0]["dims"], snaps[-1]["dims"]
            evolution = [{"key": k, "label": DIM_META[k][0], "delta": last[k] - first.get(k, BASELINE)}
                         for k in last if last[k] != first.get(k, BASELINE)]
        return {
            "known": dims is not None,
            "dimensions": [{"key": k, "label": label, "tagline": tag, "value": dims[k] if dims else BASELINE}
                           for k, label, tag, _ in DIMENSIONS],
            "top_genres": [GENRES[g] for g, _ in liked.most_common(3)],
            "description": describe(dims),
            "evolution": {"deltas": evolution, "history": [round(sum(s["dims"].values()) / len(s["dims"])) for s in snaps]},
        }
