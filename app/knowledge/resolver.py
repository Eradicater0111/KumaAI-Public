from __future__ import annotations

import re

from app.knowledge.contracts import (
    KnowledgeDomain,
    KnowledgeIntent,
    KnowledgePlan,
    LocationScope,
    TemporalScope,
)


_WEATHER_TERMS = (
    "weather",
    "forecast",
    "temperature",
    "temp",
    "rain",
    "humidity",
    "wind",
    "storm",
    "snow",
)

_SELF_LOCATION_TERMS = (
    "near me",
    "around me",
    "where i am",
    "where i'm at",
    "my location",
    "our location",
    "current location",
    "right here",
    "weather here",
    "forecast here",
)

_TODAY_TERMS = (
    "today",
    "today's",
    "todays",
    "tonight",
    "this morning",
    "this afternoon",
    "this evening",
)

_TOMORROW_TERMS = (
    "tomorrow",
    "tomorrow's",
    "tomorrows",
    "tmr",
    "tmrw",
    "tmrs",
    "tmr's",
)

_HISTORICAL_TERMS = (
    "yesterday",
    "yesterday's",
    "yesterdays",
    "last night",
    "last week",
    "last month",
    "last year",
    "ago",
)

_FUTURE_TERMS = (
    "next week",
    "next month",
    "next year",
    "later this week",
)

_CURRENT_PUBLIC_TERMS = (
    "latest",
    "current",
    "today",
    "news",
    "score",
    "price",
    "stock",
    "market",
    "election",
    "weather",
    "forecast",
    "release",
    "version",
)


def _normalized(request) -> str:
    return (
        str(request or "")
        .strip()
        .lower()
        .replace("’", "'")
        .replace("-", " ")
    )


def _contains_term(
    text: str,
    terms: tuple[str, ...],
) -> bool:
    words = set(
        re.findall(
            r"[a-z0-9']+",
            text,
        )
    )

    for term in terms:
        if " " in term:
            if term in text:
                return True
        elif term in words:
            return True

    return False


def _extract_weather_place(
    text: str,
) -> str | None:
    self_relative = (
        *_SELF_LOCATION_TERMS,
        "here",
    )

    # Resolve self-relative location language BEFORE splitting on
    # prepositions. Without this guard, "weather near me tomorrow"
    # becomes tail="me tomorrow", which can be mistaken for the
    # explicit place "me".
    if any(
        marker in text
        for marker in _SELF_LOCATION_TERMS
    ):
        return None

    if re.search(
        r"\\bhere\\b",
        text,
    ):
        return None

    for separator in (
        " in ",
        " for ",
        " at ",
        " near ",
    ):
        if separator not in text:
            continue

        tail = (
            text
            .split(separator, 1)[1]
            .strip(" .!?")
        )

        if not tail:
            continue

        if any(
            tail == marker
            or tail.startswith(marker + " ")
            for marker in self_relative
        ):
            return None

        temporal_starts = (
            *_TODAY_TERMS,
            *_TOMORROW_TERMS,
            *_HISTORICAL_TERMS,
            *_FUTURE_TERMS,
            "now",
            "right now",
        )

        if any(
            tail == marker
            or tail.startswith(marker + " ")
            for marker in temporal_starts
        ):
            continue

        for marker in (
            " today",
            " tomorrow",
            " tonight",
            " yesterday",
            " next week",
        ):
            if tail.endswith(marker):
                tail = tail[:-len(marker)].strip()

        return tail or None

    return None


# =========================================================
# KUMA KNOWLEDGE-1C — CONSERVATIVE PUBLIC-WEB SEMANTICS
# =========================================================
#
# Freshness words such as "today" and "current" are not, by
# themselves, proof that public internet evidence is needed.
# Keep action requests and personal/advice requests out of the
# PUBLIC_WEB domain. The resolver grants no execution authority.
# =========================================================

_ACTION_PREFIXES = (
    "open ",
    "launch ",
    "start ",
    "run ",
    "delete ",
    "remove ",
    "type ",
    "click ",
    "press ",
    "scroll ",
    "move ",
    "create ",
    "write ",
    "edit ",
    "send ",
    "message ",
    "email ",
)

