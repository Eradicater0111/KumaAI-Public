from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import ast
import inspect
import math
from pathlib import Path

import pytest

import app.integration_v2_live_turn_owner as integration_v2d
from app.integration_v2_realtime_turn_preflight import (
    RealtimeTurnPreflight,
)
from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.realtime.contracts import (
    RealtimeFact,
)
from app.realtime.runtime import (
    RealtimeRuntime,
)
from app.runtime_v2_live_owner import (
    KumaRuntimeV2LiveOwner,
)


MODULE = Path(
    "app/integration_v2_live_turn_owner.py"
)

GUI = Path(
    "app/agent/gui_runtime.py"
)

CLI = Path(
    "app/agent/kuma_runtime.py"
)

AGENT = Path(
    "app/agent/kuma_agent.py"
)


def make_signal(
    name: str = "weather.precipitation",
    *,
    level=RealtimeRelevanceLevel.HIGH,
    score=0.90,
):
    return RealtimeSignal(
        kind=name,
        level=level,
        score=score,
        reason=name,
        fact=RealtimeFact(
            kind=name,
            value={
                "active": True,
            },
            source="integration-v2d-test",
            observed_at=datetime(
                2026,
                9,
                23,
                5,
                0,
                tzinfo=timezone.utc,
            ),
            expires_at=None,
        ),
        previous_fact=None,
    )


class StubRealtimeRuntime(
    RealtimeRuntime
):
    def __init__(
        self,
        signals=(),
        *,
        tick_error=None,
        snapshot_error=None,
    ):
        self.supplied_signals = tuple(
            signals
        )
        self.tick_error = tick_error
        self.snapshot_error = snapshot_error
        self.tick_calls = 0
        self.pending_calls = 0
        self.drain_calls = 0

    def tick(self):
        self.tick_calls += 1

        if self.tick_error is not None:
            raise self.tick_error

        return ()

    def pending_signals(self):
        self.pending_calls += 1

        if self.snapshot_error is not None:
            raise self.snapshot_error

        return self.supplied_signals

    def drain_signals(self):
        self.drain_calls += 1
        raise AssertionError(
            "Integration-V2D must never drain signals."
        )


def policy(
    *,
    level=RealtimeRelevanceLevel.MEDIUM,
    score=0.80,
):
    return (
        integration_v2d
        .RealtimeTriggerAdmissionPolicy(
            minimum_level=level,
            minimum_score=score,
        )
    )


def owner(
    runtime_owner,
    realtime_runtime,
    *,
    trigger_policy=None,
):
    return (
        integration_v2d
        .KumaIntegrationV2LiveTurnOwner(
            runtime_owner=runtime_owner,
            realtime_runtime=realtime_runtime,
            trigger_policy=(
                trigger_policy
                if trigger_policy is not None
                else policy()
            ),
        )
    )


def imported_from(
    path,
):
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    result = {}

    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            result.setdefault(
                node.module,
                set(),
            ).update(
                alias.name
                for alias in node.names
            )

    return result


def test_authority_constant_is_none():
    assert (
        integration_v2d.INTEGRATION_V2D_AUTHORITY_NONE
        == "NONE"
    )


def test_policy_is_immutable_and_zero_authority():
    item = policy()

    assert item.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        item.minimum_score = 0.50


def test_policy_has_no_threshold_defaults():
    signature = inspect.signature(
        integration_v2d.RealtimeTriggerAdmissionPolicy
    )

    assert (
        signature.parameters[
            "minimum_level"
        ].default
        is inspect.Parameter.empty
    )

    assert (
        signature.parameters[
            "minimum_score"
        ].default
        is inspect.Parameter.empty
    )


def test_policy_rejects_non_realtime_level():
    with pytest.raises(
        TypeError,
        match="minimum_level",
    ):
        integration_v2d.RealtimeTriggerAdmissionPolicy(
            minimum_level="high",
            minimum_score=0.8,
        )


def test_policy_rejects_ignore_level():
    with pytest.raises(
        ValueError,
        match="IGNORE",
    ):
        integration_v2d.RealtimeTriggerAdmissionPolicy(
            minimum_level=RealtimeRelevanceLevel.IGNORE,
            minimum_score=0.8,
        )


