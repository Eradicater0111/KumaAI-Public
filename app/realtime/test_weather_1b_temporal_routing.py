from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path

import app.agent.kuma_agent as kuma_agent_module
from app.agent.kuma_agent import KumaAgent
from app.realtime import (
    RealtimeFact,
    RealtimeFactStore,
)
from app.realtime.weather_provider import (
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_GEOCODING_URL,
    WEATHER_DAILY_FACT_KIND,
    OpenMeteoWeatherProvider,
)
from app.realtime.weather_render import (
    format_daily_weather,
)


UTC = timezone.utc
NOW = datetime(
    2026,
    9,
    11,
    7,
    30,
    tzinfo=UTC,
)


def _agent():
    return KumaAgent.__new__(
        KumaAgent
    )


def _location_fact():
    return RealtimeFact(
        kind="location.current",
        value={
            "locality": "Bengaluru",
            "region": "Karnataka",
            "country": "India",
            "precision": "city_or_approximate",
            "location_history_persisted": False,
        },
        source="macOS Core Location",
        source_timestamp=NOW,
        observed_at=NOW,
        expires_at=(
            NOW
            + timedelta(
                seconds=30
            )
        ),
        confidence=1.0,
        location="Bengaluru, Karnataka, India",
        raw_evidence_digest="location-digest",
    )


def _fetcher():
    calls = []

    def fetch(
        url,
        params,
    ):
        calls.append(
            (
                url,
                dict(
                    params
                ),
            )
        )

        if url == OPEN_METEO_GEOCODING_URL:
            return {
                "results": [
                    {
                        "latitude": 12.97,
                        "longitude": 77.59,
                    }
                ]
            }

        if url == OPEN_METEO_FORECAST_URL:
            return {
                "daily": {
                    "time": [
                        "2026-09-11",
                        "2026-09-12",
                    ],
                    "weather_code": [
                        2,
                        61,
                    ],
                    "temperature_2m_max": [
                        27.0,
                        26.0,
                    ],
                    "temperature_2m_min": [
                        19.0,
                        18.0,
                    ],
                    "apparent_temperature_max": [
                        28.0,
                        27.0,
                    ],
                    "apparent_temperature_min": [
                        19.0,
                        18.0,
                    ],
                    "precipitation_sum": [
                        0.0,
                        4.2,
                    ],
                    "precipitation_probability_max": [
                        20,
                        70,
                    ],
                    "wind_speed_10m_max": [
                        12.0,
                        18.0,
                    ],
                }
            }

        raise AssertionError(
            "unexpected endpoint"
        )

    return fetch, calls


def test_unanchored_today_weather_needs_device_location():
    agent = _agent()

    assert (
        agent._weather_request_needs_device_location(
            "hows today weather"
        )
        is True
    )


def test_unanchored_tomorrow_abbreviation_needs_device_location():
    agent = _agent()

    assert (
        agent._weather_request_needs_device_location(
            "give tmrs weather report"
        )
        is True
    )

    assert (
        agent._kuma_weather_period_for_request(
            "give tmrs weather report"
        )
        == "tomorrow"
    )


def test_explicit_city_weather_still_does_not_use_device_location():
    agent = _agent()

    assert (
        agent._weather_request_needs_device_location(
            "hows the weather in Bengaluru"
        )
        is False
    )

    assert (
        agent._weather_request_needs_device_location(
            "forecast for Mysuru tomorrow"
        )
        is False
    )


def test_relative_weather_location_still_uses_device_location():
    agent = _agent()

    assert (
        agent._weather_request_needs_device_location(
            "weather at my current location tomorrow"
        )
        is True
    )


def test_daily_provider_returns_tomorrow_fact_without_storing_coordinates():
    store = RealtimeFactStore()
    store.put(
        _location_fact()
    )

    fetch, calls = _fetcher()

    provider = OpenMeteoWeatherProvider(
        store=store,
        fetch_json=fetch,
        clock=lambda: NOW,
    )

    fact = provider.refresh_daily(
        period="tomorrow"
    )

    assert fact is not None
    assert fact.kind == WEATHER_DAILY_FACT_KIND
    assert fact.authority == "NONE"
    assert (
        fact.value["period"]
        == "tomorrow"
    )
    assert (
        fact.value["date"]
        == "2026-09-12"
    )
    assert (
        fact.value["temperature_max_c"]
        == 26.0
    )
    assert (
        fact.value[
            "precipitation_probability_max_percent"
        ]
        == 70
    )

    serialized = repr(
        fact
    )

    assert "12.97" not in serialized
    assert "77.59" not in serialized
    assert len(calls) == 2


def test_daily_renderer_is_deterministic():
    fact = RealtimeFact(
        kind=WEATHER_DAILY_FACT_KIND,
        value={
            "period": "tomorrow",
            "date": "2026-09-12",
            "weather_code": 61,
            "temperature_max_c": 26.0,
            "temperature_min_c": 18.0,
            "precipitation_sum_mm": 4.2,
            "precipitation_probability_max_percent": 70,
            "wind_speed_max_kmh": 18.0,
        },
        source="Open-Meteo",
        source_timestamp=NOW,
        observed_at=NOW,
        expires_at=(
            NOW
            + timedelta(
                minutes=10
            )
        ),
        confidence=0.9,
        location="Bengaluru, Karnataka, India",
        raw_evidence_digest="forecast-digest",
    )

    assert format_daily_weather(
        fact
    ) == (
        "Tomorrow (2026-09-12) in Bengaluru, Karnataka, India: "
        "light rain, high 26°C, low 18°C, rain chance up to 70%, "
        "precipitation 4.2 mm, max wind 18 km/h."
    )


def test_agent_weather_1b_fast_path_and_web_fallback_survive():
    source = Path(
        kuma_agent_module.__file__
    ).read_text()

    assert (
        "KUMA WEATHER-1B — LOCATION-AWARE TEMPORAL WEATHER"
        in source
    )

    assert (
        "refresh_weather_daily("
        in source
    )

    assert (
        "format_daily_weather("
        in source
    )

    assert (
        "self._pending_live_location_web_query = weather_query"
        in source
    )

    assert (
        "preserving web fallback. "
        in source
    )
