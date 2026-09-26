from __future__ import annotations

"""
KUMA RUNTIME-V2C regression.

CALLER INTENT -> RuntimeInvocation -> DISPATCH
OPTIONAL OBSERVATION -> BRANCH METADATA ONLY

DISPATCH != ADMISSION
SYNCHRONIZATION != SCHEDULER
OBSERVATION != INVOCATION
OBSERVATION != PERMISSION
ONE INVOCATION = ONE SELECTED BRANCH
ONE SUCCESSFUL INVOCATION = ONE RUNTIME TURN
OPERATION EXECUTES EXACTLY ONCE
CLOSED DISPATCHER != FAIL-OPEN EXECUTION
RE-ENTRANT DISPATCH != FAIL-OPEN EXECUTION
TRACE != CONTROL
AUTHORITY: NONE
"""

import ast
import inspect
from pathlib import Path
from threading import Event, Thread

import pytest

from app.realtime.trigger_observation import (
    RealtimeTriggerObservation,
    RealtimeTriggerObservationStatus,
)
from app.runtime_v2_invocation import (
    RuntimeInvocation,
)
import app.runtime_v2_dispatch as runtime_v2c


MODULE = Path(
    "app/runtime_v2_dispatch.py"
)


def _observation(
    prefix: str = "runtime-v2c",
):
    return RealtimeTriggerObservation(
        observation_id=f"{prefix}-observation",
        request_id=f"{prefix}-request",
        proposal_id=f"{prefix}-proposal",
        kind=prefix,
        status=RealtimeTriggerObservationStatus.OBSERVED,
        reason=f"{prefix} proof",
    )


def _event_names(
    dispatcher,
):
    return tuple(
        event.event_kind
        for event in dispatcher.events()
    )


def _app_imports():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    result = {}

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("app.")
        ):
            result.setdefault(
                node.module,
                set(),
            ).update(
                alias.name
                for alias in node.names
            )

    return {
        key: tuple(sorted(value))
        for key, value in result.items()
    }


def test_runtime_v2c_module_exists():
    assert MODULE.is_file()


def test_runtime_v2c_authority_constant_is_none():
    assert (
        runtime_v2c.RUNTIME_V2C_AUTHORITY_NONE
        == "NONE"
    )


def test_dispatcher_constructor_is_zero_argument():
    signature = inspect.signature(
        runtime_v2c.KumaRuntimeInvocationDispatcher
    )

    assert tuple(
        signature.parameters
    ) == ()


def test_dispatcher_does_not_accept_correlation_injection():
    source = inspect.getsource(
        runtime_v2c.KumaRuntimeInvocationDispatcher.__init__
    )

    assert "correlation:" not in source
    assert "correlation=" not in str(
        inspect.signature(
            runtime_v2c.KumaRuntimeInvocationDispatcher
        )
    )


def test_dispatcher_authority_is_none():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    assert dispatcher.authority == "NONE"


def test_run_requires_runtime_invocation():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    with pytest.raises(
        TypeError,
        match="invocation must be RuntimeInvocation",
    ):
        dispatcher.run(
            object()
        )


def test_plain_invocation_returns_result():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    result = dispatcher.run(
        RuntimeInvocation(
            operation=lambda: "plain-result",
        )
    )

    assert result == "plain-result"


def test_plain_invocation_executes_operation_exactly_once():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    calls = []

    dispatcher.run(
        RuntimeInvocation(
            operation=lambda: calls.append(
                "called"
            )
        )
    )

    assert calls == ["called"]


def test_plain_invocation_is_exactly_one_runtime_turn():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    dispatcher.run(
        RuntimeInvocation(
            operation=lambda: "ok",
        )
    )

    names = _event_names(
        dispatcher
    )

    assert names == (
        "turn.started",
        "agent.run.started",
        "agent.run.returned",
        "turn.ended",
    )


def test_observed_invocation_returns_result():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    result = dispatcher.run(
        RuntimeInvocation(
            operation=lambda: "observed-result",
            observation=_observation(),
        )
    )

    assert result == "observed-result"


def test_observed_invocation_executes_operation_exactly_once():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    calls = []

    dispatcher.run(
        RuntimeInvocation(
            operation=lambda: calls.append(
                "called"
            ),
            observation=_observation(),
        )
    )

    assert calls == ["called"]


def test_observed_invocation_is_exactly_one_runtime_turn():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    dispatcher.run(
        RuntimeInvocation(
            operation=lambda: "ok",
            observation=_observation(),
        )
    )

    names = _event_names(
        dispatcher
    )

    assert names == (
        "turn.started",
        "agent.run.started",
        "trigger.observed",
        "agent.run.returned",
        "turn.ended",
    )


