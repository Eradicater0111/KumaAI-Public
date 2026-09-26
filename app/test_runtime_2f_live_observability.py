from __future__ import annotations

import ast
from dataclasses import (
    FrozenInstanceError,
    fields,
)
import inspect
from pathlib import Path

import pytest

import app.agent.gui_runtime as gui_runtime

from app.runtime_correlation import (
    KumaRuntimeCorrelation,
)
from app.runtime_live_binding import (
    KumaRuntimeLiveTraceBinding,
)
from app.runtime_observability import (
    RUNTIME_OBSERVABILITY_AUTHORITY_NONE,
    RUNTIME_OBSERVABILITY_MAX_EVENTS,
    RuntimeObservationEvent,
    RuntimeObservationSnapshot,
    project_runtime_observation,
)
from app.runtime_trace import (
    KumaRuntimeTrace,
)


ROOT = Path(__file__).resolve().parents[1]

MODULE = (
    ROOT
    / "app/runtime_observability.py"
)

GUI = (
    ROOT
    / "app/agent/gui_runtime.py"
)


def make_binding():
    ticks = iter(
        range(
            100,
            50000,
            100,
        )
    )

    trace = KumaRuntimeTrace(
        clock_ns=lambda: next(ticks),
        trace_id_factory=(
            lambda: "trace-2f-test"
        ),
    )

    correlation = KumaRuntimeCorrelation(
        trace=trace,
        session_id_factory=(
            lambda: "session-2f-test"
        ),
        turn_id_factory=(
            lambda: "turn-2f-test"
        ),
    )

    return (
        KumaRuntimeLiveTraceBinding(
            correlation=correlation
        ),
        correlation,
    )


def make_complete_snapshot():
    binding, _ = make_binding()

    def operation():
        for event_kind, outcome in (
            (
                "permission.classified",
                "dangerous",
            ),
            (
                "confirmation.resolved",
                "approved",
            ),
            (
                "executor.returned",
                "success",
            ),
            (
                "verifier.returned",
                "true",
            ),
            (
                "body_verifier.returned",
                "true",
            ),
            (
                "state_verification.returned",
                "known_changed",
            ),
            (
                "objective_verification.returned",
                "unsatisfied",
            ),
            (
                "recovery.strategy_mode",
                "manual",
            ),
            (
                "recovery.decision",
                "resume",
            ),
        ):
            binding.observe_pipeline_event(
                event_kind=event_kind,
                outcome=outcome,
            )

        return "private-result"

    assert (
        binding.run(
            operation
        )
        == "private-result"
    )

    return (
        project_runtime_observation(
            binding.events()
        )
    )


def imports():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
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


def test_authority_constant_is_none():
    assert (
        RUNTIME_OBSERVABILITY_AUTHORITY_NONE
        == "NONE"
    )


def test_capacity_matches_frozen_trace_capacity():
    assert (
        RUNTIME_OBSERVABILITY_MAX_EVENTS
        == 256
    )


def test_observation_event_fields_are_exact():
    assert [
        value.name
        for value in fields(
            RuntimeObservationEvent
        )
    ] == [
        "trace_id",
        "sequence",
        "stage",
        "event_kind",
        "monotonic_ns",
        "duration_ms",
        "outcome",
        "session_id",
        "turn_id",
        "turn_index",
        "authority",
    ]


def test_snapshot_fields_are_exact():
    assert [
        value.name
        for value in fields(
            RuntimeObservationSnapshot
        )
    ] == [
        "events",
        "authority",
    ]


def test_observation_event_is_frozen():
    snapshot = (
        make_complete_snapshot()
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        snapshot.events[0].stage = (
            "mutated"
        )


def test_snapshot_is_frozen():
    snapshot = (
        make_complete_snapshot()
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        snapshot.events = ()


def test_observation_types_are_slotted():
    assert hasattr(
        RuntimeObservationEvent,
        "__slots__",
    )
    assert hasattr(
        RuntimeObservationSnapshot,
        "__slots__",
    )


def test_authority_is_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            RuntimeObservationEvent
        ).parameters
    )

    assert (
        "authority"
        not in inspect.signature(
            RuntimeObservationSnapshot
        ).parameters
    )


def test_empty_snapshot_is_zero_authority():
    snapshot = (
        RuntimeObservationSnapshot()
    )

    assert snapshot.events == ()
    assert snapshot.event_count == 0
    assert snapshot.authority == "NONE"


