"""Location verification, anchoring, and map-safe coordinate fallbacks."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from typing import Any, TypedDict

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from schemas import Activity, DayItinerary, ItineraryPlan, TimeBlock, TimeSlot

logger = logging.getLogger(__name__)

_GEOCODER = Nominatim(user_agent="itinera-mvp/2.1")
_SLOT_ORDER = [TimeSlot.MORNING, TimeSlot.LUNCH, TimeSlot.AFTERNOON, TimeSlot.EVENING]
_NOMINATIM_MIN_INTERVAL_SEC = 1.1
_geocode_lock = asyncio.Lock()
_last_geocode_at: float = 0.0

# Max spread ~±400 m around city center for unverified fallbacks
_CITY_OFFSET_DEG = 0.004


class AnchoredLocation(TypedDict):
    """Result of verify_and_anchor_location."""

    latitude: float
    longitude: float
    formatted_address: str | None
    is_verified: bool


def is_valid_coordinate(latitude: float | None, longitude: float | None) -> bool:
    """Return False for missing, out-of-range, or null-island coordinates."""
    if latitude is None or longitude is None:
        return False
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return False
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return False
    if abs(latitude) < 1e-4 and abs(longitude) < 1e-4:
        return False
    return True


def _format_location_address(location: Any) -> str:
    """Build a human-readable address from a Nominatim location object."""
    try:
        if getattr(location, "address", None):
            parts = location.address
            if isinstance(parts, dict):
                ordered_keys = (
                    "amenity",
                    "tourism",
                    "building",
                    "road",
                    "suburb",
                    "city",
                    "state",
                    "country",
                )
                segments = [str(parts[k]) for k in ordered_keys if k in parts]
                if segments:
                    return ", ".join(segments)
        if getattr(location, "raw", None) and isinstance(location.raw, dict):
            display = location.raw.get("display_name")
            if display:
                return str(display)
    except (TypeError, AttributeError, KeyError) as exc:
        logger.debug("Could not parse formatted address: %s", exc)
    return str(getattr(location, "address", location))


def _deterministic_city_offset(venue_name: str, city: str, slot_index: int) -> tuple[float, float]:
    """Stable micro-offset so unverified pins do not stack on the city center."""
    seed = f"{venue_name.strip().lower()}|{city.strip().lower()}|{slot_index}"
    digest = hashlib.sha256(seed.encode()).hexdigest()
    lat_seed = int(digest[:8], 16) / 0xFFFFFFFF
    lng_seed = int(digest[8:16], 16) / 0xFFFFFFFF
    return (lat_seed - 0.5) * _CITY_OFFSET_DEG, (lng_seed - 0.5) * _CITY_OFFSET_DEG


def _nominatim_geocode_sync(query: str) -> Any | None:
    """Blocking Nominatim lookup with defensive error handling."""
    try:
        return _GEOCODER.geocode(query, timeout=8, addressdetails=True)
    except (GeocoderTimedOut, GeocoderServiceError) as exc:
        logger.warning("Nominatim error for '%s': %s", query, exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected geocoder error for '%s': %s", query, exc)
        return None


async def _rate_limited_geocode(query: str) -> Any | None:
    """Serialize geocode requests to respect Nominatim usage limits."""
    global _last_geocode_at

    async with _geocode_lock:
        loop = asyncio.get_running_loop()
        now = loop.time()
        wait = _NOMINATIM_MIN_INTERVAL_SEC - (now - _last_geocode_at)
        if wait > 0:
            await asyncio.sleep(wait)
        result = await asyncio.to_thread(_nominatim_geocode_sync, query)
        _last_geocode_at = loop.time()
        return result


def _resolve_city_center(city: str, fallback_lat: float, fallback_lng: float) -> tuple[float, float]:
    """Resolve city center; prefer Nominatim, then LLM fallback, then static defaults."""
    if is_valid_coordinate(fallback_lat, fallback_lng):
        return fallback_lat, fallback_lng

    location = _nominatim_geocode_sync(city.strip())
    if location is not None:
        return float(location.latitude), float(location.longitude)

    dest = city.lower()
    defaults: dict[str, tuple[float, float]] = {
        "tokyo": (35.6762, 139.6503),
        "paris": (48.8566, 2.3522),
        "barcelona": (41.3851, 2.1734),
        "new york": (40.7128, -74.0060),
        "london": (51.5074, -0.1278),
    }
    for key, coords in defaults.items():
        if key in dest:
            return coords
    return 48.8566, 2.3522


def verify_and_anchor_location(
    venue_name: str,
    city: str,
    fallback_lat: float,
    fallback_lng: float,
    *,
    slot_index: int = 0,
) -> AnchoredLocation:
    """
    Verify a venue against OpenStreetMap and anchor coordinates to real-world data.

    When a match is found, LLM coordinates are overwritten with Nominatim values.
    When no match is found, coordinates fall back to the city center with a small
    deterministic offset and ``is_verified=False``.
    """
    venue = venue_name.strip()
    city_name = city.strip()

    if not venue or not city_name:
        center_lat, center_lng = _resolve_city_center(city_name or "unknown", fallback_lat, fallback_lng)
        dlat, dlng = _deterministic_city_offset(venue or "unknown", city_name or "unknown", slot_index)
        return AnchoredLocation(
            latitude=center_lat + dlat,
            longitude=center_lng + dlng,
            formatted_address=None,
            is_verified=False,
        )

    query = f"{venue}, {city_name}"
    try:
        location = _nominatim_geocode_sync(query)
        if location is not None:
            return AnchoredLocation(
                latitude=float(location.latitude),
                longitude=float(location.longitude),
                formatted_address=_format_location_address(location),
                is_verified=True,
            )

        logger.info("No Nominatim match for '%s' — suspected hallucination; using city fallback", query)
        center_lat, center_lng = _resolve_city_center(city_name, fallback_lat, fallback_lng)
        dlat, dlng = _deterministic_city_offset(venue, city_name, slot_index)
        return AnchoredLocation(
            latitude=center_lat + dlat,
            longitude=center_lng + dlng,
            formatted_address=f"Estimated near {city_name} (venue not verified)",
            is_verified=False,
        )
    except Exception as exc:
        logger.error("verify_and_anchor_location failed for '%s': %s", query, exc)
        safe_lat, safe_lng = _resolve_city_center(city_name, fallback_lat, fallback_lng)
        dlat, dlng = _deterministic_city_offset(venue, city_name, slot_index)
        return AnchoredLocation(
            latitude=safe_lat + dlat,
            longitude=safe_lng + dlng,
            formatted_address=None,
            is_verified=False,
        )


async def _verify_and_anchor_location_async(
    venue_name: str,
    city: str,
    fallback_lat: float,
    fallback_lng: float,
    *,
    slot_index: int = 0,
) -> AnchoredLocation:
    """Async wrapper: venue geocode, then city fallback if needed."""
    venue = venue_name.strip()
    city_name = city.strip()

    if not venue or not city_name:
        center = await _rate_limited_geocode(city_name or "unknown")
        if center is not None:
            base_lat, base_lng = float(center.latitude), float(center.longitude)
        else:
            base_lat, base_lng = _resolve_city_center(city_name or "unknown", fallback_lat, fallback_lng)
        dlat, dlng = _deterministic_city_offset(venue or "unknown", city_name or "unknown", slot_index)
        return AnchoredLocation(
            latitude=base_lat + dlat,
            longitude=base_lng + dlng,
            formatted_address=None,
            is_verified=False,
        )

    query = f"{venue}, {city_name}"
    try:
        location = await _rate_limited_geocode(query)
        if location is not None:
            return AnchoredLocation(
                latitude=float(location.latitude),
                longitude=float(location.longitude),
                formatted_address=_format_location_address(location),
                is_verified=True,
            )

        logger.info("No Nominatim match for '%s' — using city-level fallback", query)
        city_location = await _rate_limited_geocode(city_name)
        if city_location is not None:
            center_lat = float(city_location.latitude)
            center_lng = float(city_location.longitude)
        else:
            center_lat, center_lng = _resolve_city_center(city_name, fallback_lat, fallback_lng)

        dlat, dlng = _deterministic_city_offset(venue, city_name, slot_index)
        return AnchoredLocation(
            latitude=center_lat + dlat,
            longitude=center_lng + dlng,
            formatted_address=f"Estimated near {city_name} (venue not verified)",
            is_verified=False,
        )
    except Exception as exc:
        logger.error("Async anchor failed for '%s': %s", query, exc)
        center_lat, center_lng = _resolve_city_center(city_name, fallback_lat, fallback_lng)
        dlat, dlng = _deterministic_city_offset(venue, city_name, slot_index)
        return AnchoredLocation(
            latitude=center_lat + dlat,
            longitude=center_lng + dlng,
            formatted_address=None,
            is_verified=False,
        )


async def anchor_itinerary_locations(plan: ItineraryPlan) -> ItineraryPlan:
    """
    Post-generation validation: verify every activity against Nominatim.

    Never raises — individual failures degrade to city-level estimates.
    """
    updated_days: list[DayItinerary] = []
    verified_count = 0
    total_count = 0

    for day in plan.days:
        sorted_blocks = sorted(
            day.time_blocks,
            key=lambda b: _SLOT_ORDER.index(b.time_slot),
        )
        updated_blocks: list[TimeBlock] = []

        for slot_index, block in enumerate(sorted_blocks):
            activity = block.activity
            total_count += 1
            fallback_lat = activity.latitude if is_valid_coordinate(activity.latitude, activity.longitude) else 0.0
            fallback_lng = activity.longitude if is_valid_coordinate(activity.latitude, activity.longitude) else 0.0

            try:
                anchored = await _verify_and_anchor_location_async(
                    activity.activity_name,
                    plan.destination,
                    fallback_lat,
                    fallback_lng,
                    slot_index=slot_index + (day.day_number * 10),
                )
            except Exception as exc:
                logger.error(
                    "Skipping anchor for '%s' on day %d: %s",
                    activity.activity_name,
                    day.day_number,
                    exc,
                )
                anchored = verify_and_anchor_location(
                    activity.activity_name,
                    plan.destination,
                    fallback_lat,
                    fallback_lng,
                    slot_index=slot_index + (day.day_number * 10),
                )

            if anchored["is_verified"]:
                verified_count += 1

            updated_blocks.append(
                TimeBlock(
                    time_slot=block.time_slot,
                    activity=Activity(
                        activity_name=activity.activity_name,
                        description=activity.description,
                        estimated_cost=activity.estimated_cost,
                        latitude=anchored["latitude"],
                        longitude=anchored["longitude"],
                        is_live_event=activity.is_live_event,
                        source_hint=activity.source_hint,
                        is_verified=anchored["is_verified"],
                        formatted_address=anchored["formatted_address"],
                    ),
                )
            )

        updated_days.append(DayItinerary(day_number=day.day_number, time_blocks=updated_blocks))

    logger.info(
        "Location anchoring complete for %s: %d/%d venues verified",
        plan.destination,
        verified_count,
        total_count,
    )

    return ItineraryPlan(
        destination=plan.destination,
        duration_days=plan.duration_days,
        days=updated_days,
    )


# Backward-compatible alias used during Phase 2 migration
async def normalize_itinerary_coordinates(plan: ItineraryPlan) -> ItineraryPlan:
    """Anchor all itinerary coordinates via the verification pipeline."""
    return await anchor_itinerary_locations(plan)
