"""Streamlit UI components (presentation layer only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd
import streamlit as st

from frontend.api_client import ItineraryAPIClient
from schemas import (
    BudgetTier,
    Interest,
    ItineraryPlan,
    Pace,
    TimeSlot,
    TravelParty,
    UserPreferences,
    daily_budget_allocation,
    day_estimated_cost,
)


@dataclass
class SidebarResult:
    """Outcome of sidebar interaction."""

    action: Literal["none", "generate", "load_saved"]
    preferences: UserPreferences | None = None
    itinerary_id: str | None = None


def render_sidebar(client: ItineraryAPIClient) -> SidebarResult:
    """
    Render configuration + saved trips sidebar.

    Returns generate preferences, a saved itinerary id to load, or none.
    """
    st.sidebar.header("Trip Configuration")

    summaries = client.list_summaries()
    st.sidebar.subheader("Saved Trips")
    trip_options = ["— Create new trip —"] + [s.label for s in summaries]
    trip_ids = [None] + [s.itinerary_id for s in summaries]
    selected_idx = st.sidebar.selectbox(
        "Load a saved itinerary",
        range(len(trip_options)),
        format_func=lambda i: trip_options[i],
        key="saved_trip_select",
    )
    selected_trip_id = trip_ids[selected_idx]

    load_saved = st.sidebar.button(
        "Open Saved Trip",
        use_container_width=True,
        disabled=selected_trip_id is None,
    )

    if load_saved and selected_trip_id:
        return SidebarResult(action="load_saved", itinerary_id=selected_trip_id)

    st.sidebar.divider()
    st.sidebar.markdown("**New trip** — configure and generate with Grok.")

    destination = st.sidebar.text_input(
        "Destination",
        placeholder="e.g. Tokyo, Paris, Barcelona",
    )
    duration_days = st.sidebar.number_input(
        "Duration (days)",
        min_value=1,
        max_value=14,
        value=3,
    )
    travel_party = st.sidebar.selectbox(
        "Travel party",
        options=[p.value for p in TravelParty],
    )
    pace = st.sidebar.selectbox(
        "Pace",
        options=[p.value for p in Pace],
    )
    budget_tier = st.sidebar.selectbox(
        "Budget tier",
        options=[b.value for b in BudgetTier],
    )
    interests = st.sidebar.multiselect(
        "Interests",
        options=[i.value for i in Interest],
        default=[Interest.FOODIE.value, Interest.CULTURE.value],
    )

    submitted = st.sidebar.button(
        "Generate Itinerary",
        type="primary",
        use_container_width=True,
    )

    if not submitted:
        return SidebarResult(action="none")

    if not destination.strip():
        st.sidebar.error("Please enter a destination.")
        return SidebarResult(action="none")
    if not interests:
        st.sidebar.error("Select at least one interest.")
        return SidebarResult(action="none")

    return SidebarResult(
        action="generate",
        preferences=UserPreferences(
            destination=destination.strip(),
            duration_days=int(duration_days),
            travel_party=TravelParty(travel_party),
            pace=Pace(pace),
            budget_tier=BudgetTier(budget_tier),
            interests=[Interest(i) for i in interests],
        ),
    )


def render_daily_itinerary(plan: ItineraryPlan, preferences: UserPreferences) -> None:
    """Tab 1: expandable daily schedule with budget burn-rate metrics."""
    total_cost = _compute_total_cost(plan)
    daily_budget = daily_budget_allocation(preferences.budget_tier)
    trip_budget = daily_budget * plan.duration_days

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Destination", plan.destination)
    col2.metric("Duration", f"{plan.duration_days} days")
    col3.metric("Trip budget (tier)", f"${trip_budget:,.0f}")
    col4.metric("Est. total spend", f"${total_cost:,.0f}", delta=f"${total_cost - trip_budget:+,.0f}")

    st.markdown("### Daily budget burn rate")
    burn_cols = st.columns(len(plan.days))
    for idx, day in enumerate(plan.days):
        actual = day_estimated_cost(day)
        allocated = daily_budget
        delta = actual - allocated
        burn_cols[idx].metric(
            f"Day {day.day_number}",
            f"${actual:,.0f}",
            delta=f"${delta:+,.0f} vs ${allocated:,.0f}/day",
            delta_color="inverse" if delta > 0 else "normal",
        )

    for day in plan.days:
        day_cost = day_estimated_cost(day)
        allocated = daily_budget
        over_under = day_cost - allocated
        with st.expander(
            f"Day {day.day_number} — ${day_cost:,.0f} spent "
            f"({'over' if over_under > 0 else 'under'} budget by ${abs(over_under):,.0f})",
            expanded=day.day_number == 1,
        ):
            m1, m2, m3 = st.columns(3)
            m1.metric("Allocated / day", f"${allocated:,.0f}")
            m2.metric("AI estimate", f"${day_cost:,.0f}")
            m3.metric("Burn rate", f"{(day_cost / allocated * 100):.0f}%")

            for block in sorted(day.time_blocks, key=lambda b: _slot_order(b.time_slot)):
                activity = block.activity
                st.markdown(f"#### {block.time_slot.value}")
                gem_badge = " · Hidden Gem" if activity.hidden_gem else ""
                verify_badge = "" if activity.is_verified else " · ⚠️ Location estimated"
                st.markdown(f"**{activity.activity_name}**{gem_badge}{verify_badge}")
                location_line = (
                    f"${activity.estimated_cost:,.0f} · "
                    f"({activity.latitude:.4f}, {activity.longitude:.4f})"
                )
                if activity.formatted_address and activity.is_verified:
                    location_line += f" · {activity.formatted_address}"
                st.caption(location_line)
                if not activity.is_verified:
                    st.caption(
                        "⚠️ Location estimated — double-check venue status before visiting."
                    )
                st.write(activity.description)
                st.divider()


def render_foodie_hidden_gems(plan: ItineraryPlan) -> None:
    """Tab 2: culinary highlights and hidden-gem attractions."""
    st.subheader("Foodie & Hidden Gems")

    lunch_blocks = []
    hidden_gems = []

    for day in plan.days:
        for block in day.time_blocks:
            if block.time_slot == TimeSlot.LUNCH:
                lunch_blocks.append((day.day_number, block))
            if block.activity.hidden_gem:
                hidden_gems.append((day.day_number, block))

    st.markdown("### Progressive Foodie Tour — Lunch Pairings")
    if lunch_blocks:
        for day_num, block in lunch_blocks:
            activity = block.activity
            st.info(f"**Day {day_num} — {activity.activity_name}**")
            st.write(activity.description)
    else:
        st.write("No lunch blocks found.")

    st.markdown("### Hidden Gems")
    if hidden_gems:
        for day_num, block in hidden_gems:
            activity = block.activity
            st.success(f"**Day {day_num} — {activity.activity_name}** ({block.time_slot.value})")
            st.write(activity.description)
    else:
        st.write("No hidden gems flagged in this itinerary. Try selecting the Hidden Gems interest.")


def render_map_view(plan: ItineraryPlan) -> None:
    """Tab 3: sequential per-day maps with coordinate summary tables."""
    st.subheader("Map View — Daily Routes")
    st.caption("Activities are plotted in Morning → Lunch → Afternoon → Evening order per day.")

    if not plan.days:
        st.warning("No coordinates to display.")
        return

    for day in plan.days:
        st.markdown(f"#### Day {day.day_number}")
        rows = []
        for order, block in enumerate(
            sorted(day.time_blocks, key=lambda b: _slot_order(b.time_slot)),
            start=1,
        ):
            activity = block.activity
            verification_note = (
                "Verified"
                if activity.is_verified
                else "⚠️ Location estimated - double check venue status"
            )
            rows.append(
                {
                    "stop": order,
                    "time_slot": block.time_slot.value,
                    "activity": activity.activity_name,
                    "latitude": round(activity.latitude, 5),
                    "longitude": round(activity.longitude, 5),
                    "verification": verification_note,
                    "hidden_gem": activity.hidden_gem,
                }
            )

        df = pd.DataFrame(rows)
        unverified_count = sum(1 for r in rows if r["verification"].startswith("⚠️"))
        if unverified_count:
            st.warning(
                f"{unverified_count} stop(s) on Day {day.day_number} use estimated placements "
                "— venues could not be confirmed on OpenStreetMap."
            )

        map_col, table_col = st.columns([3, 2])

        with map_col:
            st.map(
                df,
                latitude="latitude",
                longitude="longitude",
                size=100,
                color="#1f77b4",
            )

        with table_col:
            st.markdown("**Localized coordinates**")
            st.dataframe(
                df[["stop", "time_slot", "activity", "latitude", "longitude", "verification"]],
                use_container_width=True,
                hide_index=True,
            )

        st.divider()


def _compute_total_cost(plan: ItineraryPlan) -> float:
    """Sum estimated costs across all activities."""
    return sum(day_estimated_cost(day) for day in plan.days)


def _slot_order(slot: TimeSlot) -> int:
    """Sort key for canonical time slot ordering."""
    order = {
        TimeSlot.MORNING: 0,
        TimeSlot.LUNCH: 1,
        TimeSlot.AFTERNOON: 2,
        TimeSlot.EVENING: 3,
    }
    return order[slot]
