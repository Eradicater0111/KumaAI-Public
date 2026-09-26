from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import ast

import pytest

from app.realtime.runtime_trace_adapter import (
    REALTIME_RUNTIME_TRACE_AUTHORITY_NONE,
    record_trigger_observation,
)
from app.realtime.trigger_observation import (
    RealtimeTriggerObservation,
    RealtimeTriggerObservationStatus,
)
from app.runtime_correlation import (
    KumaRuntimeCorrelation,
    RuntimeTurnCorrelation,
)
from app.runtime_observability import (
    project_runtime_observation,
)
from app.runtime_trace import (
    KumaRuntimeTrace,
    RuntimeTraceEvent,
)


MODULE = Path(
    "app/realtime/runtime_trace_adapter.py"
)

FROZEN_2D = Path(
    "app/realtime/trigger_observation.py"
)

FROZEN_RUNTIME = (
    Path("app/runtime_trace.py"),
    Path("app/runtime_correlation.py"),
    Path("app/runtime_live_binding.py"),
    Path("app/runtime_observability.py"),
    Path("app/agent/gui_runtime.py"),
)


def _observation(
    *,
    observation_id: str = (
        "rto-"
        + "a" * 64
    ),
    request_id: str = (
        "rtr-"
        + "b" * 64
    ),
    proposal_id: str = (
        "rtp-"
        + "c" * 64
    ),
    kind: str = "weather.current",
) -> RealtimeTriggerObservation:
    return RealtimeTriggerObservation(
        observation_id=observation_id,
        request_id=request_id,
        proposal_id=proposal_id,
        kind=kind,
        status=(
            RealtimeTriggerObservationStatus.OBSERVED
        ),
        reason=(
            "caller observed zero-authority realtime trigger request"
        ),
    )


def _active_runtime():
    correlation = KumaRuntimeCorrelation()
    turn = correlation.begin_turn()
    return correlation, turn


def _forged_observation(
    *,
    authority="NONE",
    status=RealtimeTriggerObservationStatus.OBSERVED,
):
    value = object.__new__(
        RealtimeTriggerObservation
    )

    object.__setattr__(
        value,
        "observation_id",
        "rto-" + "a" * 64,
    )
    object.__setattr__(
        value,
        "request_id",
        "rtr-" + "b" * 64,
    )
    object.__setattr__(
        value,
        "proposal_id",
        "rtp-" + "c" * 64,
    )
    object.__setattr__(
        value,
        "kind",
        "weather.current",
    )
    object.__setattr__(
        value,
        "status",
        status,
    )
    object.__setattr__(
        value,
        "reason",
        "structural",
    )
    object.__setattr__(
        value,
        "authority",
        authority,
    )

    return value


def test_2f_files_exist():
    assert MODULE.is_file()


def test_2f_authority_constant_is_none():
    assert (
        REALTIME_RUNTIME_TRACE_AUTHORITY_NONE
        == "NONE"
    )


def test_2f_records_one_structural_runtime_event():
    correlation, turn = _active_runtime()

    event = record_trigger_observation(
        _observation(),
        correlation=correlation,
        turn=turn,
    )

    assert isinstance(
        event,
        RuntimeTraceEvent,
    )
    assert event.stage == "realtime"
    assert event.event_kind == "trigger.observed"
    assert event.outcome == "observed"
    assert event.authority == "NONE"


def test_2f_requires_exact_active_turn_object():
    correlation, turn = _active_runtime()

    reconstructed = RuntimeTurnCorrelation(
        session_id=turn.session_id,
        turn_id=turn.turn_id,
        trace_id=turn.trace_id,
        turn_index=turn.turn_index,
        started_monotonic_ns=(
            turn.started_monotonic_ns
        ),
    )

    with pytest.raises(
        ValueError,
        match="exact active",
    ):
        record_trigger_observation(
            _observation(),
            correlation=correlation,
            turn=reconstructed,
        )


