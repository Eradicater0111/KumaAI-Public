from __future__ import annotations

from datetime import datetime, timezone
import ast
import inspect
from pathlib import Path

import pytest

from app.agent.kuma_agent import (
    KumaAgent,
)
from app.integration_v2_agent_prepared_turn import (
    INTEGRATION_V2E_AUTHORITY_NONE,
    resolve_prepared_realtime_signals,
)
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


MODULE = Path(
    "app/integration_v2_agent_prepared_turn.py"
)

AGENT = Path(
    "app/agent/kuma_agent.py"
)

GUI = Path(
    "app/agent/gui_runtime.py"
)

CLI = Path(
    "app/agent/kuma_runtime.py"
)


def make_signal():
    return RealtimeSignal(
        kind="weather.precipitation",
        level=RealtimeRelevanceLevel.HIGH,
        score=0.90,
        reason="precipitation started",
        fact=RealtimeFact(
            kind="weather.precipitation",
            value={
                "active": True,
            },
            source="integration-v2e-test",
            observed_at=datetime(
                2026,
                9,
                23,
                6,
                0,
                tzinfo=timezone.utc,
            ),
            expires_at=None,
        ),
        previous_fact=None,
    )


def preflight(
    signals=(),
    *,
    tick_attempted=True,
    tick_succeeded=True,
    snapshot_succeeded=True,
):
    supplied = tuple(
        signals
    )

    return RealtimeTurnPreflight(
        signals=supplied,
        selected_signal=(
            supplied[0]
            if supplied
            else None
        ),
        tick_attempted=tick_attempted,
        tick_succeeded=tick_succeeded,
        snapshot_succeeded=snapshot_succeeded,
    )


def run_source():
    return inspect.getsource(
        KumaAgent.run
    )


def test_authority_constant_is_none():
    assert (
        INTEGRATION_V2E_AUTHORITY_NONE
        == "NONE"
    )


def test_none_resolves_to_legacy_sentinel_none():
    assert (
        resolve_prepared_realtime_signals(
            None
        )
        is None
    )


def test_invalid_prepared_turn_is_rejected():
    with pytest.raises(
        TypeError,
        match="prepared_realtime_turn",
    ):
        resolve_prepared_realtime_signals(
            object()
        )


def test_resolver_returns_exact_signal_tuple_identity():
    signal = make_signal()

    item = preflight(
        (
            signal,
        )
    )

    result = (
        resolve_prepared_realtime_signals(
            item
        )
    )

    assert result is item.signals
    assert result[0] is signal


def test_empty_prepared_snapshot_is_not_legacy_none():
    item = preflight(
        (),
        snapshot_succeeded=False,
    )

    result = (
        resolve_prepared_realtime_signals(
            item
        )
    )

    assert result is item.signals
    assert result == ()
    assert result is not None


