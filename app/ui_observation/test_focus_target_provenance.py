from dataclasses import (
    FrozenInstanceError,
    replace,
)
from pathlib import Path

import pytest

from app.desktop.contracts import (
    ApplicationIdentity,
    DesktopContextObservation,
)
from app.ui_observation.focus_binding import (
    DesktopFocusBinding,
)
from app.ui_observation.focus_contracts import (
    FocusedUIObservation,
)
from app.ui_observation.focus_provenance import (
    FocusDesktopProvenance,
)
from app.ui_observation.focus_target_correlation import (
    CORRELATION_STATUS_MATCHED,
    CORRELATION_STATUS_MISMATCHED,
    MISMATCH_CODE,
    FocusTargetCorrelationResult,
    FocusTargetSemanticCandidate,
)
from app.ui_observation.focus_target_provenance import (
    FOCUS_TARGET_CORRELATION_MAX_AGE_SECONDS,
    FocusTargetProvenance,
    FocusTargetProvenanceError,
    FocusTargetProvenanceStore,
    compose_focus_target_provenance,
)
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)
from app.ui_observation.target_revalidation import (
    StructuredUITargetRevalidationResult,
)
from app.ui_observation.test_focus_provenance import (
    evidence as existing_focus_evidence,
)
from app.ui_observation.test_target_revalidation import (
    revalidate as existing_revalidate,
)


def _walk_fixture(value):
    queue = [value]
    seen = set()

    while queue:
        current = queue.pop(0)
        identity = id(current)

        if identity in seen:
            continue

        seen.add(identity)
        yield current

        if isinstance(
            current,
            (
                tuple,
                list,
                set,
                frozenset,
            ),
        ):
            queue.extend(current)

        elif isinstance(current, dict):
            queue.extend(
                current.values()
            )

        else:
            for name in (
                "binding",
                "focus_observation",
                "desktop_before",
                "desktop_after",
                "provenance",
                "result",
            ):
                try:
                    child = getattr(
                        current,
                        name,
                    )
                except Exception:
                    continue

                if child is not None:
                    queue.append(child)


def _base_focus_provenance():
    produced = existing_focus_evidence()

    objects = list(
        _walk_fixture(
            produced
        )
    )

    roots = [
        item
        for item in objects
        if type(item)
        is FocusDesktopProvenance
    ]

    if len(roots) == 1:
        return roots[0]

    bindings = [
        item
        for item in objects
        if type(item)
        is DesktopFocusBinding
    ]

    focuses = [
        item
        for item in objects
        if type(item)
        is FocusedUIObservation
    ]

    desktops = [
        item
        for item in objects
        if type(item)
        is DesktopContextObservation
    ]

    assert len(bindings) == 1
    assert len(focuses) == 1

    binding = bindings[0]
    focus = focuses[0]

    before = next(
        item
        for item in desktops
        if item.observation_id
        == binding.desktop_before_id
    )

    after = next(
        item
        for item in desktops
        if item.observation_id
        == binding.desktop_after_id
    )

    return FocusDesktopProvenance(
        binding=binding,
        focus_observation=focus,
        desktop_before=before,
        desktop_after=after,
    )


def _shift_focus_to_bound_at(
    wanted_bound_at,
):
    original = _base_focus_provenance()

    delta = (
        wanted_bound_at
        - original.binding.bound_at_monotonic
    )

    before = replace(
        original.desktop_before,
        captured_at_monotonic=(
            original.desktop_before.captured_at_monotonic
            + delta
        ),
    )

    focus = replace(
        original.focus_observation,
        captured_at_monotonic=(
            original.focus_observation.captured_at_monotonic
            + delta
        ),
    )

    after = replace(
        original.desktop_after,
        captured_at_monotonic=(
            original.desktop_after.captured_at_monotonic
            + delta
        ),
    )

    binding = replace(
        original.binding,
        desktop_before_captured_at=(
            original.binding.desktop_before_captured_at
            + delta
        ),
        focus_captured_at=(
            original.binding.focus_captured_at
            + delta
        ),
        desktop_after_captured_at=(
            original.binding.desktop_after_captured_at
            + delta
        ),
        bound_at_monotonic=(
            original.binding.bound_at_monotonic
            + delta
        ),
        expires_at_monotonic=(
            original.binding.expires_at_monotonic
            + delta
        ),
    )

    shifted = FocusDesktopProvenance(
        binding=binding,
        focus_observation=focus,
        desktop_before=before,
        desktop_after=after,
    )

    assert (
        shifted.binding.bound_at_monotonic
        == wanted_bound_at
    )

    return shifted


