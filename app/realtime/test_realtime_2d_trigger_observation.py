from __future__ import annotations

import ast
from dataclasses import (
    FrozenInstanceError,
    fields,
)
from pathlib import Path

import pytest

from app.realtime.trigger_observation import (
    REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE,
    RealtimeTriggerObservation,
    RealtimeTriggerObservationStatus,
    observe_trigger_request,
)
from app.realtime.trigger_request import (
    RealtimeTriggerRequest,
)


ROOT = Path(__file__).resolve().parents[2]

MODULE = (
    ROOT
    / "app/realtime/trigger_observation.py"
)

TWO_C = (
    ROOT
    / "app/realtime/trigger_request.py"
)

TWO_B = (
    ROOT
    / "app/realtime/trigger_policy.py"
)

TWO_A = (
    ROOT
    / "app/realtime/runtime_trigger.py"
)

TWO_C_TEST = (
    ROOT
    / "app/realtime/test_realtime_2c_trigger_request.py"
)

TWO_B_TEST = (
    ROOT
    / "app/realtime/test_realtime_2b_trigger_policy.py"
)

TWO_A_TEST = (
    ROOT
    / "app/realtime/test_realtime_2a_runtime_trigger_boundary.py"
)

V1_REGRESSION = (
    ROOT
    / "app/realtime/test_realtime_v1_architecture_regression.py"
)


def _request(
    *,
    request_id: str = "rtr-test",
    proposal_id: str = "rtp-test",
    kind: str = "weather.current",
    reason: str = "eligible realtime trigger awaits future caller-owned handling",
    authority: str = "NONE",
) -> RealtimeTriggerRequest:
    request = object.__new__(
        RealtimeTriggerRequest
    )

    object.__setattr__(
        request,
        "request_id",
        request_id,
    )
    object.__setattr__(
        request,
        "proposal_id",
        proposal_id,
    )
    object.__setattr__(
        request,
        "kind",
        kind,
    )
    object.__setattr__(
        request,
        "reason",
        reason,
    )
    object.__setattr__(
        request,
        "authority",
        authority,
    )

    return request


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


def test_2d_files_and_frozen_dependencies_exist():
    assert MODULE.is_file()
    assert TWO_A.is_file()
    assert TWO_B.is_file()
    assert TWO_C.is_file()
    assert TWO_A_TEST.is_file()
    assert TWO_B_TEST.is_file()
    assert TWO_C_TEST.is_file()
    assert V1_REGRESSION.is_file()


def test_observation_authority_constant_is_none():
    assert (
        REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE
        == "NONE"
    )


def test_observation_surface_is_privacy_minimized():
    assert _field_names(
        RealtimeTriggerObservation
    ) == (
        "observation_id",
        "request_id",
        "proposal_id",
        "kind",
        "status",
        "reason",
        "authority",
    )


def test_observation_exposes_no_control_or_delivery_fields():
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
        "accepted",
        "acknowledged",
        "delivered",
        "handled",
        "consumed",
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
            RealtimeTriggerObservation
        )
    ).isdisjoint(
        forbidden
    )


