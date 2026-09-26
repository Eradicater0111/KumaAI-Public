from __future__ import annotations

import ast
from dataclasses import (
    FrozenInstanceError,
    fields,
)
from pathlib import Path

import pytest

from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
)
from app.realtime.runtime_trigger import (
    RealtimeTriggerProposal,
)
from app.realtime.trigger_policy import (
    RealtimeTriggerEligibilityDecision,
    RealtimeTriggerEligibilityStatus,
)
from app.realtime.trigger_request import (
    MAX_TRIGGER_REQUEST_REASON_CHARS,
    REALTIME_TRIGGER_REQUEST_AUTHORITY_NONE,
    RealtimeTriggerRequest,
    create_trigger_request,
)


ROOT = Path(__file__).resolve().parents[2]

MODULE = (
    ROOT
    / "app/realtime/trigger_request.py"
)

TWO_A = (
    ROOT
    / "app/realtime/runtime_trigger.py"
)

TWO_B = (
    ROOT
    / "app/realtime/trigger_policy.py"
)

TWO_A_TEST = (
    ROOT
    / "app/realtime/test_realtime_2a_runtime_trigger_boundary.py"
)

TWO_B_TEST = (
    ROOT
    / "app/realtime/test_realtime_2b_trigger_policy.py"
)

V1_REGRESSION = (
    ROOT
    / "app/realtime/test_realtime_v1_architecture_regression.py"
)


def _proposal(
    *,
    proposal_id: str = "rtp-test",
    kind: str = "weather.current",
    authority: str = "NONE",
) -> RealtimeTriggerProposal:
    proposal = object.__new__(
        RealtimeTriggerProposal
    )

    object.__setattr__(
        proposal,
        "proposal_id",
        proposal_id,
    )
    object.__setattr__(
        proposal,
        "kind",
        kind,
    )
    object.__setattr__(
        proposal,
        "level",
        RealtimeRelevanceLevel.HIGH,
    )
    object.__setattr__(
        proposal,
        "score",
        0.9,
    )
    object.__setattr__(
        proposal,
        "reason",
        "precipitation started",
    )
    object.__setattr__(
        proposal,
        "authority",
        authority,
    )

    return proposal


def _decision(
    *,
    proposal_id: str = "rtp-test",
    status: RealtimeTriggerEligibilityStatus = (
        RealtimeTriggerEligibilityStatus.ELIGIBLE
    ),
    reason: str = (
        "proposal satisfies the explicit caller-supplied relevance thresholds"
    ),
    authority: str = "NONE",
) -> RealtimeTriggerEligibilityDecision:
    decision = object.__new__(
        RealtimeTriggerEligibilityDecision
    )

    object.__setattr__(
        decision,
        "proposal_id",
        proposal_id,
    )
    object.__setattr__(
        decision,
        "status",
        status,
    )
    object.__setattr__(
        decision,
        "reason",
        reason,
    )
    object.__setattr__(
        decision,
        "authority",
        authority,
    )

    return decision


def _field_names(
    cls,
) -> tuple[str, ...]:
    return tuple(
        item.name
        for item in fields(
            cls
        )
    )


