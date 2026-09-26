from __future__ import annotations

"""
KUMA RUNTIME-V2A regression.

Runtime-V2A is an additive explicit-caller owner that attaches one already
created frozen Realtime V2 observation to an already-active frozen Runtime V1
turn, then invokes the caller-supplied operation exactly once.

OBSERVATION ATTACHMENT != ADMISSION TO EXECUTE
TRACE != CONTROL
OBSERVATION != EXECUTION
ATTACHMENT FAILURE != EXECUTION FAILURE
AUTHORITY: NONE
"""

import ast
import inspect
from pathlib import Path

import pytest

import app.runtime_v2_turn_observation as runtime_v2
from app.realtime.trigger_observation import (
    RealtimeTriggerObservation,
    RealtimeTriggerObservationStatus,
)
from app.runtime_correlation import (
    KumaRuntimeCorrelation,
    RuntimeTurnCorrelation,
)
from app.runtime_trace import (
    RuntimeTraceEvent,
)


MODULE = Path(
    "app/runtime_v2_turn_observation.py"
)


def _observation():
    return RealtimeTriggerObservation(
        observation_id="rto-" + "a" * 64,
        request_id="rtr-" + "b" * 64,
        proposal_id="rtp-" + "c" * 64,
        kind="weather.current",
        status=RealtimeTriggerObservationStatus.OBSERVED,
        reason=(
            "caller observed zero-authority realtime trigger request"
        ),
    )


def _trigger_events(owner):
    return tuple(
        event
        for event in owner.events()
        if (
            event.stage == "realtime"
            and event.event_kind == "trigger.observed"
        )
    )


def _app_imports(path: Path):
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    imports = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("app.")
        ):
            imports.add(node.module)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    imports.add(alias.name)

    return imports


def test_runtime_v2a_module_exists():
    assert MODULE.is_file()


def test_runtime_v2a_authority_constant_is_none():
    assert (
        runtime_v2.RUNTIME_V2_TURN_OBSERVATION_AUTHORITY_NONE
        == "NONE"
    )


def test_owner_default_authority_is_none():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    assert owner.authority == "NONE"


def test_owner_creates_zero_authority_correlation_by_default():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()

    assert isinstance(
        owner.correlation,
        KumaRuntimeCorrelation,
    )
    assert owner.correlation.authority == "NONE"


def test_owner_accepts_caller_supplied_correlation_by_identity():
    correlation = KumaRuntimeCorrelation()

    owner = runtime_v2.KumaRuntimeTurnObservationOwner(
        correlation=correlation
    )

    assert owner.correlation is correlation


@pytest.mark.parametrize(
    "value",
    (
        False,
        True,
        0,
        1,
        "",
        object(),
    ),
)
def test_owner_rejects_invalid_correlation_types(value):
    with pytest.raises(TypeError):
        runtime_v2.KumaRuntimeTurnObservationOwner(
            correlation=value
        )


def test_owner_starts_without_active_turn():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()

    assert owner.active_turn is None
    assert owner.correlation.active_turn is None


def test_run_invokes_explicit_operation_exactly_once():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    calls = []

    def operation():
        calls.append("called")
        return "done"

    result = owner.run(
        operation,
        observation=_observation(),
    )

    assert result == "done"
    assert calls == ["called"]


def test_run_returns_operation_result_unchanged():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    marker = object()

    assert (
        owner.run(
            lambda: marker,
            observation=_observation(),
        )
        is marker
    )


def test_active_turn_exists_inside_operation():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    captured = {}

    def operation():
        captured["turn"] = owner.active_turn
        return None

    owner.run(
        operation,
        observation=_observation(),
    )

    assert isinstance(
        captured["turn"],
        RuntimeTurnCorrelation,
    )


def test_owner_and_correlation_expose_exact_same_active_turn():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    captured = {}

    def operation():
        captured["owner"] = owner.active_turn
        captured["correlation"] = owner.correlation.active_turn
        return None

    owner.run(
        operation,
        observation=_observation(),
    )

    assert captured["owner"] is captured["correlation"]


def test_active_turn_authority_remains_none():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    captured = {}

    def operation():
        captured["authority"] = owner.active_turn.authority
        return None

    owner.run(
        operation,
        observation=_observation(),
    )

    assert captured["authority"] == "NONE"


def test_active_turn_closes_after_successful_run():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()

    owner.run(
        lambda: "ok",
        observation=_observation(),
    )

    assert owner.active_turn is None
    assert owner.correlation.active_turn is None


def test_valid_observation_records_one_structural_trace_event():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()

    owner.run(
        lambda: None,
        observation=_observation(),
    )

    events = _trigger_events(owner)
    assert len(events) == 1

    event = events[0]
    assert isinstance(event, RuntimeTraceEvent)
    assert event.authority == "NONE"
    assert event.stage == "realtime"
    assert event.event_kind == "trigger.observed"
    assert event.outcome == "observed"


def test_observation_event_occurs_inside_runtime_turn_lifecycle():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()

    owner.run(
        lambda: None,
        observation=_observation(),
    )

    kinds = tuple(
        event.event_kind
        for event in owner.events()
    )

    assert kinds == (
        "turn.started",
        "agent.run.started",
        "trigger.observed",
        "agent.run.returned",
        "turn.ended",
    )


def test_runtime_trace_event_uses_exact_active_turn_trace_id():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    captured = {}

    def operation():
        captured["trace_id"] = owner.active_turn.trace_id
        return None

    owner.run(
        operation,
        observation=_observation(),
    )

    event = _trigger_events(owner)[0]
    assert event.trace_id == captured["trace_id"]