def test_projector_signature_accepts_only_events():
    assert tuple(
        inspect.signature(
            project_runtime_observation
        ).parameters
    ) == (
        "events",
    )


def test_projector_requires_tuple():
    with pytest.raises(
        TypeError,
        match="tuple",
    ):
        project_runtime_observation(
            []
        )


def test_projector_rejects_non_trace_event():
    with pytest.raises(
        TypeError,
        match="RuntimeTraceEvent",
    ):
        project_runtime_observation(
            (
                object(),
            )
        )


def test_complete_runtime_stream_projects():
    snapshot = (
        make_complete_snapshot()
    )

    assert snapshot.event_count == 13

    assert [
        event.event_kind
        for event in snapshot.events
    ] == [
        "turn.started",
        "agent.run.started",
        "permission.classified",
        "confirmation.resolved",
        "executor.returned",
        "verifier.returned",
        "body_verifier.returned",
        "state_verification.returned",
        "objective_verification.returned",
        "recovery.strategy_mode",
        "recovery.decision",
        "agent.run.returned",
        "turn.ended",
    ]


def test_complete_runtime_stream_preserves_stage_order():
    snapshot = (
        make_complete_snapshot()
    )

    assert [
        event.stage
        for event in snapshot.events
    ] == [
        "correlation",
        "runtime",
        "authority",
        "authority",
        "execution",
        "verification",
        "verification",
        "verification",
        "verification",
        "recovery",
        "recovery",
        "runtime",
        "correlation",
    ]


def test_projection_preserves_structural_correlation():
    snapshot = (
        make_complete_snapshot()
    )

    assert {
        event.session_id
        for event in snapshot.events
    } == {
        "session-2f-test"
    }

    assert {
        event.turn_id
        for event in snapshot.events
    } == {
        "turn-2f-test"
    }

    assert {
        event.turn_index
        for event in snapshot.events
    } == {
        1
    }


def test_projection_preserves_single_trace_identity():
    snapshot = (
        make_complete_snapshot()
    )

    assert {
        event.trace_id
        for event in snapshot.events
    } == {
        "trace-2f-test"
    }


def test_all_projected_events_are_zero_authority():
    snapshot = (
        make_complete_snapshot()
    )

    assert snapshot.authority == "NONE"

    assert all(
        event.authority == "NONE"
        for event in snapshot.events
    )


def test_projection_contains_no_raw_metadata_field():
    names = {
        value.name
        for value in fields(
            RuntimeObservationEvent
        )
    }

    assert "metadata" not in names
    assert "reason" not in names


def test_projection_contains_no_payload_field_names():
    names = {
        value.name
        for value in fields(
            RuntimeObservationEvent
        )
    }

    for forbidden in (
        "prompt",
        "message",
        "arguments",
        "result",
        "response",
        "evidence",
        "objective",
        "state",
        "screen",
        "clipboard",
        "memory",
        "memory_context",
        "error",
        "exception",
        "tool_name",
    ):
        assert forbidden not in names


def test_private_wrapped_result_does_not_enter_projection():
    snapshot = (
        make_complete_snapshot()
    )

    assert (
        "private-result"
        not in repr(snapshot)
    )


def test_turn_end_extra_metadata_is_not_exposed():
    snapshot = (
        make_complete_snapshot()
    )

    terminal = snapshot.events[-1]

    assert terminal.event_kind == "turn.ended"

    assert (
        "turn.end_kind"
        not in repr(terminal)
    )


def test_module_imports_only_runtime_trace_inside_kuma():
    app_imports = {
        value
        for value in imports()
        if value.startswith(
            "app."
        )
    }

    assert app_imports == {
        "app.runtime_trace"
    }


def test_module_has_no_authority_or_execution_dependencies():
    imported = imports()

    for prefix in (
        "app.agent",
        "app.tools",
        "app.memory",
        "app.ui",
        "app.voice",
        "app.realtime",
    ):
        assert not any(
            value == prefix
            or value.startswith(
                prefix + "."
            )
            for value in imported
        )


def test_module_has_no_network_or_persistence_dependencies():
    roots = {
        value.split(
            ".",
            1,
        )[0]
        for value in imports()
    }

    assert roots.isdisjoint(
        {
            "requests",
            "httpx",
            "urllib",
            "socket",
            "aiohttp",
            "websockets",
            "sqlite3",
            "pathlib",
        }
    )


