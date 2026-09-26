from __future__ import annotations

import ast
from dataclasses import fields
import inspect
from pathlib import Path

from app.runtime_correlation import (
    KumaRuntimeCorrelation,
)
from app.runtime_live_binding import (
    KumaRuntimeLiveTraceBinding,
)
from app.runtime_observability import (
    RuntimeObservationEvent,
    RuntimeObservationSnapshot,
    project_runtime_observation,
)
from app.runtime_trace import (
    KumaRuntimeTrace,
    RuntimeTraceEvent,
)


ROOT = Path(__file__).resolve().parents[1]

TRACE = ROOT / "app/runtime_trace.py"
CORRELATION = ROOT / "app/runtime_correlation.py"
LIVE = ROOT / "app/runtime_live_binding.py"
OBSERVABILITY = ROOT / "app/runtime_observability.py"

GUI = ROOT / "app/agent/gui_runtime.py"
AGENT = ROOT / "app/agent/kuma_agent.py"
MISSION = ROOT / "app/agent/mission_service.py"
MISSION_EXECUTOR = (
    ROOT / "app/agent/kuma_mission_executor.py"
)

EXECUTOR = ROOT / "app/agent/executor.py"
PERMISSIONS = ROOT / "app/agent/permissions.py"

RECOVERY = (
    ROOT / "app/agent/recovery_manager.py"
)
RECOVERY_POLICY = (
    ROOT / "app/agent/recovery_policy.py"
)
RECOVERY_STRATEGY = (
    ROOT / "app/agent/recovery_strategy.py"
)
STATE_VERIFIER = (
    ROOT / "app/agent/recovery_state_verifier.py"
)
OBJECTIVE_VERIFIER = (
    ROOT / "app/agent/objective_verifier.py"
)

WINDOW = ROOT / "app/ui/window.py"
MAIN = ROOT / "app/main.py"


def imported_modules(
    path,
):
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


def test_runtime_v1_authority_is_monotonically_none():
    trace = KumaRuntimeTrace()

    assert trace.authority == "NONE"

    correlation = KumaRuntimeCorrelation(
        trace=trace
    )

    assert (
        correlation.authority
        == "NONE"
    )

    binding = (
        KumaRuntimeLiveTraceBinding(
            correlation=correlation
        )
    )

    assert binding.authority == "NONE"

    snapshot = (
        RuntimeObservationSnapshot()
    )

    assert snapshot.authority == "NONE"


def test_runtime_v1_event_authority_is_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            RuntimeTraceEvent
        ).parameters
    )

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


def test_runtime_v1_observability_is_projection_only():
    assert tuple(
        inspect.signature(
            project_runtime_observation
        ).parameters
    ) == (
        "events",
    )

    source = (
        OBSERVABILITY.read_text()
    )

    for forbidden in (
        "request_confirmation(",
        "require_explicit_permission(",
        "register_tool(",
        "ActionExecutor",
        "PermissionLevel",
        "RecoveryManager",
        "RecoveryStrategyAdvisor",
        "safe_verify_state(",
        "safe_verify_objective(",
        ".execute(",
    ):
        assert forbidden not in source


def test_runtime_v1_projection_has_no_raw_payload_fields():
    names = {
        value.name
        for value in fields(
            RuntimeObservationEvent
        )
    }

    for forbidden in (
        "metadata",
        "reason",
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
        "error",
        "exception",
        "tool_name",
    ):
        assert forbidden not in names


def test_runtime_v1_dependency_direction_is_one_way():
    assert {
        value
        for value in imported_modules(
            CORRELATION
        )
        if value.startswith("app.")
    } == {
        "app.runtime_trace"
    }

    assert {
        value
        for value in imported_modules(
            LIVE
        )
        if value.startswith("app.")
    } == {
        "app.runtime_correlation"
    }

    assert {
        value
        for value in imported_modules(
            OBSERVABILITY
        )
        if value.startswith("app.")
    } == {
        "app.runtime_trace"
    }


def test_runtime_v1_authority_owners_do_not_depend_on_observability():
    for path in (
        AGENT,
        MISSION,
        MISSION_EXECUTOR,
        EXECUTOR,
        PERMISSIONS,
        RECOVERY,
        RECOVERY_POLICY,
        RECOVERY_STRATEGY,
        STATE_VERIFIER,
        OBJECTIVE_VERIFIER,
    ):
        assert (
            "runtime_observability"
            not in path.read_text()
        )


def test_runtime_v1_ui_window_does_not_consume_trace():
    source = WINDOW.read_text()

    assert (
        "runtime_observability"
        not in source
    )

    assert (
        "runtime_observation_snapshot"
        not in source
    )


def test_runtime_v1_main_does_not_consume_trace():
    source = MAIN.read_text()

    assert (
        "runtime_observability"
        not in source
    )

    assert (
        "runtime_observation_snapshot"
        not in source
    )


def test_runtime_v1_gui_is_the_only_live_projection_seam():
    source = GUI.read_text()

    assert (
        source.count(
            "runtime_observation_snapshot"
        )
        == 1
    )

    assert (
        source.count(
            "project_runtime_observation"
        )
        == 2
    )


def test_runtime_v1_existing_raw_trace_read_remains():
    source = GUI.read_text()

    assert (
        source.count(
            "def runtime_trace_events("
        )
        == 1
    )


def test_runtime_v1_pipeline_observer_remains_payload_free():
    assert tuple(
        inspect.signature(
            KumaRuntimeLiveTraceBinding
            .observe_pipeline_event
        ).parameters
    ) == (
        "self",
        "event_kind",
        "outcome",
    )


def test_runtime_v1_structural_stage_vocabulary_is_present():
    source = LIVE.read_text()

    for value in (
        '"authority"',
        '"execution"',
        '"verification"',
        '"recovery"',
    ):
        assert value in source


def test_runtime_v1_verification_recovery_vocabulary_is_present():
    source = LIVE.read_text()

    for event_kind in (
        "verifier.returned",
        "body_verifier.returned",
        "state_verification.returned",
        "objective_verification.returned",
        "recovery.effect_barrier",
        "recovery.strategy_mode",
        "recovery.decision",
    ):
        assert event_kind in source


def test_runtime_v1_projection_does_not_claim_goal_completion():
    source = (
        OBSERVABILITY.read_text()
    )

    assert (
        "RESPONSE != VERIFIED GOAL COMPLETION"
        in source
    )


def test_runtime_v1_trace_is_bounded_in_memory():
    trace = KumaRuntimeTrace()

    assert not hasattr(
        trace,
        "save",
    )

    roots = {
        value.split(
            ".",
            1,
        )[0]
        for value in imported_modules(
            TRACE
        )
    }

    assert roots.isdisjoint(
        {
            "sqlite3",
            "requests",
            "httpx",
            "socket",
        }
    )


def test_runtime_v1_has_no_background_observability_loop():
    for path in (
        TRACE,
        CORRELATION,
        LIVE,
        OBSERVABILITY,
    ):
        source = path.read_text()

        for forbidden in (
            "threading.Thread",
            "asyncio.create_task",
            "while True",
        ):
            assert forbidden not in source


def test_runtime_v1_sources_compile():
    for path in (
        TRACE,
        CORRELATION,
        LIVE,
        OBSERVABILITY,
        GUI,
    ):
        compile(
            path.read_text(),
            str(path),
            "exec",
        )