_PERSONAL_ADVICE_TERMS = (
    "what do you think i should",
    "what do you think i need",
    "what should i focus",
    "what should i work on",
    "what should i prioritize",
    "what would you focus",
    "what would you recommend i",
    "what do you recommend i",
    "help me decide what i should",
    "give me advice on what i should",
)

_EXPLICIT_WEB_TERMS = (
    "search the web",
    "search online",
    "look it up",
    "look up ",
    "check online",
    "on the web",
    "internet",
)

_PUBLIC_FACT_TERMS = (
    "news",
    "score",
    "price",
    "stock",
    "market",
    "election",
    "release",
    "version",
    "crypto",
    "cryptocurrency",
    "bitcoin",
    "exchange rate",
    "rate",
    "status",
    "result",
    "results",
    "standings",
    "schedule",
    "outage",
    "value",
)

_FRESHNESS_TERMS = (
    "latest",
    "current",
    "today",
    "right now",
    "recent",
    "live",
    "newest",
)


def _is_public_web_request(
    text: str,
) -> bool:
    """
    Conservative semantic gate for public/live internet knowledge.

    This function plans evidence needs only. It never performs network
    access, chooses an action tool, or grants authority.
    """

    normalized = str(
        text
        or ""
    ).strip().lower()

    if not normalized:
        return False

    if normalized.startswith(
        _ACTION_PREFIXES
    ):
        return False

    if any(
        marker in normalized
        for marker in _PERSONAL_ADVICE_TERMS
    ):
        return False

    if any(
        marker in normalized
        for marker in _EXPLICIT_WEB_TERMS
    ):
        return True

    has_public_fact_topic = any(
        marker in normalized
        for marker in _PUBLIC_FACT_TERMS
    )

    if not has_public_fact_topic:
        return False

    has_freshness = any(
        marker in normalized
        for marker in _FRESHNESS_TERMS
    )

    # Certain public-fact nouns (news, price, score, market, status,
    # outage, standings) are inherently time-sensitive in ordinary
    # user queries. Others still need a freshness qualifier.
    inherently_live = any(
        marker in normalized
        for marker in (
            "news",
            "price",
            "score",
            "market",
            "status",
            "outage",
            "standings",
            "exchange rate",
        )
    )

    return (
        has_freshness
        or inherently_live
    )


# =========================================================
# KUMA MEMORY-1G — CONSERVATIVE MEMORY KNOWLEDGE SEMANTICS
# =========================================================
#
# This layer decides only whether a request is asking to READ
# already-authorized long-term memory as knowledge.
#
# It does NOT:
# - retrieve memory
# - mutate memory
# - authorize remember/forget
# - authorize an action that happens to depend on memory
# =========================================================

_MEMORY_MUTATION_PREFIXES = (
    "remember ",
    "remember that ",
    "remember this",
    "save this",
    "save that",
    "keep in mind",
    "don't forget",
    "do not forget",
    "forget ",
    "remove from memory",
    "delete from memory",
)

_MEMORY_READ_PREFIXES = (
    "what do you remember",
    "what did i tell you",
    "what have i told you",
    "do you remember",
    "recall ",
    "remember what",
    "what do you know about me",
    "what do you know about my ",
)


def _is_memory_read_request(
    text: str,
) -> bool:
    """Conservatively recognize zero-authority memory read intent."""

    normalized = str(
        text
        or ""
    ).strip().lower()

    if not normalized:
        return False

    if normalized.startswith(
        _ACTION_PREFIXES
    ):
        return False

    if normalized.startswith(
        _MEMORY_MUTATION_PREFIXES
    ):
        return False

    if normalized.startswith(
        _MEMORY_READ_PREFIXES
    ):
        return True

    if re.match(
        r"^(what is|what's|whats) my "
        r"(preferred|favorite|favourite)\b",
        normalized,
    ):
        return True

    if re.match(
        r"^(what|which)\s+.+\s+do i prefer[?.!]*$",
        normalized,
    ):
        return True

    if re.match(
        r"^what project(?:s)? am i working on[?.!]*$",
        normalized,
    ):
        return True

    return False


