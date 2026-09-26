from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import ast
import inspect
from pathlib import Path

import pytest

import app.integration_v2_realtime_turn_preflight as integration_v2c
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


MODULE = Path(
    "app/integration_v2_realtime_turn_preflight.py"
)


def make_signal(
    name: str,
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
                "name": name,
            },
            source="integration-v2c-test",
            observed_at=datetime(
                2026,
                9,
                23,
                4,
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
            "Integration-V2C must never drain signals."
        )


def prepare(
    runtime,
    *,
    minimum_level=RealtimeRelevanceLevel.MEDIUM,
    minimum_score=0.80,
):
    return integration_v2c.prepare_realtime_turn(
        runtime,
        minimum_level=minimum_level,
        minimum_score=minimum_score,
    )


def _app_imports():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    result = {}

    for node in ast.walk(tree):
        if isinstance(
            node,
            ast.ImportFrom,
        ) and node.module:
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
        integration_v2c.INTEGRATION_V2C_AUTHORITY_NONE
        == "NONE"
    )


def test_preflight_is_immutable_zero_authority():
    item = integration_v2c.RealtimeTurnPreflight(
        signals=(),
        selected_signal=None,
        tick_attempted=False,
        tick_succeeded=False,
        snapshot_succeeded=False,
    )

    assert item.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        item.tick_attempted = True


