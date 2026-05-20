"""CRUD utilities for user profiles and itineraries."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import ItineraryORM, UserProfileORM, get_session_factory, utc_now
from schemas import (
    BudgetTier,
    Interest,
    ItineraryPlan,
    ItineraryRecord,
    Pace,
    TravelParty,
    UserPreferences,
)

logger = logging.getLogger(__name__)


def _interests_to_json(interests: list[Interest]) -> str:
    return json.dumps([i.value for i in interests])


def _interests_from_json(raw: str) -> list[Interest]:
    values: list[str] = json.loads(raw)
    return [Interest(v) for v in values]


def _preferences_from_profile(profile: UserProfileORM) -> UserPreferences:
    return UserPreferences(
        destination=profile.destination,
        duration_days=profile.duration_days,
        travel_party=TravelParty(profile.travel_party),
        pace=Pace(profile.pace),
        budget_tier=BudgetTier(profile.budget_tier),
        interests=_interests_from_json(profile.interests_json),
    )


def _record_from_orm(itinerary: ItineraryORM, profile: UserProfileORM) -> ItineraryRecord:
    plan = ItineraryPlan.model_validate_json(itinerary.plan_json)
    return ItineraryRecord(
        itinerary_id=itinerary.id,
        preferences=_preferences_from_profile(profile),
        plan=plan,
        created_at=itinerary.created_at.isoformat(),
    )


async def create_user_profile(preferences: UserPreferences) -> UserProfileORM:
    """Persist a new user profile from trip preferences."""
    profile = UserProfileORM(
        id=str(uuid.uuid4()),
        destination=preferences.destination,
        duration_days=preferences.duration_days,
        travel_party=preferences.travel_party.value,
        pace=preferences.pace.value,
        budget_tier=preferences.budget_tier.value,
        interests_json=_interests_to_json(preferences.interests),
        created_at=utc_now(),
    )
    factory = get_session_factory()
    async with factory() as session:
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    logger.info("Created user profile %s for %s", profile.id, profile.destination)
    return profile


async def save_itinerary(
    preferences: UserPreferences,
    plan: ItineraryPlan,
    *,
    profile: UserProfileORM | None = None,
) -> ItineraryRecord:
    """Save user profile (if needed) and itinerary plan; return API record."""
    factory = get_session_factory()
    async with factory() as session:
        if profile is None:
            profile = UserProfileORM(
                id=str(uuid.uuid4()),
                destination=preferences.destination,
                duration_days=preferences.duration_days,
                travel_party=preferences.travel_party.value,
                pace=preferences.pace.value,
                budget_tier=preferences.budget_tier.value,
                interests_json=_interests_to_json(preferences.interests),
                created_at=utc_now(),
            )
            session.add(profile)

        itinerary = ItineraryORM(
            id=str(uuid.uuid4()),
            user_profile_id=profile.id,
            destination=plan.destination,
            total_days=plan.duration_days,
            plan_json=plan.model_dump_json(),
            created_at=utc_now(),
        )
        session.add(itinerary)
        await session.commit()
        await session.refresh(itinerary)
        await session.refresh(profile)

    logger.info("Saved itinerary %s (%s, %d days)", itinerary.id, plan.destination, plan.duration_days)
    return _record_from_orm(itinerary, profile)


async def get_itinerary(itinerary_id: str) -> ItineraryRecord | None:
    """Retrieve a single itinerary by ID."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(ItineraryORM)
            .where(ItineraryORM.id == itinerary_id)
            .options(selectinload(ItineraryORM.user_profile))
        )
        result = await session.execute(stmt)
        itinerary = result.scalar_one_or_none()
        if itinerary is None:
            return None
        return _record_from_orm(itinerary, itinerary.user_profile)


async def list_itineraries(limit: int = 50) -> list[ItineraryRecord]:
    """List itineraries newest-first."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(ItineraryORM)
            .options(selectinload(ItineraryORM.user_profile))
            .order_by(ItineraryORM.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [_record_from_orm(row, row.user_profile) for row in rows]


async def list_itinerary_summaries(limit: int = 50) -> list[dict[str, Any]]:
    """Lightweight summaries for sidebar dropdowns."""
    records = await list_itineraries(limit=limit)
    return [
        {
            "itinerary_id": r.itinerary_id,
            "destination": r.plan.destination,
            "duration_days": r.plan.duration_days,
            "budget_tier": r.preferences.budget_tier.value,
            "created_at": r.created_at,
            "label": (
                f"{r.plan.destination} · {r.plan.duration_days}d · "
                f"{r.created_at[:10]}"
            ),
        }
        for r in records
    ]
