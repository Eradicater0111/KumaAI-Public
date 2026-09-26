from __future__ import annotations

from datetime import datetime, timezone
import inspect
from pathlib import Path

import pytest

import app.integration_v2_explicit_signal_runtime_bridge as integration_v2b
from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.realtime.contracts import (
    RealtimeFact,
)
from app.runtime_v2_live_owner import (
    KumaRuntimeV2LiveOwner,
)


MODULE = Path(
    "app/integration_v2_explicit_signal_runtime_bridge.py"
)


def make_signal(
    *,
    level=RealtimeRelevanceLevel.HIGH,
    score=0.90,
):
    return RealtimeSignal(
        kind="weather.precipitation",
        level=level,
        score=score,
        reason="precipitation started",
        fact=RealtimeFact(
            kind="weather.precipitation",
            value={"active": True},
            source="test",
            observed_at=datetime(
                2026,
                9,
                22,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            expires_at=None,
        ),
        previous_fact=None,
    )


def test_authority_constant_is_none():
    assert (
        integration_v2b.INTEGRATION_V2B_AUTHORITY_NONE
        == "NONE"
    )


def test_signature_requires_explicit_thresholds_and_single_signal():
    signature = inspect.signature(
        integration_v2b.run_explicit_operation_with_realtime_signal
    )

    assert tuple(
        signature.parameters
    ) == (
        "runtime_owner",
        "operation",
        "signal",
        "minimum_level",
        "minimum_score",
    )

    assert (
        signature.parameters["signal"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    assert (
        signature.parameters["minimum_level"].default
        is inspect.Parameter.empty
    )
    assert (
        signature.parameters["minimum_score"].default
        is inspect.Parameter.empty
    )


def test_runtime_owner_type_is_required():
    called = []

    with pytest.raises(
        TypeError,
        match="runtime_owner",
    ):
        integration_v2b.run_explicit_operation_with_realtime_signal(
            object(),
            lambda: called.append("operation"),
            signal=None,
            minimum_level=RealtimeRelevanceLevel.HIGH,
            minimum_score=0.80,
        )

    assert called == []


def test_operation_must_be_callable():
    owner = KumaRuntimeV2LiveOwner()

    try:
        with pytest.raises(
            TypeError,
            match="operation",
        ):
            integration_v2b.run_explicit_operation_with_realtime_signal(
                owner,
                None,
                signal=None,
                minimum_level=RealtimeRelevanceLevel.HIGH,
                minimum_score=0.80,
            )
    finally:
        owner.close()


def test_none_signal_runs_explicit_operation_once_without_admission(
    monkeypatch,
):
    owner = KumaRuntimeV2LiveOwner()
    calls = []

    def fail_admission(*args, **kwargs):
        raise AssertionError(
            "admission must not run when signal is None"
        )

    monkeypatch.setattr(
        integration_v2b,
        "admit_realtime_observation",
        fail_admission,
    )

    try:
        result = (
            integration_v2b
            .run_explicit_operation_with_realtime_signal(
                owner,
                lambda: calls.append("operation") or "result",
                signal=None,
                minimum_level=RealtimeRelevanceLevel.HIGH,
                minimum_score=0.80,
            )
        )
    finally:
        owner.close()

    assert result == "result"
    assert calls == ["operation"]


def test_eligible_signal_is_admitted_and_forwarded_once(
    monkeypatch,
):
    owner = KumaRuntimeV2LiveOwner()
    signal = make_signal()
    observation = object()
    admissions = []
    runs = []

    def admit(
        supplied_signal,
        *,
        minimum_level,
        minimum_score,
    ):
        admissions.append(
            (
                supplied_signal,
                minimum_level,
                minimum_score,
            )
        )
        return observation

    def fake_run(
        self,
        operation,
        *,
        observation=None,
    ):
        runs.append(
            observation
        )
        return operation()

    monkeypatch.setattr(
        integration_v2b,
        "admit_realtime_observation",
        admit,
    )
    monkeypatch.setattr(
        KumaRuntimeV2LiveOwner,
        "run",
        fake_run,
    )

    try:
        result = (
            integration_v2b
            .run_explicit_operation_with_realtime_signal(
                owner,
                lambda: "ok",
                signal=signal,
                minimum_level=RealtimeRelevanceLevel.HIGH,
                minimum_score=0.80,
            )
        )
    finally:
        owner.close()

    assert result == "ok"
    assert admissions == [
        (
            signal,
            RealtimeRelevanceLevel.HIGH,
            0.80,
        )
    ]
    assert runs == [
        observation
    ]


def test_ineligible_signal_still_runs_explicit_operation_once():
    owner = KumaRuntimeV2LiveOwner()
    calls = []

    try:
        result = (
            integration_v2b
            .run_explicit_operation_with_realtime_signal(
                owner,
                lambda: calls.append("operation") or 7,
                signal=make_signal(
                    level=RealtimeRelevanceLevel.LOW,
                    score=0.20,
                ),
                minimum_level=RealtimeRelevanceLevel.HIGH,
                minimum_score=0.80,
            )
        )

        events = owner.events()
    finally:
        owner.close()

    assert result == 7
    assert calls == ["operation"]

    realtime_events = tuple(
        event
        for event in events
        if event.stage == "realtime"
    )

    assert realtime_events == ()


def test_admission_failure_cannot_cancel_explicit_operation(
    monkeypatch,
):
    owner = KumaRuntimeV2LiveOwner()
    calls = []

    def fail(*args, **kwargs):
        raise RuntimeError(
            "synthetic admission failure"
        )

    monkeypatch.setattr(
        integration_v2b,
        "admit_realtime_observation",
        fail,
    )

    try:
        result = (
            integration_v2b
            .run_explicit_operation_with_realtime_signal(
                owner,
                lambda: calls.append("operation") or "survived",
                signal=make_signal(),
                minimum_level=RealtimeRelevanceLevel.HIGH,
                minimum_score=0.80,
            )
        )
    finally:
        owner.close()

    assert result == "survived"
    assert calls == ["operation"]


def test_operation_exception_propagates_without_retry():
    owner = KumaRuntimeV2LiveOwner()
    calls = []

    def operation():
        calls.append("operation")
        raise LookupError(
            "operation failed"
        )

    try:
        with pytest.raises(
            LookupError,
            match="operation failed",
        ):
            integration_v2b.run_explicit_operation_with_realtime_signal(
                owner,
                operation,
                signal=None,
                minimum_level=RealtimeRelevanceLevel.HIGH,
                minimum_score=0.80,
            )
    finally:
        owner.close()

    assert calls == ["operation"]


def test_real_eligible_signal_becomes_trace_evidence_only():
    owner = KumaRuntimeV2LiveOwner()

    try:
        result = (
            integration_v2b
            .run_explicit_operation_with_realtime_signal(
                owner,
                lambda: "done",
                signal=make_signal(),
                minimum_level=RealtimeRelevanceLevel.HIGH,
                minimum_score=0.80,
            )
        )

        events = owner.events()
    finally:
        owner.close()

    assert result == "done"

    realtime = tuple(
        event
        for event in events
        if event.stage == "realtime"
    )

    assert len(realtime) == 1
    assert realtime[0].event_kind == "trigger.observed"
    assert realtime[0].outcome == "observed"
    assert realtime[0].authority == "NONE"

    kinds = tuple(
        event.event_kind
        for event in events
    )

    assert kinds[0] == "turn.started"
    assert "agent.run.started" in kinds
    assert "agent.run.returned" in kinds
    assert kinds[-1] == "turn.ended"


def test_source_has_no_signal_acquisition_selection_or_control():
    source = MODULE.read_text()

    required = (
        "EXPLICIT OPERATION != REALTIME INVOCATION",
        "SIGNAL INPUT != INVOCATION",
        "ADMISSION != INVOCATION",
        "OBSERVATION != INVOCATION",
        "ADMISSION FAILURE != CALLER OPERATION FAILURE",
        "BRIDGE != SIGNAL ACQUISITION",
        "BRIDGE != SIGNAL SELECTION",
        "BRIDGE != WAKE",
        "AUTHORITY: NONE",
    )

    for marker in required:
        assert marker in source

    for forbidden in (
        "get_realtime_runtime",
        "pending_signals",
        "drain_signals",
        ".tick(",
        "refresh_weather",
        "deque(",
        "QTimer",
        "QThread",
        "threading",
        "create_task",
        "emit_status",
        "get_permission_level",
        "app.tools",
        "KumaGUIRuntime",
        "RuntimeInvocation",
        "KumaRuntimeInvocationDispatcher",
    ):
        assert forbidden not in source


def test_source_composes_only_frozen_public_boundaries():
    source = MODULE.read_text()

    assert (
        "admit_realtime_observation"
        in source
    )
    assert (
        "KumaRuntimeV2LiveOwner"
        in source
    )

    assert source.count(
        "runtime_owner.run("
    ) == 1

    assert source.count(
        "admit_realtime_observation("
    ) == 1
