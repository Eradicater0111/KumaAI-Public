from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from app.realtime import (
    RealtimeEventBus,
    RealtimeFact,
    RealtimeFactStore,
    RealtimeScheduler,
)


UTC = timezone.utc
T0 = datetime(
    2026,
    9,
    11,
    5,
    0,
    tzinfo=UTC,
)


def _fact(
    *,
    observed_at=T0,
    value=1,
):
    return RealtimeFact(
        kind="system.test",
        value=value,
        source="test-provider",
        source_timestamp=observed_at,
        observed_at=observed_at,
        expires_at=(
            observed_at
            + timedelta(
                seconds=60
            )
        ),
        confidence=1.0,
        location=None,
        raw_evidence_digest="abc123",
    )


def test_immediate_job_runs_once_and_reschedules():
    store = RealtimeFactStore()
    scheduler = RealtimeScheduler(
        store=store
    )

    calls = []

    def provider():
        calls.append(
            True
        )
        return _fact()

    scheduler.register(
        name="system-test",
        interval_seconds=30,
        callback=provider,
        now=T0,
        run_immediately=True,
    )

    executions = scheduler.tick(
        at=T0
    )

    assert len(
        executions
    ) == 1
    assert executions[
        0
    ].success is True
    assert executions[
        0
    ].fact_count == 1
    assert len(
        calls
    ) == 1
    assert len(
        store
    ) == 1

    assert scheduler.next_run_at(
        "system-test"
    ) == (
        T0
        + timedelta(
            seconds=30
        )
    )

    assert scheduler.tick(
        at=(
            T0
            + timedelta(
                seconds=29
            )
        )
    ) == ()


def test_missed_intervals_are_coalesced_not_replayed():
    store = RealtimeFactStore()
    scheduler = RealtimeScheduler(
        store=store
    )

    calls = []

    scheduler.register(
        name="coalesced",
        interval_seconds=10,
        callback=lambda: (
            calls.append(
                True
            )
            or _fact()
        ),
        now=T0,
        run_immediately=False,
    )

    much_later = (
        T0
        + timedelta(
            minutes=5
        )
    )

    executions = scheduler.tick(
        at=much_later
    )

    assert len(
        executions
    ) == 1
    assert len(
        calls
    ) == 1
    assert scheduler.next_run_at(
        "coalesced"
    ) == (
        much_later
        + timedelta(
            seconds=10
        )
    )


def test_callback_failure_isolated_from_other_jobs():
    store = RealtimeFactStore()
    scheduler = RealtimeScheduler(
        store=store
    )

    def explode():
        raise RuntimeError(
            "boom"
        )

    scheduler.register(
        name="a-failing",
        interval_seconds=30,
        callback=explode,
        now=T0,
    )

    scheduler.register(
        name="b-working",
        interval_seconds=30,
        callback=lambda: _fact(
            value=2
        ),
        now=T0,
    )

    executions = scheduler.tick(
        at=T0
    )

    assert len(
        executions
    ) == 2

    failing = executions[
        0
    ]
    working = executions[
        1
    ]

    assert failing.name == "a-failing"
    assert failing.success is False
    assert failing.error_type == "RuntimeError"

    assert working.name == "b-working"
    assert working.success is True
    assert working.fact_count == 1

    assert len(
        store
    ) == 1


def test_disabled_job_does_not_run_until_reenabled():
    store = RealtimeFactStore()
    scheduler = RealtimeScheduler(
        store=store
    )

    calls = []

    scheduler.register(
        name="toggle",
        interval_seconds=20,
        callback=lambda: (
            calls.append(
                True
            )
            or _fact()
        ),
        now=T0,
    )

    scheduler.set_enabled(
        "toggle",
        enabled=False,
    )

    assert scheduler.tick(
        at=T0
    ) == ()
    assert calls == []

    scheduler.set_enabled(
        "toggle",
        enabled=True,
        now=T0,
        run_immediately=True,
    )

    assert len(
        scheduler.tick(
            at=T0
        )
    ) == 1
    assert len(
        calls
    ) == 1


def test_tick_purges_expired_facts_before_refresh():
    bus = RealtimeEventBus()
    events = []
    bus.subscribe(
        events.append
    )

    store = RealtimeFactStore(
        event_bus=bus
    )

    expired = RealtimeFact(
        kind="weather.current",
        value={
            "temperature_c": 25,
        },
        source="test",
        observed_at=T0,
        source_timestamp=T0,
        expires_at=(
            T0
            + timedelta(
                seconds=5
            )
        ),
        confidence=1.0,
        location="Example",
        raw_evidence_digest="old",
    )

    store.put(
        expired
    )
    events.clear()

    scheduler = RealtimeScheduler(
        store=store
    )

    scheduler.tick(
        at=(
            T0
            + timedelta(
                seconds=6
            )
        )
    )

    assert len(
        store
    ) == 0
    assert len(
        events
    ) == 1
    assert (
        events[0].event_type.value
        == "expired"
    )


def test_scheduler_accepts_multiple_facts_from_one_provider():
    store = RealtimeFactStore()
    scheduler = RealtimeScheduler(
        store=store
    )

    second = RealtimeFact(
        kind="system.other",
        value=2,
        source="test-provider",
        observed_at=T0,
        source_timestamp=T0,
        expires_at=(
            T0
            + timedelta(
                seconds=60
            )
        ),
        confidence=1.0,
        location=None,
        raw_evidence_digest="def456",
    )

    scheduler.register(
        name="multi",
        interval_seconds=30,
        callback=lambda: (
            _fact(),
            second,
        ),
        now=T0,
    )

    execution = scheduler.tick(
        at=T0
    )[0]

    assert execution.success is True
    assert execution.fact_count == 2
    assert len(
        store
    ) == 2


def test_scheduler_rejects_naive_time():
    store = RealtimeFactStore()
    scheduler = RealtimeScheduler(
        store=store
    )

    naive = datetime(
        2026,
        9,
        11,
        5,
        0,
    )

    try:
        scheduler.register(
            name="bad-time",
            interval_seconds=30,
            callback=lambda: None,
            now=naive,
        )
    except ValueError as error:
        assert "timezone-aware" in str(
            error
        )
    else:
        raise AssertionError(
            "naive scheduler time should have been rejected."
        )