def test_2f_rejects_turn_owned_by_other_correlation():
    first, turn = _active_runtime()
    second, _ = _active_runtime()

    with pytest.raises(
        ValueError,
        match="exact active",
    ):
        record_trigger_observation(
            _observation(),
            correlation=second,
            turn=turn,
        )

    assert first.active_turn is turn


def test_2f_rejects_non_observation():
    correlation, turn = _active_runtime()

    with pytest.raises(TypeError):
        record_trigger_observation(
            object(),
            correlation=correlation,
            turn=turn,
        )


def test_2f_rejects_non_correlation():
    _, turn = _active_runtime()

    with pytest.raises(TypeError):
        record_trigger_observation(
            _observation(),
            correlation=object(),
            turn=turn,
        )


def test_2f_rejects_non_turn():
    correlation, _ = _active_runtime()

    with pytest.raises(TypeError):
        record_trigger_observation(
            _observation(),
            correlation=correlation,
            turn=object(),
        )


def test_2f_rejects_forged_observation_authority():
    correlation, turn = _active_runtime()

    with pytest.raises(
        ValueError,
        match="authority",
    ):
        record_trigger_observation(
            _forged_observation(
                authority="EXECUTE",
            ),
            correlation=correlation,
            turn=turn,
        )


def test_2f_rejects_forged_observation_status():
    correlation, turn = _active_runtime()

    forged = _forged_observation(
        status="delivered",
    )

    with pytest.raises(
        ValueError,
        match="OBSERVED",
    ):
        record_trigger_observation(
            forged,
            correlation=correlation,
            turn=turn,
        )


def test_2f_metadata_is_privacy_minimized():
    correlation, turn = _active_runtime()

    event = record_trigger_observation(
        _observation(),
        correlation=correlation,
        turn=turn,
    )

    metadata = dict(
        event.metadata
    )

    assert set(
        metadata
    ) == {
        "realtime.observation_id",
        "realtime.kind",
        "realtime.status",
        "session.id",
        "turn.id",
        "turn.index",
    }


def test_2f_metadata_keeps_only_observation_identity_not_request_or_proposal():
    correlation, turn = _active_runtime()

    observation = _observation()

    event = record_trigger_observation(
        observation,
        correlation=correlation,
        turn=turn,
    )

    metadata = dict(
        event.metadata
    )

    assert (
        metadata[
            "realtime.observation_id"
        ]
        == observation.observation_id
    )
    assert "realtime.request_id" not in metadata
    assert "realtime.proposal_id" not in metadata


def test_2f_does_not_copy_observation_reason():
    correlation, turn = _active_runtime()

    observation = _observation()

    event = record_trigger_observation(
        observation,
        correlation=correlation,
        turn=turn,
    )

    assert (
        observation.reason
        not in repr(
            event
        )
    )
    assert event.reason == ""


def test_2f_does_not_copy_raw_realtime_fact_fields():
    correlation, turn = _active_runtime()

    event = record_trigger_observation(
        _observation(),
        correlation=correlation,
        turn=turn,
    )

    metadata = dict(
        event.metadata
    )

    forbidden = {
        "value",
        "raw_value",
        "fact",
        "previous_fact",
        "location",
        "latitude",
        "longitude",
        "prompt",
        "user_message",
        "payload",
        "tool",
        "command",
    }

    assert not (
        set(metadata)
        & forbidden
    )


def test_2f_runtime_2f_projection_strips_realtime_metadata():
    correlation, turn = _active_runtime()

    record_trigger_observation(
        _observation(),
        correlation=correlation,
        turn=turn,
    )

    snapshot = (
        project_runtime_observation(
            correlation.events_for_turn(
                turn.turn_id
            )
        )
    )

    projected = snapshot.events[-1]

    assert projected.stage == "realtime"
    assert (
        projected.event_kind
        == "trigger.observed"
    )
    assert projected.outcome == "observed"
    assert projected.authority == "NONE"

    assert not hasattr(
        projected,
        "observation_id",
    )
    assert not hasattr(
        projected,
        "request_id",
    )
    assert not hasattr(
        projected,
        "proposal_id",
    )
    assert not hasattr(
        projected,
        "kind",
    )


