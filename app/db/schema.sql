-- 2026-02-01 add unique indexes for trends pipeline
CREATE UNIQUE INDEX IF NOT EXISTS ux_trend ON trend_items (trend);
CREATE UNIQUE INDEX IF NOT EXISTS ux_volume ON volume_points (trend_id, ts);