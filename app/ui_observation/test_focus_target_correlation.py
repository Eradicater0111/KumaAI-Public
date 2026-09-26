from dataclasses import (
    FrozenInstanceError,
)
from pathlib import Path

import pytest

from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation.focus_target_correlation import (
    AMBIGUOUS_CODE,
    CORRELATION_STATUS_AMBIGUOUS,
    CORRELATION_STATUS_MATCHED,
    CORRELATION_STATUS_MISMATCHED,
    CORRELATION_STATUS_UNKNOWN,
    FocusTargetCorrelationResult,
    FocusTargetSemanticCandidate,
    MISMATCH_CODE,
    collect_focus_target_correlation,
    focus_target_correlation_from_dict,
    focus_target_correlation_to_dict,
)
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)


APP = ApplicationIdentity(
    123,
    "test.app",
    "Example",
)

OTHER = ApplicationIdentity(
    456,
    "other.app",
    "Other",
)


class Provider:
    def __init__(
        self,
    ):
        self.root = object()
        self.target = object()
        self.other = object()

        self.application = APP
        self.frontmost_sequence = None
        self.frontmost_reads = 0

        self.trusted = True

        self.children = {
            self.root: [
                self.target,
            ],
            self.target: [],
            self.other: [],
        }

        self.nodes = {
            self.root: {
                "role": "AXApplication",
                "subrole": None,
                "title": "Example",
                "description": None,
                "enabled": True,
                "position_x": 0.0,
                "position_y": 0.0,
                "width": 1000.0,
                "height": 800.0,
            },
            self.target: {
                "role": "AXTextField",
                "subrole": None,
                "title": "Search",
                "description": None,
                "enabled": True,
                "position_x": 10.0,
                "position_y": 20.0,
                "width": 200.0,
                "height": 30.0,
            },
            self.other: {
                "role": "AXButton",
                "subrole": None,
                "title": "Other",
                "description": None,
                "enabled": True,
                "position_x": 250.0,
                "position_y": 20.0,
                "width": 100.0,
                "height": 30.0,
            },
        }

        self.owner = {
            self.root: 123,
            self.target: 123,
            self.other: 123,
        }

        self.focus_sequence = [
            self.target,
            self.target,
        ]

        self.focus_reads = 0
        self.same_calls = []

        self.truncated = set()
        self.read_failure = set()
        self.children_failure = set()

        self.identity_override = {}

    def accessibility_trusted(
        self,
    ):
        return self.trusted

    def frontmost_application(
        self,
    ):
        self.frontmost_reads += 1

        if self.frontmost_sequence is None:
            return self.application

        index = min(
            self.frontmost_reads - 1,
            len(
                self.frontmost_sequence
            )
            - 1,
        )

        return self.frontmost_sequence[
            index
        ]

    def application_element(
        self,
        pid,
    ):
        assert pid == 123
        return self.root

    def element_pid(
        self,
        element,
    ):
        return self.owner.get(
            element
        )

    def read_target_node(
        self,
        element,
        selector,
    ):
        assert (
            type(selector)
            is StructuredUITargetSelector
        )

        if element in self.read_failure:
            raise RuntimeError(
                "private"
            )

        return dict(
            self.nodes[
                element
            ]
        )

    def children_for_element(
        self,
        element,
        limit,
    ):
        if element in self.children_failure:
            raise RuntimeError(
                "private"
            )

        children = list(
            self.children.get(
                element,
                []
            )
        )

        return (
            children[
                :limit
            ],
            (
                element in self.truncated
                or len(children)
                > limit
            ),
        )

    def element_identity(
        self,
        element,
    ):
        return self.identity_override.get(
            element,
            (
                "object",
                id(
                    element
                ),
            ),
        )

    def focused_element(
        self,
        application_element,
    ):
        assert (
            application_element
            is self.root
        )

        self.focus_reads += 1

        index = min(
            self.focus_reads - 1,
            len(
                self.focus_sequence
            )
            - 1,
        )

        value = self.focus_sequence[
            index
        ]

        if isinstance(
            value,
            BaseException,
        ):
            raise value

        return value

    def same_element(
        self,
        left,
        right,
    ):
        self.same_calls.append(
            (
                left,
                right,
            )
        )

        return left is right


def collect(
    provider=None,
    *,
    selector=None,
    **kwargs,
):
    return (
        collect_focus_target_correlation(
            provider
            or Provider(),
            expected_application=APP,
            selector=(
                selector
                or StructuredUITargetSelector(
                    role="AXTextField",
                    text="Search",
                )
            ),
            clock=lambda: 100.0,
            **kwargs,
        )
    )


