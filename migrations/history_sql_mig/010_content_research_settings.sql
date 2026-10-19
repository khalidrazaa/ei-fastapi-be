-- Equivalent to Alembic c02_research_settings. Use one migration method only.
CREATE TABLE content_research_settings (
    id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    instructions TEXT NOT NULL,
    source_groups JSON NOT NULL,
    CONSTRAINT ck_content_research_settings_singleton CHECK (id = 1),
    CONSTRAINT ck_content_research_settings_version CHECK (version >= 1),
    PRIMARY KEY (id)
);
