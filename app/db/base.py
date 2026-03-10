# app/db/base.py

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

import app.db.models  # Import all models to register them with SQLAlchemy