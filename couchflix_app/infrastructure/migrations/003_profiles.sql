-- Session profiles (family members). `users` is the profile row: alias = name, avatar = built-in id ("a1".."a12") or a data-URL.
-- Everything personal already hangs from users.id; the suggestion sessions now do too.
ALTER TABLE users ADD COLUMN avatar TEXT;
ALTER TABLE sessions ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1;
CREATE INDEX ix_sessions_user ON sessions (user_id, kind);
-- The pre-existing profile becomes "Javi" with a random built-in avatar.
UPDATE users SET alias = 'Javi', avatar = 'a' || (abs(random()) % 12 + 1) WHERE id = 1;