def test_2f_recording_does_not_end_turn():
    correlation, turn = _active_runtime()

    record_trigger_observation(
        _observation(),
        correlation=correlation,
        turn=turn,
    )

    assert correlation.active_turn is turn


def test_2f_recording_does_not_begin_another_turn():
    correlation, turn = _active_runtime()

    before = tuple(
        correlation.events_for_session()
    )

    record_trigger_observation(
        _observation(),
        correlation=correlation,
        turn=turn,
    )

    after = tuple(
        correlation.events_for_session()
    )

    assert (
        sum(
            event.event_kind
            == "turn.started"
            for event in after
        )
        == sum(
            event.event_kind
            == "turn.started"
            for event in before
        )
    )


def test_2f_recording_is_fail_soft_after_valid_boundary(monkeypatch):
    correlation, turn = _active_runtime()

    trace = correlation.trace

    def boom(**kwargs):
        raise RuntimeError(
            "diagnostic failure"
        )

    monkeypatch.setattr(
        trace,
        "record",
        boom,
    )

    assert (
        record_trigger_observation(
            _observation(),
            correlation=correlation,
            turn=turn,
        )
        is None
    )


def test_2f_module_imports_only_realtime_2d_and_frozen_runtime_contracts():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    app_imports = set()

    for node in ast.walk(tree):
        if isinstance(
            node,
            ast.ImportFrom,
        ) and node.module:
            if node.module.startswith(
                "app."
            ):
                app_imports.add(
                    node.module
                )

        elif isinstance(
            node,
            ast.Import,
        ):
            for alias in node.names:
                if alias.name.startswith(
                    "app."
                ):
                    app_imports.add(
                        alias.name
                    )

    assert app_imports == {
        "app.realtime.trigger_observation",
        "app.runtime_correlation",
        "app.runtime_trace",
    }


@pytest.mark.parametrize(
    "forbidden",
    (
        "app.agent",
        "app.ui",
        "app.tools",
        "get_realtime_runtime",
        "KumaAgent",
        "KumaGUIRuntime",
        "emit_status",
        "pending_signals",
        "drain_signals",
        "scheduler",
        "QTimer",
        "QThread",
        "Thread(",
        "create_task(",
        ".run(",
        ".emit(",
        ".connect(",
        ".subscribe(",
        ".publish(",
    ),
)
def test_2f_module_has_no_control_or_background_surface(
    forbidden,
):
    assert forbidden not in MODULE.read_text()


@pytest.mark.parametrize(
    "marker",
    (
        "RECORDING != CONTROL",
        "TRACE != AUTHORITY",
        "OBSERVATION != EXECUTION",
        "RECORDING != DELIVERY",
        "RECORDING != ACKNOWLEDGMENT",
        "RECORDING != VERIFIED COMPLETION",
        "AUTHORITY: NONE",
    ),
)
def test_2f_boundary_markers_are_explicit(
    marker,
):
    assert marker in MODULE.read_text()


def test_2f_does_not_edit_frozen_2d_contract_shape():
    source = FROZEN_2D.read_text()

    for required in (
        "class RealtimeTriggerObservationStatus",
        "class RealtimeTriggerObservation",
        "def observe_trigger_request(",
        'REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE = "NONE"',
    ):
        assert required in source


def test_2f_does_not_depend_on_frozen_runtime_private_members():
    source = MODULE.read_text()

    assert "._correlation" not in source
    assert "._trace" not in source
    assert "._active_turn" not in source
    assert "._record" not in source


def test_2f_uses_public_correlation_trace_and_active_turn():
    source = MODULE.read_text()

    assert "correlation.active_turn" in source
    assert "correlation.trace" in source


def test_2f_source_compiles():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )


def test_frozen_runtime_files_still_exist():
    for path in FROZEN_RUNTIME:
        assert path.is_file()
