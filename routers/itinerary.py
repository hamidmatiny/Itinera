"""Itinerary generation and retrieval endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from data.store import itinerary_store
from schemas import (
    ItineraryGenerateRequest,
    ItineraryGenerateResponse,
    ItineraryRecord,
)
from services.ai_engine import AIItineraryEngine
from services.exceptions import XAIConfigurationError, XAIConnectionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itinerary", tags=["itinerary"])

_engine: AIItineraryEngine | None = None


def get_engine() -> AIItineraryEngine:
    """Lazy-initialize the AI engine so import-time config errors surface per-request."""
    global _engine
    if _engine is None:
        _engine = AIItineraryEngine()
    return _engine


@router.post(
    "/generate",
    response_model=ItineraryGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_itinerary(
    body: ItineraryGenerateRequest,
) -> ItineraryGenerateResponse:
    """
    Generate a personalized itinerary from user preferences.

    Persists the result in the in-memory store and returns the plan.
    """
    preferences = body.preferences
    try:
        engine = get_engine()
        plan = await engine.generate(preferences)
    except XAIConfigurationError as exc:
        logger.error("xAI configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except XAIConnectionError as exc:
        logger.error("xAI connection error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.exception("Itinerary generation failed after retries")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during itinerary generation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while generating the itinerary.",
        ) from exc

    record = itinerary_store.save(preferences, plan)
    return ItineraryGenerateResponse(
        itinerary_id=record.itinerary_id,
        plan=record.plan,
    )


@router.get("/{itinerary_id}", response_model=ItineraryRecord)
async def get_itinerary(itinerary_id: str) -> ItineraryRecord:
    """Fetch a previously generated itinerary by ID."""
    record = itinerary_store.get(itinerary_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Itinerary '{itinerary_id}' not found.",
        )
    return record


@router.get("", response_model=list[ItineraryRecord])
async def list_itineraries() -> list[ItineraryRecord]:
    """List all stored itineraries."""
    return itinerary_store.list_all()
