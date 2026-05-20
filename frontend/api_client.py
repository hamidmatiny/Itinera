"""HTTP client for communicating with the FastAPI backend."""

from __future__ import annotations

import httpx

from config import get_settings
from schemas import (
    ItineraryGenerateResponse,
    ItineraryRecord,
    ItinerarySummary,
    UserPreferences,
)


class ItineraryAPIError(Exception):
    """User-facing API error with an optional HTTP status code."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ItineraryAPIClient:
    """Thin wrapper around itinerary REST endpoints."""

    def __init__(self, base_url: str | None = None, timeout: float = 120.0) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.api_base_url).rstrip("/")
        self._timeout = timeout

    def generate(self, preferences: UserPreferences) -> ItineraryGenerateResponse:
        """POST preferences and return the generated itinerary."""
        payload = {"preferences": preferences.model_dump(mode="json")}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/api/itinerary/generate",
                    json=payload,
                )
                response.raise_for_status()
                return ItineraryGenerateResponse.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(exc.response)
            raise ItineraryAPIError(detail, status_code=exc.response.status_code) from exc
        except httpx.ConnectError as exc:
            raise ItineraryAPIError(
                "Cannot connect to the itinerary API. "
                "Start the backend with: uvicorn main:app --reload"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ItineraryAPIError(
                "The itinerary request timed out. xAI may be under heavy load — try again."
            ) from exc
        except httpx.HTTPError as exc:
            raise ItineraryAPIError(
                "A network error occurred while contacting the itinerary API."
            ) from exc

    def list_summaries(self) -> list[ItinerarySummary]:
        """Fetch saved trip summaries for the sidebar."""
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self._base_url}/api/itinerary/summaries")
                response.raise_for_status()
                return [
                    ItinerarySummary.model_validate(item)
                    for item in response.json()
                ]
        except httpx.HTTPError:
            return []

    def get_itinerary(self, itinerary_id: str) -> ItineraryRecord:
        """Load a saved itinerary without re-invoking xAI."""
        return self._fetch_record(f"/api/itinerary/{itinerary_id}", "saved itinerary")

    def get_shared_itinerary(self, itinerary_id: str) -> ItineraryRecord:
        """Load a publicly shared itinerary (view-only)."""
        return self._fetch_record(
            f"/shared/itinerary/{itinerary_id}",
            "shared itinerary",
        )

    def _fetch_record(self, path: str, label: str) -> ItineraryRecord:
        """GET an itinerary record from the API."""
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(f"{self._base_url}{path}")
                response.raise_for_status()
                return ItineraryRecord.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(exc.response)
            raise ItineraryAPIError(detail, status_code=exc.response.status_code) from exc
        except httpx.HTTPError as exc:
            raise ItineraryAPIError(f"Failed to load the {label}.") from exc

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        """Parse FastAPI error payloads into a user-friendly message."""
        try:
            body = response.json()
            detail = body.get("detail")
            if isinstance(detail, str):
                return detail
            if isinstance(detail, list) and detail:
                first = detail[0]
                if isinstance(first, dict) and "msg" in first:
                    return str(first["msg"])
        except (ValueError, AttributeError):
            pass
        return f"Request failed with status {response.status_code}."

    def health(self) -> bool:
        """Return True if the backend health endpoint responds OK."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self._base_url}/health")
                return response.status_code == 200
        except httpx.HTTPError:
            return False