def test_observation_is_frozen():
    observation = observe_trigger_request(
        _request()
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        observation.kind = "other"


def test_observation_rejects_non_none_authority():
    with pytest.raises(
        ValueError,
        match="permanently NONE",
    ):
        RealtimeTriggerObservation(
            observation_id="rto-test",
            request_id="rtr-test",
            proposal_id="rtp-test",
            kind="weather.current",
            status=(
                RealtimeTriggerObservationStatus.OBSERVED
            ),
            reason="observed",
            authority="USER",
        )


def test_projection_rejects_non_request_input():
    with pytest.raises(
        TypeError,
        match="RealtimeTriggerRequest",
    ):
        observe_trigger_request(
            object()
        )


def test_projection_rejects_forged_request_authority():
    with pytest.raises(
        ValueError,
        match="RealtimeTriggerRequest authority",
    ):
        observe_trigger_request(
            _request(
                authority="USER",
            )
        )


@pytest.mark.parametrize(
    "field_name,kwargs",
    (
        (
            "request_id",
            {
                "request_id": "   ",
            },
        ),
        (
            "proposal_id",
            {
                "proposal_id": "   ",
            },
        ),
        (
            "kind",
            {
                "kind": "   ",
            },
        ),
    ),
)
def test_projection_rejects_blank_request_identity_fields(
    field_name,
    kwargs,
):
    with pytest.raises(
        ValueError,
        match=field_name,
    ):
        observe_trigger_request(
            _request(
                **kwargs
            )
        )


def test_observation_status_is_observed_only():
    assert tuple(
        RealtimeTriggerObservationStatus
    ) == (
        RealtimeTriggerObservationStatus.OBSERVED,
    )


def test_valid_request_produces_observation():
    observation = observe_trigger_request(
        _request()
    )

    assert (
        observation.status
        == RealtimeTriggerObservationStatus.OBSERVED
    )
    assert (
        observation.authority
        == "NONE"
    )


def test_observation_preserves_request_identity_only():
    request = _request()

    observation = observe_trigger_request(
        request
    )

    assert (
        observation.request_id
        == request.request_id
    )
    assert (
        observation.proposal_id
        == request.proposal_id
    )
    assert (
        observation.kind
        == request.kind
    )


def test_observation_does_not_copy_request_reason():
    request = _request(
        reason="caller-specific safe request reason",
    )

    observation = observe_trigger_request(
        request
    )

    assert (
        observation.reason
        != request.reason
    )
    assert (
        observation.reason
        == "caller observed zero-authority realtime trigger request"
    )


def test_observation_identity_is_deterministic():
    first = observe_trigger_request(
        _request()
    )
    second = observe_trigger_request(
        _request()
    )

    assert (
        first.observation_id
        == second.observation_id
    )


def test_observation_identity_changes_with_request_identity():
    first = observe_trigger_request(
        _request(
            request_id="rtr-one",
        )
    )
    second = observe_trigger_request(
        _request(
            request_id="rtr-two",
        )
    )

    assert (
        first.observation_id
        != second.observation_id
    )


def test_observation_does_not_claim_ack_accept_delivery_or_handling():
    observation = observe_trigger_request(
        _request()
    )

    payload = " ".join(
        str(
            getattr(
                observation,
                item.name,
            )
        )
        for item in fields(
            observation
        )
    ).lower()

    for forbidden in (
        "acknowledged",
        "accepted",
        "delivered",
        "handled",
        "consumed",
        "executed",
        "completed",
    ):
        assert forbidden not in payload


def test_2d_module_imports_only_trigger_request_from_app():
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
        "app.realtime.trigger_request",
    }


def test_2d_module_does_not_import_agent_ui_or_tools():
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


def test_2d_module_has_no_network_or_persistence_dependency():
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


def test_2d_module_has_no_background_execution_primitive():
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


def test_2d_module_has_no_runtime_side_effect_calls():
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
        ".claim(",
        ".clear(",
    ):
        assert forbidden not in source


def test_2d_module_has_no_hidden_control_flags():
    source = MODULE.read_text()

    for forbidden in (
        "should_wake",
        "should_surface",
        "should_notify",
        "should_execute",
        "accepted =",
        "acknowledged =",
        "delivered =",
        "handled =",
    ):
        assert forbidden not in source


def test_2d_boundary_markers_are_explicit():
    source = MODULE.read_text()

    for marker in (
        "OBSERVATION != ACKNOWLEDGMENT",
        "OBSERVATION != ACCEPTANCE",
        "OBSERVATION != DELIVERY",
        "OBSERVATION != NOTIFICATION",
        "OBSERVATION != WAKE",
        "OBSERVATION != EXECUTION",
        "OBSERVATION != VERIFIED COMPLETION",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_2d_does_not_modify_frozen_2c_contract():
    source = TWO_C.read_text()

    assert (
        "class RealtimeTriggerRequest"
        in source
    )
    assert (
        "def create_trigger_request("
        in source
    )
    assert (
        "REQUEST != WAKE"
        in source
    )


def test_2d_does_not_modify_frozen_2b_contract():
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
        "ELIGIBILITY != EXECUTION"
        in source
    )


def test_2d_does_not_modify_frozen_2a_contract():
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


def test_2d_does_not_modify_frozen_v1_regression_contract():
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


def test_2d_source_compiles():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