def test_plain_then_observed_share_one_session_trace():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    dispatcher.run(
        RuntimeInvocation(
            operation=lambda: "plain",
        )
    )

    dispatcher.run(
        RuntimeInvocation(
            operation=lambda: "observed",
            observation=_observation(
                "second"
            ),
        )
    )

    names = _event_names(
        dispatcher
    )

    assert names.count(
        "turn.started"
    ) == 2

    assert names.count(
        "turn.ended"
    ) == 2

    assert names.count(
        "trigger.observed"
    ) == 1


def test_run_after_close_rejects_before_operation():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    dispatcher.close()

    calls = []

    with pytest.raises(
        RuntimeError,
        match="dispatcher is closed",
    ):
        dispatcher.run(
            RuntimeInvocation(
                operation=lambda: calls.append(
                    "must-not-run"
                )
            )
        )

    assert calls == []


def test_close_is_idempotent():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    assert dispatcher.close() is None
    assert dispatcher.close() is None


def test_reentrant_plain_dispatch_rejects_before_inner_operation():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    calls = []

    def inner():
        calls.append(
            "inner"
        )
        return "inner"

    def outer():
        calls.append(
            "outer"
        )

        with pytest.raises(
            RuntimeError,
            match="already active",
        ):
            dispatcher.run(
                RuntimeInvocation(
                    operation=inner
                )
            )

        calls.append(
            "inner-rejected"
        )

        return "outer-result"

    assert (
        dispatcher.run(
            RuntimeInvocation(
                operation=outer
            )
        )
        == "outer-result"
    )

    assert calls == [
        "outer",
        "inner-rejected",
    ]

    assert _event_names(
        dispatcher
    ).count(
        "turn.started"
    ) == 1


def test_reentrant_observed_dispatch_rejects_before_inner_operation():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    calls = []

    def inner():
        calls.append(
            "inner"
        )
        return "inner"

    def outer():
        calls.append(
            "outer"
        )

        with pytest.raises(
            RuntimeError,
            match="already active",
        ):
            dispatcher.run(
                RuntimeInvocation(
                    operation=inner,
                    observation=_observation(
                        "inner"
                    ),
                )
            )

        calls.append(
            "inner-rejected"
        )

        return "outer-result"

    assert (
        dispatcher.run(
            RuntimeInvocation(
                operation=outer
            )
        )
        == "outer-result"
    )

    assert calls == [
        "outer",
        "inner-rejected",
    ]

    names = _event_names(
        dispatcher
    )

    assert names.count(
        "turn.started"
    ) == 1

    assert "trigger.observed" not in names


def test_close_during_active_invocation_rejects():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    calls = []

    def operation():
        calls.append(
            "operation"
        )

        with pytest.raises(
            RuntimeError,
            match="cannot close dispatcher during active invocation",
        ):
            dispatcher.close()

        calls.append(
            "close-rejected"
        )

        return "ok"

    assert (
        dispatcher.run(
            RuntimeInvocation(
                operation=operation
            )
        )
        == "ok"
    )

    assert calls == [
        "operation",
        "close-rejected",
    ]


def test_close_after_completed_invocation_succeeds():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    dispatcher.run(
        RuntimeInvocation(
            operation=lambda: "ok",
        )
    )

    assert dispatcher.close() is None


def test_concurrent_invocations_serialize_into_distinct_turns():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    first_entered = Event()
    release_first = Event()
    second_finished = Event()

    calls = []
    results = []
    errors = []

    def first_operation():
        calls.append(
            "first-start"
        )
        first_entered.set()

        if not release_first.wait(
            timeout=5
        ):
            raise RuntimeError(
                "timed out waiting to release first operation"
            )

        calls.append(
            "first-end"
        )
        return "first-result"

    def second_operation():
        calls.append(
            "second"
        )
        return "second-result"

    def first_thread():
        try:
            results.append(
                dispatcher.run(
                    RuntimeInvocation(
                        operation=first_operation
                    )
                )
            )
        except BaseException as error:
            errors.append(
                error
            )

    def second_thread():
        try:
            results.append(
                dispatcher.run(
                    RuntimeInvocation(
                        operation=second_operation
                    )
                )
            )
        except BaseException as error:
            errors.append(
                error
            )
        finally:
            second_finished.set()

    thread_one = Thread(
        target=first_thread
    )

    thread_two = Thread(
        target=second_thread
    )

    thread_one.start()

    assert first_entered.wait(
        timeout=5
    )

    thread_two.start()

    assert not second_finished.wait(
        timeout=0.15
    )

    release_first.set()

    thread_one.join(
        timeout=5
    )
    thread_two.join(
        timeout=5
    )

    assert not thread_one.is_alive()
    assert not thread_two.is_alive()
    assert errors == []

    assert calls == [
        "first-start",
        "first-end",
        "second",
    ]

    assert set(results) == {
        "first-result",
        "second-result",
    }

    names = _event_names(
        dispatcher
    )

    assert names.count(
        "turn.started"
    ) == 2

    assert names.count(
        "turn.ended"
    ) == 2