def test_unique_semantic_candidate_then_exact_focus_matches():
    provider = Provider()

    result = collect(
        provider
    )

    assert (
        result.status
        == CORRELATION_STATUS_MATCHED
    )

    assert result.matched

    assert (
        result.candidate_count
        == 1
    )

    assert (
        result.candidate.path
        == (
            0,
        )
    )

    assert (
        result.candidate.role
        == "AXTextField"
    )

    assert (
        result.diagnostics
        == ()
    )

    assert (
        provider.focus_reads
        == 2
    )


def test_unique_semantic_candidate_can_be_focus_mismatch():
    provider = Provider()

    provider.children[
        provider.root
    ].append(
        provider.other
    )

    provider.focus_sequence = [
        provider.other,
        provider.other,
    ]

    result = collect(
        provider
    )

    assert (
        result.status
        == CORRELATION_STATUS_MISMATCHED
    )

    assert not result.matched

    assert (
        result.candidate_count
        == 1
    )

    assert (
        result.candidate.title
        == "Search"
    )

    assert (
        result.diagnostics
        == (
            MISMATCH_CODE,
        )
    )


def test_ambiguous_semantics_never_consult_focus():
    provider = Provider()

    second = object()

    provider.children[
        provider.root
    ].append(
        second
    )

    provider.children[
        second
    ] = []

    provider.owner[
        second
    ] = 123

    provider.nodes[
        second
    ] = dict(
        provider.nodes[
            provider.target
        ]
    )

    provider.nodes[
        second
    ][
        "title"
    ] = "Second"

    result = collect(
        provider,
        selector=(
            StructuredUITargetSelector(
                role="AXTextField"
            )
        ),
    )

    assert (
        result.status
        == CORRELATION_STATUS_AMBIGUOUS
    )

    assert (
        result.candidate_count
        == 2
    )

    assert (
        result.diagnostics
        == (
            AMBIGUOUS_CODE,
        )
    )

    assert (
        provider.focus_reads
        == 0
    )

    assert (
        provider.same_calls
        == []
    )


def test_focused_semantic_candidate_cannot_break_ambiguity():
    provider = Provider()

    second = object()

    provider.children[
        provider.root
    ].append(
        second
    )

    provider.children[
        second
    ] = []

    provider.owner[
        second
    ] = 123

    provider.nodes[
        second
    ] = {
        "role": "AXTextField",
        "subrole": None,
        "title": "Second",
        "description": None,
        "enabled": True,
        "position_x": 10.0,
        "position_y": 60.0,
        "width": 200.0,
        "height": 30.0,
    }

    provider.focus_sequence = [
        second,
        second,
    ]

    result = collect(
        provider,
        selector=(
            StructuredUITargetSelector(
                role="AXTextField"
            )
        ),
    )

    assert (
        result.status
        == CORRELATION_STATUS_AMBIGUOUS
    )

    assert (
        provider.focus_reads
        == 0
    )


def test_no_semantic_match_never_consults_focus():
    provider = Provider()

    result = collect(
        provider,
        selector=(
            StructuredUITargetSelector(
                role="AXTextArea"
            )
        ),
    )

    assert (
        result.status
        == CORRELATION_STATUS_UNKNOWN
    )

    assert (
        result.diagnostics
        == (
            "no_semantic_match",
        )
    )

    assert provider.focus_reads == 0
    assert provider.same_calls == []


def test_unknown_required_enabled_state_never_reaches_focus():
    provider = Provider()

    provider.nodes[
        provider.target
    ][
        "enabled"
    ] = None

    result = collect(
        provider,
        selector=(
            StructuredUITargetSelector(
                role="AXTextField",
                text="Search",
                require_enabled=True,
            )
        ),
    )

    assert (
        result.diagnostics
        == (
            "candidate_eligibility_unknown",
        )
    )

    assert (
        result.candidate_count
        == 1
    )

    assert provider.focus_reads == 0


def test_known_disabled_target_is_not_focus_selected():
    provider = Provider()

    provider.nodes[
        provider.target
    ][
        "enabled"
    ] = False

    result = collect(
        provider,
        selector=(
            StructuredUITargetSelector(
                role="AXTextField",
                text="Search",
                require_enabled=True,
            )
        ),
    )

    assert (
        result.diagnostics
        == (
            "no_eligible_candidate",
        )
    )

    assert provider.focus_reads == 0


