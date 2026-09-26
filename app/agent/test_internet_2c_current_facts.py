from __future__ import annotations

from app.agent.kuma_agent import KumaAgent


def test_weather_requires_current_information():
    assert (
        KumaAgent._requires_current_information(
            "hows the weather"
        )
        is True
    )


def test_latest_news_requires_current_information():
    assert (
        KumaAgent._requires_current_information(
            "latest OpenAI news"
        )
        is True
    )


def test_crypto_requires_current_information():
    assert (
        KumaAgent._requires_current_information(
            "whats today crypto currency value"
        )
        is True
    )


def test_timeless_conversation_does_not_require_web():
    assert (
        KumaAgent._requires_current_information(
            "tell me a joke"
        )
        is False
    )


def test_locationless_weather_is_detected():
    assert (
        KumaAgent._is_locationless_weather_request(
            "hows the weather"
        )
        is True
    )

    assert (
        KumaAgent._is_locationless_weather_request(
            "weather in Bengaluru"
        )
        is False
    )


def test_synthetic_web_response_matches_reasoning_contract():
    response = (
        KumaAgent._synthetic_model_response(
            tool_name="web_search",
            arguments={
                "query": "latest OpenAI news",
                "max_results": 5,
            },
        )
    )

    assert response.message.content == ""
    assert len(
        response.message.tool_calls
    ) == 1

    call = (
        response.message.tool_calls[
            0
        ]
    )

    assert (
        call.function.name
        == "web_search"
    )

    assert (
        call.function.arguments[
            "query"
        ]
        == "latest OpenAI news"
    )


def test_synthetic_clarification_has_no_tool_authority():
    response = (
        KumaAgent._synthetic_model_response(
            content=(
                "Which city should I check "
                "the weather for?"
            )
        )
    )

    assert (
        response.message.tool_calls
        == []
    )
