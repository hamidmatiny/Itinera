"""Streamlit frontend entrypoint for the AI Itinerary Generator."""

from __future__ import annotations

import streamlit as st

from frontend.api_client import ItineraryAPIClient, ItineraryAPIError
from frontend.components import (
    render_daily_itinerary,
    render_foodie_live_events,
    render_map_view,
    render_sidebar,
    render_trip_actions,
)
from frontend.sharing import get_shared_trip_id_from_query
from frontend.theme import (
    inject_global_theme,
    inject_inline_style,
    render_hero_header,
    render_loading_shell,
    render_status_banner,
)
from schemas import ItineraryPlan, ItineraryRecord

st.set_page_config(
    page_title="Itinera — AI Itinerary Generator",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_global_theme()


def _init_session_state() -> None:
    """Initialize persistent UI state for the active itinerary."""
    if "active_itinerary" not in st.session_state:
        st.session_state.active_itinerary = None
    if "active_plan" not in st.session_state:
        st.session_state.active_plan = None


def _set_active_itinerary(record: ItineraryRecord) -> None:
    """Persist the full record and plan; survives sidebar button reruns."""
    st.session_state.active_itinerary = record
    st.session_state.active_plan = record.plan


def _get_active_record() -> ItineraryRecord | None:
    """Return the active itinerary record if present."""
    record = st.session_state.get("active_itinerary")
    if isinstance(record, ItineraryRecord):
        return record
    return None


def _render_api_error(exc: ItineraryAPIError) -> None:
    """Display a user-friendly error based on API failure type."""
    if exc.status_code == 503:
        render_status_banner("Configuration required — " + exc.message, variant="warn")
    elif exc.status_code == 502:
        render_status_banner("xAI service unavailable — " + exc.message, variant="warn")
    elif exc.status_code == 404:
        render_status_banner("Trip not found — " + exc.message, variant="info")
    else:
        render_status_banner(f"Failed to load itinerary — {exc.message}", variant="warn")


def _render_dashboard(
    record: ItineraryRecord,
    *,
    from_saved: bool = False,
    view_only: bool = False,
) -> None:
    """Render the main tabs for the active itinerary (never clears session state)."""
    plan: ItineraryPlan = record.plan
    preferences = record.preferences
    itinerary_id = record.itinerary_id

    if view_only:
        render_status_banner(
            f"Shared trip · {plan.destination} · {plan.duration_days} days",
            variant="info",
        )
    elif from_saved:
        render_status_banner(
            f"Loaded saved trip · {itinerary_id[:8]}… · {plan.destination}",
            variant="success",
        )
    else:
        render_status_banner(
            f"Search-verified itinerary ready · {itinerary_id[:8]}… · {plan.destination}",
            variant="success",
        )

    render_trip_actions(record, view_only=view_only)

    tab_daily, tab_events, tab_map = st.tabs(
        ["Daily Itinerary", "Foodie & Live Events", "Map View"]
    )

    with tab_daily:
        render_daily_itinerary(plan, preferences)

    with tab_events:
        render_foodie_live_events(plan)

    with tab_map:
        render_map_view(plan)


def _render_shared_view(client: ItineraryAPIClient, trip_id: str) -> None:
    """View-only mode when ``?trip=<uuid>`` is present in the URL."""
    inject_inline_style("[data-testid='stSidebar']{display:none;}")
    render_hero_header(
        kicker="Shared itinerary",
        title="Itinera",
        subtitle=f"View-only trip · {trip_id[:8]}…",
    )

    try:
        record = client.get_shared_itinerary(trip_id)
    except ItineraryAPIError as exc:
        _render_api_error(exc)
        return

    _set_active_itinerary(record)
    _render_dashboard(record, view_only=True)


def _handle_sidebar_actions(
    client: ItineraryAPIClient,
    sidebar,
) -> bool:
    """
    Process generate/load actions. Returns True if an error was shown.
    """
    if sidebar.action == "load_saved" and sidebar.itinerary_id:
        try:
            record = client.get_itinerary(sidebar.itinerary_id)
        except ItineraryAPIError as exc:
            _render_api_error(exc)
            return True
        _set_active_itinerary(record)
        return False

    if sidebar.action == "generate" and sidebar.preferences:
        preferences = sidebar.preferences
        loader = st.empty()
        try:
            with loader.container():
                render_loading_shell(
                    "Researching verified venues with Grok web search — "
                    "this may take a minute…"
                )
            response = client.generate(preferences)
        except ItineraryAPIError as exc:
            _render_api_error(exc)
            return True
        except Exception as exc:
            render_status_banner(f"An unexpected error occurred: {exc}", variant="warn")
            return True
        finally:
            loader.empty()

        record = ItineraryRecord(
            itinerary_id=response.itinerary_id,
            preferences=preferences,
            plan=response.plan,
            created_at="",
        )
        _set_active_itinerary(record)
        return False

    return False


def main() -> None:
    """Application entrypoint."""
    _init_session_state()
    client = ItineraryAPIClient()

    shared_trip_id = get_shared_trip_id_from_query()
    if shared_trip_id:
        if not client.health():
            render_status_banner(
                "Backend API is not reachable. Shared trips require the API server.",
                variant="warn",
            )
            st.code("uvicorn main:app --reload", language="bash")
            return
        _render_shared_view(client, shared_trip_id)
        return

    render_hero_header(
        kicker="Itinera Studio",
        title="Itinera",
        subtitle=(
            "Hyper-personalized AI itineraries — Search-then-Synthesize with "
            "xAI Grok live web search, then map-verified coordinates."
        ),
    )

    if not client.health():
        render_status_banner(
            "Backend API is not reachable. Start it with: uvicorn main:app --reload",
            variant="warn",
        )

    sidebar = render_sidebar(client)
    had_error = _handle_sidebar_actions(client, sidebar)

    active_record = _get_active_record()
    if active_record is not None and not had_error:
        from_saved = sidebar.action != "generate"
        _render_dashboard(active_record, from_saved=from_saved)
    elif not had_error and active_record is None:
        render_status_banner(
            "Select a Saved Trip to reopen without calling xAI, or configure a "
            "new trip and click Generate Itinerary.",
            variant="info",
        )


if __name__ == "__main__":
    main()
