from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.agent.kuma_agent import KumaAgent
from app.agent.mission_service import MissionService
from app.runtime_correlation import KumaRuntimeCorrelation
from app.runtime_live_binding import KumaRuntimeLiveTraceBinding
from app.runtime_trace import KumaRuntimeTrace


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "app/runtime_live_binding.py"
GUI = ROOT / "app/agent/gui_runtime.py"
AGENT = ROOT / "app/agent/kuma_agent.py"
MISSION = ROOT / "app/agent/mission_service.py"


def make_binding():
    ticks = iter(range(100, 10000, 100))
    trace_ids = iter(("trace-a", "trace-b"))
    turn_ids = iter(("turn-a", "turn-b"))

    trace = KumaRuntimeTrace(
        clock_ns=lambda: next(ticks),
        trace_id_factory=lambda: next(trace_ids),
    )
    correlation = KumaRuntimeCorrelation(
        trace=trace,
        session_id_factory=lambda: "session-a",
        turn_id_factory=lambda: next(turn_ids),
    )
    return (
        KumaRuntimeLiveTraceBinding(
            correlation=correlation
        ),
        correlation,
    )


def test_observer_signature_accepts_no_payload():
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


def test_observer_without_active_turn_is_noop():
    binding, _ = make_binding()
    assert (
        binding.observe_pipeline_event(
            event_kind="permission.classified",
            outcome="safe",
        )
        is None
    )
    assert binding.events() == ()


def test_structural_pipeline_events_share_active_trace():
    binding, correlation = make_binding()

    def operation():
        binding.observe_pipeline_event(
            event_kind="permission.classified",
            outcome="dangerous",
        )
        binding.observe_pipeline_event(
            event_kind="confirmation.resolved",
            outcome="approved",
        )
        binding.observe_pipeline_event(
            event_kind="executor.returned",
            outcome="success",
        )
        binding.observe_pipeline_event(
            event_kind="verifier.returned",
            outcome="true",
        )
        return "private-result"

    assert binding.run(operation) == "private-result"

    events = binding.events()

    assert [
        item.event_kind
        for item in events
    ] == [
        "turn.started",
        "agent.run.started",
        "permission.classified",
        "confirmation.resolved",
        "executor.returned",
        "verifier.returned",
        "agent.run.returned",
        "turn.ended",
    ]

    assert [
        item.stage
        for item in events
    ] == [
        "correlation",
        "runtime",
        "authority",
        "authority",
        "execution",
        "verification",
        "runtime",
        "correlation",
    ]

    assert len({
        item.trace_id
        for item in events
    }) == 1

    assert all(
        item.authority == "NONE"
        for item in events
    )

    assert "private-result" not in repr(events)
    assert correlation.active_turn is None


@pytest.mark.parametrize(
    ("event_kind", "outcome"),
    (
        ("permission.classified", "unknown"),
        ("confirmation.resolved", "yes"),
        ("executor.returned", "private-result"),
        ("verifier.returned", "verified"),
        ("prompt", "safe"),
        ("raw user sentence", "safe"),
    ),
)
def test_non_structural_event_values_fail_soft(
    event_kind,
    outcome,
):
    binding, _ = make_binding()

    def operation():
        binding.observe_pipeline_event(
            event_kind=event_kind,
            outcome=outcome,
        )
        return "ok"

    assert binding.run(operation) == "ok"

    assert [
        item.event_kind
        for item in binding.events()
    ] == [
        "turn.started",
        "agent.run.started",
        "agent.run.returned",
        "turn.ended",
    ]


def test_agent_observer_callback_result_is_ignored():
    agent = object.__new__(KumaAgent)
    calls = []
    agent._runtime_observer = (
        lambda **event:
        calls.append(event) or False
    )

    assert (
        agent._observe_runtime_pipeline(
            event_kind="executor.returned",
            outcome="success",
        )
        is None
    )

    assert calls == [
        {
            "event_kind": "executor.returned",
            "outcome": "success",
        }
    ]


def test_agent_observer_callback_failure_is_swallowed():
    agent = object.__new__(KumaAgent)

    def broken(**_):
        raise RuntimeError("private trace failure")

    agent._runtime_observer = broken

    assert (
        agent._observe_runtime_pipeline(
            event_kind="executor.returned",
            outcome="failure",
        )
        is None
    )


def test_confirmation_approval_is_observed_without_payload():
    agent = object.__new__(KumaAgent)
    observed = []
    agent._runtime_observer = (
        lambda **event:
        observed.append(event)
    )
    agent.confirmation_callback = (
        lambda tool, arguments: True
    )

    assert agent.request_confirmation(
        "execute_command",
        {"command": "private command"},
    ) is True

    assert observed == [
        {
            "event_kind": "confirmation.resolved",
            "outcome": "approved",
        }
    ]
    assert "execute_command" not in repr(observed)
    assert "private command" not in repr(observed)