def test_module_has_no_background_runtime():
    text = MODULE.read_text()

    for forbidden in (
        "threading.Thread",
        "asyncio.create_task",
        "while True",
        "schedule.",
        "Timer(",
    ):
        assert forbidden not in text


def test_module_has_no_permission_execution_surface():
    text = MODULE.read_text()

    for forbidden in (
        "request_confirmation(",
        "require_explicit_permission(",
        "register_tool(",
        "ActionExecutor",
        "PermissionLevel",
        ".execute(",
        ".run(",
    ):
        assert forbidden not in text


def test_gui_snapshot_signature_accepts_no_input():
    assert tuple(
        inspect.signature(
            gui_runtime.KumaGUIRuntime
            .runtime_observation_snapshot
        ).parameters
    ) == (
        "self",
    )


def test_gui_keeps_existing_raw_trace_read():
    assert tuple(
        inspect.signature(
            gui_runtime.KumaGUIRuntime
            .runtime_trace_events
        ).parameters
    ) == (
        "self",
    )


def test_gui_snapshot_projects_existing_binding():
    class FakeKuma:
        def __init__(
            self,
            **_,
        ):
            self._runtime_observer = None
            self.realtime_runtime = None

        def run(
            self,
            message,
            *,
            prepared_realtime_turn=None,
        ):
            assert (
                message
                == "private-request"
            )
            return (
                "private-response"
            )

    original_create = (
        gui_runtime.create_kuma
    )

    try:
        gui_runtime.create_kuma = (
            lambda **kwargs:
            FakeKuma(
                **kwargs
            )
        )

        runtime = (
            gui_runtime.KumaGUIRuntime()
        )

        assert runtime.run(
            "private-request"
        ) == "private-response"

        snapshot = (
            runtime
            .runtime_observation_snapshot()
        )

        assert isinstance(
            snapshot,
            RuntimeObservationSnapshot,
        )

        assert snapshot.event_count == 4

        assert [
            event.event_kind
            for event in snapshot.events
        ] == [
            "turn.started",
            "agent.run.started",
            "agent.run.returned",
            "turn.ended",
        ]

        assert (
            "private-request"
            not in repr(snapshot)
        )

        assert (
            "private-response"
            not in repr(snapshot)
        )

    finally:
        gui_runtime.create_kuma = (
            original_create
        )


def test_gui_snapshot_projection_failure_is_fail_soft(
    monkeypatch,
):
    class FakeKuma:
        def __init__(
            self,
            **_,
        ):
            self._runtime_observer = None
            self.realtime_runtime = None

    original_create = (
        gui_runtime.create_kuma
    )

    try:
        gui_runtime.create_kuma = (
            lambda **kwargs:
            FakeKuma(
                **kwargs
            )
        )

        runtime = (
            gui_runtime.KumaGUIRuntime()
        )

        def broken(
            _events,
        ):
            raise RuntimeError(
                "diagnostic failure"
            )

        monkeypatch.setattr(
            gui_runtime,
            "project_runtime_observation",
            broken,
        )

        snapshot = (
            runtime
            .runtime_observation_snapshot()
        )

        assert isinstance(
            snapshot,
            RuntimeObservationSnapshot,
        )

        assert snapshot.events == ()
        assert snapshot.authority == "NONE"

    finally:
        gui_runtime.create_kuma = (
            original_create
        )


def test_gui_runtime_does_not_feed_snapshot_into_agent():
    source = GUI.read_text()

    method_source = inspect.getsource(
        gui_runtime.KumaGUIRuntime
        .runtime_observation_snapshot
    )

    assert (
        "self.kuma.run"
        not in method_source
    )

    assert (
        "confirmation_callback"
        not in method_source
    )

    assert (
        "status_callback"
        not in method_source
    )

    assert (
        source.count(
            "runtime_observation_snapshot"
        )
        == 1
    )


def test_module_documents_trace_not_control():
    text = MODULE.read_text()

    assert "TRACE != CONTROL" in text
    assert "OBSERVATION != COMMAND" in text
    assert "AUTHORITY = NONE" in text


def test_runtime_2f_sources_compile():
    for path in (
        MODULE,
        GUI,
    ):
        compile(
            path.read_text(),
            str(path),
            "exec",
        )