def _imports(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    result = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            result.update(
                alias.name
                for alias in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            result.add(
                node.module
            )

    return result


def test_2c_files_and_frozen_dependencies_exist():
    assert MODULE.is_file()
    assert TWO_A.is_file()
    assert TWO_B.is_file()
    assert TWO_A_TEST.is_file()
    assert TWO_B_TEST.is_file()
    assert V1_REGRESSION.is_file()


def test_request_authority_constant_is_none():
    assert (
        REALTIME_TRIGGER_REQUEST_AUTHORITY_NONE
        == "NONE"
    )


def test_request_surface_is_privacy_minimized():
    assert _field_names(
        RealtimeTriggerRequest
    ) == (
        "request_id",
        "proposal_id",
        "kind",
        "reason",
        "authority",
    )


def test_request_exposes_no_execution_or_presentation_fields():
    forbidden = {
        "tool",
        "tool_name",
        "arguments",
        "command",
        "permission",
        "confirmation",
        "execute",
        "executor",
        "callback",
        "mission",
        "retry",
        "resume",
        "wake",
        "notify",
        "notification",
        "surface",
        "status_text",
        "verified",
        "verified_complete",
        "fact",
        "previous_fact",
        "value",
        "location",
        "message",
        "user_message",
    }

    assert set(
        _field_names(
            RealtimeTriggerRequest
        )
    ).isdisjoint(
        forbidden
    )


def test_request_is_frozen():
    request = create_trigger_request(
        _proposal(),
        _decision(),
    )

    assert request is not None

    with pytest.raises(
        FrozenInstanceError
    ):
        request.kind = "other"


def test_request_rejects_non_none_authority():
    with pytest.raises(
        ValueError,
        match="permanently NONE",
    ):
        RealtimeTriggerRequest(
            request_id="rtr-test",
            proposal_id="rtp-test",
            kind="weather.current",
            reason="eligible",
            authority="USER",
        )


def test_projection_rejects_non_proposal_input():
    with pytest.raises(
        TypeError,
        match="RealtimeTriggerProposal",
    ):
        create_trigger_request(
            object(),
            _decision(),
        )


def test_projection_rejects_non_decision_input():
    with pytest.raises(
        TypeError,
        match="RealtimeTriggerEligibilityDecision",
    ):
        create_trigger_request(
            _proposal(),
            object(),
        )


def test_projection_rejects_forged_proposal_authority():
    with pytest.raises(
        ValueError,
        match="RealtimeTriggerProposal authority",
    ):
        create_trigger_request(
            _proposal(
                authority="USER",
            ),
            _decision(),
        )


def test_projection_rejects_forged_decision_authority():
    with pytest.raises(
        ValueError,
        match="EligibilityDecision authority",
    ):
        create_trigger_request(
            _proposal(),
            _decision(
                authority="USER",
            ),
        )


def test_projection_rejects_mismatched_identity():
    with pytest.raises(
        ValueError,
        match="match the proposal identity",
    ):
        create_trigger_request(
            _proposal(
                proposal_id="rtp-one",
            ),
            _decision(
                proposal_id="rtp-two",
            ),
        )


def test_ineligible_decision_produces_no_request():
    result = create_trigger_request(
        _proposal(),
        _decision(
            status=(
                RealtimeTriggerEligibilityStatus.INELIGIBLE
            ),
            reason="score below explicit minimum",
        ),
    )

    assert result is None


def test_eligible_decision_produces_request():
    request = create_trigger_request(
        _proposal(),
        _decision(),
    )

    assert request is not None
    assert (
        request.proposal_id
        == "rtp-test"
    )
    assert (
        request.kind
        == "weather.current"
    )
    assert (
        request.authority
        == "NONE"
    )


def test_request_identity_is_deterministic():
    first = create_trigger_request(
        _proposal(),
        _decision(),
    )
    second = create_trigger_request(
        _proposal(),
        _decision(),
    )

    assert first is not None
    assert second is not None
    assert (
        first.request_id
        == second.request_id
    )


def test_request_identity_changes_with_proposal_identity():
    first = create_trigger_request(
        _proposal(
            proposal_id="rtp-one",
        ),
        _decision(
            proposal_id="rtp-one",
        ),
    )
    second = create_trigger_request(
        _proposal(
            proposal_id="rtp-two",
        ),
        _decision(
            proposal_id="rtp-two",
        ),
    )

    assert first is not None
    assert second is not None
    assert (
        first.request_id
        != second.request_id
    )


def test_request_reason_is_normalized_and_bounded():
    request = create_trigger_request(
        _proposal(),
        _decision(
            reason=(
                "  eligible   for   caller review  "
                + ("x" * 400)
            ),
        ),
    )

    assert request is not None
    assert "  " not in request.reason
    assert (
        len(
            request.reason
        )
        <= MAX_TRIGGER_REQUEST_REASON_CHARS
    )


def test_request_does_not_copy_score_or_level():
    request = create_trigger_request(
        _proposal(),
        _decision(),
    )

    assert request is not None
    assert not hasattr(
        request,
        "score",
    )
    assert not hasattr(
        request,
        "level",
    )


def test_request_does_not_copy_raw_fact_or_previous_fact():
    request = create_trigger_request(
        _proposal(),
        _decision(),
    )

    assert request is not None
    assert not hasattr(
        request,
        "fact",
    )
    assert not hasattr(
        request,
        "previous_fact",
    )


def test_2c_module_imports_only_realtime_dependencies_from_app():
    app_imports = {
        module
        for module in _imports(
            MODULE
        )
        if module.startswith(
            "app."
        )
    }

    assert app_imports == {
        "app.realtime.runtime_trigger",
        "app.realtime.trigger_policy",
    }


def test_2c_module_does_not_import_agent_ui_or_tools():
    for module in _imports(
        MODULE
    ):
        assert not module.startswith(
            (
                "app.agent",
                "app.ui",
                "app.tools",
            )
        ), module


def test_2c_module_has_no_network_or_persistence_dependency():
    roots = {
        module.split(
            ".",
            1,
        )[0]
        for module in _imports(
            MODULE
        )
    }

    assert roots.isdisjoint(
        {
            "httpx",
            "requests",
            "urllib",
            "socket",
            "aiohttp",
            "websockets",
            "sqlite3",
            "sqlalchemy",
            "shelve",
        }
    )


def test_2c_module_has_no_background_execution_primitive():
    source = MODULE.read_text()

    for forbidden in (
        "threading.Thread",
        "Thread(",
        "QThread",
        "asyncio.create_task",
        "create_task(",
        "while True",
        "run_forever(",
        "Timer(",
        "QTimer",
        "daemon=",
    ):
        assert forbidden not in source


def test_2c_module_has_no_runtime_side_effect_calls():
    source = MODULE.read_text()

    for forbidden in (
        ".tick(",
        "pending_signals(",
        "drain_signals(",
        "refresh_weather(",
        "refresh_weather_daily(",
        ".publish(",
        ".put(",
        ".register(",
        ".subscribe(",
        "emit_status(",
        ".emit(",
        ".connect(",
        ".run(",
        ".execute(",
        ".start(",
    ):
        assert forbidden not in source


def test_2c_module_does_not_own_hidden_wake_or_surface_flags():
    source = MODULE.read_text()

    assert "should_wake" not in source
    assert "should_surface" not in source
    assert "wake_kuma" not in source
    assert "surface_now" not in source


def test_2c_boundary_markers_are_explicit():
    source = MODULE.read_text()

    for marker in (
        "REQUEST != COMMAND",
        "REQUEST != PERMISSION",
        "REQUEST != WAKE",
        "REQUEST != SURFACE SIDE EFFECT",
        "REQUEST != EXECUTION",
        "REQUEST != VERIFIED COMPLETION",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_2c_does_not_modify_frozen_2a_contract():
    source = TWO_A.read_text()

    assert (
        "class RealtimeTriggerProposal"
        in source
    )
    assert (
        "def propose_runtime_trigger("
        in source
    )
    assert (
        "TRIGGER PROPOSAL != EXECUTION"
        in source
    )


def test_2c_does_not_modify_frozen_2b_contract():
    source = TWO_B.read_text()

    assert (
        "class RealtimeTriggerEligibilityDecision"
        in source
    )
    assert (
        "def evaluate_trigger_eligibility("
        in source
    )
    assert (
        "ELIGIBILITY != WAKE"
        in source
    )


def test_2c_does_not_modify_frozen_v1_regression_contract():
    source = V1_REGRESSION.read_text()

    assert (
        "def test_realtime_v1_phase_tests_exist():"
        in source
    )
    assert (
        "def test_realtime_subsystem_has_no_background_execution_loop():"
        in source
    )
    assert (
        "def test_realtime_v1_boundary_markers_are_explicit():"
        in source
    )


def test_2c_source_compiles():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
