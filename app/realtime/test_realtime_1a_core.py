from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)

import pytest

from app.realtime import (
    RealtimeEventBus,
    RealtimeEventType,
    RealtimeFact,
    RealtimeFactStore,
)


UTC = timezone.utc


def _fact(
    *,
    kind="weather.current",
    value=None,
    observed_seconds=0,
    ttl_seconds=60,
    location="Bengaluru, Karnataka, India",
):
    observed_at = datetime(
        2026,
        9,
        11,
        3,
        30,
        tzinfo=UTC,
    ) + timedelta(
        seconds=observed_seconds
    )

    return RealtimeFact(
        kind=kind,
        value=(
            value
            if value is not None
            else {
                "temperature_c": 26.0,
            }
        ),
        source="test-provider",
        source_timestamp=observed_at,
        observed_at=observed_at,
        expires_at=(
            observed_at
            + timedelta(
                seconds=ttl_seconds
            )
        ),
        confidence=0.9,
        location=location,
        raw_evidence_digest="abc123",
    )


def test_realtime_fact_is_permanently_zero_authority():
    fact = _fact()

    assert fact.authority == "NONE"

    with pytest.raises(
        ValueError,
        match="permanently NONE",
    ):
        RealtimeFact(
            kind="system.test",
            value=True,
            source="test",
            observed_at=datetime.now(
                UTC
            ),
            expires_at=None,
            authority="SAFE",
        )


def test_realtime_fact_requires_aware_time():
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        RealtimeFact(
            kind="system.test",
            value=True,
            source="test",
            observed_at=datetime(
                2026,
                9,
                11,
                3,
                30,
            ),
            expires_at=None,
        )


def test_store_keeps_latest_state_not_history():
    store = RealtimeFactStore()

    first = _fact(
        value={
            "temperature_c": 25.0,
        },
        observed_seconds=0,
    )
    second = _fact(
        value={
            "temperature_c": 26.0,
        },
        observed_seconds=10,
    )

    assert store.put(
        first
    ) is True
    assert store.put(
        second
    ) is True
    assert len(
        store
    ) == 1

    assert store.get_latest(
        "weather.current",
        location="Bengaluru, Karnataka, India",
    ) == second


def test_older_observation_cannot_overwrite_newer_fact():
    store = RealtimeFactStore()

    newer = _fact(
        observed_seconds=20
    )
    older = _fact(
        observed_seconds=10
    )

    assert store.put(
        newer
    ) is True
    assert store.put(
        older
    ) is False

    assert store.get_latest(
        "weather.current",
        location="Bengaluru, Karnataka, India",
    ) == newer


def test_expired_fact_is_hidden_by_default():
    store = RealtimeFactStore()
    fact = _fact(
        ttl_seconds=30
    )

    store.put(
        fact
    )

    after_expiry = (
        fact.expires_at
        + timedelta(
            seconds=1
        )
    )

    assert store.get_latest(
        "weather.current",
        location=fact.location,
        at=after_expiry,
    ) is None

    assert store.get_latest(
        "weather.current",
        location=fact.location,
        at=after_expiry,
        allow_expired=True,
    ) == fact


def test_purge_expired_emits_expired_event():
    bus = RealtimeEventBus()
    events = []

    bus.subscribe(
        events.append
    )

    store = RealtimeFactStore(
        event_bus=bus
    )

    fact = _fact(
        ttl_seconds=10
    )

    store.put(
        fact
    )
    events.clear()

    removed = store.purge_expired(
        at=(
            fact.expires_at
            + timedelta(
                seconds=1
            )
        )
    )

    assert removed == 1
    assert len(
        store
    ) == 0
    assert len(
        events
    ) == 1
    assert (
        events[0].event_type
        == RealtimeEventType.EXPIRED
    )


def test_event_bus_filters_and_isolates_failures():
    bus = RealtimeEventBus()
    seen = []

    def explode(
        event,
    ):
        raise RuntimeError(
            "consumer failed"
        )

    bus.subscribe(
        explode
    )
    bus.subscribe(
        seen.append,
        kind="weather.current",
    )

    store = RealtimeFactStore(
        event_bus=bus
    )
    fact = _fact()

    assert store.put(
        fact
    ) is True
    assert len(
        seen
    ) == 1
    assert seen[
        0
    ].fact == fact


def test_storage_key_separates_locations():
    store = RealtimeFactStore()

    bengaluru = _fact(
        location="Bengaluru, Karnataka, India"
    )
    mysuru = _fact(
        location="Mysuru, Karnataka, India"
    )

    store.put(
        bengaluru
    )
    store.put(
        mysuru
    )

    assert len(
        store
    ) == 2
