-- Equivalent to Alembic c04_article_images. Use one migration method only.
-- Media rows survive article deletion because deployed static pages may use them.
CREATE TABLE article_images (
    id VARCHAR(36) PRIMARY KEY,
    article_id INTEGER REFERENCES articles(id) ON DELETE SET NULL,
    original_article_id INTEGER NOT NULL,
    storage_name VARCHAR(40) NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(40) NOT NULL,
    byte_size INTEGER NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_article_images_article_id ON article_images(article_id);
CREATE INDEX ix_article_images_original_article_id ON article_images(original_article_id);
CREATE TABLE article_imports (
    request_id VARCHAR(36) PRIMARY KEY,
    admin_id VARCHAR NOT NULL,
    article_id INTEGER REFERENCES articles(id) ON DELETE SET NULL,
    target_article_id INTEGER,
    payload_sha256 VARCHAR(64) NOT NULL,
    response JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_article_imports_article_id ON article_imports(article_id);
