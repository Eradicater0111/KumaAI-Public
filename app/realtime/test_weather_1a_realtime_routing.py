from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import app.agent.kuma_agent as kuma_agent_module
from app.realtime import RealtimeFact
from app.realtime.weather_render import (
    format_current_weather,
    weather_code_description,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)


def _fact(value=None):
    return RealtimeFact(
        kind="weather.current",
        value=value or {
            "temperature_c": 24.8,
            "apparent_temperature_c": 25.4,
            "relative_humidity_percent": 73,
            "precipitation_mm": 0.0,
            "weather_code": 2,
            "wind_speed_kmh": 11.4,
        },
        source="Open-Meteo",
        source_timestamp=NOW,
        observed_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        confidence=0.9,
        location="Bengaluru, Karnataka, India",
        raw_evidence_digest="abc123",
    )


def test_weather_code_mapping():
    assert weather_code_description(0) == "clear"
    assert weather_code_description(2) == "partly cloudy"
    assert weather_code_description(95) == "thunderstorm"
    assert weather_code_description(12345) is None


def test_deterministic_weather_render():
    assert format_current_weather(_fact()) == (
        "Current weather in Bengaluru, Karnataka, India: "
        "24.8°C, feels like 25.4°C, partly cloudy, "
        "humidity 73%, wind 11.4 km/h, precipitation 0 mm."
    )


def test_renderer_omits_missing_fields():
    assert format_current_weather(
        _fact({
            "temperature_c": 21.0,
            "weather_code": 3,
        })
    ) == (
        "Current weather in Bengaluru, Karnataka, India: "
        "21°C, overcast."
    )


def test_renderer_rejects_non_weather_fact():
    fact = RealtimeFact(
        kind="system.test",
        value=True,
        source="test",
        observed_at=NOW,
        expires_at=None,
    )

    try:
        format_current_weather(fact)
    except ValueError as error:
        assert "weather.current" in str(error)
    else:
        raise AssertionError("non-weather fact should be rejected")


def test_agent_has_weather_1a_fast_completion():
    source = Path(kuma_agent_module.__file__).read_text()

    assert "KUMA WEATHER-1A — REALTIME CURRENT WEATHER" in source
    assert "realtime_runtime.refresh_weather()" in source
    assert "format_current_weather(" in source
    assert (
        "KUMA WEATHER → realtime "
        in source
    )

    assert (
        "+ weather_period"
        in source
    )

    assert (
        "+ \" weather resolved.\""
        in source
    )


def test_weather_1a_preserves_web_fallback():
    source = Path(kuma_agent_module.__file__).read_text()

    assert (
        "self._pending_live_location_web_query = weather_query"
        in source
    )
    assert (
        "KUMA WEATHER → realtime weather unavailable; "
        in source
    )

    assert (
        "preserving web fallback. "
        in source
    )
