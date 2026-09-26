from __future__ import annotations
from pathlib import Path
import app.agent.kuma_agent as kuma_agent_module
from app.agent.capability_registry import create_default_capability_registry
from app.agent.kuma_agent import KumaAgent
from app.agent.permissions import PermissionLevel, get_permission_level
import app.agent.kuma_runtime as kuma_runtime_module


def _agent():
    agent = KumaAgent.__new__(KumaAgent)
    agent.tool_registry = {
        "get_current_location": lambda: None,
        "web_search": lambda **kwargs: kwargs,
    }
    agent._successful_actions = {}
    agent._pending_live_location_web_query = ""
    return agent


def test_location_permission_is_user_authorized():
    assert get_permission_level("get_current_location") == PermissionLevel.USER_AUTHORIZED


def test_live_location_capability_is_registered():
    capability = create_default_capability_registry().get("live_location")
    assert capability is not None
    assert capability.tools == ("get_current_location",)


def test_runtime_registers_location_tool():
    source = Path(kuma_runtime_module.__file__).read_text()
    assert '"get_current_location"' in source


def test_locationless_weather_prefers_live_location(monkeypatch):
    agent = _agent()
    monkeypatch.setattr(kuma_agent_module, "live_location_enabled", lambda: True)
    tools = agent.get_available_tools([{"role": "user", "content": "hows the weather"}])
    assert tools == [agent.tool_registry["get_current_location"]]


def test_explicit_city_weather_does_not_use_device_location(monkeypatch):
    agent = _agent()
    monkeypatch.setattr(kuma_agent_module, "live_location_enabled", lambda: True)
    tools = agent.get_available_tools([{"role": "user", "content": "hows the weather in Bengaluru"}])
    assert tools == [agent.tool_registry["web_search"]]


def test_weather_grounds_location_only_when_enabled(monkeypatch):
    agent = _agent()
    monkeypatch.setattr(kuma_agent_module, "live_location_enabled", lambda: True)
    assert agent.explicitly_requests_tool_action("hows the weather", "get_current_location", {}) is True
    monkeypatch.setattr(kuma_agent_module, "live_location_enabled", lambda: False)
    assert agent.explicitly_requests_tool_action("hows the weather", "get_current_location", {}) is False


def test_location_evidence_builds_weather_query():
    query = KumaAgent._weather_query_from_location_evidence(
        "KUMA_LOCAL_LOCATION_EVIDENCE\nWEATHER_LOCATION: Bengaluru, Karnataka, India\nAUTHORITY: NONE\n"
    )
    assert query == "current weather Bengaluru, Karnataka, India"


def test_location_evidence_falls_back_to_approx_coordinates():
    query = KumaAgent._weather_query_from_location_evidence(
        "KUMA_LOCAL_LOCATION_EVIDENCE\nWEATHER_LOCATION: \nLATITUDE_APPROX: 12.97\nLONGITUDE_APPROX: 77.59\n"
    )
    assert query == "current weather near 12.97, 77.59"
