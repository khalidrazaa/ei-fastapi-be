import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Use your existing SQLAlchemy DB URL (with pgbouncer if that's your only option)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")


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


def record_migration(filename):
    """Record a migration as applied."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schema_migrations (filename, applied_at) VALUES (:filename, :applied_at)"
            ),
            {"filename": filename, "applied_at": datetime.utcnow()},
        )


def run_sql_file(path):
    """Run a SQL file with multiple statements."""
    with open(path, "r", encoding="utf-8") as file:
        sql = file.read()
    with engine.begin() as conn:
        for statement in sql.strip().split(";"):
            if statement.strip():
                conn.execute(text(statement))


if __name__ == "__main__":
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

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    migrations_dir = os.path.join(BASE_DIR, "history_sql_mig")

    for file_name in sorted(os.listdir(migrations_dir)):
        if file_name.endswith(".sql"):
            if has_migration_run(file_name):
                print(f"Skipping already applied migration: {file_name}")
                continue

            print(f"Running migration: {file_name}")
            try:
                run_sql_file(os.path.join(migrations_dir, file_name))
                record_migration(file_name)
                print(f"✅ Applied: {file_name}")
            except Exception as e:
                print(f"❌ Error running {file_name}: {e}")
                break
    else:
        print("All pending migrations applied successfully.")
