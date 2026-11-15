CREATE TABLE users (
  id INTEGER PRIMARY KEY, alias TEXT NOT NULL, country TEXT NOT NULL DEFAULT 'ES',
  preferences TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
INSERT INTO users (id, alias, country, created_at) VALUES (1, 'Tú', 'ES', datetime('now'));

CREATE TABLE platforms (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, key TEXT NOT NULL UNIQUE,
  external_id INTEGER, icon TEXT, subscribed INTEGER NOT NULL DEFAULT 0
);
-- Initial platforms. Only Netflix is subscribed until the user configures their own.
INSERT INTO platforms (name, key, external_id, subscribed) VALUES
  ('Netflix', 'netflix', 8, 1), ('Amazon Prime Video', 'prime video', 119, 0),
  ('HBO Max', 'hbo max', 384, 0), ('Max', 'max', 1899, 0), ('Disney+', 'disney plus', 337, 0),
  ('Apple TV+', 'apple tv plus', 350, 0), ('Crunchyroll', 'crunchyroll', 283, 0),
  ('Rakuten TV', 'rakuten tv', 35, 0), ('Atresplayer', 'atresplayer', NULL, 0),
  ('Movistar Plus+', 'movistar plus', 149, 0), ('Orange TV', 'orange tv', NULL, 0);

CREATE TABLE contents (
  id INTEGER PRIMARY KEY, type TEXT NOT NULL, title TEXT NOT NULL, original_title TEXT,
  norm_title TEXT NOT NULL, norm_original TEXT, synopsis TEXT, year INTEGER, poster TEXT,
  runtime INTEGER, seasons INTEGER, genres TEXT NOT NULL DEFAULT '[]', ratings TEXT NOT NULL DEFAULT '{}',
  popularity REAL, detailed INTEGER NOT NULL DEFAULT 0,
  metadata_updated_at TEXT, availability_updated_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX ix_contents_match ON contents (norm_title, type);

CREATE TABLE content_sources (
  provider TEXT NOT NULL, external_id TEXT NOT NULL, content_id INTEGER NOT NULL REFERENCES contents (id),
  raw TEXT, fetched_at TEXT NOT NULL, PRIMARY KEY (provider, external_id)
);
CREATE INDEX ix_sources_content ON content_sources (content_id);

CREATE TABLE provenance (
  content_id INTEGER NOT NULL, attribute TEXT NOT NULL, provider TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (content_id, attribute)
);

CREATE TABLE availability (
  content_id INTEGER NOT NULL, platform_id INTEGER NOT NULL, mode TEXT NOT NULL, country TEXT NOT NULL,
  url TEXT, source TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (content_id, platform_id, mode, country, source)
);

CREATE TABLE interactions (
  user_id INTEGER NOT NULL, content_id INTEGER NOT NULL, watched INTEGER NOT NULL DEFAULT 0,
  rating TEXT, comment TEXT, origin TEXT, updated_at TEXT NOT NULL, PRIMARY KEY (user_id, content_id)
);

CREATE TABLE activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
  content_id INTEGER, detail TEXT, created_at TEXT NOT NULL
);

CREATE TABLE searches (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, query TEXT NOT NULL,
  criteria TEXT NOT NULL, results TEXT NOT NULL, origin TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE profile_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, dims TEXT NOT NULL, computed_at TEXT NOT NULL
);

CREATE TABLE sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, criteria TEXT NOT NULL DEFAULT '{}',
  results TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);

CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
