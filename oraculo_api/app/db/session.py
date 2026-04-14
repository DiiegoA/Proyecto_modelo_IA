from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base


def build_engine(settings: Settings) -> Engine:
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    engine_kwargs = {
        "echo": settings.database_echo,
        "pool_pre_ping": True,
        "future": True,
        "connect_args": connect_args,
    }
    if settings.database_url.endswith(":memory:"):
        engine_kwargs["poolclass"] = StaticPool

    return create_engine(
        settings.database_url,
        **engine_kwargs,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def create_tables(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)


def check_database_connection(session: Session) -> bool:
    session.execute(text("SELECT 1"))
    return True


def get_db_session_factory(request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def yield_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
