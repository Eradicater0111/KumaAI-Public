from dataclasses import FrozenInstanceError, replace

import pytest

from app.desktop.contracts import ApplicationIdentity, DesktopContextObservation
from app.desktop.provenance import (
    ScreenDesktopProvenance,
    ScreenDesktopProvenanceStore,
)
from app.desktop.screen_binding import DesktopScreenBinding


BEFORE_ID = "1" * 32
SCREEN_ID = "2" * 32
AFTER_ID = "3" * 32


class Clock:
    def __init__(self, value=10.4):
        self.value = value

    def __call__(self):
        return self.value


def context(observation_id, captured, *, pid=42, bundle="test.app", status="available", diagnostics=()):
    return DesktopContextObservation(
        captured_at_monotonic=captured,
        status=status,
        active_application=ApplicationIdentity(pid, bundle),
        enumeration_succeeded=True,
        diagnostics=diagnostics,
        observation_id=observation_id,
    )


def evidence(*, expiry=20.0):
    before = context(BEFORE_ID, 10.0)
    after = context(AFTER_ID, 10.2)
    binding = DesktopScreenBinding(
        screen_observation_id=SCREEN_ID,
        desktop_before_id=BEFORE_ID,
        desktop_after_id=AFTER_ID,
        application_pid=42,
        application_bundle_id="test.app",
        desktop_before_captured_at=10.0,
        screen_captured_at=10.1,
        desktop_after_captured_at=10.2,
        bound_at_monotonic=10.3,
        expires_at_monotonic=expiry,
        desktop_before_status="available",
        desktop_after_status="available",
    )
    return ScreenDesktopProvenance(binding, before, after)


def test_exact_screen_id_publishes_and_reads():
    clock = Clock()
    store = ScreenDesktopProvenanceStore(clock=clock)
    value = evidence()
    assert store.publish(value)
    assert store.get(SCREEN_ID) is value
    assert store.get("9" * 32) is None
    assert store.get(SCREEN_ID) is value


def test_store_has_no_latest_fallback_api():
    assert not hasattr(ScreenDesktopProvenanceStore, "latest")


def test_evidence_is_immutable():
    value = evidence()
    with pytest.raises(FrozenInstanceError):
        value.binding = None


@pytest.mark.parametrize("field,new_value", [
    ("desktop_before_id", "8" * 32),
    ("desktop_after_id", "8" * 32),
    ("desktop_before_captured_at", 9.9),
    ("desktop_after_captured_at", 10.25),
    ("application_pid", 99),
    ("application_bundle_id", "other.app"),
])
def test_binding_source_substitution_is_rejected(field, new_value):
    value = evidence()
    bad_binding = replace(value.binding, **{field: new_value})
    with pytest.raises(ValueError):
        ScreenDesktopProvenance(bad_binding, value.desktop_before, value.desktop_after)


def test_partial_integrity_must_match_binding():
    before = context(BEFORE_ID, 10.0, status="partial", diagnostics=("focus_unavailable",))
    after = context(AFTER_ID, 10.2)
    binding = replace(
        evidence().binding,
        desktop_before_status="partial",
        desktop_before_diagnostics=("focus_unavailable",),
    )
    value = ScreenDesktopProvenance(binding, before, after)
    assert value.desktop_before.status == "partial"


def test_expired_publish_fails_and_clears_previous():
    clock = Clock(10.4)
    store = ScreenDesktopProvenanceStore(clock=clock)
    assert store.publish(evidence(expiry=11.0))
    clock.value = 11.0
    assert not store.publish(evidence(expiry=11.0))
    assert store.get(SCREEN_ID) is None


def test_expiry_on_read_clears_record():
    clock = Clock(10.4)
    store = ScreenDesktopProvenanceStore(clock=clock)
    assert store.publish(evidence(expiry=11.0))
    clock.value = 11.0
    assert store.get(SCREEN_ID) is None


def test_clear_discards_active_record():
    store = ScreenDesktopProvenanceStore(clock=Clock())
    assert store.publish(evidence())
    store.clear()
    assert store.get(SCREEN_ID) is None


def test_clock_rollback_clears_and_fails_closed():
    clock = Clock(10.4)
    store = ScreenDesktopProvenanceStore(clock=clock)
    assert store.publish(evidence())
    assert store.get(SCREEN_ID) is not None
    clock.value = 10.0
    with pytest.raises(ValueError):
        store.get(SCREEN_ID)
    clock.value = 10.5
    assert store.get(SCREEN_ID) is None


def test_invalid_clock_value_clears_and_fails_closed():
    clock = Clock(10.4)
    store = ScreenDesktopProvenanceStore(clock=clock)
    assert store.publish(evidence())
    clock.value = float("nan")
    with pytest.raises(ValueError):
        store.get(SCREEN_ID)


def test_non_string_lookup_is_rejected():
    store = ScreenDesktopProvenanceStore(clock=Clock())
    with pytest.raises(TypeError):
        store.get(123)
