"""SQLAlchemy engine, session factory, and declarative base.

Also responsible for making sure the `pgcrypto` extension is available in
the target Postgres database, since sensitive finding columns are encrypted
with it (see app/models/finding.py and app/core/crypto.py).
"""
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the app."""
    pass


def ensure_pgcrypto_extension() -> None:
    """Create the pgcrypto extension if it doesn't already exist.

    Safe to call on every startup — CREATE EXTENSION IF NOT EXISTS is
    idempotent. Requires the connecting role to have privileges to create
    extensions, which the default local `sentinelx` superuser-equivalent
    role has in the docker-compose Postgres image.
    """
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        conn.commit()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()