def semantic_result():
    result = existing_revalidate()

    assert (
        type(result)
        is StructuredUITargetRevalidationResult
    )

    assert result.revalidated

    return result


def matched_correlation(
    semantic,
    *,
    focus,
    captured,
    selector=None,
    application=None,
):
    target = semantic.revalidation

    selector = (
        replace(target.selector)
        if selector is None
        else selector
    )

    application = (
        application
        or ApplicationIdentity(
            target.application_pid,
            target.application_bundle_id,
            "Example",
        )
    )

    candidate = FocusTargetSemanticCandidate(
        path=(0,),
        owner_pid=application.pid,
        role=selector.role,
        subrole=selector.subrole,
        title=selector.text,
        description=None,
        enabled=(
            True
            if selector.require_enabled
            else None
        ),
        position_x=(
            10.0
            if selector.require_positive_area
            else None
        ),
        position_y=(
            20.0
            if selector.require_positive_area
            else None
        ),
        width=(
            100.0
            if selector.require_positive_area
            else None
        ),
        height=(
            30.0
            if selector.require_positive_area
            else None
        ),
    )

    return FocusTargetCorrelationResult(
        captured_at_monotonic=captured,
        status=CORRELATION_STATUS_MATCHED,
        expected_application=application,
        selector=selector,
        candidate_count=1,
        candidate=candidate,
        diagnostics=(),
    )


def sources():
    semantic = semantic_result()

    focus = _shift_focus_to_bound_at(
        109.10
    )

    prerequisite = max(
        semantic.revalidation.revalidated_at_monotonic,
        focus.binding.bound_at_monotonic,
    )

    source_expiry = min(
        semantic.revalidation.expires_at_monotonic,
        focus.binding.expires_at_monotonic,
    )

    room = (
        source_expiry
        - prerequisite
    )

    assert room > 0

    gap = min(
        0.05,
        room / 4,
    )

    assert gap > 0

    captured = (
        prerequisite
        + gap
    )

    issued = (
        captured
        + gap
    )

    correlation = matched_correlation(
        semantic,
        focus=focus,
        captured=captured,
    )

    return (
        semantic,
        focus,
        correlation,
        issued,
    )


def provenance():
    (
        semantic,
        focus,
        correlation,
        issued,
    ) = sources()

    result = compose_focus_target_provenance(
        semantic,
        focus,
        correlation,
        clock=lambda: issued,
    )

    return (
        semantic,
        focus,
        correlation,
        issued,
        result,
    )


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def store_for(
    focus,
    *,
    now,
):
    clock = Clock(now)

    active = {
        "focus": focus,
    }

    def lookup(
        observation_id,
    ):
        candidate = active["focus"]

        if candidate is None:
            return None

        if (
            observation_id
            != candidate.focus_observation_id
        ):
            return None

        return candidate

    store = FocusTargetProvenanceStore(
        focus_lookup=lookup,
        clock=clock,
    )

    return (
        store,
        clock,
        active,
    )


