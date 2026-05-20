"""Streamlit frontend entrypoint for the AI Itinerary Generator."""

from __future__ import annotations

import time

import streamlit as st

from frontend.api_client import ItineraryAPIClient, ItineraryAPIError
from frontend.components import (
    render_daily_itinerary,
    render_foodie_hidden_gems,
    render_map_view,
    render_sidebar,
)
from schemas import ItineraryPlan, UserPreferences

st.set_page_config(
    page_title="Itinera — AI Itinerary Generator",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

LOADING_MESSAGES = [
    "Analyzing your travel preferences…",
    "Curating hidden gems and local favorites…",
    "Building your progressive foodie tour…",
    "Optimizing daily routes and time blocks…",
    "Finalizing coordinates for your map…",
]


def _render_api_error(exc: ItineraryAPIError) -> None:
    """Display a user-friendly error based on API failure type."""
    if exc.status_code == 503:
        st.error("**Configuration required**")
        st.info(exc.message)
    elif exc.status_code == 502:
        st.error("**xAI service unavailable**")
        st.warning(exc.message)
    else:
        st.error(f"**Failed to generate itinerary** — {exc.message}")


def _render_dashboard(
    plan: ItineraryPlan,
    preferences: UserPreferences,
    itinerary_id: str,
    *,
    from_saved: bool = False,
) -> None:
    """Render the main tabs for a loaded or newly generated itinerary."""
    if from_saved:
        st.success(f"Loaded saved trip · `{itinerary_id[:8]}…` · {plan.destination}")
    else:
        st.success(f"Itinerary ready · ID `{itinerary_id[:8]}…`")

    tab_daily, tab_foodie, tab_map = st.tabs(
        ["Daily Itinerary", "Foodie & Hidden Gems", "Map View"]
    )

    with tab_daily:
        render_daily_itinerary(plan, preferences)

    with tab_foodie:
        render_foodie_hidden_gems(plan)

    with tab_map:
        render_map_view(plan)


def main() -> None:
    """Application entrypoint."""
    st.title("Itinera")
    st.markdown(
        "Hyper-personalized **AI-powered itineraries** tailored to your pace, "
        "budget, and interests — powered by **xAI Grok**."
    )

    client = ItineraryAPIClient()
    if not client.health():
        st.warning(
            "Backend API is not reachable. Start it with: "
            "`uvicorn main:app --reload`"
        )

    sidebar = render_sidebar(client)

    if sidebar.action == "none":
        st.info(
            "Select a **Saved Trip** to reopen without calling xAI, or configure a "
            "new trip and click **Generate Itinerary**."
        )
        return

    if sidebar.action == "load_saved" and sidebar.itinerary_id:
        try:
            record = client.get_itinerary(sidebar.itinerary_id)
        except ItineraryAPIError as exc:
            _render_api_error(exc)
            return
        _render_dashboard(
            record.plan,
            record.preferences,
            record.itinerary_id,
            from_saved=True,
        )
        return

    if sidebar.action == "generate" and sidebar.preferences:
        preferences = sidebar.preferences
        progress = st.empty()
        with st.spinner("Generating your personalized itinerary with Grok…"):
            try:
                for message in LOADING_MESSAGES[:-1]:
                    progress.caption(message)
                    time.sleep(0.35)
                progress.caption(LOADING_MESSAGES[-1])
                response = client.generate(preferences)
            except ItineraryAPIError as exc:
                _render_api_error(exc)
                return
            except Exception as exc:
                st.error(f"An unexpected error occurred: {exc}")
                return

        _render_dashboard(
            response.plan,
            preferences,
            response.itinerary_id,
            from_saved=False,
        )


if __name__ == "__main__":
    main()
