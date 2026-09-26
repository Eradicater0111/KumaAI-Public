from dataclasses import (
    FrozenInstanceError,
    replace,
)
from pathlib import Path

import pytest

from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation.contracts import (
    StructuredUIObservation,
    UIElementObservation,
    unavailable,
)
from app.ui_observation.focus_target_resolution import (
    AMBIGUOUS_CODE,
    CANDIDATE_STATUS_AMBIGUOUS,
    CANDIDATE_STATUS_RESOLVED,
    CANDIDATE_STATUS_UNKNOWN,
    FocusTargetCandidateResolutionResult,
    ResolvedFocusTargetCandidate,
    resolve_focus_target_candidate,
)
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)


APP = ApplicationIdentity(
    123,
    "test.app",
    "Example",
)


def element(
    number,
    *,
    role="AXTextField",
    title=None,
    description=None,
    enabled=True,
    focused=False,
    selected=False,
    x=10.0,
    y=20.0,
    width=200.0,
    height=30.0,
):
    return UIElementObservation(
        path=(
            number,
        ),
        owner_pid=123,
        role=role,
        subrole=None,
        title=title,
        description=description,
        enabled=enabled,
        focused=focused,
        selected=selected,
        position_x=x,
        position_y=y,
        width=width,
        height=height,
    )


def root_element():
    return UIElementObservation(
        path=(),
        owner_pid=123,
        role="AXApplication",
        subrole=None,
        title="Example",
        description=None,
        enabled=True,
        focused=False,
        selected=False,
        position_x=0.0,
        position_y=0.0,
        width=1000.0,
        height=800.0,
    )


def observation(
    *elements,
    status="available",
    diagnostics=(),
):
    return StructuredUIObservation(
        captured_at_monotonic=100.0,
        status=status,
        active_application=APP,
        elements=(
            root_element(),
            *elements,
        ),
        traversal_succeeded=True,
        diagnostics=diagnostics,
    )


def test_unique_semantic_candidate_resolves():
    target = element(
        0,
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                target
            ),
            StructuredUITargetSelector(
                role="AXTextField"
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_RESOLVED
    )

    assert result.resolved

    assert (
        result.resolution.element
        is target
    )

    assert (
        result.resolution.path
        == (
            0,
        )
    )

    assert (
        result.candidate_count
        == 1
    )

    assert (
        result.diagnostics
        == ()
    )


def test_multiple_same_role_candidates_are_ambiguous():
    result = (
        resolve_focus_target_candidate(
            observation(
                element(
                    0
                ),
                element(
                    1
                ),
                element(
                    2
                ),
            ),
            StructuredUITargetSelector(
                role="AXTextField"
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_AMBIGUOUS
    )

    assert not result.resolved

    assert (
        result.candidate_count
        == 3
    )

    assert (
        result.diagnostics
        == (
            AMBIGUOUS_CODE,
        )
    )


def test_focused_candidate_does_not_break_semantic_ambiguity():
    first = element(
        0,
        focused=False,
    )

    second = element(
        1,
        focused=True,
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                first,
                second,
            ),
            StructuredUITargetSelector(
                role="AXTextField"
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_AMBIGUOUS
    )

    assert (
        result.candidate_count
        == 2
    )

    assert result.resolution is None


def test_selected_candidate_does_not_break_semantic_ambiguity():
    first = element(
        0,
        selected=False,
    )

    second = element(
        1,
        selected=True,
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                first,
                second,
            ),
            StructuredUITargetSelector(
                role="AXTextField"
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_AMBIGUOUS
    )

    assert (
        result.candidate_count
        == 2
    )


def test_exact_semantic_text_can_independently_select_one_candidate():
    search = element(
        0,
        title="Search",
    )

    other = element(
        1,
        title="Command",
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                search,
                other,
            ),
            StructuredUITargetSelector(
                role="AXTextField",
                text="search",
            ),
        )
    )

    assert result.resolved

    assert (
        result.resolution.element
        is search
    )


def test_focus_never_overrides_wrong_semantic_text():
    wrong = element(
        0,
        title="Wrong",
        focused=True,
    )

    intended = element(
        1,
        title="Intended",
        focused=False,
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                wrong,
                intended,
            ),
            StructuredUITargetSelector(
                role="AXTextField",
                text="Intended",
            ),
        )
    )

    assert result.resolved

    assert (
        result.resolution.element
        is intended
    )

    assert (
        result.resolution.element
        is not wrong
    )


