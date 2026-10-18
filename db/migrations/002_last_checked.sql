-- Store only price CHANGES; remember when each listing was last checked.
ALTER TABLE listings ADD COLUMN IF NOT EXISTS last_checked TIMESTAMPTZ;
