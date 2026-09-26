from __future__ import annotations

from pathlib import Path

from app.agent.kuma_agent import KumaAgent
import app.agent.kuma_agent as kuma_agent_module


def _agent():
    return KumaAgent.__new__(KumaAgent)


def test_explicit_location_weather_request_grounds_web_search():
    agent = _agent()

    assert agent.explicitly_requests_tool_action(
        "hows the weather in Bengaluru",
        "web_search",
        {
            "query": "hows the weather in Bengaluru",
            "max_results": 5,
        },
    ) is True


def test_forecast_request_grounds_web_search():
    agent = _agent()

    assert agent.explicitly_requests_tool_action(
        "forecast for Bengaluru tomorrow",
        "web_search",
        {
            "query": "forecast for Bengaluru tomorrow",
            "max_results": 5,
        },
    ) is True


def test_current_crypto_request_still_grounds_web_search():
    agent = _agent()

    assert agent.explicitly_requests_tool_action(
        "whats today crypto currency value",
        "web_search",
        {
            "query": "whats today crypto currency value",
            "max_results": 5,
        },
    ) is True


def test_casual_request_does_not_ground_web_search():
    agent = _agent()

    assert agent.explicitly_requests_tool_action(
        "tell me a joke",
        "web_search",
        {
            "query": "tell me a joke",
            "max_results": 5,
        },
    ) is False


def test_local_current_request_does_not_auto_ground_web_search():
    agent = _agent()

    assert agent.explicitly_requests_tool_action(
        "what is the current version of my local file",
        "web_search",
        {
            "query": "what is the current version of my local file",
            "max_results": 5,
        },
    ) is False


def test_planner_uses_resolved_task_goal_source_contract():
    source = Path(kuma_agent_module.__file__).read_text()

    assert "planning_goal = (" in source
    assert "goal=planning_goal" in source
