-- Equivalent to Alembic c03_youtube_scan_controls. Use one migration method only.
ALTER TABLE popular_scan_settings ADD COLUMN youtube_scan_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE popular_scan_settings ADD COLUMN popular_scan_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE popular_scan_settings ADD COLUMN niche_scan_enabled BOOLEAN NOT NULL DEFAULT TRUE;