def test_positive_area_unknown_does_not_reach_focus():
    provider = Provider()

    for name in (
        "position_x",
        "position_y",
        "width",
        "height",
    ):
        provider.nodes[
            provider.target
        ][
            name
        ] = None

    result = collect(
        provider,
        selector=(
            StructuredUITargetSelector(
                role="AXTextField",
                text="Search",
                require_positive_area=True,
            )
        ),
    )

    assert (
        result.diagnostics
        == (
            "candidate_eligibility_unknown",
        )
    )

    assert provider.focus_reads == 0


def test_truncated_tree_is_unknown_before_focus():
    provider = Provider()

    provider.truncated.add(
        provider.root
    )

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "observation_incomplete",
        )
    )

    assert provider.focus_reads == 0


def test_node_read_failure_is_unknown_before_focus():
    provider = Provider()

    provider.read_failure.add(
        provider.target
    )

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "observation_incomplete",
        )
    )

    assert provider.focus_reads == 0


def test_children_failure_is_unknown_before_focus():
    provider = Provider()

    provider.children_failure.add(
        provider.root
    )

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "observation_incomplete",
        )
    )

    assert provider.focus_reads == 0


def test_duplicate_native_identity_blocks_semantic_proof():
    provider = Provider()

    second = object()

    provider.children[
        provider.root
    ].append(
        second
    )

    provider.children[
        second
    ] = []

    provider.owner[
        second
    ] = 123

    provider.nodes[
        second
    ] = {
        "role": "AXButton",
        "subrole": None,
        "title": "Other",
        "description": None,
        "enabled": True,
        "position_x": 1.0,
        "position_y": 1.0,
        "width": 10.0,
        "height": 10.0,
    }

    provider.identity_override[
        second
    ] = provider.element_identity(
        provider.target
    )

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "observation_incomplete",
        )
    )

    assert provider.focus_reads == 0


def test_foreign_tree_element_blocks_semantic_proof():
    provider = Provider()

    provider.owner[
        provider.target
    ] = 999

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "observation_incomplete",
        )
    )

    assert provider.focus_reads == 0


def test_node_bound_blocks_semantic_proof_before_focus():
    provider = Provider()

    result = collect(
        provider,
        max_nodes=1,
    )

    assert (
        result.diagnostics
        == (
            "observation_incomplete",
        )
    )

    assert provider.focus_reads == 0


def test_missing_focus_after_unique_target_is_unknown():
    provider = Provider()

    provider.focus_sequence = [
        None,
    ]

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "focused_element_unavailable",
        )
    )


def test_foreign_focus_is_rejected():
    provider = Provider()

    provider.owner[
        provider.other
    ] = 999

    provider.focus_sequence = [
        provider.other,
        provider.other,
    ]

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "focused_element_foreign",
        )
    )


def test_focus_read_exception_fails_closed():
    provider = Provider()

    provider.focus_sequence = [
        RuntimeError(
            "private"
        ),
    ]

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "focused_element_read_failed",
        )
    )


def test_focus_change_between_reads_fails_closed():
    provider = Provider()

    provider.children[
        provider.root
    ].append(
        provider.other
    )

    provider.focus_sequence = [
        provider.target,
        provider.other,
    ]

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "focus_changed_during_collection",
        )
    )


def test_unknown_native_identity_fails_closed():
    provider = Provider()

    def unknown_identity(
        left,
        right,
    ):
        provider.same_calls.append(
            (
                left,
                right,
            )
        )

        return None

    provider.same_element = (
        unknown_identity
    )

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "focus_identity_unavailable",
        )
    )


def test_frontmost_application_change_before_focus_blocks_correlation():
    provider = Provider()

    provider.frontmost_sequence = [
        APP,
        OTHER,
    ]

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "active_application_changed",
        )
    )

    assert provider.focus_reads == 0


def test_frontmost_application_change_after_focus_blocks_result():
    provider = Provider()

    provider.frontmost_sequence = [
        APP,
        APP,
        OTHER,
    ]

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "active_application_changed",
        )
    )