def test_operation_exception_propagates():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    marker = RuntimeError(
        "operation failed"
    )

    def operation():
        raise marker

    with pytest.raises(
        RuntimeError
    ) as caught:
        dispatcher.run(
            RuntimeInvocation(
                operation=operation
            )
        )

    assert caught.value is marker


def test_operation_exception_does_not_leave_active_dispatcher():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    def operation():
        raise RuntimeError(
            "boom"
        )

    with pytest.raises(
        RuntimeError,
        match="boom",
    ):
        dispatcher.run(
            RuntimeInvocation(
                operation=operation
            )
        )

    assert (
        dispatcher.run(
            RuntimeInvocation(
                operation=lambda: "recovered"
            )
        )
        == "recovered"
    )


def test_operation_exception_turn_is_closed_as_error():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    def operation():
        raise RuntimeError(
            "boom"
        )

    with pytest.raises(
        RuntimeError,
        match="boom",
    ):
        dispatcher.run(
            RuntimeInvocation(
                operation=operation
            )
        )

    names = _event_names(
        dispatcher
    )

    assert names == (
        "turn.started",
        "agent.run.started",
        "agent.run.raised",
        "turn.ended",
    )


def test_events_are_tuple_snapshot():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    assert isinstance(
        dispatcher.events(),
        tuple,
    )


def test_events_available_after_close():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    dispatcher.run(
        RuntimeInvocation(
            operation=lambda: "ok"
        )
    )

    before = dispatcher.events()

    dispatcher.close()

    assert dispatcher.events() == before


def test_dispatcher_app_import_surface_is_exact():
    assert _app_imports() == {
        "app.runtime_correlation": (
            "KumaRuntimeCorrelation",
        ),
        "app.runtime_live_binding": (
            "KumaRuntimeLiveTraceBinding",
        ),
        "app.runtime_v2_invocation": (
            "RuntimeInvocation",
        ),
        "app.runtime_v2_turn_observation": (
            "KumaRuntimeTurnObservationOwner",
        ),
    }


def test_dispatcher_has_no_direct_realtime_v2_import():
    imports = _app_imports()

    assert not any(
        name.startswith(
            "app.realtime"
        )
        for name in imports
    )


def test_dispatcher_does_not_import_integration_v2a():
    source = MODULE.read_text()

    assert (
        "integration_realtime_observation_admission"
        not in source
    )

    assert (
        "admit_realtime_observation"
        not in source
    )


def test_dispatcher_does_not_import_gui_cli_or_agent():
    imports = _app_imports()

    assert not any(
        name.startswith(
            "app.agent"
        )
        or name.startswith(
            "app.ui"
        )
        for name in imports
    )


def test_dispatcher_does_not_reference_signal_queue_or_attention():
    source = MODULE.read_text()

    for forbidden in (
        "RealtimeSignal",
        "pending_signals",
        "drain_signals",
        "get_realtime_runtime",
        "evaluate_attention_surfacing",
        "remember_seen_event",
        "minimum_level",
        "minimum_score",
    ):
        assert forbidden not in source


def test_dispatcher_does_not_reference_tool_model_permission_execution():
    source = MODULE.read_text()

    for forbidden in (
        "ActionExecutor",
        "tool_registry",
        "execute_command",
        "call_mission_model",
        "get_permission_level",
        "requires_confirmation",
        "request_confirmation",
        "confirmation_callback",
        "USER_AUTHORIZED",
        "EXECUTION_ALLOWED",
    ):
        assert forbidden not in source


def test_dispatcher_uses_rlock_for_synchronous_serialization():
    source = MODULE.read_text()

    assert (
        "from threading import RLock"
        in source
    )

    assert (
        "self._lock = RLock()"
        in source
    )


