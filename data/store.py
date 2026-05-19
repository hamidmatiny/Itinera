"""In-memory itinerary store (swappable with PostgreSQL/PostGIS later)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TypedDict

from schemas import ItineraryPlan, ItineraryRecord, UserPreferences


class _StoreEntry(TypedDict):
    """Internal typed dict representation for in-memory storage."""

    itinerary_id: str
    preferences: UserPreferences
    plan: ItineraryPlan
    created_at: str


class InMemoryItineraryStore:
    """
    Thread-unsafe in-memory store for MVP.

    Replace with a PostgreSQL repository implementing the same interface.
    """

    def __init__(self) -> None:
        self._records: dict[str, _StoreEntry] = {}

    def save(
        self,
        preferences: UserPreferences,
        plan: ItineraryPlan,
    ) -> ItineraryRecord:
        """Persist a generated itinerary and return the record."""
        itinerary_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        entry: _StoreEntry = {
            "itinerary_id": itinerary_id,
            "preferences": preferences,
            "plan": plan,
            "created_at": created_at,
        }
        self._records[itinerary_id] = entry
        return ItineraryRecord(
            itinerary_id=itinerary_id,
            preferences=preferences,
            plan=plan,
            created_at=created_at,
        )

    def get(self, itinerary_id: str) -> ItineraryRecord | None:
        """Retrieve an itinerary by ID."""
        entry = self._records.get(itinerary_id)
        if entry is None:
            return None
        return ItineraryRecord(
            itinerary_id=entry["itinerary_id"],
            preferences=entry["preferences"],
            plan=entry["plan"],
            created_at=entry["created_at"],
        )

    def list_all(self) -> list[ItineraryRecord]:
        """Return all stored itineraries (newest first)."""
        records = [
            ItineraryRecord(
                itinerary_id=e["itinerary_id"],
                preferences=e["preferences"],
                plan=e["plan"],
                created_at=e["created_at"],
            )
            for e in self._records.values()
        ]
        return sorted(records, key=lambda r: r.created_at, reverse=True)


itinerary_store = InMemoryItineraryStore()