def test_agent_run_adds_only_keyword_only_prepared_turn():
    signature = inspect.signature(
        KumaAgent.run
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
        "user_message",
        "prepared_realtime_turn",
    )

    prepared = signature.parameters[
        "prepared_realtime_turn"
    ]

    assert (
        prepared.kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    assert prepared.default is None


def test_agent_keeps_exactly_one_legacy_tick_call_surface():
    source = run_source()

    assert source.count(
        "realtime_runtime.tick()"
    ) == 1


def test_agent_tick_is_guarded_by_prepared_signal_sentinel():
    source = run_source()

    normalized = " ".join(
        source.split()
    )

    assert (
        "if ( prepared_realtime_signals is None "
        "and realtime_runtime is not None ): "
        "try: realtime_runtime.tick()"
        in normalized
    )


def test_agent_keeps_exactly_one_legacy_pending_signal_read_surface():
    source = run_source()

    assert source.count(
        "realtime_runtime.pending_signals()"
    ) == 1


def test_agent_prepared_path_uses_exact_resolved_tuple_without_tuple_copy():
    source = run_source()

    normalized = " ".join(
        source.split()
    )

    assert (
        "if prepared_realtime_signals is not None: "
        "pending_attention_signals = ( prepared_realtime_signals )"
        in normalized
    )

    assert (
        "tuple( prepared_realtime_signals )"
        not in normalized
    )


def test_agent_fallback_pending_read_occurs_only_when_no_prepared_tuple():
    source = run_source()

    normalized = " ".join(
        source.split()
    )

    assert (
        "if prepared_realtime_signals is not None: "
        "pending_attention_signals = ( prepared_realtime_signals ) "
        "else: pending_attention_signals = tuple( "
        "realtime_runtime.pending_signals() )"
        in normalized
    )


def test_agent_no_runtime_requirement_when_prepared_tuple_exists():
    source = run_source()

    normalized = " ".join(
        source.split()
    )

    assert (
        "if ( realtime_runtime is None "
        "and prepared_realtime_signals is None ):"
        in normalized
    )


def test_agent_does_not_use_selected_signal_or_threshold_policy():
    source = run_source()

    assert "prepared_realtime_turn.selected_signal" not in source
    assert "minimum_level" not in source
    assert "minimum_score" not in source
    assert "RealtimeTriggerAdmissionPolicy" not in source


def test_resolver_module_has_no_realtime_acquisition_or_control():
    source = MODULE.read_text()

    for forbidden in (
        "get_realtime_runtime",
        "RealtimeRuntime",
        "pending_signals",
        "drain_signals",
        ".tick(",
        "prepare_realtime_turn",
        "selected_signal",
        "minimum_level",
        "minimum_score",
        "run_explicit_operation_with_realtime_signal",
        "KumaRuntimeV2LiveOwner",
        "get_permission_level",
        "request_confirmation",
        "ask_model",
        "register_tool",
        ".execute(",
        "QTimer",
        "QThread",
        "Thread(",
        "asyncio",
    ):
        assert forbidden not in source


def test_resolver_module_declares_zero_authority_boundaries():
    source = MODULE.read_text()

    for marker in (
        "PREPARED TURN != INVOCATION",
        "PREPARED SNAPSHOT != ACQUISITION",
        "PREPARED SNAPSHOT != DRAIN",
        "SNAPSHOT CONSUMPTION != SIGNAL SELECTION",
        "SNAPSHOT CONSUMPTION != ADMISSION",
        "SNAPSHOT CONSUMPTION != PERMISSION",
        "SNAPSHOT CONSUMPTION != EXECUTION",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_gui_cli_production_paths_use_prepared_turn_after_v2f_promotion():
    for path in (
        GUI,
        CLI,
    ):
        source = path.read_text()

        assert "prepared_realtime_turn" in source
        assert "KumaIntegrationV2LiveTurnOwner" in source
        assert "PRODUCTION_REALTIME_TRIGGER_POLICY" in source


def test_agent_source_still_has_one_1e_snapshot_assignment():
    source = AGENT.read_text()

    assert source.count(
        "raphael_loop_attention_signals = (\n"
        "                            pending_attention_signals\n"
        "                        )"
    ) == 1


def test_agent_source_still_never_drains_realtime_signals():
    source = run_source()

    assert "drain_signals(" not in source


def test_agent_prepared_seam_has_no_wake_or_execution_markers():
    source = run_source()

    marker_start = source.index(
        "# KUMA INTEGRATION-V2E — PREPARED REALTIME TURN"
    )

    marker_end = source.index(
        'self._pending_live_location_web_query = ""'
    )

    block = source[
        marker_start:marker_end
    ]

    for forbidden in (
        "refresh_weather",
        "request_confirmation",
        "self.executor",
        "ask_model",
        "register_tool",
        "emit_status",
        "create_task",
        "Thread(",
        "QThread",
        "QTimer",
    ):
        assert forbidden not in block


def test_agent_imports_resolver_locally_inside_run():
    source = run_source()

    assert (
        "from app.integration_v2_agent_prepared_turn import ("
        in source
    )

    assert (
        "resolve_prepared_realtime_signals"
        in source
    )


def test_resolver_import_surface_is_exact():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    imports = {}

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
            imports.setdefault(
                node.module,
                set(),
            ).update(
                alias.name
                for alias in node.names
            )

    assert imports == {
        "__future__": {
            "annotations",
        },
        "app.integration_v2_realtime_turn_preflight": {
            "RealtimeTurnPreflight",
        },
        "app.realtime.change_detection": {
            "RealtimeSignal",
        },
    }
