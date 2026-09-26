from __future__ import annotations

from app.agent.kuma_agent import KumaAgent
from app.tools import location_tools


def _agent():
    return KumaAgent.__new__(
        KumaAgent
    )


def test_unified_location_detail_resolution():
    agent = _agent()

    assert (
        agent._location_detail_for_request(
            "locate us"
        )
        == "approximate"
    )

    assert (
        agent._location_detail_for_request(
            "hows the weather"
        )
        == "approximate"
    )

    assert (
        agent._location_detail_for_request(
            "give me our address of the location"
        )
        == "address"
    )


def test_location_actions_are_not_read_intents():
    agent = _agent()

    assert (
        agent._location_detail_for_request(
            "send our location to Alex"
        )
        is None
    )

    assert (
        agent._location_detail_for_request(
            "fill our current address in the form"
        )
        is None
    )

    assert (
        agent._location_detail_for_request(
            "order this to my current address"
        )
        is None
    )


def test_approximate_mode_preserves_existing_sensor(
    monkeypatch,
):
    sentinel = object()

    monkeypatch.setattr(
        location_tools,
        "_get_current_location_approximate",
        lambda: sentinel,
    )

    assert (
        location_tools.get_current_location(
            detail="approximate"
        )
        is sentinel
    )


def test_address_mode_returns_sensitive_read_only_candidate(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv(
        "KUMA_LOCATION_CONFIG_DIR",
        str(
            tmp_path
        ),
    )

    location_tools.set_live_location_enabled(
        True
    )

    monkeypatch.setattr(
        location_tools,
        "_run_native_helper",
        lambda: {
            "ok": True,
            "latitude": 13.0735,
            "longitude": 77.6699,
            "horizontal_accuracy_m": 35.0,
            "timestamp": "2026-09-10T19:18:53Z",
            "authorization": "authorized",
            "street_number": "42",
            "street": "Example Road",
            "sub_locality": "Example Layout",
            "locality": "Bengaluru",
            "administrative_area": "Karnataka",
            "postal_code": "560001",
            "country": "India",
            "iso_country_code": "IN",
        },
    )

    result = (
        location_tools.get_current_location(
            detail="address"
        )
    )

    assert result.success is True

    text = str(
        result.result
    )

    assert "DETAIL: address" in text

    assert (
        "ADDRESS_CANDIDATE: "
        "42 Example Road, Example Layout, Bengaluru, "
        "Karnataka 560001, India"
        in text
    )

    assert "AUTHORITY: NONE" in text
    assert "DELIVERY_READY: false" in text
    assert "ADDRESS_HISTORY_PERSISTED: false" in text


def test_bad_detail_fails_closed():
    result = (
        location_tools.get_current_location(
            detail="street_exact_secret_mode"
        )
    )

    assert result.success is False


def test_grounding_requires_matching_location_precision(
    monkeypatch,
):
    agent = _agent()

    monkeypatch.setattr(
        "app.agent.kuma_agent.live_location_enabled",
        lambda: True,
    )

    assert (
        agent.explicitly_requests_tool_action(
            "give me our address of the location",
            "get_current_location",
            {
                "detail": "address",
            },
        )
        is True
    )

    assert (
        agent.explicitly_requests_tool_action(
            "give me our address of the location",
            "get_current_location",
            {
                "detail": "approximate",
            },
        )
        is False
    )

    assert (
        agent.explicitly_requests_tool_action(
            "hows the weather",
            "get_current_location",
            {
                "detail": "approximate",
            },
        )
        is True
    )

    assert (
        agent.explicitly_requests_tool_action(
            "hows the weather",
            "get_current_location",
            {
                "detail": "address",
            },
        )
        is False
    )