def test_composition_preserves_exact_parent_side_graph():
    (
        semantic,
        focus,
        correlation,
        issued,
        result,
    ) = provenance()

    assert (
        result.semantic_result
        is semantic
    )

    assert (
        result.focus_provenance
        is focus
    )

    assert (
        result.correlation
        is correlation
    )

    assert (
        result.semantic_target
        is semantic.revalidation
    )

    assert (
        result.selector
        is semantic.revalidation.selector
    )

    assert (
        correlation.selector
        == result.selector
    )

    assert (
        correlation.selector
        is not result.selector
    )

    assert (
        result.issued_at_monotonic
        == issued
    )


def test_lifetime_is_exact_shortest_source():
    (
        semantic,
        focus,
        correlation,
        _issued,
        result,
    ) = provenance()

    expected = min(
        semantic.revalidation.expires_at_monotonic,
        focus.binding.expires_at_monotonic,
        correlation.captured_at_monotonic
        + FOCUS_TARGET_CORRELATION_MAX_AGE_SECONDS,
    )

    assert (
        result.expires_at_monotonic
        == expected
    )


def test_correlation_must_follow_semantic_revalidation():
    (
        semantic,
        focus,
        _correlation,
        issued,
    ) = sources()

    correlation = matched_correlation(
        semantic,
        focus=focus,
        captured=(
            semantic.revalidation.revalidated_at_monotonic
            - 0.01
        ),
    )

    with pytest.raises(
        ValueError,
        match="predates semantic",
    ):
        compose_focus_target_provenance(
            semantic,
            focus,
            correlation,
            clock=lambda: issued,
        )


def test_correlation_must_follow_completed_focus_binding():
    (
        semantic,
        focus,
        _correlation,
        issued,
    ) = sources()

    captured = (
        focus.binding.bound_at_monotonic
        - 0.01
    )

    assert (
        captured
        >= semantic.revalidation.revalidated_at_monotonic
    )

    correlation = matched_correlation(
        semantic,
        focus=focus,
        captured=captured,
    )

    with pytest.raises(
        ValueError,
        match="predates trusted focus binding",
    ):
        compose_focus_target_provenance(
            semantic,
            focus,
            correlation,
            clock=lambda: issued,
        )


def test_correlation_cannot_be_from_future():
    (
        semantic,
        focus,
        _correlation,
        issued,
    ) = sources()

    correlation = matched_correlation(
        semantic,
        focus=focus,
        captured=(
            issued
            + 0.01
        ),
    )

    with pytest.raises(
        ValueError,
        match="future",
    ):
        compose_focus_target_provenance(
            semantic,
            focus,
            correlation,
            clock=lambda: issued,
        )


def test_application_identity_must_agree_across_all_roots():
    (
        semantic,
        focus,
        _correlation,
        issued,
    ) = sources()

    foreign = ApplicationIdentity(
        999,
        "other.app",
        "Other",
    )

    correlation = matched_correlation(
        semantic,
        focus=focus,
        captured=(
            max(
                semantic.revalidation.revalidated_at_monotonic,
                focus.binding.bound_at_monotonic,
            )
            + 0.01
        ),
        application=foreign,
    )

    with pytest.raises(
        ValueError,
        match="application identity",
    ):
        compose_focus_target_provenance(
            semantic,
            focus,
            correlation,
            clock=lambda: issued,
        )


def test_selector_must_equal_semantic_selector_by_value():
    (
        semantic,
        focus,
        _correlation,
        issued,
    ) = sources()

    changed = StructuredUITargetSelector(
        role="AXButton",
        text="Other",
    )

    correlation = matched_correlation(
        semantic,
        focus=focus,
        captured=(
            max(
                semantic.revalidation.revalidated_at_monotonic,
                focus.binding.bound_at_monotonic,
            )
            + 0.01
        ),
        selector=changed,
    )

    with pytest.raises(
        ValueError,
        match="different semantic selector",
    ):
        compose_focus_target_provenance(
            semantic,
            focus,
            correlation,
            clock=lambda: issued,
        )