def test_operation_exception_propagates_unchanged():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    error = RuntimeError("operation failed")

    def operation():
        raise error

    with pytest.raises(RuntimeError) as caught:
        owner.run(
            operation,
            observation=_observation(),
        )

    assert caught.value is error


def test_active_turn_closes_after_operation_exception():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()

    def operation():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        owner.run(
            operation,
            observation=_observation(),
        )

    assert owner.active_turn is None
    assert owner.correlation.active_turn is None


def test_observation_is_recorded_before_operation_exception():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()

    def operation():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        owner.run(
            operation,
            observation=_observation(),
        )

    assert len(_trigger_events(owner)) == 1


def test_invalid_observation_cannot_block_explicit_operation():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    calls = []

    result = owner.run(
        lambda: (
            calls.append("called"),
            "result",
        )[1],
        observation=object(),
    )

    assert result == "result"
    assert calls == ["called"]
    assert _trigger_events(owner) == ()


def test_trace_adapter_failure_cannot_block_explicit_operation(
    monkeypatch,
):
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    calls = []

    def fail_attachment(*args, **kwargs):
        raise RuntimeError("diagnostic failure")

    monkeypatch.setattr(
        runtime_v2,
        "record_trigger_observation",
        fail_attachment,
    )

    result = owner.run(
        lambda: (
            calls.append("called"),
            7,
        )[1],
        observation=_observation(),
    )

    assert result == 7
    assert calls == ["called"]


def test_noncallable_operation_is_rejected_before_runtime_run():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()

    with pytest.raises(TypeError):
        owner.run(
            None,
            observation=_observation(),
        )

    assert owner.events() == ()
    assert owner.active_turn is None


def test_events_returns_immutable_tuple():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()

    owner.run(
        lambda: None,
        observation=_observation(),
    )

    assert isinstance(owner.events(), tuple)


def test_close_delegates_runtime_lifecycle_without_realtime_action():
    owner = runtime_v2.KumaRuntimeTurnObservationOwner()
    owner.close()
    assert owner.active_turn is None


def test_run_signature_requires_keyword_observation():
    signature = inspect.signature(
        runtime_v2.KumaRuntimeTurnObservationOwner.run
    )

    assert tuple(signature.parameters) == (
        "self",
        "operation",
        "observation",
    )

    assert (
        signature.parameters["observation"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )


def test_constructor_correlation_is_keyword_only():
    signature = inspect.signature(
        runtime_v2.KumaRuntimeTurnObservationOwner
    )

    assert tuple(signature.parameters) == (
        "correlation",
    )

    assert (
        signature.parameters["correlation"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )


def test_runtime_v2a_import_surface_is_exact():
    assert _app_imports(MODULE) == {
        "app.realtime.runtime_trace_adapter",
        "app.realtime.trigger_observation",
        "app.runtime_correlation",
        "app.runtime_live_binding",
        "app.runtime_trace",
    }


def test_runtime_v2a_has_no_agent_ui_tool_or_permission_import():
    imports = _app_imports(MODULE)

    assert not any(
        name.startswith(
            (
                "app.agent",
                "app.ui",
                "app.tools",
            )
        )
        for name in imports
    )


def test_runtime_v2a_does_not_create_realtime_trigger_chain():
    source = MODULE.read_text()

    for forbidden in (
        "propose_runtime_trigger",
        "evaluate_trigger_eligibility",
        "create_trigger_request",
        "observe_trigger_request",
        "pending_signals",
        "drain_signals",
        "get_realtime_runtime",
    ):
        assert forbidden not in source


def test_runtime_v2a_does_not_own_background_or_scheduler_lifecycle():
    source = MODULE.read_text()

    for forbidden in (
        "threading",
        "Thread(",
        "QThread",
        "QTimer",
        "asyncio",
        "create_task(",
        "scheduler",
        ".tick(",
        "while True",
    ):
        assert forbidden not in source


def test_runtime_v2a_does_not_own_ui_status_or_notification():
    source = MODULE.read_text()

    for forbidden in (
        "emit_status",
        "status_callback",
        ".emit(",
        ".connect(",
        "notification",
        "toast",
    ):
        assert forbidden not in source


def test_runtime_v2a_does_not_own_tool_model_permission_or_execution():
    source = MODULE.read_text()

    for forbidden in (
        "ActionExecutor",
        "get_permission_level",
        "requires_confirmation",
        "request_confirmation",
        "call_mission_model",
        "chat.",
        "tool_registry",
        "execute_command",
    ):
        assert forbidden not in source


def test_runtime_v2a_never_calls_turn_begin_or_end_directly():
    source = MODULE.read_text()

    assert ".begin_turn(" not in source
    assert ".end_turn(" not in source


def test_runtime_v2a_uses_no_private_runtime_v1_member():
    source = MODULE.read_text()

    for forbidden in (
        "._active_turn",
        "._trace",
        "._next_sequence",
        "._record(",
    ):
        assert forbidden not in source


def test_runtime_v2a_owns_no_queue_seen_or_ack_state():
    source = MODULE.read_text()

    for forbidden in (
        "deque(",
        "seen_event_ids",
        "acknowledged_event_ids",
        "remember_seen_event",
        ".append(",
        ".popleft(",
    ):
        assert forbidden not in source


def test_runtime_v2a_boundary_markers_are_explicit():
    source = MODULE.read_text()

    for marker in (
        "CALLER INVOCATION -> RUN",
        "REALTIME OBSERVATION -> TRACE ATTACHMENT ONLY",
        "OBSERVATION ATTACHMENT != ADMISSION TO EXECUTE",
        "TRACE != CONTROL",
        "OBSERVATION != EXECUTION",
        "ATTACHMENT FAILURE != EXECUTION FAILURE",
        "AUTHORITY: NONE",
    ):
        assert marker in source
