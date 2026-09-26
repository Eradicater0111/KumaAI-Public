from types import SimpleNamespace

from app.agent.kuma_mission_executor import (
    KumaMissionExecutor,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)


class PlanAwareKuma:
    def __init__(
        self,
    ):
        self.calls = []

    def execute_mission_step(
        self,
        step,
        plan=None,
    ):
        self.calls.append(
            (
                step,
                plan,
            )
        )

        return MissionExecutionResult(
            success=True,
            step_id=step.id,
            verified=True,
        )


class LegacyKuma:
    def __init__(
        self,
    ):
        self.calls = []

    def execute_mission_step(
        self,
        step,
    ):
        self.calls.append(
            step
        )

        return MissionExecutionResult(
            success=True,
            step_id=step.id,
            verified=True,
        )


def test_bound_plan_is_forwarded_by_exact_identity():
    kuma = PlanAwareKuma()

    executor = KumaMissionExecutor(
        kuma
    )

    plan = object()

    step = SimpleNamespace(
        id="step-1"
    )

    executor.bind_runtime_plan(
        plan
    )

    result = executor.execute(
        step
    )

    assert result.completed

    assert len(
        kuma.calls
    ) == 1

    received_step, received_plan = (
        kuma.calls[0]
    )

    assert received_step is step
    assert received_plan is plan


def test_unbound_executor_preserves_legacy_single_argument_call():
    kuma = LegacyKuma()

    executor = KumaMissionExecutor(
        kuma
    )

    step = SimpleNamespace(
        id="step-1"
    )

    result = executor.execute(
        step
    )

    assert result.completed

    assert kuma.calls == [
        step
    ]


def test_plan_binding_does_not_clone_or_reconstruct():
    kuma = PlanAwareKuma()

    executor = KumaMissionExecutor(
        kuma
    )

    plan = {
        "identity": "must-be-exact"
    }

    step = SimpleNamespace(
        id="step-1"
    )

    executor.bind_runtime_plan(
        plan
    )

    executor.execute(
        step
    )

    assert (
        kuma.calls[0][1]
        is plan
    )
