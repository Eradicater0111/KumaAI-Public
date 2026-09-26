from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier
from unittest.mock import Mock

import pytest

from app.desktop.contracts import ApplicationIdentity
from app.ui_observation.focus_contracts import (
    FOCUS_STATUS_AVAILABLE,
    FocusedUIObservation,
    unavailable_focus,
)
from app.ui_observation.focus_store import (
    FocusedUIObservationStore,
)


APP = ApplicationIdentity(
    123,
    "test.app",
    "Example",
)


class Clock:
    def __init__(
        self,
        now=100.0,
    ):
        self.now = now

    def __call__(
        self,
    ):
        return self.now


def observation(
    captured=100.0,
    number=1,
    *,
    unavailable=False,
):
    if unavailable:
        return replace(
            unavailable_focus(
                "collection_failed",
                captured,
            ),
            observation_id=f"{number:032x}",
        )

    return FocusedUIObservation(
        captured_at_monotonic=captured,
        status=FOCUS_STATUS_AVAILABLE,
        active_application=APP,
        role="AXTextField",
        title="Input",
        description="Example",
        enabled=True,
        position_x=10.0,
        position_y=20.0,
        width=100.0,
        height=30.0,
        observation_id=f"{number:032x}",
    )


def test_store_is_exact_id_only_and_has_no_latest_api():
    store = FocusedUIObservationStore(
        clock=Clock()
    )

    result = observation()

    assert len(store) == 0
    assert not hasattr(
        store,
        "latest",
    )

    assert store.publish(
        result
    )

    assert store.get(
        result.observation_id
    ) is result

    assert store.get(
        "f" * 32
    ) is None

    with pytest.raises(
        FrozenInstanceError
    ):
        store.get(
            result.observation_id
        ).role = "AXButton"


def test_expiry_uses_capture_time_and_reads_do_not_extend_lifetime():
    clock = Clock(
        102
    )

    store = FocusedUIObservationStore(
        clock=clock,
        ttl_seconds=5,
    )

    result = observation(
        100
    )

    assert store.publish(
        result
    )

    clock.now = 104.99

    assert store.get(
        result.observation_id
    ) is result

    assert store.get(
        result.observation_id
    ) is result

    clock.now = 105

    assert store.get(
        result.observation_id
    ) is None

    assert len(store) == 0


def test_newer_focus_replaces_old_focus():
    store = FocusedUIObservationStore(
        clock=Clock(103),
        ttl_seconds=10,
    )

    first = observation(
        101,
        1,
    )
    second = observation(
        102,
        2,
    )

    assert store.publish(
        first
    )

    assert store.publish(
        second
    )

    assert store.get(
        first.observation_id
    ) is None

    assert store.get(
        second.observation_id
    ) is second


def test_active_observation_id_cannot_be_rebound_to_newer_object():
    store = FocusedUIObservationStore(
        clock=Clock(103),
        ttl_seconds=10,
    )

    first = observation(
        101,
        1,
    )

    replacement = replace(
        observation(
            102,
            2,
        ),
        observation_id=(
            first.observation_id
        ),
    )

    assert first is not replacement
    assert first.observation_id == replacement.observation_id

    assert store.publish(
        first
    )

    assert not store.publish(
        replacement
    )

    assert store.get(
        first.observation_id
    ) is first


def test_newer_unavailable_focus_replaces_available_without_fallback():
    store = FocusedUIObservationStore(
        clock=Clock(103),
        ttl_seconds=10,
    )

    available = observation(
        101,
        1,
    )

    missing = observation(
        102,
        2,
        unavailable=True,
    )

    assert store.publish(
        available
    )

    assert store.publish(
        missing
    )

    assert store.get(
        available.observation_id
    ) is None

    assert store.get(
        missing.observation_id
    ) is missing

    assert (
        missing.status
        == "unavailable"
    )


def test_duplicate_equal_older_and_expired_inputs_cannot_replace_newer():
    store = FocusedUIObservationStore(
        clock=Clock(110),
        ttl_seconds=20,
    )

    current = observation(
        105,
        1,
    )

    assert store.publish(
        current
    )

    assert not store.publish(
        current
    )

    assert not store.publish(
        observation(
            104,
            2,
        )
    )

    assert not store.publish(
        observation(
            105,
            3,
        )
    )

    assert not store.publish(
        observation(
            89,
            4,
        )
    )

    assert store.get(
        current.observation_id
    ) is current