def test_nonmatched_correlation_cannot_be_promoted():
    (
        semantic,
        focus,
        correlation,
        issued,
    ) = sources()

    mismatched = FocusTargetCorrelationResult(
        captured_at_monotonic=(
            correlation.captured_at_monotonic
        ),
        status=(
            CORRELATION_STATUS_MISMATCHED
        ),
        expected_application=(
            correlation.expected_application
        ),
        selector=correlation.selector,
        candidate_count=1,
        candidate=correlation.candidate,
        diagnostics=(
            MISMATCH_CODE,
        ),
    )

    with pytest.raises(
        ValueError,
        match="matched native correlation",
    ):
        compose_focus_target_provenance(
            semantic,
            focus,
            mismatched,
            clock=lambda: issued,
        )


def test_explicit_expiry_forgery_is_rejected():
    (
        semantic,
        focus,
        correlation,
        issued,
        good,
    ) = provenance()

    with pytest.raises(
        ValueError,
        match="lifetime",
    ):
        FocusTargetProvenance(
            semantic_result=semantic,
            focus_provenance=focus,
            correlation=correlation,
            issued_at_monotonic=issued,
            expires_at_monotonic=(
                good.expires_at_monotonic
                + 0.01
            ),
        )


def test_exact_active_store_round_trip():
    (
        _semantic,
        focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    store, _clock, _active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    assert (
        store.get(good)
        is good
    )

    assert len(store) == 1


def test_equal_value_top_level_reconstruction_cannot_substitute():
    (
        _semantic,
        focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    store, _clock, _active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    reconstructed = replace(
        good
    )

    assert reconstructed == good
    assert reconstructed is not good

    assert (
        store.get(
            reconstructed
        )
        is None
    )

    assert (
        store.get(good)
        is good
    )


def test_reconstructed_correlation_cannot_substitute_for_active_graph():
    (
        semantic,
        focus,
        correlation,
        issued,
        good,
    ) = provenance()

    store, _clock, _active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    reconstructed = replace(
        correlation
    )

    alternate = replace(
        good,
        correlation=reconstructed,
    )

    assert reconstructed == correlation
    assert reconstructed is not correlation

    assert (
        alternate.semantic_result
        is semantic
    )

    assert (
        store.get(alternate)
        is None
    )


def test_reconstructed_semantic_result_cannot_substitute_for_active_graph():
    (
        semantic,
        focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    store, _clock, _active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    reconstructed = replace(
        semantic
    )

    alternate = replace(
        good,
        semantic_result=reconstructed,
    )

    assert reconstructed == semantic
    assert reconstructed is not semantic

    assert (
        store.get(alternate)
        is None
    )


def test_reconstructed_focus_provenance_cannot_publish_as_active_source():
    (
        _semantic,
        focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    store, _clock, _active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    reconstructed = replace(
        focus
    )

    alternate = replace(
        good,
        focus_provenance=reconstructed,
    )

    assert reconstructed == focus
    assert reconstructed is not focus

    assert not store.publish(
        alternate
    )

    assert len(store) == 0


def test_active_8d1_focus_replacement_invalidates_provenance():
    (
        _semantic,
        focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    store, _clock, active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    active["focus"] = replace(
        focus
    )

    assert (
        store.get(good)
        is None
    )

    assert len(store) == 0


def test_focus_clear_invalidates_provenance():
    (
        _semantic,
        focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    store, _clock, active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    active["focus"] = None

    assert (
        store.get(good)
        is None
    )


def test_expiry_invalidates_store_entry():
    (
        _semantic,
        focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    store, clock, _active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    clock.now = (
        good.expires_at_monotonic
    )

    assert (
        store.get(good)
        is None
    )

    assert len(store) == 0


def test_clock_rollback_clears_and_fails_closed():
    (
        _semantic,
        focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    store, clock, _active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    clock.now = (
        issued
        - 0.01
    )

    with pytest.raises(
        FocusTargetProvenanceError,
        match="backward",
    ):
        store.get(good)

    assert len(store) == 0


def test_focus_lookup_failure_fails_closed_without_leaking_exception():
    (
        _semantic,
        _focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    def fail(
        _observation_id,
    ):
        raise RuntimeError(
            "SECRET"
        )

    store = FocusTargetProvenanceStore(
        focus_lookup=fail,
        clock=lambda: issued,
    )

    assert not store.publish(
        good
    )

    assert len(store) == 0


def test_get_requires_exact_top_level_object_type():
    (
        _semantic,
        focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    store, _clock, _active = store_for(
        focus,
        now=issued,
    )

    assert store.publish(good)

    with pytest.raises(
        TypeError
    ):
        store.get(
            object()
        )


def test_publish_requires_exact_provenance_type():
    store = FocusTargetProvenanceStore(
        focus_lookup=lambda _value: None,
        clock=lambda: 1.0,
    )

    with pytest.raises(
        TypeError
    ):
        store.publish(
            object()
        )


def test_store_has_no_latest_or_claim_fallback():
    store = FocusTargetProvenanceStore(
        focus_lookup=lambda _value: None,
        clock=lambda: 1.0,
    )

    assert not hasattr(
        store,
        "latest",
    )

    assert not hasattr(
        store,
        "claim",
    )

    assert not hasattr(
        store,
        "get_by_id",
    )


def test_provenance_is_immutable():
    (
        _semantic,
        _focus,
        _correlation,
        _issued,
        good,
    ) = provenance()

    with pytest.raises(
        FrozenInstanceError
    ):
        good.issued_at_monotonic = 999


def test_provenance_has_no_authority_surface():
    (
        _semantic,
        _focus,
        _correlation,
        _issued,
        good,
    ) = provenance()

    forbidden = (
        "allowed",
        "approved",
        "authorized",
        "permission",
        "attestation",
        "keyboard_authority",
        "text_authority",
        "semantic_target_verified",
        "execute",
        "type_text",
        "press_key",
        "click",
    )

    for name in forbidden:
        assert not hasattr(
            good,
            name,
        )


def test_no_dict_reconstruction_or_serialization_surface():
    assert not hasattr(
        FocusTargetProvenance,
        "from_dict",
    )

    assert not hasattr(
        FocusTargetProvenance,
        "to_dict",
    )


def test_module_has_no_native_permission_or_execution_surface():
    path = Path(
        __file__
    ).with_name(
        "focus_target_provenance.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    forbidden = (
        "ApplicationServices",
        "AppKit",
        "CoreFoundation",
        "CFEqual(",
        "AXUIElementSetAttributeValue",
        "AXUIElementPerformAction",
        "pyautogui",
        "computer_tools",
        "mission_service",
        "permissions",
    )

    for marker in forbidden:
        assert marker not in text


def test_invalid_clock_is_rejected():
    (
        semantic,
        focus,
        correlation,
        _issued,
    ) = sources()

    with pytest.raises(
        ValueError,
        match="clock",
    ):
        compose_focus_target_provenance(
            semantic,
            focus,
            correlation,
            clock=lambda: float(
                "nan"
            ),
        )


def test_noncallable_clock_is_rejected():
    (
        semantic,
        focus,
        correlation,
        _issued,
    ) = sources()

    with pytest.raises(
        TypeError,
        match="clock",
    ):
        compose_focus_target_provenance(
            semantic,
            focus,
            correlation,
            clock=None,
        )


def test_freshness_starts_at_issue_and_ends_at_exact_expiry():
    (
        _semantic,
        _focus,
        _correlation,
        issued,
        good,
    ) = provenance()

    assert not good.is_fresh(
        issued
        - 0.001
    )

    assert good.is_fresh(
        issued
    )

    midpoint = (
        issued
        + (
            good.expires_at_monotonic
            - issued
        )
        / 2
    )

    assert good.is_fresh(
        midpoint
    )

    assert not good.is_fresh(
        good.expires_at_monotonic
    )