def test_require_enabled_rejects_known_disabled_candidate():
    disabled = element(
        0,
        enabled=False,
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                disabled
            ),
            StructuredUITargetSelector(
                role="AXTextField",
                require_enabled=True,
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_UNKNOWN
    )

    assert (
        result.diagnostics
        == (
            "no_eligible_candidate",
        )
    )


def test_unknown_required_enabled_state_is_not_guessed():
    candidate = element(
        0,
        enabled=None,
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                candidate
            ),
            StructuredUITargetSelector(
                role="AXTextField",
                require_enabled=True,
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_UNKNOWN
    )

    assert (
        result.candidate_count
        == 1
    )

    assert (
        result.diagnostics
        == (
            "candidate_eligibility_unknown",
        )
    )


def test_positive_area_requirement_is_independent_of_focus():
    focused_zero = element(
        0,
        focused=True,
        width=0.0,
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                focused_zero
            ),
            StructuredUITargetSelector(
                role="AXTextField",
                require_positive_area=True,
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_UNKNOWN
    )

    assert (
        result.diagnostics
        == (
            "no_eligible_candidate",
        )
    )


def test_incomplete_observation_cannot_establish_uniqueness():
    target = element(
        0,
        title="Search",
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                target,
                status="partial",
                diagnostics=(
                    "nodes_truncated",
                ),
            ),
            StructuredUITargetSelector(
                role="AXTextField",
                text="Search",
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_UNKNOWN
    )

    assert (
        result.diagnostics
        == (
            "observation_incomplete",
        )
    )


