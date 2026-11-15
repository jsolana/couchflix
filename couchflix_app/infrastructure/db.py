"""SQLite access: one connection, serialized by a lock, plus a tiny migration runner."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

MIGRATIONS = Path(__file__).parent / "migrations"


class Db:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.migrate()

    def run(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(sql, params).fetchone()

    def migrate(self) -> None:
        with self.lock:
            self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (name TEXT PRIMARY KEY)")
            done = {r[0] for r in self.conn.execute("SELECT name FROM schema_version")}
            for script in sorted(MIGRATIONS.glob("*.sql")):
                if script.name not in done:
                    self.conn.executescript(script.read_text())
                    self.conn.execute("INSERT INTO schema_version VALUES (?)", (script.name,))
                    self.conn.commit()
