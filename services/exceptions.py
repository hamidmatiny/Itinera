"""Domain exceptions for the AI itinerary engine."""

from __future__ import annotations


class ItineraryEngineError(Exception):
    """Base exception for itinerary generation failures."""


class XAIConfigurationError(ItineraryEngineError):
    """Raised when xAI credentials or environment configuration is invalid."""


class XAIConnectionError(ItineraryEngineError):
    """Raised when the xAI API is unreachable or returns an auth/HTTP error."""
