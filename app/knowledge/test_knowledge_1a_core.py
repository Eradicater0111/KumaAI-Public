from __future__ import annotations

import inspect

import pytest

from app.knowledge import (
    KnowledgeDomain,
    KnowledgeIntent,
    KnowledgeResolver,
    LocationScope,
    TemporalScope,
)


def test_today_weather_is_current_device_forecast():
    plan = KnowledgeResolver().plan(
        "hows today weather"
    )

    assert plan.intent.domain == KnowledgeDomain.WEATHER
    assert plan.intent.temporal_scope == TemporalScope.TODAY
    assert plan.intent.location_scope == LocationScope.CURRENT_DEVICE
    assert plan.requires_device_location is True
    assert plan.provider_order == (
        "weather.forecast",
        "web",
    )
    assert plan.authority == "NONE"


def test_tomorrow_alias_is_not_current_weather():
    plan = KnowledgeResolver().plan(
        "give tmrs weather report"
    )

    assert plan.intent.temporal_scope == TemporalScope.TOMORROW
    assert plan.provider_order[0] == "weather.forecast"


def test_yesterday_is_historical_and_never_degrades_to_current():
    plan = KnowledgeResolver().plan(
        "yesterdays weather report"
    )

    assert plan.intent.temporal_scope == TemporalScope.HISTORICAL
    assert plan.provider_order == (
        "weather.archive",
        "web",
    )
    assert "weather.current" not in plan.provider_order


def test_explicit_weather_place_does_not_require_device_location():
    plan = KnowledgeResolver().plan(
        "weather in Bengaluru tomorrow"
    )

    assert plan.intent.location_scope == LocationScope.EXPLICIT_PLACE
    assert plan.intent.explicit_place == "bengaluru"
    assert plan.requires_device_location is False
    assert plan.intent.temporal_scope == TemporalScope.TOMORROW


def test_relative_weather_place_requires_device_location():
    plan = KnowledgeResolver().plan(
        "weather near me tomorrow"
    )

    assert plan.intent.location_scope == LocationScope.CURRENT_DEVICE
    assert plan.requires_device_location is True


def test_current_weather_uses_current_provider_before_web():
    plan = KnowledgeResolver().plan(
        "what's the weather"
    )

    assert plan.intent.temporal_scope == TemporalScope.NOW
    assert plan.provider_order == (
        "weather.current",
        "web",
    )


def test_general_current_knowledge_can_plan_web():
    plan = KnowledgeResolver().plan(
        "latest python release"
    )

    assert plan.intent.domain == KnowledgeDomain.PUBLIC_WEB
    assert plan.provider_order == ("web",)
    assert plan.requires_device_location is False


def test_unknown_conversation_does_not_force_a_provider():
    plan = KnowledgeResolver().plan(
        "bro what do you think about this idea"
    )

    assert plan.intent.domain == KnowledgeDomain.UNKNOWN
    assert plan.provider_order == ()


def test_knowledge_intent_authority_is_permanently_none():
    with pytest.raises(
        ValueError,
        match="permanently NONE",
    ):
        KnowledgeIntent(
            domain=KnowledgeDomain.WEATHER,
            temporal_scope=TemporalScope.NOW,
            location_scope=LocationScope.CURRENT_DEVICE,
            query="weather",
            authority="SAFE",
        )


def test_resolver_is_internal_planning_not_model_tool_surface():
    from app.knowledge import resolver

    source = inspect.getsource(resolver)

    assert "register_tool(" not in source
    assert "execute_command" not in source
    assert "pyautogui" not in source
