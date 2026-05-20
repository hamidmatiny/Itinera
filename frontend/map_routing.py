"""Folium-based sequential route maps for daily itineraries."""

from __future__ import annotations

import folium
from folium import plugins

from schemas import DayItinerary, TimeSlot

_SLOT_ORDER = [TimeSlot.MORNING, TimeSlot.LUNCH, TimeSlot.AFTERNOON, TimeSlot.EVENING]
_ROUTE_COLOR = "#2563eb"
_ROUTE_WEIGHT = 4


def _slot_sort_key(slot: TimeSlot) -> int:
    return _SLOT_ORDER.index(slot)


def build_day_route_map(day: DayItinerary, destination: str) -> folium.Map:
    """
    Build an interactive map with numbered stops and a connecting route polyline.

    Stops follow Morning → Lunch → Afternoon → Evening.
    """
    sorted_blocks = sorted(day.time_blocks, key=lambda b: _slot_sort_key(b.time_slot))
    if not sorted_blocks:
        return folium.Map(location=[0, 0], zoom_start=2)

    coordinates: list[tuple[float, float]] = [
        (block.activity.latitude, block.activity.longitude) for block in sorted_blocks
    ]
    center_lat = sum(c[0] for c in coordinates) / len(coordinates)
    center_lng = sum(c[1] for c in coordinates) / len(coordinates)

    route_map = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=14,
        tiles="OpenStreetMap",
    )

    if len(coordinates) >= 2:
        folium.PolyLine(
            locations=coordinates,
            color=_ROUTE_COLOR,
            weight=_ROUTE_WEIGHT,
            opacity=0.85,
            dash_array="8 12",
            tooltip=f"Day {day.day_number} route · {destination}",
        ).add_to(route_map)

        plugins.AntPath(
            locations=coordinates,
            color=_ROUTE_COLOR,
            weight=3,
            opacity=0.5,
            delay=800,
            dash_array=[10, 20],
        ).add_to(route_map)

    for stop_num, block in enumerate(sorted_blocks, start=1):
        activity = block.activity
        verify_tag = "✅ Verified" if activity.is_verified else "⚠️ Estimated"
        popup_html = (
            f"<b>Stop {stop_num} · {block.time_slot.value}</b><br>"
            f"{activity.activity_name}<br>"
            f"${activity.estimated_cost:,.0f}<br>"
            f"{verify_tag}"
        )
        folium.Marker(
            location=[activity.latitude, activity.longitude],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{stop_num}. {block.time_slot.value}: {activity.activity_name}",
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:14px;font-weight:bold;color:white;'
                    f"background:{_ROUTE_COLOR};border-radius:50%;width:26px;height:26px;"
                    f"display:flex;align-items:center;justify-content:center;"
                    f'border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,.4);">'
                    f"{stop_num}</div>"
                ),
                icon_size=(26, 26),
                icon_anchor=(13, 13),
            ),
        ).add_to(route_map)

    folium.LayerControl().add_to(route_map)
    return route_map