def test_no_semantic_match_is_unknown_not_focus_fallback():
    result = (
        resolve_focus_target_candidate(
            observation(
                element(
                    0,
                    role="AXButton",
                    focused=True,
                )
            ),
            StructuredUITargetSelector(
                role="AXTextField"
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_UNKNOWN
    )

    assert (
        result.diagnostics
        == (
            "no_semantic_match",
        )
    )


def test_unavailable_observation_is_unknown():
    result = (
        resolve_focus_target_candidate(
            unavailable(
                "collection_failed",
                100.0,
            ),
            StructuredUITargetSelector(
                role="AXTextField"
            ),
        )
    )

    assert (
        result.status
        == CANDIDATE_STATUS_UNKNOWN
    )

    assert (
        result.diagnostics
        == (
            "observation_unavailable",
        )
    )


def test_invalid_sources_are_structured_unknown():
    valid_observation = (
        observation(
            element(
                0
            )
        )
    )

    valid_selector = (
        StructuredUITargetSelector(
            role="AXTextField"
        )
    )

    first = (
        resolve_focus_target_candidate(
            object(),
            valid_selector,
        )
    )

    assert (
        first.diagnostics
        == (
            "invalid_observation",
        )
    )

    second = (
        resolve_focus_target_candidate(
            valid_observation,
            object(),
        )
    )

    assert (
        second.diagnostics
        == (
            "invalid_selector",
        )
    )


def test_resolved_candidate_preserves_exact_element_object():
    target = element(
        0,
        title="Search",
    )

    source = observation(
        target
    )

    selector = (
        StructuredUITargetSelector(
            role="AXTextField",
            text="Search",
        )
    )

    result = (
        resolve_focus_target_candidate(
            source,
            selector,
        )
    )

    assert result.resolved

    resolved = (
        result.resolution
    )

    assert (
        resolved.observation
        is source
    )

    assert (
        resolved.selector
        is selector
    )

    assert (
        resolved.element
        is target
    )


def test_equal_value_reconstructed_element_is_not_exact_source_object():
    target = element(
        0,
        title="Search",
    )

    source = observation(
        target
    )

    reconstructed = replace(
        target
    )

    assert (
        reconstructed
        == target
    )

    assert (
        reconstructed
        is not target
    )

    with pytest.raises(
        ValueError,
        match="exact element",
    ):
        ResolvedFocusTargetCandidate(
            observation=source,
            selector=(
                StructuredUITargetSelector(
                    role="AXTextField",
                    text="Search",
                )
            ),
            element=reconstructed,
        )


def test_candidate_evidence_is_immutable():
    target = element(
        0
    )

    result = (
        resolve_focus_target_candidate(
            observation(
                target
            ),
            StructuredUITargetSelector(
                role="AXTextField"
            ),
        )
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        result.candidate_count = 99

    with pytest.raises(
        FrozenInstanceError
    ):
        result.resolution.element = object()


def test_result_contract_rejects_forged_shapes():
    with pytest.raises(
        ValueError
    ):
        FocusTargetCandidateResolutionResult(
            status="made_up",
        )

    with pytest.raises(
        ValueError
    ):
        FocusTargetCandidateResolutionResult(
            status=(
                CANDIDATE_STATUS_RESOLVED
            ),
            resolution=None,
            candidate_count=1,
        )

    with pytest.raises(
        ValueError
    ):
        FocusTargetCandidateResolutionResult(
            status=(
                CANDIDATE_STATUS_AMBIGUOUS
            ),
            candidate_count=1,
            diagnostics=(
                AMBIGUOUS_CODE,
            ),
        )


def test_contract_has_no_focus_or_authority_selection_surface():
    resolved_fields = set(
        ResolvedFocusTargetCandidate
        .__dataclass_fields__
    )

    result_fields = set(
        FocusTargetCandidateResolutionResult
        .__dataclass_fields__
    )

    forbidden = {
        "focused",
        "focus_observation_id",
        "focus_attestation",
        "keyboard_authority",
        "authorized",
        "approved",
        "permission",
        "semantic_target_verified",
        "execute",
        "type_text",
        "text_authority",
    }

    assert not (
        resolved_fields
        & forbidden
    )

    assert not (
        result_fields
        & forbidden
    )


def test_module_has_no_native_or_execution_surface():
    path = Path(
        __file__
    ).with_name(
        "focus_target_resolution.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    forbidden = (
        "ApplicationServices",
        "AppKit",
        "CoreFoundation",
        "CFEqual",
        "AXUIElement",
        "pyautogui",
        "computer_tools",
        "mission_service",
        "permissions",
    )

    for marker in forbidden:
        assert marker not in text

def test_direct_constructor_rejects_ambiguous_semantic_source():
    from app.ui_observation.focus_target_resolution import (
        ResolvedFocusTargetCandidate,
    )

    first = element(
        0,
        title="Search",
    )

    second = element(
        1,
        title="Search",
    )

    source = observation(
        first,
        second,
    )

    selector = (
        StructuredUITargetSelector(
            text="Search"
        )
    )

    with pytest.raises(
        ValueError,
        match="unique",
    ):
        ResolvedFocusTargetCandidate(
            observation=source,
            selector=selector,
            element=first,
        )


def test_direct_constructor_rejects_wrong_semantic_exact_member():
    from app.ui_observation.focus_target_resolution import (
        ResolvedFocusTargetCandidate,
    )

    wanted = element(
        0,
        title="Search",
    )

    wrong = element(
        1,
        title="Other",
    )

    source = observation(
        wanted,
        wrong,
    )

    selector = (
        StructuredUITargetSelector(
            text="Search"
        )
    )

    with pytest.raises(
        ValueError,
        match="unique",
    ):
        ResolvedFocusTargetCandidate(
            observation=source,
            selector=selector,
            element=wrong,
        )


def test_direct_constructor_rejects_unknown_required_eligibility():
    from app.ui_observation.focus_target_resolution import (
        ResolvedFocusTargetCandidate,
    )

    uncertain = element(
        0,
        enabled=None,
    )

    source = observation(
        uncertain,
    )

    selector = (
        StructuredUITargetSelector(
            role="AXTextField",
            require_enabled=True,
        )
    )

    with pytest.raises(
        ValueError,
        match="unique",
    ):
        ResolvedFocusTargetCandidate(
            observation=source,
            selector=selector,
            element=uncertain,
        )


def test_direct_constructor_rejects_blocked_incomplete_source():
    from app.ui_observation.focus_target_resolution import (
        ResolvedFocusTargetCandidate,
    )

    target = element(
        0,
        title="Search",
    )

    source = observation(
        target,
        status="partial",
        diagnostics=(
            "nodes_truncated",
        ),
    )

    selector = (
        StructuredUITargetSelector(
            role="AXTextField",
            text="Search",
        )
    )

    with pytest.raises(
        ValueError,
        match="uniqueness",
    ):
        ResolvedFocusTargetCandidate(
            observation=source,
            selector=selector,
            element=target,
        )


def test_direct_constructor_accepts_only_valid_unique_exact_target():
    from app.ui_observation.focus_target_resolution import (
        ResolvedFocusTargetCandidate,
    )

    target = element(
        0,
        title="Search",
    )

    other = element(
        1,
        role="AXButton",
        title="Cancel",
    )

    source = observation(
        target,
        other,
    )

    selector = (
        StructuredUITargetSelector(
            role="AXTextField",
            text="Search",
        )
    )

    resolved = (
        ResolvedFocusTargetCandidate(
            observation=source,
            selector=selector,
            element=target,
        )
    )

    assert resolved.observation is source
    assert resolved.selector is selector
    assert resolved.element is target
