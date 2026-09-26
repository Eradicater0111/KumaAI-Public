import unittest

from types import SimpleNamespace
from unittest.mock import patch

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)

from app.agent.kuma_agent import (
    KumaAgent,
)

from app.agent.kuma_mission_executor import (
    KumaMissionExecutor,
)

from app.agent.mission_controller import (
    MissionController,
)

from app.agent.mission_result import (
    MissionExecutionResult,
)

from app.agent.mission_state import (
    MissionState,
    MissionStatus,
)


class FakePersistence:

    def __init__(self):
        self.items = {}

    def save(
        self,
        mission,
    ):
        self.items[
            mission.mission_id
        ] = MissionState.from_json(
            mission.to_json()
        )

    def load(
        self,
        mission_id,
    ):
        mission = self.items.get(
            mission_id
        )

        if mission is None:
            return None

        return MissionState.from_json(
            mission.to_json()
        )


class TestContinuationExecution(unittest.TestCase):

    def make_mission(
        self,
        *,
        previous_target="old",
    ):

        plan = GoalPlan(
            goal="Continue safely."
        )

        step = GoalStep(
            id="third",
            objective=(
                "Perform the original third action."
            ),
            required_capabilities=[
                "continuation_capability"
            ],
            success_criteria=[
                "Original third action is complete."
            ],
            verification_requirements=[
                "Verify the original third action."
            ],
        )

        plan.add_step(
            step
        )

        step.status = (
            StepStatus.IN_PROGRESS
        )

        plan.current_step_id = (
            step.id
        )

        mission = MissionState.create(
            plan.goal
        )

        mission.plan = plan

        mission.status = (
            MissionStatus.PAUSED
        )

        mission.current_step_id = (
            step.id
        )

        mission.last_evidence = (
            "PARTIAL_STATE_VERIFIED"
        )

        mission.remaining_objective = (
            "Perform only the unfinished work."
        )

        mission.continuation_guard_known = True

        mission.continuation_guard_tool = (
            "continuation_test"
        )

        mission.continuation_guard_arguments = {
            "target": previous_target,
        }

        mission.continuation_guard_capability = (
            "continuation_capability"
        )

        return mission

    def make_kuma(
        self,
        calls,
    ):

        def continuation_test(
            target="",
        ):

            calls.append(
                target
            )

            return "CONTINUED_OK"

        kuma = KumaAgent(
            model="test-model",
            tool_registry={
                "continuation_test": (
                    continuation_test
                ),
            },
        )

        kuma.capability_registry.register(
            type(
                "Capability",
                (),
                {
                    "name": (
                        "continuation_capability"
                    ),
                    "description": (
                        "test continuation"
                    ),
                    "tools": (
                        "continuation_test",
                    ),
                    "platform": "macos",
                    "risk_level": "normal",
                    "tags": (),
                },
            )()
        )

        return kuma

    def response_for(
        self,
        target,
    ):

        return SimpleNamespace(
            message=SimpleNamespace(
                content="",
                tool_calls=[
                    SimpleNamespace(
                        function=SimpleNamespace(
                            name=(
                                "continuation_test"
                            ),
                            arguments={
                                "target": target,
                            },
                        )
                    )
                ],
            )
        )

    def test_pending_barrier_survives_json_round_trip(
        self,
    ):

        mission = MissionState.create(
            "Continue safely."
        )

        mission.continuation_verification_pending = True

        restored = MissionState.from_json(
            mission.to_json()
        )

        self.assertTrue(
            restored.continuation_verification_pending
        )

    def test_controller_restores_pending_barrier(
        self,
    ):

        mission = self.make_mission()

        mission.continuation_verification_pending = True

        controller = (
            MissionController
            .from_mission_state(
                mission
            )
        )

        self.assertTrue(
            controller.task_state
            .continuation_verification_pending
        )

    def test_explicit_lower_safety_escalation_is_not_retried(
        self,
    ):

        calls = []

        class FakeKuma:

            def execute_mission_step(
                self,
                step,
            ):

                calls.append(
                    step.id
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=step.id,
                    tool_name=(
                        "continuation_test"
                    ),
                    arguments={
                        "target": "same",
                    },
                    error=(
                        "Continuation replay blocked."
                    ),
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=(
                        "Continuation replay blocked."
                    ),
                )

        executor = KumaMissionExecutor(
            FakeKuma()
        )

        step = SimpleNamespace(
            id="continue",
            objective="Continue safely.",
            success_criteria=[],
            verification_requirements=[],
        )

        result = executor.execute(
            step
        )

        self.assertEqual(
            calls,
            [
                "continue",
            ],
        )

        self.assertFalse(
            result.success
        )

        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

    def test_synthetic_continuation_does_not_inherit_gui_target_intent(
        self,
    ):

        persistence = (
            FakePersistence()
        )

        mission = self.make_mission(
            previous_target="old"
        )

        original_step = (
            mission.plan.get_step(
                "third"
            )
        )

        stale_intent = {
            "role": "AXButton",
            "text": "Settings",
            "require_enabled": True,
            "require_positive_area": True,
        }

        # The original persisted planner step is allowed to retain
        # its own untrusted semantic target metadata.
        original_step.gui_target_intent = dict(
            stale_intent
        )

        original_step.planned_tool = (
            "continuation_test"
        )

        persistence.save(
            mission
        )

        calls = []

        kuma = self.make_kuma(
            calls
        )

        captured_steps = []

        def execute_mission_step(
            step,
        ):

            captured_steps.append(
                step
            )

            return MissionExecutionResult(
                success=True,
                step_id=step.id,
                capability=(
                    "continuation_capability"
                ),
                tool_name=(
                    "continuation_test"
                ),
                arguments={
                    "target": "new",
                },
                result="CONTINUED_OK",
                verified=True,
            )

        with patch(
            (
                "app.agent.mission_service."
                "MissionPersistence"
            ),
            return_value=persistence,
        ), patch.object(
            kuma,
            "execute_mission_step",
            side_effect=execute_mission_step,
        ), patch(
            "app.agent.mission_service.chat",
            side_effect=AssertionError(
                "A persisted remaining objective "
                "must not require replanning here."
            ),
        ):

            result = kuma.resume_mission(
                mission.mission_id
            )

        self.assertEqual(
            len(
                captured_steps
            ),
            1,
        )

        continuation_step = (
            captured_steps[0]
        )

        # The recovery continuation receives the independently
        # resolved remaining objective.
        self.assertEqual(
            continuation_step.objective,
            "Perform only the unfinished work.",
        )

        # B8K5 invariant:
        # semantic target intent never crosses an objective-change
        # boundary merely because the mission is continuing.
        self.assertIsNone(
            continuation_step.gui_target_intent
        )

        # Other continuation constraints remain intact.
        self.assertEqual(
            continuation_step.planned_tool,
            "continuation_test",
        )

        self.assertEqual(
            continuation_step.required_capabilities,
            [
                "continuation_capability",
            ],
        )

        self.assertTrue(
            result.success
        )

        restored = persistence.load(
            mission.mission_id
        )

        # K5 isolates the synthetic continuation. It must not erase
        # or mutate the original planner step's durable metadata.
        self.assertEqual(
            restored.plan.get_step(
                "third"
            ).gui_target_intent,
            stale_intent,
        )


    def test_exact_replay_is_blocked_before_execution(
        self,
    ):

        persistence = (
            FakePersistence()
        )

        mission = self.make_mission(
            previous_target="same"
        )

        persistence.save(
            mission
        )

        calls = []

        kuma = self.make_kuma(
            calls
        )

        with patch(
            (
                "app.agent.mission_service."
                "MissionPersistence"
            ),
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            return_value=(
                self.response_for(
                    "same"
                )
            ),
        ):

            result = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertEqual(
            calls,
            [],
        )

        self.assertFalse(
            result.success
        )

        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

        self.assertEqual(
            restored.status,
            MissionStatus.PAUSED,
        )

        self.assertEqual(
            restored.plan.get_step(
                "third"
            ).status,
            StepStatus.IN_PROGRESS,
        )

    def test_safe_continuation_executes_once_then_waits(
        self,
    ):

        persistence = (
            FakePersistence()
        )

        mission = self.make_mission(
            previous_target="old"
        )

        persistence.save(
            mission
        )

        calls = []

        kuma = self.make_kuma(
            calls
        )

        with patch(
            (
                "app.agent.mission_service."
                "MissionPersistence"
            ),
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            return_value=(
                self.response_for(
                    "new"
                )
            ),
        ):

            first = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertEqual(
            calls,
            [
                "new",
            ],
        )

        self.assertTrue(
            first.success
        )

        self.assertFalse(
            first.completed
        )

        self.assertFalse(
            first.verified
        )

        self.assertEqual(
            first.recovery_action,
            "resume",
        )

        self.assertEqual(
            restored.status,
            MissionStatus.PAUSED,
        )

        self.assertEqual(
            restored.plan.get_step(
                "third"
            ).status,
            StepStatus.IN_PROGRESS,
        )

        self.assertTrue(
            restored.continuation_verification_pending
        )

        self.assertEqual(
            restored.remaining_objective,
            "",
        )

        self.assertEqual(
            restored.continuation_guard_tool,
            "continuation_test",
        )

        self.assertEqual(
            restored.continuation_guard_arguments,
            {
                "target": "new",
            },
        )

        # -------------------------------------------------
        # SECOND RESUME MUST EXECUTE NOTHING
        # -------------------------------------------------

        with patch(
            (
                "app.agent.mission_service."
                "MissionPersistence"
            ),
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            side_effect=AssertionError(
                "Verification-pending resume "
                "must not call the model."
            ),
        ):

            second = kuma.resume_mission(
                mission.mission_id
            )

        self.assertEqual(
            calls,
            [
                "new",
            ],
        )

        self.assertFalse(
            second.success
        )

        self.assertFalse(
            second.completed
        )

        self.assertEqual(
            second.recovery_action,
            "escalate",
        )

        self.assertIn(
            "state",
            second.recovery_reason.lower(),
        )


if __name__ == "__main__":
    unittest.main()
