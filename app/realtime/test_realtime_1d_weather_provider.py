from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from app.realtime import (
    RealtimeFact,
    RealtimeFactStore,
)
from app.realtime.location_adapter import (
    LOCATION_FACT_KIND,
)
from app.realtime.weather_provider import (
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_GEOCODING_URL,
    WEATHER_FACT_KIND,
    OpenMeteoWeatherProvider,
)


UTC = timezone.utc
NOW = datetime(
    2026,
    9,
    11,
    5,
    30,
    tzinfo=UTC,
)


def _location_fact(
    *,
    observed_at=None,
    location="Bengaluru, Karnataka, India",
):
    observed_at = (
        observed_at
        or NOW
    )

    return RealtimeFact(
        kind=LOCATION_FACT_KIND,
        value={
            "locality": "Bengaluru",
            "region": "Karnataka",
            "country": "India",
            "precision": "city_or_approximate",
            "location_history_persisted": False,
        },
        source="macOS Core Location",
        source_timestamp=observed_at,
        observed_at=observed_at,
        expires_at=(
            observed_at
            + timedelta(
                seconds=30
            )
        ),
        confidence=1.0,
        location=location,
        raw_evidence_digest="loc123",
    )


def _fake_fetcher():
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
                        "name": "Bengaluru",
                        "latitude": 12.97,
                        "longitude": 77.59,
                        "country": "India",
                        "admin1": "Karnataka",
                    }
                ]
            }

        if url == OPEN_METEO_FORECAST_URL:
            return {
                "current": {
                    "time": 1789104600,
                    "temperature_2m": 24.8,
                    "apparent_temperature": 25.1,
                    "relative_humidity_2m": 73,
                    "precipitation": 0.0,
                    "weather_code": 2,
                    "cloud_cover": 48,
                    "wind_speed_10m": 11.4,
                    "wind_direction_10m": 245,
                    "is_day": 1,
                }
            }

        raise AssertionError(
            "unexpected endpoint"
        )

    return fetch, calls


def test_weather_provider_returns_none_without_location():
    store = RealtimeFactStore()
    fetch, calls = _fake_fetcher()

    provider = OpenMeteoWeatherProvider(
        store=store,
        fetch_json=fetch,
        clock=lambda: NOW,
    )

    assert provider.refresh() is None
    assert calls == []


def test_weather_provider_emits_zero_authority_fact():
    store = RealtimeFactStore()
    store.put(
        _location_fact()
    )

    fetch, _ = _fake_fetcher()

    provider = OpenMeteoWeatherProvider(
        store=store,
        fetch_json=fetch,
        clock=lambda: NOW,
    )

    fact = provider.refresh()

    assert fact is not None
    assert fact.kind == WEATHER_FACT_KIND
    assert fact.authority == "NONE"
    assert fact.source == "Open-Meteo"
    assert (
        fact.location
        == "Bengaluru, Karnataka, India"
    )


def test_weather_provider_maps_current_conditions():
    store = RealtimeFactStore()
    store.put(
        _location_fact()
    )

    fetch, _ = _fake_fetcher()

    fact = OpenMeteoWeatherProvider(
        store=store,
        fetch_json=fetch,
        clock=lambda: NOW,
    ).refresh()

    assert fact.value == {
        "temperature_c": 24.8,
        "apparent_temperature_c": 25.1,
        "relative_humidity_percent": 73,
        "precipitation_mm": 0.0,
        "weather_code": 2,
        "cloud_cover_percent": 48,
        "wind_speed_kmh": 11.4,
        "wind_direction_degrees": 245,
        "is_day": 1,
    }


def test_weather_provider_does_not_store_geocoded_coordinates():
    store = RealtimeFactStore()
    store.put(
        _location_fact()
    )

    fetch, calls = _fake_fetcher()

    fact = OpenMeteoWeatherProvider(
        store=store,
        fetch_json=fetch,
        clock=lambda: NOW,
    ).refresh()

    assert len(
        calls
    ) == 2

    assert calls[
        0
    ][0] == OPEN_METEO_GEOCODING_URL

    assert calls[
        1
    ][0] == OPEN_METEO_FORECAST_URL

    serialized = repr(
        fact
    )

    assert "12.97" not in serialized
    assert "77.59" not in serialized


def test_weather_provider_uses_freshest_unexpired_location():
    store = RealtimeFactStore()

    older = _location_fact(
        observed_at=(
            NOW
            - timedelta(
                seconds=20
            )
        ),
        location="Older City, Example",
    )

    newer = _location_fact(
        observed_at=(
            NOW
            - timedelta(
                seconds=5
            )
        ),
        location="Bengaluru, Karnataka, India",
    )

    store.put(
        older
    )
    store.put(
        newer
    )

    fetch, calls = _fake_fetcher()

    provider = OpenMeteoWeatherProvider(
        store=store,
        fetch_json=fetch,
        clock=lambda: NOW,
    )

    fact = provider.refresh()

    assert fact.location == newer.location
    assert (
        calls[0][1]["name"]
        == newer.location
    )


def test_weather_provider_ignores_expired_location():
    store = RealtimeFactStore()

    expired = _location_fact(
        observed_at=(
            NOW
            - timedelta(
                minutes=2
            )
        )
    )

    store.put(
        expired
    )

    fetch, calls = _fake_fetcher()

    provider = OpenMeteoWeatherProvider(
        store=store,
        fetch_json=fetch,
        clock=lambda: NOW,
    )

    assert provider.refresh() is None
    assert calls == []


def test_weather_fact_has_short_ttl_and_digest_only():
    store = RealtimeFactStore()
    store.put(
        _location_fact()
    )

    fetch, _ = _fake_fetcher()

    fact = OpenMeteoWeatherProvider(
        store=store,
        fetch_json=fetch,
        clock=lambda: NOW,
        ttl_seconds=600,
    ).refresh()

    assert (
        fact.expires_at
        - fact.observed_at
        == timedelta(
            seconds=600
        )
    )

    assert len(
        fact.raw_evidence_digest
    ) == 64

    assert "current" not in repr(
        fact.raw_evidence_digest
    )


def test_weather_provider_can_feed_realtime_store_via_scheduler_callback_shape():
    store = RealtimeFactStore()
    store.put(
        _location_fact()
    )

    fetch, _ = _fake_fetcher()

    provider = OpenMeteoWeatherProvider(
        store=store,
        fetch_json=fetch,
        clock=lambda: NOW,
    )

    fact = provider.refresh()

    assert store.put(
        fact
    ) is True

    assert store.get_latest(
        WEATHER_FACT_KIND,
        location=fact.location,
        at=NOW,
    ) == fact