def test_accessibility_permission_failure_blocks_before_tree():
    provider = Provider()

    provider.trusted = False

    result = collect(
        provider
    )

    assert (
        result.diagnostics
        == (
            "accessibility_permission_denied",
        )
    )

    assert provider.focus_reads == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "max_nodes": 0,
        },
        {
            "max_nodes": 1025,
        },
        {
            "max_depth": -1,
        },
        {
            "max_depth": 17,
        },
        {
            "max_children": 0,
        },
        {
            "max_children": 129,
        },
    ],
)
def test_dedicated_correlation_bounds_are_hard(
    kwargs,
):
    with pytest.raises(
        ValueError
    ):
        collect(
            **kwargs
        )


def test_invalid_clock_is_rejected():
    with pytest.raises(
        ValueError,
        match="clock",
    ):
        collect_focus_target_correlation(
            Provider(),
            expected_application=APP,
            selector=(
                StructuredUITargetSelector(
                    role="AXTextField"
                )
            ),
            clock=lambda: float(
                "nan"
            ),
        )


def test_candidate_contract_has_no_focus_or_native_identity_fields():
    fields = set(
        FocusTargetSemanticCandidate
        .__dataclass_fields__
    )

    forbidden = {
        "focused",
        "selected",
        "native_element",
        "native_target",
        "ax_element",
        "element_ref",
        "focus_observation_id",
        "keyboard_authority",
        "permission",
        "authorized",
        "execute",
        "type_text",
    }

    assert not (
        fields
        & forbidden
    )


def test_result_contract_has_no_authority_surface():
    fields = set(
        FocusTargetCorrelationResult
        .__dataclass_fields__
    )

    forbidden = {
        "keyboard_authority",
        "text_authority",
        "permission",
        "authorized",
        "approved",
        "semantic_target_verified",
        "execute",
        "type_text",
    }

    assert not (
        fields
        & forbidden
    )


def test_correlation_evidence_is_immutable():
    result = collect()

    with pytest.raises(
        FrozenInstanceError
    ):
        result.status = (
            CORRELATION_STATUS_UNKNOWN
        )

    with pytest.raises(
        FrozenInstanceError
    ):
        result.candidate.role = "AXButton"


def test_result_contract_rejects_forged_matched_shape():
    candidate = FocusTargetSemanticCandidate(
        path=(
            0,
        ),
        owner_pid=123,
        role="AXTextField",
        subrole=None,
        title="Search",
        description=None,
        enabled=True,
        position_x=10.0,
        position_y=20.0,
        width=100.0,
        height=30.0,
    )

    with pytest.raises(
        ValueError
    ):
        FocusTargetCorrelationResult(
            captured_at_monotonic=100.0,
            status=(
                CORRELATION_STATUS_MATCHED
            ),
            expected_application=APP,
            selector=(
                StructuredUITargetSelector(
                    role="AXTextField"
                )
            ),
            candidate_count=2,
            candidate=candidate,
            diagnostics=(),
        )


def test_module_has_no_native_import_or_execution_surface():
    path = Path(
        __file__
    ).with_name(
        "focus_target_correlation.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    forbidden = (
        "import ApplicationServices",
        "import AppKit",
        "import CoreFoundation",
        "pyautogui",
        "computer_tools",
        "mission_service",
        "AXUIElementSetAttributeValue",
        "AXUIElementPerformAction",
    )

    for marker in forbidden:
        assert marker not in text

def test_wire_round_trip_preserves_matched_evidence():
    result = collect()

    payload = (
        focus_target_correlation_to_dict(
            result
        )
    )

    restored = (
        focus_target_correlation_from_dict(
            payload
        )
    )

    assert restored == result
    assert restored is not result
    assert (
        restored.candidate
        == result.candidate
    )
    assert (
        restored.candidate
        is not result.candidate
    )


def test_wire_round_trip_preserves_ambiguous_result():
    provider = Provider()

    second = object()

    provider.children[
        provider.root
    ].append(
        second
    )

    provider.children[
        second
    ] = []

    provider.owner[
        second
    ] = 123

    provider.nodes[
        second
    ] = dict(
        provider.nodes[
            provider.target
        ]
    )

    result = collect(
        provider,
        selector=(
            StructuredUITargetSelector(
                role="AXTextField"
            )
        ),
    )

    assert (
        result.status
        == CORRELATION_STATUS_AMBIGUOUS
    )

    payload = (
        focus_target_correlation_to_dict(
            result
        )
    )

    restored = (
        focus_target_correlation_from_dict(
            payload
        )
    )

    assert restored == result
    assert restored.candidate is None


