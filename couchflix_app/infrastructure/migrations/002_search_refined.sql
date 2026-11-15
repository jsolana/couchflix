-- Refinements ("otras opciones", "más reciente"…) repeat an earlier request: they are kept in history
-- but are not a new expression of taste, so they must not feed the profile.
ALTER TABLE searches ADD COLUMN refined INTEGER NOT NULL DEFAULT 0;