@pytest.mark.parametrize(
    "callback",
    (
        None,
        lambda tool, arguments: False,
    ),
)
def test_confirmation_denial_is_observed_without_payload(
    callback,
):
    agent = object.__new__(KumaAgent)
    observed = []
    agent._runtime_observer = (
        lambda **event:
        observed.append(event)
    )
    agent.confirmation_callback = callback

    assert agent.request_confirmation(
        "execute_command",
        {"command": "private command"},
    ) is False

    assert observed == [
        {
            "event_kind": "confirmation.resolved",
            "outcome": "denied",
        }
    ]
    assert "private command" not in repr(observed)


def test_confirmation_callback_failure_stays_denied():
    agent = object.__new__(KumaAgent)
    observed = []
    agent._runtime_observer = (
        lambda **event:
        observed.append(event)
    )

    def broken(tool, arguments):
        raise RuntimeError(
            "private confirmation failure"
        )

    agent.confirmation_callback = broken

    assert agent.request_confirmation(
        "execute_command",
        {"command": "private command"},
    ) is False

    assert observed == [
        {
            "event_kind": "confirmation.resolved",
            "outcome": "denied",
        }
    ]


def test_mission_observer_forwards_structural_fields_only():
    class FakeKuma:
        def __init__(self):
            self.calls = []

        def _observe_runtime_pipeline(
            self,
            **event,
        ):
            self.calls.append(event)

    service = object.__new__(
        MissionService
    )
    service.kuma = FakeKuma()

    assert (
        service._observe_runtime_pipeline(
            event_kind="verifier.returned",
            outcome="true",
        )
        is None
    )

    assert service.kuma.calls == [
        {
            "event_kind": "verifier.returned",
            "outcome": "true",
        }
    ]


def test_mission_observer_absence_is_noop():
    service = object.__new__(
        MissionService
    )
    service.kuma = object()

    assert (
        service._observe_runtime_pipeline(
            event_kind="executor.returned",
            outcome="success",
        )
        is None
    )


def test_gui_runtime_attaches_live_observer(monkeypatch):
    import app.agent.gui_runtime as gui_runtime

    class FakeKuma:
        def __init__(self):
            self.confirmation_callback = None
            self.status_callback = None
            self._runtime_observer = None
            self.realtime_runtime = None

        def run(
            self,
            _message,
            *,
            prepared_realtime_turn=None,
        ):
            self._runtime_observer(
                event_kind="permission.classified",
                outcome="safe",
            )
            return "private-response"

    fake = FakeKuma()

    monkeypatch.setattr(
        gui_runtime,
        "create_kuma",
        lambda: fake,
    )

    runtime = gui_runtime.KumaGUIRuntime()

    assert runtime.run(
        "private-user-message"
    ) == "private-response"

    pipeline = [
        item
        for item in runtime.runtime_trace_events()
        if item.event_kind
        == "permission.classified"
    ]

    assert len(pipeline) == 1
    assert pipeline[0].stage == "authority"
    assert pipeline[0].outcome == "safe"
    assert pipeline[0].authority == "NONE"

    rendered = repr(
        runtime.runtime_trace_events()
    )
    assert "private-user-message" not in rendered
    assert "private-response" not in rendered


def imported_runtime_modules(path):
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )
    result = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(
                alias.name
                for alias in node.names
                if alias.name.startswith(
                    "app.runtime_"
                )
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith(
                "app.runtime_"
            )
        ):
            result.add(node.module)

    return result


def test_authority_owners_do_not_import_runtime_modules():
    assert imported_runtime_modules(
        AGENT
    ) == set()
    assert imported_runtime_modules(
        MISSION
    ) == set()


def test_observation_calls_are_standalone_expressions():
    for path in (
        AGENT,
        MISSION,
    ):
        tree = ast.parse(
            path.read_text(),
            filename=str(path),
        )
        parents = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(
                parent
            ):
                parents[child] = parent

        calls = [
            node
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.Call)
                and isinstance(
                    node.func,
                    ast.Attribute,
                )
                and node.func.attr
                == "_observe_runtime_pipeline"
            )
        ]

        assert calls

        for call in calls:
            assert isinstance(
                parents.get(call),
                ast.Expr,
            )


def test_live_binding_has_no_authority_dependency():
    source = LIVE.read_text()

    for forbidden in (
        "app.agent.permissions",
        "app.agent.executor",
        "app.agent.verifier",
        "PermissionLevel",
        "ActionExecutor",
        "request_confirmation(",
        ".execute(",
        "TaskState",
    ):
        assert forbidden not in source


def test_verifier_event_does_not_claim_goal_completion():
    source = LIVE.read_text()

    assert "verifier.returned" in source

    for forbidden in (
        "goal.verified",
        "goal.completed",
        "verified.goal",
        "task.complete",
    ):
        assert forbidden not in source
