from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.agent.kuma_mission_executor import KumaMissionExecutor
from app.runtime_correlation import KumaRuntimeCorrelation
from app.runtime_live_binding import KumaRuntimeLiveTraceBinding
from app.runtime_trace import KumaRuntimeTrace


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "app/runtime_live_binding.py"
AGENT = ROOT / "app/agent/kuma_agent.py"
MISSION = ROOT / "app/agent/mission_service.py"
MISSION_EXECUTOR = ROOT / "app/agent/kuma_mission_executor.py"
VERIFIER = ROOT / "app/agent/verifier.py"
RECOVERY_MANAGER = ROOT / "app/agent/recovery_manager.py"
RECOVERY_POLICY = ROOT / "app/agent/recovery_policy.py"
RECOVERY_STRATEGY = ROOT / "app/agent/recovery_strategy.py"
STATE_VERIFIER = ROOT / "app/agent/recovery_state_verifier.py"
OBJECTIVE_VERIFIER = ROOT / "app/agent/objective_verifier.py"


def make_binding():
    ticks = iter(range(100, 20000, 100))
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
    return KumaRuntimeLiveTraceBinding(
        correlation=correlation
    )


def test_runtime_2e_keeps_payload_free_observer_signature():
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


@pytest.mark.parametrize(
    ("event_kind", "outcome", "stage"),
    (
        ("body_verifier.returned", "true", "verification"),
        ("body_verifier.returned", "false", "verification"),
        ("state_verification.returned", "known_changed", "verification"),
        ("state_verification.returned", "known_unchanged", "verification"),
        ("state_verification.returned", "unknown", "verification"),
        ("state_verification.returned", "contract_failure", "verification"),
        ("objective_verification.returned", "satisfied", "verification"),
        ("objective_verification.returned", "unsatisfied", "verification"),
        ("objective_verification.returned", "unknown", "verification"),
        ("objective_verification.returned", "contract_failure", "verification"),
        ("recovery.effect_barrier", "escalate", "recovery"),
        ("recovery.decision", "none", "recovery"),
        ("recovery.decision", "retry", "recovery"),
        ("recovery.decision", "repair_arguments", "recovery"),
        ("recovery.decision", "alternative_capability", "recovery"),
        ("recovery.decision", "resume", "recovery"),
        ("recovery.decision", "escalate", "recovery"),
        ("recovery.strategy_mode", "automatic", "recovery"),
        ("recovery.strategy_mode", "manual", "recovery"),
    ),
)
def test_runtime_2e_structural_events_are_accepted(
    event_kind,
    outcome,
    stage,
):
    binding = make_binding()

    def operation():
        binding.observe_pipeline_event(
            event_kind=event_kind,
            outcome=outcome,
        )
        return "private-result"

    assert binding.run(operation) == "private-result"

    selected = [
        event
        for event in binding.events()
        if event.event_kind == event_kind
    ]

    assert len(selected) == 1
    assert selected[0].stage == stage
    assert selected[0].outcome == outcome
    assert selected[0].authority == "NONE"
    assert "private-result" not in repr(binding.events())


@pytest.mark.parametrize(
    ("event_kind", "outcome"),
    (
        ("body_verifier.returned", "verified"),
        ("state_verification.returned", "changed with secret"),
        ("objective_verification.returned", "goal text"),
        ("recovery.effect_barrier", "retry"),
        ("recovery.decision", "execute"),
        ("recovery.strategy_mode", "reason text"),
    ),
)
def test_runtime_2e_invalid_or_content_like_values_fail_soft(
    event_kind,
    outcome,
):
    binding = make_binding()

    def operation():
        binding.observe_pipeline_event(
            event_kind=event_kind,
            outcome=outcome,
        )
        return "ok"

    assert binding.run(operation) == "ok"

    assert event_kind not in {
        event.event_kind
        for event in binding.events()
    }


def test_runtime_2e_event_sequence_can_share_one_live_trace():
    binding = make_binding()

    def operation():
        for event_kind, outcome in (
            ("verifier.returned", "true"),
            ("body_verifier.returned", "true"),
            ("state_verification.returned", "known_changed"),
            ("objective_verification.returned", "unsatisfied"),
            ("recovery.strategy_mode", "manual"),
            ("recovery.decision", "resume"),
        ):
            binding.observe_pipeline_event(
                event_kind=event_kind,
                outcome=outcome,
            )
        return "private-result"

    binding.run(operation)
    events = binding.events()

    assert len({event.trace_id for event in events}) == 1
    assert all(event.authority == "NONE" for event in events)
    assert "private-result" not in repr(events)


