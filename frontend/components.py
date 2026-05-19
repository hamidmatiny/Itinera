"""Streamlit UI components (presentation layer only)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from schemas import (
    BudgetTier,
    Interest,
    ItineraryPlan,
    Pace,
    TimeSlot,
    TravelParty,
    UserPreferences,
)


def render_sidebar() -> UserPreferences | None:
    """
    Render the configuration sidebar and return preferences when submitted.

    Returns None until the user clicks Generate.
    """
    st.sidebar.header("Trip Configuration")
    st.sidebar.markdown("Tell us about your dream trip.")

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

    submitted = st.sidebar.button("Generate Itinerary", type="primary", use_container_width=True)

    if not submitted:
        return None

    if not destination.strip():
        st.sidebar.error("Please enter a destination.")
        return None
    if not interests:
        st.sidebar.error("Select at least one interest.")
        return None

    return UserPreferences(
        destination=destination.strip(),
        duration_days=int(duration_days),
        travel_party=TravelParty(travel_party),
        pace=Pace(pace),
        budget_tier=BudgetTier(budget_tier),
        interests=[Interest(i) for i in interests],
    )


def render_daily_itinerary(plan: ItineraryPlan) -> None:
    """Tab 1: expandable daily schedule with budget metrics."""
    total_cost = _compute_total_cost(plan)
    col1, col2, col3 = st.columns(3)
    col1.metric("Destination", plan.destination)
    col2.metric("Duration", f"{plan.duration_days} days")
    col3.metric("Est. Total Cost", f"${total_cost:,.0f}")

    for day in plan.days:
        day_cost = sum(b.activity.estimated_cost for b in day.time_blocks)
        with st.expander(f"Day {day.day_number} — Est. ${day_cost:,.0f}", expanded=day.day_number == 1):
            for block in sorted(day.time_blocks, key=lambda b: _slot_order(b.time_slot)):
                activity = block.activity
                st.markdown(f"#### {block.time_slot.value}")
                gem_badge = " · Hidden Gem" if activity.hidden_gem else ""
                st.markdown(f"**{activity.activity_name}**{gem_badge}")
                st.caption(
                    f"${activity.estimated_cost:,.0f} · "
                    f"({activity.latitude:.4f}, {activity.longitude:.4f})"
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
    """Tab 3: plot activity coordinates on an interactive map."""
    st.subheader("Map View")
    rows = []
    for day in plan.days:
        for block in day.time_blocks:
            activity = block.activity
            rows.append(
                {
                    "day": day.day_number,
                    "slot": block.time_slot.value,
                    "name": activity.activity_name,
                    "lat": activity.latitude,
                    "lon": activity.longitude,
                    "hidden_gem": activity.hidden_gem,
                }
            )

    if not rows:
        st.warning("No coordinates to display.")
        return

    df = pd.DataFrame(rows)
    st.map(df, latitude="lat", longitude="lon", size=80)

    with st.expander("Activity coordinates"):
        st.dataframe(df, use_container_width=True, hide_index=True)


def _compute_total_cost(plan: ItineraryPlan) -> float:
    """Sum estimated costs across all activities."""
    return sum(
        block.activity.estimated_cost
        for day in plan.days
        for block in day.time_blocks
    )


def _slot_order(slot: TimeSlot) -> int:
    """Sort key for canonical time slot ordering."""
    order = {
        TimeSlot.MORNING: 0,
        TimeSlot.LUNCH: 1,
        TimeSlot.AFTERNOON: 2,
        TimeSlot.EVENING: 3,
    }
    return order[slot]
