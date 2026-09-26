from __future__ import annotations

from app.agent.kuma_agent import KumaAgent


def _agent():
    return KumaAgent.__new__(
        KumaAgent
    )


def test_locate_us_is_live_location_intent():
    agent = _agent()
    assert agent._request_needs_live_location(
        "locate us"
    ) is True


def test_our_location_rn_is_live_location_intent():
    agent = _agent()
    assert agent._request_needs_live_location(
        "what is our location rn"
    ) is True


def test_where_are_we_is_live_location_intent():
    agent = _agent()
    assert agent._request_needs_live_location(
        "where are we"
    ) is True


def test_my_current_location_is_live_location_intent():
    agent = _agent()
    assert agent._request_needs_live_location(
        "what's my current location"
    ) is True


def test_locationless_weather_still_needs_live_location():
    agent = _agent()
    assert agent._request_needs_live_location(
        "hows the weather"
    ) is True


def test_location_disclosure_action_is_not_auto_location_read():
    agent = _agent()

    assert agent._request_needs_live_location(
        "send my location to Alex"
    ) is False

    assert agent._request_needs_live_location(
        "share our location"
    ) is False


def test_unrelated_locate_request_is_not_location_read():
    agent = _agent()

    assert agent._request_needs_live_location(
        "locate the file on my desktop"
    ) is False