class RecordingKuma:
    def __init__(self):
        self.events = []

    def _observe_runtime_pipeline(self, **event):
        self.events.append(event)
        return False


def test_mission_executor_observer_return_value_is_ignored():
    executor = object.__new__(KumaMissionExecutor)
    executor.kuma = RecordingKuma()

    assert executor._observe_runtime_pipeline(
        event_kind="recovery.decision",
        outcome="retry",
    ) is None

    assert executor.kuma.events == [
        {
            "event_kind": "recovery.decision",
            "outcome": "retry",
        }
    ]


def test_mission_executor_observer_failure_is_swallowed():
    class BrokenKuma:
        def _observe_runtime_pipeline(self, **_event):
            raise RuntimeError("private trace failure")

    executor = object.__new__(KumaMissionExecutor)
    executor.kuma = BrokenKuma()

    assert executor._observe_runtime_pipeline(
        event_kind="recovery.decision",
        outcome="escalate",
    ) is None


def test_mission_executor_observer_absence_is_noop():
    executor = object.__new__(KumaMissionExecutor)
    executor.kuma = object()

    assert executor._observe_runtime_pipeline(
        event_kind="recovery.strategy_mode",
        outcome="manual",
    ) is None


def test_mission_service_has_post_result_verification_observers():
    source = MISSION.read_text()

    assert source.count(
        'event_kind="body_verifier.returned"'
    ) == 1
    assert source.count(
        'event_kind="state_verification.returned"'
    ) == 1
    assert source.count(
        'event_kind="objective_verification.returned"'
    ) == 1

    assert source.index(
        'event_kind="body_verifier.returned"'
    ) > source.index(
        "verify_body_action_postcondition("
    )
    assert source.index(
        'event_kind="state_verification.returned"'
    ) > source.index(
        "safe_verify_state("
    )
    assert source.index(
        'event_kind="objective_verification.returned"'
    ) > source.index(
        "safe_verify_objective("
    )


def test_mission_executor_has_post_result_recovery_observers():
    source = MISSION_EXECUTOR.read_text()

    assert source.count(
        'event_kind="state_verification.returned"'
    ) == 1
    assert source.count(
        'event_kind="objective_verification.returned"'
    ) == 1
    assert source.count(
        'event_kind="recovery.effect_barrier"'
    ) == 1
    assert source.count(
        'event_kind="recovery.strategy_mode"'
    ) == 1
    assert source.count(
        'event_kind="recovery.decision"'
    ) == 3


def test_runtime_2e_does_not_modify_verifier_or_recovery_decision_modules():
    for path in (
        VERIFIER,
        RECOVERY_MANAGER,
        RECOVERY_POLICY,
        RECOVERY_STRATEGY,
        STATE_VERIFIER,
        OBJECTIVE_VERIFIER,
    ):
        source = path.read_text()
        assert "runtime_live_binding" not in source
        assert "observe_pipeline_event" not in source
        assert "_runtime_observer" not in source


def test_runtime_2e_keeps_kuma_agent_generic_verifier_observation_exact():
    source = AGENT.read_text()

    assert source.count(
        'event_kind="verifier.returned"'
    ) == 2
    assert "body_verifier.returned" not in source
    assert "state_verification.returned" not in source
    assert "objective_verification.returned" not in source
    assert "recovery.decision" not in source


def test_runtime_2e_live_binding_contains_no_verification_payload_fields():
    signature = inspect.signature(
        KumaRuntimeLiveTraceBinding.observe_pipeline_event
    )

    for forbidden in (
        "tool_name",
        "arguments",
        "result",
        "summary",
        "evidence",
        "reason",
        "objective",
        "state",
        "prompt",
        "transcript",
        "memory_context",
        "error",
    ):
        assert forbidden not in signature.parameters


def test_runtime_2e_documents_no_goal_completion_claim():
    text = LIVE.read_text()
    assert "verifier.returned" in text
    assert "objective_verification.returned" in text
    assert "recovery.decision" in text


def test_runtime_2e_source_compiles():
    for path in (
        LIVE,
        MISSION,
        MISSION_EXECUTOR,
    ):
        compile(
            path.read_text(),
            str(path),
            "exec",
        )
