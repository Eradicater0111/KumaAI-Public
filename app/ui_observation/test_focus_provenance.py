from dataclasses import (
    FrozenInstanceError,
    replace,
)

import pytest

from app.desktop.contracts import (
    ApplicationIdentity,
    DesktopContextObservation,
)
from app.ui_observation.focus_binding import (
    bind_desktop_to_focus,
)
from app.ui_observation.focus_contracts import (
    FocusedUIObservation,
)
from app.ui_observation.focus_provenance import (
    FocusDesktopProvenance,
    FocusDesktopProvenanceError,
    FocusDesktopProvenanceStore,
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
        now=103.5,
    ):
        self.now = now

    def __call__(
        self,
    ):
        return self.now


def desktop(
    captured,
    number,
    *,
    app=APP,
):
    return DesktopContextObservation(
        observation_id=f"{number:032x}",
        captured_at_monotonic=captured,
        status="available",
        active_application=app,
        enumeration_succeeded=True,
    )


def focus(
    captured=102.0,
    number=2,
    *,
    app=APP,
    title="Input",
):
    return FocusedUIObservation(
        observation_id=f"{number:032x}",
        captured_at_monotonic=captured,
        status="available",
        active_application=app,
        role="AXTextField",
        title=title,
        enabled=True,
    )


def evidence():
    before = desktop(
        101.0,
        1,
    )

    middle = focus(
        102.0,
        2,
    )

    after = desktop(
        103.0,
        3,
    )

    binding_result = (
        bind_desktop_to_focus(
            middle,
            before,
            after,
            clock=lambda: 103.2,
        )
    )

    assert binding_result.linked

    provenance = (
        FocusDesktopProvenance(
            binding=binding_result.binding,
            focus_observation=middle,
            desktop_before=before,
            desktop_after=after,
        )
    )

    return (
        before,
        middle,
        after,
        provenance,
    )


def active_store():
    clock = Clock()

    focus_store = (
        FocusedUIObservationStore(
            ttl_seconds=10.0,
            clock=clock,
        )
    )

    provenance_store = (
        FocusDesktopProvenanceStore(
            focus_store=focus_store,
            clock=clock,
        )
    )

    return (
        clock,
        focus_store,
        provenance_store,
    )