def test_wire_payload_contains_no_native_identity():
    result = collect()

    payload = (
        focus_target_correlation_to_dict(
            result
        )
    )

    rendered = repr(
        payload
    )

    forbidden = (
        "AXUIElementRef",
        "native_element",
        "native_target",
        "element_ref",
        "CFEqual",
        "object at 0x",
    )

    for marker in forbidden:
        assert marker not in rendered


def test_wire_rejects_unknown_top_level_field():
    payload = (
        focus_target_correlation_to_dict(
            collect()
        )
    )

    payload[
        "forged"
    ] = True

    with pytest.raises(
        ValueError,
        match="fields",
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_rejects_missing_top_level_field():
    payload = (
        focus_target_correlation_to_dict(
            collect()
        )
    )

    del payload[
        "status"
    ]

    with pytest.raises(
        ValueError,
        match="fields",
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_rejects_unknown_selector_field():
    payload = (
        focus_target_correlation_to_dict(
            collect()
        )
    )

    payload[
        "selector"
    ][
        "focused"
    ] = True

    with pytest.raises(
        ValueError,
        match="Selector wire payload fields",
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_rejects_unknown_candidate_field():
    payload = (
        focus_target_correlation_to_dict(
            collect()
        )
    )

    payload[
        "candidate"
    ][
        "native_identity"
    ] = "forged"

    with pytest.raises(
        ValueError,
        match="Candidate wire payload fields",
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_rejects_non_boolean_selector_requirement():
    payload = (
        focus_target_correlation_to_dict(
            collect()
        )
    )

    payload[
        "selector"
    ][
        "require_enabled"
    ] = 1

    with pytest.raises(
        ValueError,
        match="selector wire boolean",
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_rejects_non_integer_candidate_path():
    payload = (
        focus_target_correlation_to_dict(
            collect()
        )
    )

    payload[
        "candidate"
    ][
        "path"
    ] = [
        0,
        "1",
    ]

    with pytest.raises(
        ValueError,
        match="candidate wire path",
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_rejects_duplicate_diagnostics():
    result = collect(
        Provider(),
        selector=(
            StructuredUITargetSelector(
                role="AXTextArea"
            )
        ),
    )

    payload = (
        focus_target_correlation_to_dict(
            result
        )
    )

    code = payload[
        "diagnostics"
    ][
        0
    ]

    payload[
        "diagnostics"
    ] = [
        code,
        code,
    ]

    with pytest.raises(
        ValueError,
        match="diagnostics",
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_cannot_forge_matched_result_without_candidate():
    payload = (
        focus_target_correlation_to_dict(
            collect()
        )
    )

    payload[
        "candidate"
    ] = None

    with pytest.raises(
        ValueError
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_codec_has_no_authority_fields():
    result = collect()

    payload = (
        focus_target_correlation_to_dict(
            result
        )
    )

    forbidden = {
        "keyboard_authority",
        "text_authority",
        "permission",
        "authorized",
        "approved",
        "semantic_target_verified",
        "execute",
        "type_text",
        "focused",
        "selected",
    }

    assert not (
        set(
            payload
        )
        & forbidden
    )

    assert not (
        set(
            payload[
                "selector"
            ]
        )
        & forbidden
    )

    assert not (
        set(
            payload[
                "candidate"
            ]
        )
        & forbidden
    )

def test_wire_rejects_candidate_with_foreign_owner_pid():
    payload = (
        focus_target_correlation_to_dict(
            collect()
        )
    )

    payload[
        "candidate"
    ][
        "owner_pid"
    ] = 999

    with pytest.raises(
        ValueError,
        match="semantic source contract",
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_rejects_candidate_that_no_longer_matches_selector():
    payload = (
        focus_target_correlation_to_dict(
            collect()
        )
    )

    payload[
        "candidate"
    ][
        "title"
    ] = "Not Search"

    with pytest.raises(
        ValueError,
        match="semantic source contract",
    ):
        focus_target_correlation_from_dict(
            payload
        )


def test_wire_rejects_candidate_that_no_longer_meets_eligibility():
    provider = Provider()

    result = collect(
        provider,
        selector=(
            StructuredUITargetSelector(
                role="AXTextField",
                text="Search",
                require_enabled=True,
            )
        ),
    )

    payload = (
        focus_target_correlation_to_dict(
            result
        )
    )

    payload[
        "candidate"
    ][
        "enabled"
    ] = False

    with pytest.raises(
        ValueError,
        match="semantic source contract",
    ):
        focus_target_correlation_from_dict(
            payload
        )
