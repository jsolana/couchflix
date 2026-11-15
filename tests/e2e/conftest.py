"""Acceptance-test harness: boots the real app (`python -m couchflix_app`) on a free port with TEST-ONLY providers
(fictional fixtures) and an isolated SQLite file. No Internet needed."""
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest


class App:
    def __init__(self, tmp_path, providers="fake"):
        self.dir, self.providers = tmp_path, providers
        self.db = tmp_path / "couchflix.db"
        self.port, self.proc = None, None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self, providers=None):
        self.providers = providers or self.providers
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        env = {**os.environ, "COUCHFLIX_DB": str(self.db), "COUCHFLIX_PORT": str(self.port),
               "COUCHFLIX_PROVIDERS": self.providers, "TMDB_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}
        self.proc = subprocess.Popen([sys.executable, "-m", "couchflix_app"], cwd=self.dir, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if httpx.get(self.url + "/api/profile", timeout=1).status_code == 200:
                    return self
            except httpx.HTTPError:
                time.sleep(0.1)
        raise RuntimeError("app did not start")

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(3)
            except subprocess.TimeoutExpired:   # open keep-alive connections from the browser
                self.proc.kill()
                self.proc.wait()
            self.proc = None

    def restart(self, providers=None):
        self.stop()
        return self.start(providers)

    # helpers to drive/inspect the app from tests
    def api(self, method, path, **kw):
        r = httpx.request(method, self.url + path, timeout=15, **kw)
        r.raise_for_status()
        return r.json()

    def control(self, **kw):  # test-only knob of the fake provider (delay / fail)
        return self.api("POST", "/__test__/control", json=kw)


@pytest.fixture
def app(tmp_path):
    a = App(tmp_path).start()
    yield a
    a.stop()


@pytest.fixture
def app_factory(tmp_path):
    made = []

    def make(providers="fake"):
        made.append(App(tmp_path, providers).start())
        return made[-1]
    yield make
    for a in made:
        a.stop()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1440, "height": 900}, "locale": "es-ES"}
