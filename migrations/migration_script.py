import argparse
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

load_dotenv()

# Use your existing SQLAlchemy DB URL (with pgbouncer if that's your only option)
DATABASE_URL = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("ALEMBIC_DATABASE_URL or DATABASE_URL must be set.")

database_url = make_url(DATABASE_URL)
if database_url.drivername == "postgresql+asyncpg":
    database_url = database_url.set(drivername="postgresql+psycopg2")
engine = create_engine(database_url)


def ensure_migrations_table():
    """Create migrations tracking table if it doesn't exist."""
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """)
        )


def has_migration_run(filename):
    """Check if a migration file has already been applied."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM schema_migrations WHERE filename = :filename"),
            {"filename": filename},
        ).fetchone()
        return result is not None


def record_migration(filename, connection):
    """Record a migration as applied."""
    connection.execute(
        text(
            "INSERT INTO schema_migrations (filename, applied_at) "
            "VALUES (:filename, :applied_at)"
        ),
        {"filename": filename, "applied_at": datetime.now(timezone.utc)},
    )


def run_sql_file(path):
    """Run a SQL file with multiple statements."""
    with open(path, "r", encoding="utf-8") as file:
        sql = file.read()
    with engine.begin() as conn:
        for statement in sql.strip().split(";"):
            if statement.strip():
                conn.execute(text(statement))
        record_migration(os.path.basename(path), conn)


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    migrations_dir = os.path.join(BASE_DIR, "history_sql_mig")
    available_files = sorted(
        filename for filename in os.listdir(migrations_dir)
        if filename.endswith(".sql")
    )
    parser = argparse.ArgumentParser(description="Apply reviewed SQL migrations.")
    parser.add_argument(
        "--file", choices=available_files,
        help="Apply one SQL file instead of all untracked history files.",
    )
    args = parser.parse_args()
    DB_NAME = os.getenv("DB_NAME")
    # Safety: confirm DB name
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database()")).scalar()
        if db_name != DB_NAME:
            raise RuntimeError(
                f"Refusing to run on DB '{db_name}' — not the expected production DB!"
            )

    # Ensure migration tracking table exists
    ensure_migrations_table()

    for file_name in [args.file] if args.file else available_files:
        if file_name.endswith(".sql"):
            if has_migration_run(file_name):
                print(f"Skipping already applied migration: {file_name}")
                continue

            print(f"Running migration: {file_name}")
            try:
                run_sql_file(os.path.join(migrations_dir, file_name))
                print(f"Applied: {file_name}")
            except Exception as e:
                print(f"Error running {file_name}: {e}")
                raise SystemExit(1) from e
    else:
        print("All pending migrations applied successfully.")