def test_dispatcher_creates_no_thread_or_task():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    forbidden_calls = {
        "Thread",
        "create_task",
        "ensure_future",
        "start",
    }

    hits = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        func = node.func

        if (
            isinstance(func, ast.Name)
            and func.id in forbidden_calls
        ):
            hits.append(
                (
                    func.id,
                    node.lineno,
                )
            )

        elif (
            isinstance(func, ast.Attribute)
            and func.attr in forbidden_calls
        ):
            hits.append(
                (
                    func.attr,
                    node.lineno,
                )
            )

    assert hits == []


def test_dispatcher_has_no_scheduler_background_structure():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    forbidden_names = {
        "QThread",
        "QTimer",
        "scheduler",
        "asyncio",
    }

    hits = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and node.id in forbidden_names
        ):
            hits.append(
                (
                    node.id,
                    node.lineno,
                )
            )

        elif (
            isinstance(node, ast.Attribute)
            and node.attr in forbidden_names
        ):
            hits.append(
                (
                    node.attr,
                    node.lineno,
                )
            )

        elif (
            isinstance(node, ast.While)
            and isinstance(
                node.test,
                ast.Constant,
            )
            and node.test.value is True
        ):
            hits.append(
                (
                    "while-true",
                    node.lineno,
                )
            )

    assert hits == []


def test_dispatcher_branch_selection_is_observation_only():
    source = inspect.getsource(
        runtime_v2c.KumaRuntimeInvocationDispatcher.run
    )

    assert (
        "if invocation.observation is None:"
        in source
    )

    assert (
        "self._plain_binding.run("
        in source
    )

    assert (
        "self._observed_owner.run("
        in source
    )


def test_dispatcher_prechecks_closed_before_branch():
    source = inspect.getsource(
        runtime_v2c.KumaRuntimeInvocationDispatcher.run
    )

    closed_index = source.index(
        "if self._closed:"
    )

    plain_index = source.index(
        "self._plain_binding.run("
    )

    observed_index = source.index(
        "self._observed_owner.run("
    )

    assert closed_index < plain_index
    assert closed_index < observed_index


def test_dispatcher_prechecks_active_before_branch():
    source = inspect.getsource(
        runtime_v2c.KumaRuntimeInvocationDispatcher.run
    )

    active_index = source.index(
        "if self._active:"
    )

    plain_index = source.index(
        "self._plain_binding.run("
    )

    observed_index = source.index(
        "self._observed_owner.run("
    )

    assert active_index < plain_index
    assert active_index < observed_index


def test_dispatcher_owns_one_correlation():
    source = inspect.getsource(
        runtime_v2c.KumaRuntimeInvocationDispatcher.__init__
    )

    assert source.count(
        "KumaRuntimeCorrelation()"
    ) == 1


def test_dispatcher_branch_helpers_share_owned_correlation():
    dispatcher = (
        runtime_v2c.KumaRuntimeInvocationDispatcher()
    )

    assert (
        dispatcher._plain_binding._correlation
        is dispatcher._correlation
    )

    assert (
        dispatcher._observed_owner._correlation
        is dispatcher._correlation
    )


def test_dispatcher_close_uses_one_branch_close_surface_only():
    source = inspect.getsource(
        runtime_v2c.KumaRuntimeInvocationDispatcher.close
    )

    assert (
        "self._plain_binding.close()"
        in source
    )

    assert (
        "self._observed_owner.close()"
        not in source
    )


def test_dispatcher_boundary_markers_are_explicit():
    source = MODULE.read_text()

    for marker in (
        "CALLER INTENT -> RuntimeInvocation -> DISPATCH",
        "OPTIONAL OBSERVATION -> BRANCH METADATA ONLY",
        "DISPATCH != ADMISSION",
        "SYNCHRONIZATION != SCHEDULER",
        "OBSERVATION != INVOCATION",
        "OBSERVATION != PERMISSION",
        "ONE INVOCATION = ONE SELECTED BRANCH",
        "ONE SUCCESSFUL INVOCATION = ONE RUNTIME TURN",
        "OPERATION EXECUTES EXACTLY ONCE",
        "CLOSED DISPATCHER != FAIL-OPEN EXECUTION",
        "RE-ENTRANT DISPATCH != FAIL-OPEN EXECUTION",
        "TRACE != CONTROL",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_dispatcher_public_method_surface_is_narrow():
    public = {
        name
        for name, value
        in runtime_v2c.KumaRuntimeInvocationDispatcher.__dict__.items()
        if not name.startswith("_")
        and (
            inspect.isfunction(value)
            or isinstance(
                value,
                property,
            )
        )
    }

    assert public == {
        "authority",
        "run",
        "events",
        "close",
    }
