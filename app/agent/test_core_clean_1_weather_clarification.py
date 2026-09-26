from __future__ import annotations

import time
from app.agent.kuma_agent import KumaAgent


def _agent():
    agent = KumaAgent.__new__(KumaAgent)
    def web_search(**kwargs):
        return kwargs

    agent.tool_registry = {"web_search": web_search}
    agent._successful_actions = {}
    agent._pending_weather_location = False
    agent._pending_weather_location_started_at = 0.0
    agent._pending_grounded_web_query = ""
    return agent


def _user(text):
    return [{"role": "user", "content": text}]


def test_weather_location_continuation_accepts_normal_city():
    assert KumaAgent._extract_weather_location_continuation(
        "Bengaluru, Karnataka"
    ) == "Bengaluru, Karnataka"


def test_weather_location_continuation_rejects_topic_change():
    assert KumaAgent._extract_weather_location_continuation(
        "actually tell me a joke"
    ) is None


def test_weather_location_continuation_rejects_secret_like_text():
    assert KumaAgent._extract_weather_location_continuation(
        "api key sk-example-secret-value"
    ) is None


def test_pending_weather_topic_change_does_not_expose_web_search():
    agent = _agent()
    agent._pending_weather_location = True
    agent._pending_weather_location_started_at = time.monotonic()

    tools = agent.get_available_tools(_user("tell me a joke"))

    assert tools == []
    assert agent._pending_weather_location is False
    assert agent._pending_grounded_web_query == ""


def test_pending_weather_valid_city_exposes_only_web_search():
    agent = _agent()
    agent._pending_weather_location = True
    agent._pending_weather_location_started_at = time.monotonic()

    tools = agent.get_available_tools(_user("Bengaluru"))
    assert tools == [agent.tool_registry["web_search"]]


def test_expired_weather_clarification_cannot_trigger_search():
    agent = _agent()
    agent._pending_weather_location = True
    agent._pending_weather_location_started_at = time.monotonic() - 600.0

    tools = agent.get_available_tools(_user("Bengaluru"))

    assert tools == []
    assert agent._pending_weather_location is False


def test_pending_weather_city_builds_exact_direct_query_and_one_shot_token():
    agent = _agent()
    agent._pending_weather_location = True
    agent._pending_weather_location_started_at = time.monotonic()

    response = agent.ask_model(_user("Bengaluru"))

    call = response.message.tool_calls[0]
    assert call.function.name == "web_search"
    assert call.function.arguments == {
        "query": "weather in Bengaluru",
        "max_results": 5,
    }
    assert agent._pending_weather_location is False
    assert agent._pending_grounded_web_query == "weather in Bengaluru"

    assert agent._consume_grounded_web_continuation(
        "Bengaluru",
        "web_search",
        call.function.arguments,
    ) is True
    assert agent._pending_grounded_web_query == ""