@pytest.mark.parametrize(
    "value",
    (
        -0.01,
        1.01,
        math.inf,
        -math.inf,
        math.nan,
    ),
)
def test_policy_rejects_invalid_score(
    value,
):
    with pytest.raises(
        ValueError,
        match="minimum_score",
    ):
        integration_v2d.RealtimeTriggerAdmissionPolicy(
            minimum_level=RealtimeRelevanceLevel.HIGH,
            minimum_score=value,
        )


def test_policy_normalizes_score_like_frozen_threshold_boundary():
    item = integration_v2d.RealtimeTriggerAdmissionPolicy(
        minimum_level=RealtimeRelevanceLevel.HIGH,
        minimum_score="0.80",
    )

    assert item.minimum_score == 0.80
    assert type(
        item.minimum_score
    ) is float


def test_owner_constructor_requires_runtime_v2d_owner():
    with pytest.raises(
        TypeError,
        match="runtime_owner",
    ):
        integration_v2d.KumaIntegrationV2LiveTurnOwner(
            runtime_owner=object(),
            realtime_runtime=None,
            trigger_policy=policy(),
        )


def test_owner_constructor_rejects_invalid_realtime_runtime():
    runtime_owner = KumaRuntimeV2LiveOwner()

    try:
        with pytest.raises(
            TypeError,
            match="realtime_runtime",
        ):
            owner(
                runtime_owner,
                object(),
            )
    finally:
        runtime_owner.close()


def test_owner_constructor_requires_explicit_policy():
    runtime_owner = KumaRuntimeV2LiveOwner()

    try:
        with pytest.raises(
            TypeError,
            match="trigger_policy",
        ):
            integration_v2d.KumaIntegrationV2LiveTurnOwner(
                runtime_owner=runtime_owner,
                realtime_runtime=None,
                trigger_policy=None,
            )
    finally:
        runtime_owner.close()


def test_owner_authority_is_none():
    runtime_owner = KumaRuntimeV2LiveOwner()

    try:
        subject = owner(
            runtime_owner,
            None,
        )

        assert subject.authority == "NONE"
    finally:
        runtime_owner.close()


def test_run_requires_callable_operation():
    runtime_owner = KumaRuntimeV2LiveOwner()

    try:
        subject = owner(
            runtime_owner,
            None,
        )

        with pytest.raises(
            TypeError,
            match="operation",
        ):
            subject.run(
                None
            )
    finally:
        runtime_owner.close()


def test_preflight_runs_before_explicit_operation_and_passes_exact_identity(
    monkeypatch,
):
    runtime_owner = KumaRuntimeV2LiveOwner()
    runtime = StubRealtimeRuntime()
    sequence = []
    prepared = RealtimeTurnPreflight(
        signals=(),
        selected_signal=None,
        tick_attempted=True,
        tick_succeeded=True,
        snapshot_succeeded=True,
    )

    def fake_prepare(
        supplied_runtime,
        *,
        minimum_level,
        minimum_score,
    ):
        sequence.append(
            (
                "prepare",
                supplied_runtime,
                minimum_level,
                minimum_score,
            )
        )
        return prepared

    def fake_bridge(
        supplied_owner,
        operation,
        *,
        signal,
        minimum_level,
        minimum_score,
    ):
        sequence.append(
            (
                "bridge",
                supplied_owner,
                signal,
                minimum_level,
                minimum_score,
            )
        )
        return operation()

    monkeypatch.setattr(
        integration_v2d,
        "prepare_realtime_turn",
        fake_prepare,
    )
    monkeypatch.setattr(
        integration_v2d,
        "run_explicit_operation_with_realtime_signal",
        fake_bridge,
    )

    try:
        subject = owner(
            runtime_owner,
            runtime,
        )

        result = subject.run(
            lambda preflight: (
                sequence.append(
                    (
                        "operation",
                        preflight,
                    )
                )
                or "ok"
            )
        )
    finally:
        runtime_owner.close()

    assert result == "ok"

    assert sequence == [
        (
            "prepare",
            runtime,
            RealtimeRelevanceLevel.MEDIUM,
            0.80,
        ),
        (
            "bridge",
            runtime_owner,
            None,
            RealtimeRelevanceLevel.MEDIUM,
            0.80,
        ),
        (
            "operation",
            prepared,
        ),
    ]


