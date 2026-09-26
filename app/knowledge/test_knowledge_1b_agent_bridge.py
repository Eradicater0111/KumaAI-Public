from __future__ import annotations

from pathlib import Path

import app.agent.kuma_agent as kuma_agent_module
from app.agent.kuma_agent import KumaAgent
from app.knowledge import (
    KnowledgeDomain,
    KnowledgeResolver,
    LocationScope,
    TemporalScope,
)


def _agent():
    return KumaAgent.__new__(KumaAgent)


def test_agent_uses_unified_location_semantics():
    agent = _agent()

    assert agent._weather_request_needs_device_location(
        "weather near me tomorrow"
    ) is True

    assert agent._kuma_weather_request_has_explicit_place(
        "weather near me tomorrow"
    ) is False

    assert agent._weather_request_needs_device_location(
        "weather in Bengaluru tomorrow"
    ) is False

    assert agent._kuma_weather_request_has_explicit_place(
        "weather in Bengaluru tomorrow"
    ) is True


def test_agent_uses_unified_temporal_semantics():
    agent = _agent()

    assert agent._kuma_weather_period_for_request(
        "what's the weather"
    ) == "current"

    assert agent._kuma_weather_period_for_request(
        "todays weather"
    ) == "today"

    assert agent._kuma_weather_period_for_request(
        "give tmrs weather report"
    ) == "tomorrow"

    assert agent._kuma_weather_period_for_request(
        "yesterdays weather report"
    ) == "historical"

    assert agent._kuma_weather_period_for_request(
        "weather next week"
    ) == "future"


def test_historical_weather_plan_never_collapses_to_current():
    plan = KnowledgeResolver().plan(
        "yesterdays weather report"
    )

    assert plan.intent.domain == KnowledgeDomain.WEATHER
    assert plan.intent.temporal_scope == TemporalScope.HISTORICAL
    assert plan.intent.location_scope == LocationScope.CURRENT_DEVICE
    assert plan.provider_order == (
        "weather.archive",
        "web",
    )
    assert "weather.current" not in plan.provider_order


def test_agent_contains_grounded_historical_future_fallback():
    source = Path(
        kuma_agent_module.__file__
    ).read_text()

    assert "KUMA KNOWLEDGE-1B — UNIFIED WEATHER BRIDGE" in source
    assert "grounded_location = weather_query" in source
    assert '"historical",' in source
    assert '"future",' in source
    assert "self._pending_live_location_web_query = weather_query" in source


def test_knowledge_bridge_does_not_add_model_tool_registration():
    source = Path(
        kuma_agent_module.__file__
    ).read_text()

    assert "from app.knowledge import (" in source
    assert "KnowledgeResolver" in source

    import_segment = source[
        source.index("from app.knowledge import ("):
        source.index("class KumaAgent")
    ]

    assert "register_tool(" not in import_segment
