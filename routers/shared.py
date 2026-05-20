"""Public read-only itinerary endpoints for shareable links."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from schemas import ItineraryRecord
from services import db_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shared", tags=["shared"])


@router.get("/itinerary/{itinerary_id}", response_model=ItineraryRecord)
async def get_shared_itinerary(itinerary_id: str) -> ItineraryRecord:
    """
    Fetch an itinerary by UUID for public, view-only sharing.

    No authentication in MVP; the UUID acts as an unguessable share token.
    """
    record = await db_service.get_itinerary(itinerary_id)
    if record is None:
        logger.info("Shared itinerary not found: %s", itinerary_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This shared itinerary could not be found. The link may have expired.",
        )
    return record