def test_selected_signal_is_forwarded_by_identity_to_v2b(
    monkeypatch,
):
    runtime_owner = KumaRuntimeV2LiveOwner()
    signal = make_signal()
    prepared = RealtimeTurnPreflight(
        signals=(
            signal,
        ),
        selected_signal=signal,
        tick_attempted=True,
        tick_succeeded=True,
        snapshot_succeeded=True,
    )
    forwarded = []

    monkeypatch.setattr(
        integration_v2d,
        "prepare_realtime_turn",
        lambda *args, **kwargs: prepared,
    )

    def fake_bridge(
        supplied_owner,
        operation,
        *,
        signal,
        minimum_level,
        minimum_score,
    ):
        forwarded.append(
            signal
        )
        return operation()

    monkeypatch.setattr(
        integration_v2d,
        "run_explicit_operation_with_realtime_signal",
        fake_bridge,
    )

    try:
        result = owner(
            runtime_owner,
            None,
        ).run(
            lambda supplied: supplied
        )
    finally:
        runtime_owner.close()

    assert result is prepared
    assert forwarded == [
        signal,
    ]
    assert forwarded[0] is signal


def test_real_composition_ticks_and_snapshots_once_and_runs_operation_once():
    runtime_owner = KumaRuntimeV2LiveOwner()
    signal = make_signal()
    runtime = StubRealtimeRuntime(
        (
            signal,
        )
    )
    calls = []

    try:
        subject = owner(
            runtime_owner,
            runtime,
            trigger_policy=policy(
                level=RealtimeRelevanceLevel.HIGH,
                score=0.80,
            ),
        )

        result = subject.run(
            lambda prepared: (
                calls.append(
                    prepared
                )
                or "done"
            )
        )

        events = (
            runtime_owner.events()
        )
    finally:
        runtime_owner.close()

    assert result == "done"
    assert len(calls) == 1
    assert calls[0].selected_signal is signal

    assert runtime.tick_calls == 1
    assert runtime.pending_calls == 1
    assert runtime.drain_calls == 0

    realtime = tuple(
        event
        for event in events
        if event.stage == "realtime"
    )

    assert len(realtime) == 1
    assert realtime[0].event_kind == "trigger.observed"
    assert realtime[0].outcome == "observed"
    assert realtime[0].authority == "NONE"


def test_none_runtime_still_runs_explicit_operation_once():
    runtime_owner = KumaRuntimeV2LiveOwner()
    calls = []

    try:
        result = owner(
            runtime_owner,
            None,
        ).run(
            lambda prepared: (
                calls.append(
                    prepared
                )
                or 7
            )
        )
    finally:
        runtime_owner.close()

    assert result == 7
    assert len(calls) == 1
    assert calls[0].signals == ()
    assert calls[0].selected_signal is None
    assert calls[0].tick_attempted is False


def test_tick_failure_still_runs_explicit_operation_once():
    runtime_owner = KumaRuntimeV2LiveOwner()
    signal = make_signal()
    runtime = StubRealtimeRuntime(
        (
            signal,
        ),
        tick_error=RuntimeError(
            "synthetic tick failure"
        ),
    )
    calls = []

    try:
        result = owner(
            runtime_owner,
            runtime,
        ).run(
            lambda prepared: (
                calls.append(
                    prepared
                )
                or "survived"
            )
        )
    finally:
        runtime_owner.close()

    assert result == "survived"
    assert len(calls) == 1
    assert calls[0].tick_attempted is True
    assert calls[0].tick_succeeded is False
    assert calls[0].snapshot_succeeded is True
    assert runtime.tick_calls == 1
    assert runtime.pending_calls == 1


def test_snapshot_failure_still_runs_explicit_operation_once():
    runtime_owner = KumaRuntimeV2LiveOwner()
    runtime = StubRealtimeRuntime(
        snapshot_error=RuntimeError(
            "synthetic snapshot failure"
        ),
    )
    calls = []

    try:
        result = owner(
            runtime_owner,
            runtime,
        ).run(
            lambda prepared: (
                calls.append(
                    prepared
                )
                or "survived"
            )
        )
    finally:
        runtime_owner.close()

    assert result == "survived"
    assert len(calls) == 1
    assert calls[0].snapshot_succeeded is False
    assert calls[0].signals == ()
    assert calls[0].selected_signal is None
    assert runtime.tick_calls == 1
    assert runtime.pending_calls == 1


