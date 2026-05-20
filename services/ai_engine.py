"""LLM interaction, structured outputs, and itinerary parsing via xAI (Grok)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, AuthenticationError
from pydantic import ValidationError

from config import Settings, XAI_MISSING_KEY_MESSAGE, get_settings
from schemas import (
    Activity,
    ActivityLLMOutput,
    DayItinerary,
    Interest,
    ItineraryPlan,
    ItineraryPlanLLMOutput,
    TimeBlock,
    TimeSlot,
    UserPreferences,
)
from services.exceptions import XAIConfigurationError, XAIConnectionError
from services.geocoding import anchor_itinerary_locations

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Grok, an expert travel planner AI. Generate hyper-personalized daily itineraries.

RULES:
1. Each day MUST contain exactly four time_blocks: Morning, Lunch, Afternoon, Evening.
2. VENUE AUTHENTICITY (CRITICAL): Only recommend globally renowned, well-documented, real-world establishments that exist today (museums, famous restaurants, major parks, iconic landmarks). NEVER invent fictional cafés, shops, or attractions. Use exact official venue names as they appear on maps.
3. Coordinates are advisory only — they will be verified against OpenStreetMap post-generation. Still provide plausible latitude/longitude for each activity.
4. Costs must align with the user's budget tier.
5. Pace affects activity density: Relaxed = fewer/longer stops, Packed = more ambitious routing.
6. Honor all selected interest tags across the trip.

PROGRESSIVE FOODIE TOUR (MANDATORY when Foodie is selected):
- For EVERY Lunch time_block, pair the main lunch venue with a nearby dessert shop OR specialty coffee roaster.
- The Lunch description MUST describe: (a) the primary lunch spot, (b) a 5–15 minute walking route to dessert/coffee, and (c) why they pair well locally.

HIDDEN GEMS:
- Mark hidden_gem=true for low-crowd, local-favorite spots.
- Include at least one hidden_gem activity per day when Hidden Gems interest is selected.
"""