def test_signature_requires_explicit_thresholds():
    signature = inspect.signature(
        integration_v2c.prepare_realtime_turn
    )

    assert tuple(
        signature.parameters
    ) == (
        "realtime_runtime",
        "minimum_level",
        "minimum_score",
    )

    assert (
        signature.parameters[
            "minimum_level"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    assert (
        signature.parameters[
            "minimum_score"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
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


def test_none_runtime_is_explicit_empty_preflight():
    result = prepare(
        None
    )

    assert result.signals == ()
    assert result.selected_signal is None
    assert result.tick_attempted is False
    assert result.tick_succeeded is False
    assert result.snapshot_succeeded is False
    assert result.authority == "NONE"


def test_invalid_runtime_is_rejected_before_any_side_effect():
    with pytest.raises(
        TypeError,
        match="realtime_runtime",
    ):
        prepare(
            object()
        )


def test_runtime_gets_exactly_one_tick_and_one_snapshot():
    runtime = StubRealtimeRuntime()

    result = prepare(
        runtime
    )

    assert result.tick_attempted is True
    assert result.tick_succeeded is True
    assert result.snapshot_succeeded is True
    assert runtime.tick_calls == 1
    assert runtime.pending_calls == 1
    assert runtime.drain_calls == 0


def test_tick_failure_is_isolated_and_snapshot_still_occurs_once():
    signal = make_signal(
        "weather.tick-failure"
    )

    runtime = StubRealtimeRuntime(
        (
            signal,
        ),
        tick_error=RuntimeError(
            "synthetic tick failure"
        ),
    )

    result = prepare(
        runtime
    )

    assert result.tick_attempted is True
    assert result.tick_succeeded is False
    assert result.snapshot_succeeded is True
    assert result.signals == (
        signal,
    )
    assert result.selected_signal is signal
    assert runtime.tick_calls == 1
    assert runtime.pending_calls == 1
    assert runtime.drain_calls == 0


def test_snapshot_failure_is_isolated_without_retry_or_drain():
    runtime = StubRealtimeRuntime(
        snapshot_error=RuntimeError(
            "synthetic snapshot failure"
        ),
    )

    result = prepare(
        runtime
    )

    assert result.tick_attempted is True
    assert result.tick_succeeded is True
    assert result.snapshot_succeeded is False
    assert result.signals == ()
    assert result.selected_signal is None
    assert runtime.tick_calls == 1
    assert runtime.pending_calls == 1
    assert runtime.drain_calls == 0


def test_snapshot_is_preserved_by_exact_signal_identity():
    first = make_signal(
        "weather.first"
    )
    second = make_signal(
        "weather.second"
    )

    runtime = StubRealtimeRuntime(
        (
            first,
            second,
        )
    )

    result = prepare(
        runtime
    )

    assert len(
        result.signals
    ) == 2

    assert (
        result.signals[0]
        is first
    )

    assert (
        result.signals[1]
        is second
    )


def test_first_eligible_signal_in_snapshot_order_is_selected():
    ineligible = make_signal(
        "weather.ineligible",
        level=RealtimeRelevanceLevel.HIGH,
        score=0.55,
    )

    first_eligible = make_signal(
        "weather.first-eligible",
        level=RealtimeRelevanceLevel.MEDIUM,
        score=0.95,
    )

    later_eligible = make_signal(
        "weather.later-eligible",
        level=RealtimeRelevanceLevel.HIGH,
        score=0.99,
    )

    runtime = StubRealtimeRuntime(
        (
            ineligible,
            first_eligible,
            later_eligible,
        )
    )

    result = prepare(
        runtime,
        minimum_level=RealtimeRelevanceLevel.MEDIUM,
        minimum_score=0.80,
    )

    assert (
        result.selected_signal
        is first_eligible
    )

    assert (
        result.selected_signal
        is not later_eligible
    )


def test_selection_does_not_strengthen_or_copy_signal():
    signal = make_signal(
        "weather.identity"
    )

    runtime = StubRealtimeRuntime(
        (
            signal,
        )
    )

    result = prepare(
        runtime
    )

    assert result.selected_signal is signal
    assert result.selected_signal.level is signal.level
    assert result.selected_signal.score == signal.score
    assert result.selected_signal.reason == signal.reason


def test_no_eligible_signal_returns_none_without_mutating_snapshot():
    low_score = make_signal(
        "weather.low-score",
        level=RealtimeRelevanceLevel.HIGH,
        score=0.20,
    )

    low_level = make_signal(
        "weather.low-level",
        level=RealtimeRelevanceLevel.LOW,
        score=0.99,
    )

    supplied = (
        low_score,
        low_level,
    )

    runtime = StubRealtimeRuntime(
        supplied
    )

    result = prepare(
        runtime,
        minimum_level=RealtimeRelevanceLevel.MEDIUM,
        minimum_score=0.80,
    )

    assert result.selected_signal is None
    assert result.signals == supplied
    assert runtime.drain_calls == 0


def test_ignore_or_zero_score_signal_is_not_selected():
    ignore = make_signal(
        "weather.ignore",
        level=RealtimeRelevanceLevel.IGNORE,
        score=0.0,
    )

    runtime = StubRealtimeRuntime(
        (
            ignore,
        )
    )

    result = prepare(
        runtime
    )

    assert result.selected_signal is None


def test_selected_signal_must_be_exact_member_identity():
    in_snapshot = make_signal(
        "weather.member"
    )

    equal_but_distinct = make_signal(
        "weather.member"
    )

    assert (
        equal_but_distinct
        == in_snapshot
    )
    assert (
        equal_but_distinct
        is not in_snapshot
    )

    with pytest.raises(
        ValueError,
        match="exact identity",
    ):
        integration_v2c.RealtimeTurnPreflight(
            signals=(
                in_snapshot,
            ),
            selected_signal=equal_but_distinct,
            tick_attempted=True,
            tick_succeeded=True,
            snapshot_succeeded=True,
        )


def test_tick_succeeded_requires_tick_attempted():
    with pytest.raises(
        ValueError,
        match="tick_succeeded",
    ):
        integration_v2c.RealtimeTurnPreflight(
            signals=(),
            selected_signal=None,
            tick_attempted=False,
            tick_succeeded=True,
            snapshot_succeeded=False,
        )


def test_boolean_audit_fields_are_strict_bools():
    with pytest.raises(
        TypeError,
        match="tick_attempted",
    ):
        integration_v2c.RealtimeTurnPreflight(
            signals=(),
            selected_signal=None,
            tick_attempted=1,
            tick_succeeded=False,
            snapshot_succeeded=False,
        )


def test_import_surface_is_exact():
    assert _app_imports() == {
        "__future__": {
            "annotations",
        },
        "dataclasses": {
            "dataclass",
            "field",
        },
        "app.realtime.change_detection": {
            "RealtimeRelevanceLevel",
            "RealtimeSignal",
        },
        "app.realtime.runtime": {
            "RealtimeRuntime",
        },
        "app.realtime.runtime_trigger": {
            "propose_runtime_trigger",
        },
        "app.realtime.trigger_policy": {
            "RealtimeTriggerEligibilityStatus",
            "evaluate_trigger_eligibility",
        },
    }


def test_v2_consumer_surface_matches_realtime_2k_allowance_exactly():
    imports = _app_imports()

    assert imports[
        "app.realtime.runtime_trigger"
    ] == {
        "propose_runtime_trigger",
    }

    assert imports[
        "app.realtime.trigger_policy"
    ] == {
        "RealtimeTriggerEligibilityStatus",
        "evaluate_trigger_eligibility",
    }


def test_source_declares_zero_authority_boundaries():
    source = MODULE.read_text()

    for marker in (
        "TICK != WAKE",
        "SNAPSHOT != DRAIN",
        "SELECTION != RANKING",
        "SELECTED SIGNAL != COMMAND",
        "PREFLIGHT != ADMISSION",
        "PREFLIGHT != REQUEST",
        "PREFLIGHT != OBSERVATION",
        "PREFLIGHT != INVOCATION",
        "PREFLIGHT != PERMISSION",
        "PREFLIGHT != EXECUTION",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_source_has_no_runtime_acquisition_drain_or_control_surface():
    source = MODULE.read_text()

    for forbidden in (
        "get_realtime_runtime",
        "drain_signals",
        "create_trigger_request",
        "observe_trigger_request",
        "admit_realtime_observation",
        "run_explicit_operation_with_realtime_signal",
        "KumaRuntimeV2LiveOwner",
        "RuntimeInvocation",
        "KumaRuntimeInvocationDispatcher",
        "KumaAgent",
        "KumaGUIRuntime",
        "request_confirmation",
        "get_permission_level",
        "self.executor",
        "ask_model",
        "emit_status",
        "QTimer",
        "QThread",
        "Thread(",
        "asyncio",
    ):
        assert forbidden not in source


def test_source_reads_pending_signals_exactly_once_and_never_drains():
    source = MODULE.read_text()

    assert source.count(
        "realtime_runtime.pending_signals()"
    ) == 1

    assert (
        "drain_signals"
        not in source
    )


def test_source_ticks_exactly_once():
    source = inspect.getsource(
        integration_v2c.prepare_realtime_turn
    )

    assert source.count(
        "realtime_runtime.tick()"
    ) == 1


def test_selection_is_bounded_snapshot_order_not_sorting():
    source = inspect.getsource(
        integration_v2c.prepare_realtime_turn
    )

    assert (
        "for signal in signals:"
        in source
    )

    assert (
        "selected_signal = signal"
        in source
    )

    assert "sorted(" not in source
    assert ".sort(" not in source
    assert "max(" not in source
    assert "min(" not in source


def test_module_does_not_import_attention_ranking():
    imports = _app_imports()

    assert not any(
        name.startswith(
            "app.agent"
        )
        for name in imports
    )
