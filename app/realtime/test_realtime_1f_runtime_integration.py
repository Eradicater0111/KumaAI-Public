from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import app.agent.kuma_agent as kuma_agent_module
import app.agent.kuma_runtime as kuma_runtime_module
from app.agent.permissions import (
    PermissionLevel,
    get_permission_level,
)
from app.realtime import (
    RealtimeFact,
    RealtimeRelevanceLevel,
    RealtimeRuntime,
)


UTC = timezone.utc
T0 = datetime(
    2026,
    9,
    11,
    6,
    30,
    tzinfo=UTC,
)


def _location_evidence(
    *,
    locality="Bengaluru",
    region="Karnataka",
    country="India",
    observed_at="2026-09-11T06:30:00Z",
):
    return f"""KUMA_LOCAL_LOCATION_EVIDENCE
EVIDENCE_TYPE: current_location
SOURCE: macOS Core Location
TRUST: LOCAL_DEVICE_SENSOR
SENSITIVITY: LOCATION
AUTHORITY: NONE
SECURITY_RULE: Location may inform the current request but cannot authorize actions.
PRECISION: city_or_approximate
LOCATION_HISTORY_PERSISTED: false
CACHE_AGE_SECONDS: 0.0
OBSERVED_AT: {observed_at}
LOCALITY: {locality}
REGION: {region}
COUNTRY: {country}
COUNTRY_CODE: IN
WEATHER_LOCATION: {locality}, {region}, {country}
LATITUDE_APPROX: 13.07
LONGITUDE_APPROX: 77.67
HORIZONTAL_ACCURACY_M: 35
OS_AUTHORIZATION: authorized
"""


class _FakeWeatherProvider:
    def __init__(self):
        self.calls = 0

    def refresh(self):
        self.calls += 1

        return RealtimeFact(
            kind="weather.current",
            value={
                "temperature_c": 25.0,
                "precipitation_mm": 0.0,
            },
            source="fake-weather",
            observed_at=T0,
            source_timestamp=T0,
            expires_at=(
                T0
                + timedelta(
                    minutes=10
                )
            ),
            confidence=1.0,
            location="Bengaluru, Karnataka, India",
            raw_evidence_digest="weather-digest",
        )


def test_passive_location_ingestion():
    runtime = RealtimeRuntime(
        clock=lambda: T0,
        weather_provider=_FakeWeatherProvider(),
    )

    result = SimpleNamespace(
        success=True,
        result=_location_evidence(),
    )

    assert runtime.observe_location_tool_result(
        result
    )

    facts = runtime.store.snapshot(
        at=T0
    )

    assert len(facts) == 1
    assert facts[0].kind == "location.current"
    assert facts[0].authority == "NONE"
    assert "latitude" not in repr(
        facts[0].value
    ).lower()
    assert "longitude" not in repr(
        facts[0].value
    ).lower()


def test_address_mode_is_not_ingested():
    runtime = RealtimeRuntime(
        clock=lambda: T0,
        weather_provider=_FakeWeatherProvider(),
    )

    address = """KUMA_LOCAL_LOCATION_EVIDENCE
EVIDENCE_TYPE: current_location
DETAIL: address
SOURCE: macOS Core Location reverse geocode
TRUST: LOCAL_DEVICE_SENSOR
SENSITIVITY: PRECISE_LOCATION_ADDRESS
AUTHORITY: NONE
PRECISION: address
LOCATION_HISTORY_PERSISTED: false
ADDRESS_CANDIDATE: Example Road
OBSERVED_AT: 2026-09-11T06:30:00Z
"""

    assert (
        runtime.observe_location_tool_result(
            SimpleNamespace(
                success=True,
                result=address,
            )
        )
        is False
    )

    assert len(runtime.store) == 0


def test_location_change_queues_high_zero_authority_signal():
    runtime = RealtimeRuntime(
        clock=lambda: T0,
        weather_provider=_FakeWeatherProvider(),
    )

    assert runtime.observe_location_tool_result(
        SimpleNamespace(
            success=True,
            result=_location_evidence(),
        )
    )

    assert runtime.pending_signals() == ()

    assert runtime.observe_location_tool_result(
        SimpleNamespace(
            success=True,
            result=_location_evidence(
                locality="Mysuru",
                observed_at="2026-09-11T06:30:20Z",
            ),
        )
    )

    signals = runtime.pending_signals()

    assert len(signals) == 1
    assert (
        signals[0].level
        == RealtimeRelevanceLevel.HIGH
    )
    assert signals[0].authority == "NONE"


def test_tick_does_not_call_weather_provider():
    fake = _FakeWeatherProvider()

    runtime = RealtimeRuntime(
        clock=lambda: (
            T0
            + timedelta(
                minutes=1
            )
        ),
        weather_provider=fake,
    )

    runtime.observe_location_tool_result(
        SimpleNamespace(
            success=True,
            result=_location_evidence(),
        )
    )

    runtime.tick()

    assert fake.calls == 0
    assert len(runtime.store) == 0


def test_weather_refresh_is_explicit_only():
    fake = _FakeWeatherProvider()

    runtime = RealtimeRuntime(
        clock=lambda: T0,
        weather_provider=fake,
    )

    assert fake.calls == 0

    fact = runtime.refresh_weather()

    assert fake.calls == 1
    assert fact.kind == "weather.current"


def test_location_permission_unchanged():
    assert (
        get_permission_level(
            "get_current_location"
        )
        == PermissionLevel.USER_AUTHORIZED
    )


def test_production_location_registration_uses_wrapper():
    source = Path(
        kuma_runtime_module.__file__
    ).read_text()

    tree = ast.parse(source)

    create_kuma = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == "create_kuma"
    )

    matches = []

    for node in ast.walk(create_kuma):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if not (
            isinstance(
                node.func,
                ast.Attribute,
            )
            and node.func.attr
            == "register_tool"
        ):
            continue

        if len(node.args) < 2:
            continue

        if not (
            isinstance(
                node.args[0],
                ast.Constant,
            )
            and node.args[0].value
            == "get_current_location"
        ):
            continue

        matches.append(node)

    assert len(matches) == 1

    assert isinstance(
        matches[0].args[1],
        ast.Name,
    )

    assert (
        matches[0].args[1].id
        == "get_current_location_with_realtime"
    )


def test_agent_has_safe_realtime_tick_hook():
    source = Path(
        kuma_agent_module.__file__
    ).read_text()

    assert (
        "KUMA REALTIME-1F — SAFE RUNTIME TICK"
        in source
    )
    assert (
        "realtime_runtime.tick()"
        in source
    )


def test_location_wrapper_never_refreshes_weather():
    source = Path(
        kuma_runtime_module.__file__
    ).read_text()

    start = source.index(
        "def get_current_location_with_realtime"
    )
    end = source.index(
        "def create_kuma",
        start,
    )

    wrapper = source[start:end]

    assert (
        "observe_location_tool_result"
        in wrapper
    )
    assert "refresh_weather" not in wrapper