def _build_strict_json_schema() -> dict[str, Any]:
    """Build xAI/OpenAI-compatible strict JSON schema from Pydantic models."""
    schema = ItineraryPlanLLMOutput.model_json_schema(ref_template="#/$defs/{model}")

    def _apply_strict(node: dict[str, Any]) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            props = node["properties"]
            if props:
                node["required"] = list(props.keys())
        for value in node.values():
            if isinstance(value, dict):
                _apply_strict(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        _apply_strict(item)

    _apply_strict(schema)
    if "$defs" in schema:
        for def_schema in schema["$defs"].values():
            _apply_strict(def_schema)

    return schema


_ITINERARY_JSON_SCHEMA: dict[str, Any] = {
    "name": "itinerary_plan",
    "strict": True,
    "schema": _build_strict_json_schema(),
}


class AIItineraryEngine:
    """Constructs prompts, calls xAI Grok asynchronously, validates JSON, and retries on failure."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: AsyncOpenAI | None = None

        if self._settings.use_mock_llm:
            return

        try:
            api_key = self._settings.require_xai_api_key()
        except ValueError as exc:
            raise XAIConfigurationError(str(exc)) from exc

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._settings.xai_base_url,
        )

    async def generate(self, preferences: UserPreferences) -> ItineraryPlan:
        """
        Generate a validated itinerary plan.

        Uses xAI Grok structured outputs with retries, or mock when enabled.
        """
        if self._settings.use_mock_llm:
            logger.warning("USE_MOCK_LLM enabled; using mock itinerary generator.")
            plan = self._generate_mock(preferences)
            return await anchor_itinerary_locations(plan)

        if self._client is None:
            raise XAIConfigurationError(XAI_MISSING_KEY_MESSAGE)

        last_error: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                raw = await self._call_llm(preferences)
                plan = self._parse_and_validate(raw, preferences)
                plan = await anchor_itinerary_locations(plan)
                logger.info(
                    "Itinerary generated successfully on attempt %d for %s",
                    attempt,
                    preferences.destination,
                )
                return plan
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                logger.error(
                    "Itinerary parse/validation failed (attempt %d/%d): %s",
                    attempt,
                    self._settings.max_retries,
                    exc,
                    exc_info=True,
                )

        raise RuntimeError(
            f"Failed to generate valid itinerary after {self._settings.max_retries} attempts"
        ) from last_error

    def _build_user_prompt(self, preferences: UserPreferences) -> str:
        """Build the user message from validated preferences."""
        interests = ", ".join(i.value for i in preferences.interests)
        foodie_note = ""
        if Interest.FOODIE in preferences.interests:
            foodie_note = (
                "\nIMPORTANT: Apply Progressive Foodie Tour rules to every Lunch block."
            )

        return f"""Create a {preferences.duration_days}-day itinerary with these preferences:

Destination: {preferences.destination}
Travel party: {preferences.travel_party.value}
Pace: {preferences.pace.value}
Budget tier: {preferences.budget_tier.value}
Interests: {interests}
{foodie_note}

Return exactly {preferences.duration_days} days of activities."""

    async def _call_llm(self, preferences: UserPreferences) -> str:
        """Invoke xAI Grok with native structured JSON schema output."""
        if self._client is None:
            raise XAIConfigurationError(XAI_MISSING_KEY_MESSAGE)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_prompt(preferences)},
        ]

        try:
            response = await self._client.chat.completions.create(
                model=self._settings.xai_model,
                response_format={
                    "type": "json_schema",
                    "json_schema": _ITINERARY_JSON_SCHEMA,
                },
                messages=messages,
                temperature=0.7,
            )
        except APIStatusError as exc:
            if exc.status_code in (400, 422):
                logger.warning(
                    "json_schema rejected (%s); falling back to json_object mode",
                    exc.status_code,
                )
                try:
                    response = await self._client.chat.completions.create(
                        model=self._settings.xai_model,
                        response_format={"type": "json_object"},
                        messages=messages,
                        temperature=0.7,
                    )
                except APIStatusError as fallback_exc:
                    logger.error(
                        "xAI API error on fallback: %s",
                        fallback_exc.message,
                        exc_info=True,
                    )
                    raise XAIConnectionError(
                        f"xAI API error ({fallback_exc.status_code}). Please try again later."
                    ) from fallback_exc
            else:
                logger.error(
                    "xAI API returned HTTP %s: %s",
                    exc.status_code,
                    exc.message,
                    exc_info=True,
                )
                raise XAIConnectionError(
                    f"xAI API error ({exc.status_code}). Please try again later."
                ) from exc
        except AuthenticationError as exc:
            logger.error("xAI authentication failed: %s", exc, exc_info=True)
            raise XAIConnectionError(
                "xAI authentication failed. Please verify your XAI_API_KEY is valid."
            ) from exc
        except APIConnectionError as exc:
            logger.error("xAI connection error: %s", exc, exc_info=True)
            raise XAIConnectionError(
                "Unable to reach the xAI API. Check your network connection and try again."
            ) from exc

        content = response.choices[0].message.content
        if not content:
            raise ValueError("xAI returned empty content")
        return self._extract_json(content)

    @staticmethod
    def _extract_json(raw: str) -> str:
        """Extract JSON from a response that may include markdown fences."""
        text = raw.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if fence_match:
            return fence_match.group(1).strip()
        return text

    def _parse_and_validate(
        self, raw_json: str, preferences: UserPreferences
    ) -> ItineraryPlan:
        """Parse JSON string and validate against Pydantic models."""
        payload: dict[str, Any] = json.loads(raw_json)
        payload["destination"] = preferences.destination
        payload["duration_days"] = preferences.duration_days
        llm_plan = ItineraryPlanLLMOutput.model_validate(payload)
        plan = self._to_verified_plan(llm_plan)
        self._assert_progressive_foodie_tour(plan, preferences)
        return plan

    @staticmethod
    def _to_verified_plan(llm_plan: ItineraryPlanLLMOutput) -> ItineraryPlan:
        """Convert LLM output into a plan ready for location anchoring."""
        days: list[DayItinerary] = []
        for day in llm_plan.days:
            blocks: list[TimeBlock] = []
            for block in day.time_blocks:
                llm_activity = block.activity
                blocks.append(
                    TimeBlock(
                        time_slot=block.time_slot,
                        activity=Activity(
                            activity_name=llm_activity.activity_name,
                            description=llm_activity.description,
                            estimated_cost=llm_activity.estimated_cost,
                            latitude=llm_activity.latitude,
                            longitude=llm_activity.longitude,
                            hidden_gem=llm_activity.hidden_gem,
                            is_verified=False,
                            formatted_address=None,
                        ),
                    )
                )
            days.append(DayItinerary(day_number=day.day_number, time_blocks=blocks))
        return ItineraryPlan(
            destination=llm_plan.destination,
            duration_days=llm_plan.duration_days,
            days=days,
        )

    def _assert_progressive_foodie_tour(
        self, plan: ItineraryPlan, preferences: UserPreferences
    ) -> None:
        """Soft validation that lunch blocks mention paired dessert/coffee routes."""
        if Interest.FOODIE not in preferences.interests:
            return

        keywords = ("dessert", "coffee", "café", "cafe", "pastry", "gelato", "roaster")
        for day in plan.days:
            lunch_blocks = [
                b for b in day.time_blocks if b.time_slot == TimeSlot.LUNCH
            ]
            for block in lunch_blocks:
                desc_lower = block.activity.description.lower()
                if not any(kw in desc_lower for kw in keywords):
                    raise ValueError(
                        f"Day {day.day_number} Lunch must include Progressive "
                        f"Foodie Tour pairing (dessert/coffee walking route)."
                    )

    def _generate_mock(self, preferences: UserPreferences) -> ItineraryPlan:
        """Deterministic mock itinerary for local development without API keys."""
        base_lat, base_lng = 48.8566, 2.3522
        dest = preferences.destination.lower()
        if "tokyo" in dest:
            base_lat, base_lng = 35.6762, 139.6503
        elif "new york" in dest or "nyc" in dest:
            base_lat, base_lng = 40.7128, -74.0060
        elif "barcelona" in dest:
            base_lat, base_lng = 41.3851, 2.1734

        cost_multiplier = {
            "Budget": 0.6,
            "Mid-range": 1.0,
            "Luxury": 2.5,
        }[preferences.budget_tier.value]

        days: list[DayItinerary] = []
        for day_num in range(1, preferences.duration_days + 1):
            offset = (day_num - 1) * 0.01
            blocks: list[TimeBlock] = []

            slot_templates: list[tuple[TimeSlot, str, str, float, bool]] = [
                (
                    TimeSlot.MORNING,
                    f"Historic Walk — Day {day_num}",
                    f"Explore iconic streets and architecture in {preferences.destination}.",
                    15 * cost_multiplier,
                    Interest.HIDDEN_GEMS in preferences.interests and day_num % 2 == 1,
                ),
                (
                    TimeSlot.LUNCH,
                    f"Local Lunch & Coffee Trail — Day {day_num}",
                    (
                        f"Start at a neighborhood bistro for regional specialties, then take a "
                        f"10-minute walk to a specialty coffee roaster for a post-lunch digestif "
                        f"experience in {preferences.destination}."
                    ),
                    35 * cost_multiplier,
                    False,
                ),
                (
                    TimeSlot.AFTERNOON,
                    f"Cultural Afternoon — Day {day_num}",
                    "Visit a museum or gallery aligned with your cultural interests.",
                    25 * cost_multiplier,
                    False,
                ),
                (
                    TimeSlot.EVENING,
                    f"Evening Stroll & Dinner — Day {day_num}",
                    "Sunset viewpoint followed by a recommended local dinner spot.",
                    55 * cost_multiplier,
                    Interest.HIDDEN_GEMS in preferences.interests,
                ),
            ]

            for slot, name, desc, cost, hidden in slot_templates:
                lat = base_lat + offset
                lng = base_lng + offset
                blocks.append(
                    TimeBlock(
                        time_slot=slot,
                        activity=Activity(
                            activity_name=name,
                            description=desc,
                            estimated_cost=round(cost, 2),
                            latitude=lat,
                            longitude=lng,
                            hidden_gem=hidden,
                        ),
                    )
                )

            days.append(DayItinerary(day_number=day_num, time_blocks=blocks))

        return ItineraryPlan(
            destination=preferences.destination,
            duration_days=preferences.duration_days,
            days=days,
        )