def test_future_timestamp_rejected_without_replacing_current_focus():
    store = FocusedUIObservationStore(
        clock=Clock(110),
        ttl_seconds=20,
    )

    current = observation(
        105,
        1,
    )

    assert store.publish(
        current
    )

    with pytest.raises(
        ValueError,
        match="future",
    ):
        store.publish(
            observation(
                111,
                2,
            )
        )

    assert store.get(
        current.observation_id
    ) is current


def test_clear_does_not_reset_capture_high_water_mark():
    clock = Clock(
        103
    )

    store = FocusedUIObservationStore(
        clock=clock,
        ttl_seconds=10,
    )

    first = observation(
        101,
        1,
    )

    assert store.publish(
        first
    )

    store.clear()

    assert len(store) == 0

    assert not store.publish(
        observation(
            101,
            2,
        )
    )

    assert not store.publish(
        observation(
            100,
            3,
        )
    )

    second = observation(
        102,
        4,
    )

    assert store.publish(
        second
    )

    assert store.get(
        second.observation_id
    ) is second


@pytest.mark.parametrize(
    "bad",
    [
        float("nan"),
        float("inf"),
        -1,
        True,
        "100",
        10**1000,
    ],
)
def test_invalid_clock_clears_active_focus(
    bad,
):
    clock = Clock()

    store = FocusedUIObservationStore(
        clock=clock
    )

    result = observation()

    assert store.publish(
        result
    )

    clock.now = bad

    with pytest.raises(
        ValueError,
        match="Focused UI store clock",
    ):
        store.get(
            result.observation_id
        )

    clock.now = 101

    assert store.get(
        result.observation_id
    ) is None


def test_backward_clock_clears_focus_and_history_remains_fail_closed():
    clock = Clock(
        100
    )

    store = FocusedUIObservationStore(
        clock=clock
    )

    result = observation(
        100
    )

    assert store.publish(
        result
    )

    clock.now = 99

    with pytest.raises(
        ValueError
    ):
        store.get(
            result.observation_id
        )

    store.clear()

    with pytest.raises(
        ValueError
    ):
        store.publish(
            observation(
                99,
                2,
            )
        )


def test_clock_failure_is_sanitized_and_drops_active_focus():
    clock = Mock(
        side_effect=[
            100,
            RuntimeError(
                "private native details"
            ),
            101,
        ]
    )

    store = FocusedUIObservationStore(
        clock=clock
    )

    result = observation()

    assert store.publish(
        result
    )

    with pytest.raises(
        ValueError,
        match="Focused UI store clock",
    ) as caught:
        store.get(
            result.observation_id
        )

    assert (
        "private"
        not in str(
            caught.value
        )
    )

    assert store.get(
        result.observation_id
    ) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "ttl_seconds": 0,
        },
        {
            "ttl_seconds": 61,
        },
        {
            "ttl_seconds": True,
        },
        {
            "ttl_seconds": float("nan"),
        },
        {
            "ttl_seconds": float("inf"),
        },
        {
            "clock": None,
        },
    ],
)
def test_invalid_configuration_is_rejected(
    kwargs,
):
    with pytest.raises(
        (
            ValueError,
            TypeError,
        )
    ):
        FocusedUIObservationStore(
            **kwargs
        )


def test_invalid_values_are_not_coerced():
    store = FocusedUIObservationStore(
        clock=Clock()
    )

    with pytest.raises(
        TypeError
    ):
        store.publish(
            observation().to_dict()
        )

    with pytest.raises(
        TypeError
    ):
        store.get(
            1
        )


def test_concurrent_publish_finishes_with_newest_focus_only():
    store = FocusedUIObservationStore(
        ttl_seconds=20,
        clock=Clock(110),
    )

    barrier = Barrier(
        8
    )

    values = [
        observation(
            100 + index,
            index + 1,
        )
        for index in range(8)
    ]

    def publish(
        value,
    ):
        barrier.wait(
            timeout=5
        )

        return store.publish(
            value
        )

    with ThreadPoolExecutor(
        max_workers=8
    ) as executor:
        list(
            executor.map(
                publish,
                values,
            )
        )

    assert len(store) == 1

    active = [
        value
        for value in values
        if store.get(
            value.observation_id
        ) is value
    ]

    assert active == [
        values[-1]
    ]


def test_store_has_no_authority_or_execution_surface():
    store = FocusedUIObservationStore(
        clock=Clock()
    )

    for name in (
        "latest",
        "claim",
        "authorize",
        "approve",
        "execute",
        "type_text",
        "permission",
        "semantic_target_verified",
    ):
        assert not hasattr(
            store,
            name,
        )
