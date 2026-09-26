from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)

import pytest

from app.realtime import (
    RealtimeChangeDetector,
    RealtimeEvent,
    RealtimeEventType,
    RealtimeFact,
    RealtimeRelevanceLevel,
    RealtimeSignal,
)


UTC = timezone.utc
T0 = datetime(
    2026,
    9,
    11,
    6,
    0,
    tzinfo=UTC,
)


def _fact(
    *,
    kind,
    value,
    location=None,
    seconds=0,
):
    observed = (
        T0
        + timedelta(
            seconds=seconds
        )
    )

    return RealtimeFact(
        kind=kind,
        value=value,
        source="test",
        observed_at=observed,
        source_timestamp=observed,
        expires_at=(
            observed
            + timedelta(
                minutes=10
            )
        ),
        confidence=1.0,
        location=location,
        raw_evidence_digest=(
            f"digest-{seconds}"
        ),
    )


def _event(
    fact,
    *,
    event_type=RealtimeEventType.UPDATED,
    previous=None,
):
    return RealtimeEvent(
        event_type=event_type,
        fact=fact,
        previous_fact=previous,
    )


def test_realtime_signal_is_permanently_zero_authority():
    fact = _fact(
        kind="system.test",
        value=1,
    )

    signal = RealtimeSignal(
        kind=fact.kind,
        level=RealtimeRelevanceLevel.LOW,
        score=0.2,
        reason="test",
        fact=fact,
        previous_fact=None,
    )

    assert signal.authority == "NONE"

    with pytest.raises(
        ValueError,
        match="permanently NONE",
    ):
        RealtimeSignal(
            kind=fact.kind,
            level=RealtimeRelevanceLevel.LOW,
            score=0.2,
            reason="test",
            fact=fact,
            previous_fact=None,
            authority="SAFE",
        )


def test_initial_fact_is_baseline_not_proactive_signal():
    detector = RealtimeChangeDetector()

    fact = _fact(
        kind="weather.current",
        value={
            "temperature_c": 25.0,
            "precipitation_mm": 0.0,
        },
        location="Example",
    )

    signal = detector.evaluate(
        _event(
            fact,
            event_type=RealtimeEventType.ADDED,
        )
    )

    assert (
        signal.level
        == RealtimeRelevanceLevel.IGNORE
    )
    assert signal.score == 0.0
    assert signal.reason == "initial baseline fact"


def test_location_change_is_high_relevance():
    detector = RealtimeChangeDetector()

    first = _fact(
        kind="location.current",
        value={
            "locality": "Bengaluru",
        },
        location="Bengaluru, Karnataka, India",
        seconds=0,
    )

    second = _fact(
        kind="location.current",
        value={
            "locality": "Mysuru",
        },
        location="Mysuru, Karnataka, India",
        seconds=60,
    )

    detector.evaluate(
        _event(
            first,
            event_type=RealtimeEventType.ADDED,
        )
    )

    signal = detector.evaluate(
        _event(
            second,
            event_type=RealtimeEventType.ADDED,
        )
    )

    assert (
        signal.level
        == RealtimeRelevanceLevel.HIGH
    )
    assert signal.score == 0.85
    assert (
        signal.reason
        == "approximate location changed"
    )


def test_location_refresh_same_place_is_ignored():
    detector = RealtimeChangeDetector()

    first = _fact(
        kind="location.current",
        value={
            "locality": "Bengaluru",
        },
        location="Bengaluru, Karnataka, India",
        seconds=0,
    )

    second = _fact(
        kind="location.current",
        value={
            "locality": "Bengaluru",
        },
        location="Bengaluru, Karnataka, India",
        seconds=20,
    )

    detector.evaluate(
        _event(
            first,
            event_type=RealtimeEventType.ADDED,
        )
    )

    signal = detector.evaluate(
        _event(
            second,
            event_type=RealtimeEventType.UPDATED,
            previous=first,
        )
    )

    assert (
        signal.level
        == RealtimeRelevanceLevel.IGNORE
    )


def test_precipitation_start_is_high_relevance():
    detector = RealtimeChangeDetector()

    before = _fact(
        kind="weather.current",
        value={
            "temperature_c": 25.0,
            "precipitation_mm": 0.0,
            "weather_code": 2,
            "wind_speed_kmh": 10.0,
        },
        location="Example",
        seconds=0,
    )

    after = _fact(
        kind="weather.current",
        value={
            "temperature_c": 25.0,
            "precipitation_mm": 1.2,
            "weather_code": 61,
            "wind_speed_kmh": 12.0,
        },
        location="Example",
        seconds=60,
    )

    signal = detector.evaluate(
        _event(
            after,
            previous=before,
        )
    )

    assert (
        signal.level
        == RealtimeRelevanceLevel.HIGH
    )
    assert signal.score == 0.90
    assert (
        signal.reason
        == "precipitation started"
    )


def test_large_temperature_change_is_high_relevance():
    detector = RealtimeChangeDetector()

    before = _fact(
        kind="weather.current",
        value={
            "temperature_c": 20.0,
            "precipitation_mm": 0.0,
        },
        location="Example",
    )

    after = _fact(
        kind="weather.current",
        value={
            "temperature_c": 25.5,
            "precipitation_mm": 0.0,
        },
        location="Example",
        seconds=60,
    )

    signal = detector.evaluate(
        _event(
            after,
            previous=before,
        )
    )

    assert (
        signal.level
        == RealtimeRelevanceLevel.HIGH
    )
    assert (
        signal.reason
        == "temperature changed by at least 5°C"
    )


def test_small_weather_refresh_is_ignored():
    detector = RealtimeChangeDetector()

    before = _fact(
        kind="weather.current",
        value={
            "temperature_c": 25.0,
            "precipitation_mm": 0.0,
            "weather_code": 2,
            "wind_speed_kmh": 10.0,
        },
        location="Example",
    )

    after = _fact(
        kind="weather.current",
        value={
            "temperature_c": 25.5,
            "precipitation_mm": 0.0,
            "weather_code": 2,
            "wind_speed_kmh": 11.0,
        },
        location="Example",
        seconds=60,
    )

    signal = detector.evaluate(
        _event(
            after,
            previous=before,
        )
    )

    assert (
        signal.level
        == RealtimeRelevanceLevel.IGNORE
    )
    assert signal.score == 0.10


def test_expiry_is_low_relevance_not_action_authority():
    detector = RealtimeChangeDetector()

    fact = _fact(
        kind="weather.current",
        value={
            "temperature_c": 25.0,
        },
        location="Example",
    )

    signal = detector.evaluate(
        _event(
            fact,
            event_type=RealtimeEventType.EXPIRED,
        )
    )

    assert (
        signal.level
        == RealtimeRelevanceLevel.LOW
    )
    assert signal.authority == "NONE"


def test_generic_fact_change_is_low_relevance():
    detector = RealtimeChangeDetector()

    before = _fact(
        kind="system.test",
        value=1,
    )

    after = _fact(
        kind="system.test",
        value=2,
        seconds=10,
    )

    signal = detector.evaluate(
        _event(
            after,
            previous=before,
        )
    )

    assert (
        signal.level
        == RealtimeRelevanceLevel.LOW
    )
    assert signal.score == 0.25
