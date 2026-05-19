"""Pydantic data models for user preferences and itinerary structures."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


class TravelParty(str, Enum):
    """Travel party composition."""

    SOLO = "Solo"
    COUPLE = "Couple"
    FAMILY = "Family"
    GROUP = "Group"


class Pace(str, Enum):
    """Daily activity intensity."""

    RELAXED = "Relaxed"
    MODERATE = "Moderate"
    PACKED = "Packed"


class BudgetTier(str, Enum):
    """Budget constraint tier."""

    BUDGET = "Budget"
    MID_RANGE = "Mid-range"
    LUXURY = "Luxury"


class Interest(str, Enum):
    """Multi-select interest tags."""

    FOODIE = "Foodie"
    CULTURE = "Culture"
    NATURE = "Nature"
    HIDDEN_GEMS = "Hidden Gems"


class TimeSlot(str, Enum):
    """Canonical time blocks within a day."""

    MORNING = "Morning"
    LUNCH = "Lunch"
    AFTERNOON = "Afternoon"
    EVENING = "Evening"


class UserPreferences(BaseModel):
    """Validated user profile for itinerary generation."""

    destination: Annotated[str, Field(min_length=1, max_length=200)]
    duration_days: Annotated[int, Field(ge=1, le=30)]
    travel_party: TravelParty
    pace: Pace
    budget_tier: BudgetTier
    interests: Annotated[list[Interest], Field(min_length=1)]

    @field_validator("destination")
    @classmethod
    def strip_destination(cls, value: str) -> str:
        """Normalize destination input."""
        return value.strip()


class Activity(BaseModel):
    """Single activity within a time block."""

    activity_name: str
    description: str
    estimated_cost: Annotated[float, Field(ge=0)]
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    hidden_gem: bool = False


class TimeBlock(BaseModel):
    """Activity scheduled for a specific time slot."""

    time_slot: TimeSlot
    activity: Activity


class DayItinerary(BaseModel):
    """Full schedule for one day."""

    day_number: Annotated[int, Field(ge=1)]
    time_blocks: list[TimeBlock]

    @field_validator("time_blocks")
    @classmethod
    def require_all_slots(cls, blocks: list[TimeBlock]) -> list[TimeBlock]:
        """Ensure each day has the four canonical time slots."""
        slots = {block.time_slot for block in blocks}
        required = set(TimeSlot)
        if slots != required:
            missing = required - slots
            extra = slots - required
            raise ValueError(
                f"Day must include Morning, Lunch, Afternoon, Evening. "
                f"Missing: {missing or 'none'}, Extra: {extra or 'none'}"
            )
        return blocks


class ItineraryPlan(BaseModel):
    """Complete multi-day itinerary returned by the AI engine."""

    destination: str
    duration_days: int
    days: list[DayItinerary]

    @model_validator(mode="after")
    def validate_day_count(self) -> ItineraryPlan:
        """Ensure day count matches declared duration."""
        if len(self.days) != self.duration_days:
            raise ValueError(
                f"Expected {self.duration_days} days in itinerary, got {len(self.days)}"
            )
        return self


class ItineraryGenerateRequest(BaseModel):
    """API request body for itinerary generation."""

    preferences: UserPreferences


class ItineraryGenerateResponse(BaseModel):
    """API response wrapping a generated plan."""

    itinerary_id: str
    plan: ItineraryPlan


class ItineraryRecord(BaseModel):
    """Persisted itinerary record in the in-memory store."""

    itinerary_id: str
    preferences: UserPreferences
    plan: ItineraryPlan
    created_at: str
