from __future__ import annotations

import inspect

import pytest

from app.realtime.trigger_observation import (
    RealtimeTriggerObservation,
    RealtimeTriggerObservationStatus,
)
from app.runtime_v2_live_owner import (
    RUNTIME_V2D_AUTHORITY_NONE,
    KumaRuntimeV2LiveOwner,
)


def make_observation():
    return RealtimeTriggerObservation(
        observation_id="observation-a",
        request_id="request-a",
        proposal_id="proposal-a",
        kind="weather_change",
        status=RealtimeTriggerObservationStatus.OBSERVED,
        reason="explicit test observation",
    )


def test_authority_is_permanently_none():
    owner = KumaRuntimeV2LiveOwner()
    assert RUNTIME_V2D_AUTHORITY_NONE == "NONE"
    assert owner.authority == "NONE"


def test_public_surface_is_narrow():
    public = {
        name
        for name, value in KumaRuntimeV2LiveOwner.__dict__.items()
        if not name.startswith("_")
        and (inspect.isfunction(value) or isinstance(value, property))
    }
    assert public == {
        "authority",
        "run",
        "observe_pipeline_event",
        "events",
        "close",
    }


def test_plain_run_executes_once_and_returns_exact_value():
    owner = KumaRuntimeV2LiveOwner()
    calls = []
    result = owner.run(lambda: calls.append("ran") or "result")
    assert result == "result"
    assert calls == ["ran"]


def test_plain_run_has_one_runtime_turn_sequence():
    owner = KumaRuntimeV2LiveOwner()
    owner.run(lambda: "result")
    assert [event.event_kind for event in owner.events()] == [
        "turn.started",
        "agent.run.started",
        "agent.run.returned",
        "turn.ended",
    ]


def test_pipeline_observer_records_into_dispatcher_active_turn():
    owner = KumaRuntimeV2LiveOwner()

    def operation():
        owner.observe_pipeline_event(
            event_kind="permission.classified",
            outcome="safe",
        )
        return "ok"

    assert owner.run(operation) == "ok"

    matching = [
        event
        for event in owner.events()
        if event.event_kind == "permission.classified"
    ]

    assert len(matching) == 1
    assert matching[0].stage == "authority"
    assert matching[0].outcome == "safe"
    assert matching[0].authority == "NONE"


def test_pipeline_observer_outside_turn_is_noop():
    owner = KumaRuntimeV2LiveOwner()
    before = owner.events()
    assert owner.observe_pipeline_event(
        event_kind="permission.classified",
        outcome="safe",
    ) is None
    assert owner.events() == before


def test_observed_run_keeps_observation_as_trace_evidence_only():
    owner = KumaRuntimeV2LiveOwner()
    calls = []

    result = owner.run(
        lambda: calls.append("ran") or "ok",
        observation=make_observation(),
    )

    assert result == "ok"
    assert calls == ["ran"]

    realtime = [
        event
        for event in owner.events()
        if event.event_kind == "trigger.observed"
    ]

    assert len(realtime) == 1
    assert realtime[0].stage == "realtime"
    assert realtime[0].outcome == "observed"
    assert realtime[0].authority == "NONE"


def test_invalid_observation_is_rejected_before_operation():
    owner = KumaRuntimeV2LiveOwner()
    calls = []

    with pytest.raises(TypeError):
        owner.run(
            lambda: calls.append("ran"),
            observation=object(),
        )

    assert calls == []


def test_reentrant_run_is_rejected_before_inner_operation():
    owner = KumaRuntimeV2LiveOwner()
    inner_calls = []

    def outer():
        with pytest.raises(
            RuntimeError,
            match="already active",
        ):
            owner.run(
                lambda: inner_calls.append("inner")
            )
        return "outer"

    assert owner.run(outer) == "outer"
    assert inner_calls == []


def test_close_then_run_is_fail_closed():
    owner = KumaRuntimeV2LiveOwner()
    owner.close()
    calls = []

    with pytest.raises(
        RuntimeError,
        match="closed",
    ):
        owner.run(
            lambda: calls.append("ran")
        )

    assert calls == []


def test_events_remain_readable_after_close():
    owner = KumaRuntimeV2LiveOwner()
    owner.run(lambda: "ok")
    before = owner.events()
    owner.close()
    assert owner.events() == before


def test_run_does_not_acquire_or_admit_realtime_state():
    import app.runtime_v2_live_owner as module
    source = inspect.getsource(module)

    for forbidden in (
        "get_realtime_runtime",
        "pending_signals",
        "drain_signals",
        "admit_realtime_observation",
        "evaluate_trigger_eligibility",
        "propose_runtime_trigger",
        "create_trigger_request",
        "observe_trigger_request",
        "QTimer",
        "QThread",
        "Thread(",
    ):
        assert forbidden not in source


def test_boundary_markers_are_explicit():
    import app.runtime_v2_live_owner as module
    source = inspect.getsource(module)

    for marker in (
        "CALLER INTENT -> EXPLICIT OPERATION -> RuntimeInvocation -> Runtime-V2C",
        "PIPELINE EVENT -> ACTIVE TURN TRACE ONLY",
        "OPTIONAL OBSERVATION -> EVIDENCE ONLY",
        "OWNER != ADMISSION",
        "OWNER != SCHEDULER",
        "OWNER != PERMISSION",
        "OWNER != EXECUTION AUTHORITY",
        "PIPELINE OBSERVATION != CONTROL",
        "OBSERVATION != INVOCATION",
        "ONE RUN CALL = ONE RuntimeInvocation",
        "AUTHORITY: NONE",
    ):
        assert marker in source
