"""Agentic Search-then-Synthesize itinerary engine via xAI Grok + native web search."""

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

RESEARCH_SYSTEM_PROMPT_BASE = """You are Grok, a travel research agent with live web search.

MANDATORY WORKFLOW — SEARCH FIRST:
1. You MUST issue web_search tool calls BEFORE writing any venue recommendations.
2. Scan active web indices (TripAdvisor, Google Maps listings, official tourism boards, reputable local food blogs, Eater, Time Out, Michelin guides) for the target city ONLY.
3. Only include businesses and attractions you can corroborate from search results as operational and real.

ZERO-HALLUCINATION RULES:
- Rule 1 (Search-First): You are STRICTLY FORBIDDEN from relying on internal static knowledge for specific restaurants, coffee shops, or niche attractions. Use real-time web search.
- Rule 2 (No Inventions): Never fabricate venue names. Every entity must be a real-world business or landmark found in search.
- Rule 3 (Citation Mapping): For each venue, note the source domain or publication that verified it, the neighborhood, city, and country.

GEOGRAPHIC PINNING (CRITICAL):
- Every web_search query MUST explicitly include the target destination's city AND country/region name.
- Example: search "The Stand Cafe, New York City, USA" — NEVER search only "The Stand Cafe".
- You are STRICTLY FORBIDDEN from mixing matching records across different states, countries, or continents.
- Verify the geographic location in each search result BEFORE adding it to the dossier.
- Reject any venue whose address or listing is outside the requested destination boundaries.

OUTPUT FORMAT (research dossier, NOT JSON):
Produce a structured research brief with sections per day and time block (Morning, Lunch, Afternoon, Evening).
For each slot list: exact official venue name, city/neighborhood confirmation, why it fits, estimated USD cost, source citation.
For Foodie trips: Lunch should include a real lunch venue AND a nearby dessert/coffee stop with walking route notes when found in search.

LIVE EVENTS & ENTERTAINMENT (when selected):
- Search for REAL time-sensitive events during the travel dates: concerts, sports fixtures/match days, theater, festivals, and ticketed shows IN the target city.
- Use ticketing sites, venue calendars, league schedules, and local event listings (Songkick, Ticketmaster, official stadium/arena sites).
- List event name, venue, date/time window, price range, and source URL. Only include events you verified via search.
"""

SYNTHESIS_SYSTEM_PROMPT_BASE = """You are Grok, synthesizing a verified travel itinerary into strict JSON.

You receive a web-research dossier containing ONLY real venues found via live search.
- Populate the itinerary EXCLUSIVELY from that dossier. Do not invent new venues.
- Each activity description must briefly mention the verification source (e.g. "Per TripAdvisor…", "Listed on Google Maps…").
- Set source_hint to a short citation string per activity.
- Set is_live_event=true ONLY for verified time-sensitive entertainment (concerts, sports, theater, match days) from the dossier.
- Live event descriptions MUST include event date/time when known from search.
- Each day MUST have exactly four time_blocks: Morning, Lunch, Afternoon, Evening.
- Coordinates should reflect the researched location within the target city (they will be re-verified on OpenStreetMap).

GEOGRAPHIC SYNTHESIS RULES (CRITICAL):
- Cross-reference every venue in the dossier against the requested destination city/country.
- If a dossier entry lacks confirmation that the venue is inside the target destination boundaries, REJECT it.
- Replace rejected entries with a verified landmark or business explicitly located in the target city from the dossier.
- Never import venues from other cities, states, or continents — even if the business name is identical.

- Return ONLY valid JSON matching the schema. No markdown fences.
"""


def _build_research_instructions(destination: str) -> str:
    """Build Phase 1 system instructions with absolute geo-pinning for the destination."""
    return (
        f"{RESEARCH_SYSTEM_PROMPT_BASE}\n\n"
        f"ACTIVE DESTINATION LOCK:\n"
        f"- You are restricted to the requested city and country context: {destination}.\n"
        f"- Every web_search query you execute MUST include \"{destination}\" and the "
        f"appropriate country/region (e.g. \"venue name, {destination}, USA\").\n"
        f"- Do NOT use venues from other cities that share the same business name.\n"
    )


