import random

import pytest

from couchflix_app.application.couchflix import Couchflix
from couchflix_app.infrastructure.db import Db
from couchflix_app.infrastructure.providers.fake import CONTROL, FakeDownProvider, FakeProvider


@pytest.fixture(autouse=True)
def reset_fake():
    CONTROL.update(delay=0.0, fail=False)


@pytest.fixture
def core():
    """Application wired with the TEST-ONLY fake provider on an in-memory database."""
    app = Couchflix(Db(":memory:"), {"fake": FakeProvider()})
    app.recommender.rng = random.Random(7)
    return app


@pytest.fixture
def core_with_down():
    return Couchflix(Db(":memory:"), {"fake": FakeProvider(), "fake_down": FakeDownProvider()})