def test_provenance_preserves_exact_source_graph():
    (
        before,
        middle,
        after,
        provenance,
    ) = evidence()

    assert (
        provenance.focus_observation
        is middle
    )

    assert (
        provenance.desktop_before
        is before
    )

    assert (
        provenance.desktop_after
        is after
    )

    assert (
        provenance.binding
        .focus_observation_id
        == middle.observation_id
    )

    assert (
        provenance.application_pid
        == APP.pid
    )

    assert (
        provenance.application_bundle_id
        == APP.bundle_id
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        provenance.binding = None


def test_publish_requires_exact_active_focus_object():
    (
        _before,
        middle,
        _after,
        provenance,
    ) = evidence()

    (
        _clock,
        focus_store,
        provenance_store,
    ) = active_store()

    assert focus_store.publish(
        middle
    )

    assert provenance_store.publish(
        provenance
    )

    assert (
        provenance_store.get(
            middle.observation_id
        )
        is provenance
    )


def test_equal_reconstructed_focus_object_cannot_back_provenance():
    (
        before,
        middle,
        after,
        provenance,
    ) = evidence()

    (
        _clock,
        focus_store,
        provenance_store,
    ) = active_store()

    assert focus_store.publish(
        middle
    )

    reconstructed = replace(
        middle
    )

    assert reconstructed == middle
    assert reconstructed is not middle

    forged = FocusDesktopProvenance(
        binding=provenance.binding,
        focus_observation=reconstructed,
        desktop_before=before,
        desktop_after=after,
    )

    assert not provenance_store.publish(
        forged
    )

    assert (
        provenance_store.get(
            middle.observation_id
        )
        is None
    )


def test_active_focus_replacement_invalidates_provenance():
    (
        _before,
        middle,
        _after,
        provenance,
    ) = evidence()

    (
        clock,
        focus_store,
        provenance_store,
    ) = active_store()

    assert focus_store.publish(
        middle
    )

    assert provenance_store.publish(
        provenance
    )

    replacement = focus(
        103.4,
        9,
        title="Replacement",
    )

    clock.now = 103.5

    assert focus_store.publish(
        replacement
    )

    assert (
        provenance_store.get(
            middle.observation_id
        )
        is None
    )

    assert len(
        provenance_store
    ) == 0


def test_focus_clear_invalidates_provenance():
    (
        _before,
        middle,
        _after,
        provenance,
    ) = evidence()

    (
        _clock,
        focus_store,
        provenance_store,
    ) = active_store()

    assert focus_store.publish(
        middle
    )

    assert provenance_store.publish(
        provenance
    )

    focus_store.clear()

    assert (
        provenance_store.get(
            middle.observation_id
        )
        is None
    )


def test_wrong_focus_id_never_falls_back_to_active_provenance():
    (
        _before,
        middle,
        _after,
        provenance,
    ) = evidence()

    (
        _clock,
        focus_store,
        provenance_store,
    ) = active_store()

    assert focus_store.publish(
        middle
    )

    assert provenance_store.publish(
        provenance
    )

    assert (
        provenance_store.get(
            "f" * 32
        )
        is None
    )

    assert (
        provenance_store.get(
            middle.observation_id
        )
        is provenance
    )


def test_store_has_no_latest_or_claim_fallback():
    (
        _clock,
        _focus_store,
        provenance_store,
    ) = active_store()

    assert not hasattr(
        provenance_store,
        "latest",
    )

    assert not hasattr(
        provenance_store,
        "claim",
    )


def test_expired_binding_cannot_publish():
    (
        _before,
        middle,
        _after,
        provenance,
    ) = evidence()

    (
        clock,
        focus_store,
        provenance_store,
    ) = active_store()

    assert focus_store.publish(
        middle
    )

    clock.now = 106.0

    assert not provenance_store.publish(
        provenance
    )

    assert len(
        provenance_store
    ) == 0


def test_clock_rollback_clears_provenance_and_fails_closed():
    (
        _before,
        middle,
        _after,
        provenance,
    ) = evidence()

    (
        clock,
        focus_store,
        provenance_store,
    ) = active_store()

    assert focus_store.publish(
        middle
    )

    assert provenance_store.publish(
        provenance
    )

    clock.now = 102.0

    with pytest.raises(
        FocusDesktopProvenanceError
    ):
        provenance_store.get(
            middle.observation_id
        )

    clock.now = 200.0

    assert (
        provenance_store.get(
            middle.observation_id
        )
        is None
    )


def test_wrong_source_binding_relationship_is_rejected():
    (
        before,
        middle,
        after,
        provenance,
    ) = evidence()

    wrong_before = replace(
        before,
        observation_id="a" * 32,
    )

    with pytest.raises(
        ValueError
    ):
        FocusDesktopProvenance(
            binding=provenance.binding,
            focus_observation=middle,
            desktop_before=wrong_before,
            desktop_after=after,
        )


def test_application_identity_mismatch_is_rejected():
    (
        before,
        middle,
        after,
        provenance,
    ) = evidence()

    changed = replace(
        after,
        active_application=(
            ApplicationIdentity(
                456,
                "other.app",
                "Other",
            )
        ),
    )

    with pytest.raises(
        ValueError
    ):
        FocusDesktopProvenance(
            binding=provenance.binding,
            focus_observation=middle,
            desktop_before=before,
            desktop_after=changed,
        )


def test_wrong_types_are_rejected():
    (
        _before,
        middle,
        _after,
        provenance,
    ) = evidence()

    (
        _clock,
        _focus_store,
        provenance_store,
    ) = active_store()

    with pytest.raises(
        TypeError
    ):
        provenance_store.publish(
            object()
        )

    with pytest.raises(
        TypeError
    ):
        provenance_store.get(
            123
        )

    with pytest.raises(
        TypeError
    ):
        FocusDesktopProvenanceStore(
            focus_store=object()
        )

    with pytest.raises(
        TypeError
    ):
        FocusDesktopProvenanceStore(
            clock=None
        )

    assert (
        provenance.focus_observation
        is middle
    )


def test_provenance_contract_has_no_authority_surface():
    fields = set(
        FocusDesktopProvenance
        .__dataclass_fields__
    )

    forbidden = {
        "text",
        "permission",
        "approved",
        "authorized",
        "keyboard_authority",
        "semantic_target_verified",
        "execute",
        "button",
        "clicks",
    }

    assert not (
        fields & forbidden
    )
