"""Async SQLAlchemy engine and ORM models (SQLite local, Postgres-ready)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class UserProfileORM(Base):
    """Persisted user constraints and preference tags."""

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    destination: Mapped[str] = mapped_column(String(200), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    travel_party: Mapped[str] = mapped_column(String(32), nullable=False)
    pace: Mapped[str] = mapped_column(String(32), nullable=False)
    budget_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    interests_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    itineraries: Mapped[list["ItineraryORM"]] = relationship(
        back_populates="user_profile",
        cascade="all, delete-orphan",
    )


class ItineraryORM(Base):
    """Generated itinerary linked to a user profile."""

    __tablename__ = "itineraries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    destination: Mapped[str] = mapped_column(String(200), nullable=False)
    total_days: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user_profile: Mapped[UserProfileORM] = relationship(back_populates="itineraries")


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the singleton async database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.database_echo,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def init_db() -> None:
    """Create database tables if they do not exist."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Yield a new async session (for dependency injection)."""
    factory = get_session_factory()
    return factory()


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)