def _build_synthesis_instructions(destination: str) -> str:
    """Build Phase 2 system instructions with destination-scoped synthesis rules."""
    return (
        f"{SYNTHESIS_SYSTEM_PROMPT_BASE}\n\n"
        f"TARGET DESTINATION: {destination}\n"
        f"- All activities MUST be geographically located in {destination}.\n"
        f"- Discard any dossier venue not confirmed within {destination}; substitute a "
        f"verified in-bounds alternative from the dossier.\n"
    )


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

_WEB_SEARCH_TOOLS: list[dict[str, str]] = [{"type": "web_search"}]


class AIItineraryEngine:
    """
    Agentic itinerary engine: web search research → structured JSON synthesis → geocode anchor.
    """

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
        Generate a validated itinerary via Search-then-Synthesize.

        Phase 1: xAI Responses API + web_search tool (live venue research).
        Phase 2: Structured JSON synthesis from research dossier.
        Phase 3: Nominatim location anchoring.
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
                    "Search-then-Synthesize completed on attempt %d for %s",
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

    async def _call_llm(self, preferences: UserPreferences) -> str:
        """Run research (web search) then synthesis (structured JSON)."""
        if self._client is None:
            raise XAIConfigurationError(XAI_MISSING_KEY_MESSAGE)

        research_text, citations = await self._run_research_phase(preferences)
        return await self._run_synthesis_phase(preferences, research_text, citations)

    async def _run_research_phase(
        self, preferences: UserPreferences
    ) -> tuple[str, list[str]]:
        """Phase 1: xAI Responses API with native web_search tool."""
        if self._client is None:
            raise XAIConfigurationError(XAI_MISSING_KEY_MESSAGE)

        user_prompt = self._build_research_prompt(preferences)
        logger.info(
            "Starting web search research phase for %s (%d days)",
            preferences.destination,
            preferences.duration_days,
        )

        try:
            response = await self._client.responses.create(
                model=self._settings.xai_model,
                instructions=_build_research_instructions(preferences.destination),
                input=[
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                tools=_WEB_SEARCH_TOOLS,
                temperature=0.4,
            )
        except AuthenticationError as exc:
            logger.error("xAI authentication failed during research: %s", exc, exc_info=True)
            raise XAIConnectionError(
                "xAI authentication failed. Please verify your XAI_API_KEY is valid."
            ) from exc
        except APIConnectionError as exc:
            logger.error("xAI connection error during research: %s", exc, exc_info=True)
            raise XAIConnectionError(
                "Unable to reach the xAI API during web search. Check your network connection."
            ) from exc
        except APIStatusError as exc:
            logger.error(
                "xAI research API error HTTP %s: %s",
                exc.status_code,
                exc.message,
                exc_info=True,
            )
            raise XAIConnectionError(
                f"xAI API error during research ({exc.status_code}). Please try again later."
            ) from exc

        research_text = self._extract_response_text(response)
        if not research_text.strip():
            raise ValueError("Web search research phase returned empty content")

        citations = self._extract_citations(response)
        logger.info(
            "Research phase complete for %s (%d chars, %d citations)",
            preferences.destination,
            len(research_text),
            len(citations),
        )
        return research_text, citations

    async def _run_synthesis_phase(
        self,
        preferences: UserPreferences,
        research_text: str,
        citations: list[str],
    ) -> str:
        """Phase 2: funnel verified research into strict ItineraryPlan JSON."""
        if self._client is None:
            raise XAIConfigurationError(XAI_MISSING_KEY_MESSAGE)

        citation_block = "\n".join(f"- {url}" for url in citations[:20]) or "- (see research body)"
        user_content = f"""Synthesize this verified research dossier into the itinerary JSON schema.

TRIP REQUIREMENTS:
Destination: {preferences.destination}
Duration: {preferences.duration_days} days
Travel party: {preferences.travel_party.value}
Pace: {preferences.pace.value}
Budget tier: {preferences.budget_tier.value}
Interests: {", ".join(i.value for i in preferences.interests)}

WEB RESEARCH DOSSIER:
{research_text}

CITATION URLS FROM SEARCH:
{citation_block}

Return exactly {preferences.duration_days} days. Every venue must:
1. Come from the dossier above.
2. Be confirmed within {preferences.destination} — reject any out-of-bounds venue."""

        messages = [
            {
                "role": "system",
                "content": _build_synthesis_instructions(preferences.destination),
            },
            {"role": "user", "content": user_content},
        ]

        logger.info("Starting JSON synthesis phase for %s", preferences.destination)

        try:
            response = await self._client.chat.completions.create(
                model=self._settings.xai_model,
                response_format={
                    "type": "json_schema",
                    "json_schema": _ITINERARY_JSON_SCHEMA,
                },
                messages=messages,
                temperature=0.3,
            )
        except APIStatusError as exc:
            if exc.status_code in (400, 422):
                logger.warning(
                    "json_schema synthesis rejected (%s); falling back to json_object",
                    exc.status_code,
                )
                try:
                    response = await self._client.chat.completions.create(
                        model=self._settings.xai_model,
                        response_format={"type": "json_object"},
                        messages=messages,
                        temperature=0.3,
                    )
                except APIStatusError as fallback_exc:
                    raise XAIConnectionError(
                        f"xAI synthesis error ({fallback_exc.status_code}). Please try again later."
                    ) from fallback_exc
            else:
                raise XAIConnectionError(
                    f"xAI synthesis error ({exc.status_code}). Please try again later."
                ) from exc
        except AuthenticationError as exc:
            raise XAIConnectionError(
                "xAI authentication failed during synthesis."
            ) from exc
        except APIConnectionError as exc:
            raise XAIConnectionError(
                "Unable to reach the xAI API during synthesis."
            ) from exc

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Synthesis phase returned empty JSON")
        return self._extract_json(content)

    def _build_research_prompt(self, preferences: UserPreferences) -> str:
        """Prompt that forces web search before any venue listing."""
        interests = ", ".join(i.value for i in preferences.interests)
        foodie_note = ""
        if Interest.FOODIE in preferences.interests:
            foodie_note = (
                "\nFor each day, search for a real lunch restaurant AND a real nearby "
                "dessert shop or specialty coffee roaster with a walkable route between them."
            )
        events_note = ""
        if Interest.LIVE_EVENTS in preferences.interests:
            events_note = (
                "\nCRITICAL: Search for live concerts, sports matches, theater shows, and "
                "ticketed events occurring during the trip dates in this city. Include "
                "official venue names and event dates from web results."
            )

        dest = preferences.destination
        return f"""SEARCH THE WEB FIRST, then write your research dossier.

TARGET DESTINATION (GEO LOCK): {dest}
Trip length: {preferences.duration_days} days
Travel party: {preferences.travel_party.value}
Pace: {preferences.pace.value}
Budget tier: {preferences.budget_tier.value}
Interests: {interests}
{foodie_note}{events_note}

GEO SEARCH RULES:
- Every web_search query MUST include "{dest}" plus country/region (e.g. "restaurant name, {dest}, USA").
- Verify each result's address is in {dest} before adding to the dossier.
- NEVER use a venue from another city/country, even if the name matches.

You MUST call web_search to find operational venues on TripAdvisor, Google Maps, and local guides.
Do NOT output JSON. Output a day-by-day research dossier with Morning, Lunch, Afternoon, Evening slots."""

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        """Extract aggregated text from an xAI Responses API payload."""
        if hasattr(response, "output_text"):
            text = response.output_text
            if text:
                return str(text)

        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) == "message":
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "type", None) == "output_text":
                        chunks.append(str(getattr(content, "text", "")))
        return "".join(chunks)

    @staticmethod
    def _extract_citations(response: Any) -> list[str]:
        """Extract citation URLs from a Responses API payload when present."""
        citations: list[str] = []
        raw_citations = getattr(response, "citations", None)
        if isinstance(raw_citations, list):
            for item in raw_citations:
                if isinstance(item, str):
                    citations.append(item)
                elif isinstance(item, dict) and "url" in item:
                    citations.append(str(item["url"]))
        return citations

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
        self._log_progressive_foodie_tour_check(plan, preferences)
        return plan

    @staticmethod
    def _to_verified_plan(llm_plan: ItineraryPlanLLMOutput) -> ItineraryPlan:
        """Convert LLM output into a plan ready for location anchoring."""
        days: list[DayItinerary] = []
        for day in llm_plan.days:
            blocks: list[TimeBlock] = []
            for block in day.time_blocks:
                llm_activity = block.activity
                description = llm_activity.description
                if llm_activity.source_hint and llm_activity.source_hint not in description:
                    description = f"{description} (Source: {llm_activity.source_hint})"

                blocks.append(
                    TimeBlock(
                        time_slot=block.time_slot,
                        activity=Activity(
                            activity_name=llm_activity.activity_name,
                            description=description,
                            estimated_cost=llm_activity.estimated_cost,
                            latitude=llm_activity.latitude,
                            longitude=llm_activity.longitude,
                            is_live_event=llm_activity.is_live_event,
                            source_hint=llm_activity.source_hint,
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

    def _log_progressive_foodie_tour_check(
        self, plan: ItineraryPlan, preferences: UserPreferences
    ) -> None:
        """
        Non-blocking aesthetic check for Progressive Foodie Tour phrasing.

        Never raises — missing keywords must not abort the 3-phase pipeline.
        """
        if Interest.FOODIE not in preferences.interests:
            logger.info(
                "Aesthetic check: Passing itinerary processing safely to the layout layer."
            )
            return

        keywords = ("dessert", "coffee", "café", "cafe", "pastry", "gelato", "roaster")
        for day in plan.days:
            lunch_blocks = [
                b for b in day.time_blocks if b.time_slot == TimeSlot.LUNCH
            ]
            for block in lunch_blocks:
                desc_lower = block.activity.description.lower()
                if not any(kw in desc_lower for kw in keywords):
                    logger.info(
                        "Aesthetic check: Day %d lunch missing dessert/coffee keywords; "
                        "passing itinerary safely (no retry).",
                        day.day_number,
                    )

        logger.info(
            "Aesthetic check: Passing itinerary processing safely to the layout layer."
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

            slot_templates: list[tuple[TimeSlot, str, str, float, bool, str]] = [
                (
                    TimeSlot.MORNING,
                    f"Louvre Museum — Day {day_num}",
                    f"Explore the Louvre collections in {preferences.destination}.",
                    15 * cost_multiplier,
                    False,
                    "Google Maps",
                ),
                (
                    TimeSlot.LUNCH,
                    f"Le Comptoir du Relais — Day {day_num}",
                    (
                        f"Lunch at this well-known bistro, then walk to a specialty coffee "
                        f"roaster for dessert in {preferences.destination}."
                    ),
                    35 * cost_multiplier,
                    False,
                    "TripAdvisor",
                ),
                (
                    TimeSlot.AFTERNOON,
                    f"Musée d'Orsay — Day {day_num}",
                    "Visit the impressionist galleries.",
                    25 * cost_multiplier,
                    False,
                    "Google Maps",
                ),
                (
                    TimeSlot.EVENING,
                    f"Evening at Accor Arena — Day {day_num}",
                    (
                        "Check local listings for concerts or sports at this major venue "
                        f"during your visit (Source: Ticketmaster)."
                    ),
                    85 * cost_multiplier,
                    Interest.LIVE_EVENTS in preferences.interests,
                    "Ticketmaster",
                ),
            ]

            for slot, name, desc, cost, is_live, source in slot_templates:
                lat = base_lat + offset
                lng = base_lng + offset
                blocks.append(
                    TimeBlock(
                        time_slot=slot,
                        activity=Activity(
                            activity_name=name,
                            description=f"{desc} (Source: {source})",
                            estimated_cost=round(cost, 2),
                            latitude=lat,
                            longitude=lng,
                            is_live_event=is_live,
                            source_hint=source,
                        ),
                    )
                )

            days.append(DayItinerary(day_number=day_num, time_blocks=blocks))

        return ItineraryPlan(
            destination=preferences.destination,
            duration_days=preferences.duration_days,
            days=days,
        )