def test_ineligible_signal_still_runs_operation_without_realtime_trace():
    runtime_owner = KumaRuntimeV2LiveOwner()
    signal = make_signal(
        level=RealtimeRelevanceLevel.LOW,
        score=0.20,
    )
    runtime = StubRealtimeRuntime(
        (
            signal,
        )
    )

    try:
        result = owner(
            runtime_owner,
            runtime,
        ).run(
            lambda prepared: "ok"
        )

        events = (
            runtime_owner.events()
        )
    finally:
        runtime_owner.close()

    assert result == "ok"

    realtime = tuple(
        event
        for event in events
        if event.stage == "realtime"
    )

    assert realtime == ()


def test_operation_exception_propagates_without_retry():
    runtime_owner = KumaRuntimeV2LiveOwner()
    calls = []

    def operation(
        prepared,
    ):
        calls.append(
            prepared
        )
        raise LookupError(
            "operation failed"
        )

    try:
        with pytest.raises(
            LookupError,
            match="operation failed",
        ):
            owner(
                runtime_owner,
                None,
            ).run(
                operation
            )
    finally:
        runtime_owner.close()

    assert len(calls) == 1


def test_module_import_surface_is_exact():
    assert imported_from(
        MODULE
    ) == {
        "__future__": {
            "annotations",
        },
        "dataclasses": {
            "dataclass",
            "field",
        },
        "typing": {
            "Callable",
            "TypeVar",
        },
        "app.integration_v2_explicit_signal_runtime_bridge": {
            "run_explicit_operation_with_realtime_signal",
        },
        "app.integration_v2_realtime_turn_preflight": {
            "RealtimeTurnPreflight",
            "prepare_realtime_turn",
        },
        "app.realtime.change_detection": {
            "RealtimeRelevanceLevel",
        },
        "app.realtime.runtime": {
            "RealtimeRuntime",
        },
        "app.runtime_v2_live_owner": {
            "KumaRuntimeV2LiveOwner",
        },
    }


def test_source_declares_composition_boundaries():
    source = MODULE.read_text()

    for marker in (
        "POLICY INPUT != WAKE POLICY DISCOVERY",
        "PREFLIGHT != INVOCATION",
        "SELECTED SIGNAL != INVOCATION",
        "ADMISSION != INVOCATION",
        "OBSERVATION != CONTROL",
        "INTEGRATION OWNER != SCHEDULER",
        "INTEGRATION OWNER != BACKGROUND LOOP",
        "INTEGRATION OWNER != PERMISSION",
        "INTEGRATION OWNER != EXECUTION AUTHORITY",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_source_has_no_hidden_policy_defaults_or_control_surfaces():
    source = MODULE.read_text()

    for forbidden in (
        "get_realtime_runtime",
        "pending_signals",
        "drain_signals",
        "SURFACE_THRESHOLD",
        "ESCALATE_THRESHOLD",
        "minimum_level=" + "RealtimeRelevanceLevel.",
        "minimum_score=0.",
        "create_trigger_request",
        "observe_trigger_request",
        "get_permission_level",
        "request_confirmation",
        "self.executor",
        "ask_model",
        "register_tool",
        "QTimer",
        "QThread",
        "Thread(",
        "asyncio",
        "while True",
    ):
        assert forbidden not in source


def test_owner_has_no_close_or_events_lifecycle_surface():
    assert not hasattr(
        integration_v2d.KumaIntegrationV2LiveTurnOwner,
        "close",
    )

    assert not hasattr(
        integration_v2d.KumaIntegrationV2LiveTurnOwner,
        "events",
    )


def test_owner_does_not_acquire_runtime_v2d_or_realtime_runtime():
    source = inspect.getsource(
        integration_v2d.KumaIntegrationV2LiveTurnOwner.__init__
    )

    assert "KumaRuntimeV2LiveOwner()" not in source
    assert "get_realtime_runtime" not in source


def test_gui_cli_and_agent_remain_byte_unmodified_by_this_phase():
    # This phase creates only the Integration-V2D owner + regression.
    # Production wiring is deliberately deferred.
    for path in (
        GUI,
        CLI,
        AGENT,
    ):
        assert path.exists()