class KnowledgeResolver:
    """
    Unified read-only knowledge intent/planning layer.

    KNOWLEDGE-1A performs no network requests, invokes no tools, reads no
    device sensors, and mutates no user state.
    """

    def classify(self, request) -> KnowledgeIntent:
        text = _normalized(request)

        if not text:
            return KnowledgeIntent(
                domain=KnowledgeDomain.UNKNOWN,
                temporal_scope=TemporalScope.UNSPECIFIED,
                location_scope=LocationScope.NONE,
                query="",
                confidence=0.0,
            )

        if _contains_term(text, _WEATHER_TERMS):
            return self._weather_intent(text)

        if _is_memory_read_request(text):
            return KnowledgeIntent(
                domain=KnowledgeDomain.MEMORY,
                temporal_scope=TemporalScope.UNSPECIFIED,
                location_scope=LocationScope.NONE,
                query=text,
                confidence=0.90,
            )

        if _is_public_web_request(text):
            return KnowledgeIntent(
                domain=KnowledgeDomain.PUBLIC_WEB,
                temporal_scope=TemporalScope.UNSPECIFIED,
                location_scope=LocationScope.NONE,
                query=text,
                confidence=0.65,
            )

        return KnowledgeIntent(
            domain=KnowledgeDomain.UNKNOWN,
            temporal_scope=TemporalScope.UNSPECIFIED,
            location_scope=LocationScope.NONE,
            query=text,
            confidence=0.35,
        )

    def plan(self, request) -> KnowledgePlan:
        intent = self.classify(request)

        if intent.domain == KnowledgeDomain.WEATHER:
            return self._weather_plan(intent)

        if intent.domain == KnowledgeDomain.MEMORY:
            return KnowledgePlan(
                intent=intent,
                provider_order=("memory",),
            )

        if intent.domain == KnowledgeDomain.PUBLIC_WEB:
            return KnowledgePlan(
                intent=intent,
                provider_order=("web",),
            )

        return KnowledgePlan(
            intent=intent,
            provider_order=(),
        )

    def _weather_intent(
        self,
        text: str,
    ) -> KnowledgeIntent:
        explicit_place = _extract_weather_place(text)

        if _contains_term(text, _HISTORICAL_TERMS):
            temporal = TemporalScope.HISTORICAL
        elif _contains_term(text, _TOMORROW_TERMS):
            temporal = TemporalScope.TOMORROW
        elif _contains_term(text, _TODAY_TERMS):
            temporal = TemporalScope.TODAY
        elif _contains_term(text, _FUTURE_TERMS):
            temporal = TemporalScope.FUTURE
        else:
            temporal = TemporalScope.NOW

        location_scope = (
            LocationScope.EXPLICIT_PLACE
            if explicit_place
            else LocationScope.CURRENT_DEVICE
        )

        return KnowledgeIntent(
            domain=KnowledgeDomain.WEATHER,
            temporal_scope=temporal,
            location_scope=location_scope,
            query=text,
            explicit_place=explicit_place,
            confidence=0.95,
        )

    @staticmethod
    def _weather_plan(
        intent: KnowledgeIntent,
    ) -> KnowledgePlan:
        requires_location = (
            intent.location_scope == LocationScope.CURRENT_DEVICE
        )

        if intent.temporal_scope == TemporalScope.NOW:
            providers = (
                "weather.current",
                "web",
            )
        elif intent.temporal_scope in {
            TemporalScope.TODAY,
            TemporalScope.TOMORROW,
        }:
            providers = (
                "weather.forecast",
                "web",
            )
        elif intent.temporal_scope == TemporalScope.HISTORICAL:
            providers = (
                "weather.archive",
                "web",
            )
        elif intent.temporal_scope == TemporalScope.FUTURE:
            providers = (
                "weather.forecast",
                "web",
            )
        else:
            providers = ("web",)

        return KnowledgePlan(
            intent=intent,
            provider_order=providers,
            requires_device_location=requires_location,
        )
