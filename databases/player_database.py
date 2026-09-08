"""
Database setup and session management for async SQLAlchemy.

- Configures the async database engine from the DATABASE_URL environment
  variable (SQLite default, PostgreSQL compatible).
- Creates an async sessionmaker for ORM operations.
- Defines the declarative base class for model definitions.
- Provides a request-scoped async session and its teardown callback.

The session is stored on Flask's application context globals (`g`), which gives
it the same lifetime the FastAPI `Depends()` dependency used to have: one
session per request, closed once the response has been produced.

Environment variables:
    DATABASE_URL: Full async database URL. Defaults to SQLite:
        sqlite+aiosqlite:///./players-sqlite3.db
    STORAGE_PATH: (legacy) SQLite file path. Ignored when DATABASE_URL is set.
"""

import logging
import os
from typing import Optional
from flask import g
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from async_runner import run_async

ASYNC_SESSION_KEY = "async_session"


def get_database_url() -> str:
    """Return the async database URL from environment variables.

    Reads DATABASE_URL first; if unset, constructs a SQLite URL from
    STORAGE_PATH (defaulting to ./players-sqlite3.db).
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        storage_path = os.getenv("STORAGE_PATH", "./players-sqlite3.db")
        database_url = f"sqlite+aiosqlite:///{storage_path}"
    return database_url


DATABASE_URL: str = get_database_url()

_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# https://docs.gunicorn.org/en/stable/settings.html#logger-class
logger = logging.getLogger("gunicorn.error")
logging.getLogger("sqlalchemy.engine.Engine").handlers = logger.handlers

async_engine = create_async_engine(DATABASE_URL, connect_args=_connect_args, echo=True)

async_sessionmaker = sessionmaker(
    bind=async_engine, class_=AsyncSession, autocommit=False, autoflush=False
)

Base = declarative_base()


def generate_async_session() -> AsyncSession:
    """
    Provides the async SQLAlchemy ORM session bound to the current request.

    The session is created on first use within a request and reused for every
    subsequent call, so all operations of a single request share one session.

    Returns:
        AsyncSession: An instance of an async SQLAlchemy ORM session.
    """
    if ASYNC_SESSION_KEY not in g:
        setattr(g, ASYNC_SESSION_KEY, async_sessionmaker())
    return getattr(g, ASYNC_SESSION_KEY)


def close_async_session(_exception: Optional[BaseException] = None) -> None:
    """
    Closes the request-scoped async session, if one was created.

    Registered as a Flask `teardown_appcontext` callback, mirroring the teardown
    of the FastAPI dependency it replaces.

    Args:
        _exception (Optional[BaseException]): Unhandled exception, if any.
    """
    async_session: Optional[AsyncSession] = g.pop(ASYNC_SESSION_KEY, None)
    if async_session is not None:
        run_async(async_session.close())
