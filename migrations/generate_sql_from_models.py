import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateColumn, CreateIndex, CreateTable

from app.db.base import Base

load_dotenv()

DATABASE_URL = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("ALEMBIC_DATABASE_URL or DATABASE_URL must be set.")

database_url = make_url(DATABASE_URL)
if database_url.drivername == "postgresql+asyncpg":
    database_url = database_url.set(drivername="postgresql+psycopg2")
engine = create_engine(database_url)
inspector = inspect(engine)

# Folder where .sql files will be saved
migrations_dir = os.path.join(os.path.dirname(__file__), "history_sql_mig")
os.makedirs(migrations_dir, exist_ok=True)

# Find the next migration number
existing_files = [f for f in os.listdir(migrations_dir) if f.endswith(".sql")]
if existing_files:
    max_num = max(int(f.split("_")[0]) for f in existing_files)
    next_num = max_num + 1
else:
    next_num = 1

migration_filename = f"{next_num:03d}_update_tables.sql"
migration_file = os.path.join(migrations_dir, migration_filename)

statements = []

for table in Base.metadata.sorted_tables:
    table_name = table.name
    if table_name in inspector.get_table_names():
        # Table exists → check for new columns
        existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name not in existing_cols:
                statements.append(
                    f"ALTER TABLE {table_name} ADD COLUMN "
                    f"{CreateColumn(col).compile(engine)};"
                )
    else:
        # Table does not exist → full CREATE TABLE
        statements.append(str(CreateTable(table).compile(engine)) + ";")
        for index in sorted(table.indexes, key=lambda item: item.name):
            statements.append(str(CreateIndex(index).compile(engine)) + ";")

# Write migration SQL
with open(migration_file, "w", encoding="utf-8") as f:
    f.write("\n\n".join(statements))

print(f"Migration SQL generated at {migration_file}")
