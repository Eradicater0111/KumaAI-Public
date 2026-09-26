from types import SimpleNamespace

import pytest

from app.agent.executor import (
    ActionResult,
    ActionExecutor,
)
from app.agent.kuma_mission_executor import (
    KumaMissionExecutor,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)
from app.agent.tool_result import (
    ToolResult,
)


def test_tool_result_effect_marker_defaults_false():
    assert (
        ToolResult.ok(
            "done"
        ).effect_started
        is False
    )

    assert (
        ToolResult.fail(
            "failed"
        ).effect_started
        is False
    )


def test_tool_result_preserves_true_effect_marker():
    success = ToolResult.ok(
        "done",
        effect_started=True,
    )

    failure = ToolResult.fail(
        "failed",
        effect_started=True,
    )

    assert success.effect_started is True
    assert failure.effect_started is True


@pytest.mark.parametrize(
    "factory,args",
    (
        (
            ToolResult.ok,
            ("done",),
        ),
        (
            ToolResult.fail,
            ("failed",),
        ),
    ),
)
def test_tool_result_rejects_nonboolean_effect_marker(
    factory,
    args,
):
    with pytest.raises(
        TypeError,
        match="effect_started",
    ):
        factory(
            *args,
            effect_started=1,
        )


def test_action_result_preserves_effect_marker():
    success = ActionResult.ok(
        "type_text",
        "done",
        effect_started=True,
    )

    failure = ActionResult.fail(
        "type_text",
        "failed",
        effect_started=True,
    )

    assert success.effect_started is True
    assert failure.effect_started is True

    assert success.effect_started is True


def test_action_executor_source_transports_structured_marker():
    import inspect

    source = inspect.getsource(
        ActionExecutor.execute
    )

    assert (
        source.count(
            "raw_result.effect_started"
        )
        == 2
    )


def test_mission_result_carries_effect_marker():
    result = MissionExecutionResult(
        success=False,
        step_id="step-1",
        tool_name="type_text",
        error="failed",
        effect_started=True,
    )

    assert result.effect_started is True


class _NoDiagnosisAllowed:
    def diagnose(
        self,
        **_kwargs,
    ):
        raise AssertionError(
            "Recovery diagnosis must not run after "
            "an irreversible effect boundary."
        )


class _EffectStartedKuma:
    def __init__(
        self,
    ):
        self.calls = 0

        self.tool_registry = {
            "type_text": object(),
        }

    def execute_mission_step(
        self,
        step,
    ):
        self.calls += 1

        return MissionExecutionResult(
            success=False,
            step_id=step.id,
            tool_name="type_text",
            arguments={
                "text": "hello",
            },
            error="timeout",
            verified=False,
            effect_started=True,
        )


def test_effect_started_failure_escalates_before_diagnosis():
    kuma = (
        _EffectStartedKuma()
    )

    executor = (
        KumaMissionExecutor(
            kuma,
            recovery_manager=(
                _NoDiagnosisAllowed()
            ),
        )
    )

    step = SimpleNamespace(
        id="step-1",
    )

    result = (
        executor.execute(
            step
        )
    )

    assert kuma.calls == 1

    assert (
        result.recovery_action
        == "escalate"
    )

    assert (
        "irreversible physical effect boundary"
        in result.recovery_reason
    )

    assert (
        result.effect_started
        is True
    )


class _CompletedEffectKuma:
    def __init__(
        self,
    ):
        self.calls = 0

    def execute_mission_step(
        self,
        step,
    ):
        self.calls += 1

        return MissionExecutionResult(
            success=True,
            step_id=step.id,
            tool_name="type_text",
            result="done",
            verified=True,
            effect_started=True,
        )


def test_completed_effect_is_not_reclassified_as_failure():
    kuma = (
        _CompletedEffectKuma()
    )

    executor = (
        KumaMissionExecutor(
            kuma,
            recovery_manager=(
                _NoDiagnosisAllowed()
            ),
        )
    )

    result = executor.execute(
        SimpleNamespace(
            id="step-1"
        )
    )

    assert result.completed
    assert result.effect_started is True
    assert kuma.calls == 1


def test_mission_result_rejects_non_boolean_effect_marker():
    bad_values = (
        "yes",
        1,
        0,
        None,
        object(),
    )

    for value in bad_values:
        try:
            MissionExecutionResult(
                success=False,
                step_id="step-1",
                tool_name="type_text",
                error="synthetic failure",
                effect_started=value,
            )
        except TypeError as error:
            assert (
                "effect_started must be a boolean."
                in str(error)
            )
        else:
            raise AssertionError(
                "MissionExecutionResult accepted a "
                "non-boolean effect_started marker."
            )


def test_mission_result_accepts_exact_boolean_effect_markers():
    not_started = MissionExecutionResult(
        success=False,
        step_id="step-1",
        effect_started=False,
    )

    started = MissionExecutionResult(
        success=False,
        step_id="step-1",
        effect_started=True,
    )

    assert (
        not_started.effect_started
        is False
    )

    assert (
        started.effect_started
        is True
    )


def test_mission_result_default_effect_marker_is_false():
    result = MissionExecutionResult(
        success=False,
        step_id="step-1",
    )

    assert (
        result.effect_started
        is False
    )

