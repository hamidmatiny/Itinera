"""Share-link helpers for Streamlit."""

from __future__ import annotations

import streamlit as st

from config import get_settings
from frontend.theme import render_share_snippet


def build_share_url(itinerary_id: str) -> str:
    """Build a view-only Streamlit URL for the given itinerary UUID."""
    base = get_settings().app_public_url.rstrip("/")
    return f"{base}/?trip={itinerary_id}"


def render_share_link(itinerary_id: str) -> None:
    """Display a styled share URL snippet without HTML clipboard overlays."""
    share_url = build_share_url(itinerary_id)
    render_share_snippet(share_url)


def get_shared_trip_id_from_query() -> str | None:
    """Read shared trip UUID from ``?trip=`` query parameter."""
    trip_id = st.query_params.get("trip")
    if isinstance(trip_id, list):
        trip_id = trip_id[0] if trip_id else None
    if trip_id and isinstance(trip_id, str) and trip_id.strip():
        return trip_id.strip()
    return None
