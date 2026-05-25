"""Streamlit UI components (presentation layer only)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Literal

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from frontend.api_client import ItineraryAPIClient
from frontend.map_routing import build_day_route_map
from frontend.sharing import render_share_link
from frontend.theme import render_html, render_itinerary_card, render_metric_pills
from schemas import (
    BudgetTier,
    Interest,
    ItineraryPlan,
    ItineraryRecord,
    Pace,
    TimeSlot,
    TravelParty,
    UserPreferences,
    daily_budget_allocation,
    day_estimated_cost,
)
from services.export_service import generate_itinerary_markdown_from_record


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
        key="open_saved_trip_btn",
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
        key="generate_itinerary_btn",
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


def render_trip_actions(
    record: ItineraryRecord,
    *,
    view_only: bool = False,
) -> None:
    """Share link + Markdown export controls (no session-resetting interactions)."""
    markdown_body = generate_itinerary_markdown_from_record(record)
    safe_destination = record.plan.destination.replace(" ", "_")[:40]

    render_html(
        '<div class="section-label" style="margin-top:8px;">Trip actions</div>'
    )
    share_col, export_col = st.columns([3, 2])

    with share_col:
        render_share_link(record.itinerary_id)

    with export_col:
        render_html('<div class="section-label">Offline guide</div>')
        st.download_button(
            label="Export Markdown / PDF Guide",
            data=markdown_body,
            file_name=f"itinera_{safe_destination}_{record.itinerary_id[:8]}.md",
            mime="text/markdown",
            use_container_width=True,
            help="Save offline; print to PDF from any Markdown viewer.",
            key=f"export_md_{record.itinerary_id}",
        )

    if view_only:
        st.caption("View-only shared trip · generate your own itinerary at the home page.")


def render_daily_itinerary(plan: ItineraryPlan, preferences: UserPreferences) -> None:
    """Tab 1: daily schedule with glassmorphism cards and budget badge pills."""
    total_cost = _compute_total_cost(plan)
    daily_budget = daily_budget_allocation(preferences.budget_tier)
    trip_budget = daily_budget * plan.duration_days
    delta_total = f"${total_cost - trip_budget:+,.0f} vs tier"

    render_metric_pills(
        [
            ("Destination", plan.destination, None),
            ("Duration", f"{plan.duration_days} days", None),
            ("Trip budget", f"${trip_budget:,.0f}", None),
            ("Est. spend", f"${total_cost:,.0f}", delta_total),
        ]
    )

    render_html('<div class="section-label">Daily budget burn rate</div>')
    burn_items: list[tuple[str, str, str | None]] = []
    for day in plan.days:
        actual = day_estimated_cost(day)
        allocated = daily_budget
        delta = actual - allocated
        burn_items.append(
            (
                f"Day {day.day_number}",
                f"${actual:,.0f}",
                f"${delta:+,.0f} vs ${allocated:,.0f}/day",
            )
        )
    render_metric_pills(burn_items)

    for day in plan.days:
        day_cost = day_estimated_cost(day)
        allocated = daily_budget
        over_under = day_cost - allocated
        direction = "over" if over_under > 0 else "under"
        render_html(
            f"""
            <div class="day-section-title">
                Day {day.day_number}
                <span style="font-size:0.85rem;font-weight:500;color:rgba(244,246,251,0.55);">
                    · ${day_cost:,.0f} spent ({direction} budget by ${abs(over_under):,.0f})
                </span>
            </div>
            """
        )
        render_metric_pills(
            [
                ("Allocated / day", f"${allocated:,.0f}", None),
                ("AI estimate", f"${day_cost:,.0f}", None),
                ("Burn rate", f"{(day_cost / allocated * 100):.0f}%", None),
            ]
        )

        for block in sorted(day.time_blocks, key=lambda b: _slot_order(b.time_slot)):
            activity = block.activity
            badges: list[tuple[str, str]] = [("slot", block.time_slot.value)]
            if activity.is_live_event:
                badges.append(("live", "Live Event"))
            if activity.is_verified:
                badges.append(("verified", "Verified"))
            else:
                badges.append(("warn", "Location estimated"))

            meta_parts = [
                f"${activity.estimated_cost:,.0f}",
                f"({activity.latitude:.4f}, {activity.longitude:.4f})",
            ]
            if activity.formatted_address and activity.is_verified:
                meta_parts.append(activity.formatted_address)
            elif activity.source_hint:
                meta_parts.append(f"Source: {activity.source_hint}")

            warning = None
            if not activity.is_verified:
                warning = "Location estimated — double-check venue status before visiting."

            render_itinerary_card(
                time_slot=block.time_slot.value,
                title=activity.activity_name,
                description=activity.description,
                meta=" · ".join(meta_parts),
                badges=badges,
                is_live_event=activity.is_live_event,
                warning=warning,
            )


def render_foodie_live_events(plan: ItineraryPlan) -> None:
    """Tab 2: foodie pairings and time-sensitive live entertainment."""
    render_html('<div class="section-label">Foodie & Live Events</div>')

    lunch_blocks = []
    live_events = []

    for day in plan.days:
        for block in day.time_blocks:
            if block.time_slot == TimeSlot.LUNCH:
                lunch_blocks.append((day.day_number, block))
            if block.activity.is_live_event:
                live_events.append((day.day_number, block))

    render_html(
        '<div class="day-section-title">Progressive Foodie Tour — Lunch Pairings</div>'
    )
    if lunch_blocks:
        for day_num, block in lunch_blocks:
            activity = block.activity
            render_itinerary_card(
                time_slot="Lunch",
                title=f"Day {day_num} — {activity.activity_name}",
                description=activity.description,
                meta=f"${activity.estimated_cost:,.0f} · Lunch slot",
                badges=[("slot", "Lunch"), ("verified" if activity.is_verified else "warn", "Foodie")],
            )
    else:
        render_html('<div class="empty-state">No lunch blocks found.</div>')

    render_html('<div class="day-section-title">Live Events & Entertainment</div>')
    st.caption(
        "Concerts, sports, theater, and match days discovered via real-time web search "
        "for your travel dates."
    )
    if live_events:
        for day_num, block in live_events:
            activity = block.activity
            meta = f"Day {day_num} · {block.time_slot.value}"
            if activity.source_hint:
                meta += f" · Source: {activity.source_hint}"
            render_itinerary_card(
                time_slot=block.time_slot.value,
                title=activity.activity_name,
                description=activity.description,
                meta=meta,
                badges=[("live", "Live Event"), ("slot", block.time_slot.value)],
                is_live_event=True,
            )
    else:
        render_html(
            '<div class="empty-state">No live events flagged. Select Live Events & '
            "Entertainment and regenerate to search for concerts, sports, theater, "
            "and match days during your trip.</div>"
        )


def render_map_view(plan: ItineraryPlan) -> None:
    """Tab 3: Folium route maps with sequential walking/driving paths."""
    render_html('<div class="section-label">Map View — Daily Routes</div>')
    st.caption(
        "Connected trails follow Morning → Lunch → Afternoon → Evening. "
        "Numbered pins show stop order."
    )

    if not plan.days:
        render_html('<div class="empty-state">No coordinates to display.</div>')
        return

    for day in plan.days:
        render_html(f'<div class="day-section-title">Day {day.day_number}</div>')
        rows = []
        for order, block in enumerate(
            sorted(day.time_blocks, key=lambda b: _slot_order(b.time_slot)),
            start=1,
        ):
            activity = block.activity
            verification_note = (
                "Verified"
                if activity.is_verified
                else "Location estimated - double check venue status"
            )
            event_note = "Live Event" if activity.is_live_event else ""
            rows.append(
                {
                    "stop": order,
                    "time_slot": block.time_slot.value,
                    "activity": activity.activity_name,
                    "latitude": round(activity.latitude, 5),
                    "longitude": round(activity.longitude, 5),
                    "verification": verification_note,
                    "live_event": event_note,
                }
            )

        df = pd.DataFrame(rows)
        unverified_count = sum(1 for r in rows if "estimated" in r["verification"])
        if unverified_count:
            render_html(
                f"""
                <div class="status-banner status-banner--warn">
                    {html.escape(str(unverified_count))} stop(s) on Day {day.day_number}
                    use estimated placements — venues could not be confirmed on OpenStreetMap.
                </div>
                """
            )

        map_col, table_col = st.columns([3, 2])

        with map_col:
            try:
                route_map = build_day_route_map(day, plan.destination)
                st_folium(route_map, width=None, height=420, returned_objects=[])
            except Exception as exc:
                st.warning(f"Route map unavailable; showing point map. ({exc})")
                st.map(
                    df,
                    latitude="latitude",
                    longitude="longitude",
                    size=100,
                )

        with table_col:
            render_html('<div class="section-label">Route sequence & coordinates</div>')
            st.dataframe(
                df[
                    [
                        "stop",
                        "time_slot",
                        "activity",
                        "latitude",
                        "longitude",
                        "verification",
                        "live_event",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )


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
