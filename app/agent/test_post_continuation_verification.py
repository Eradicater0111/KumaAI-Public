import unittest

from unittest.mock import patch

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)

from app.agent.kuma_agent import (
    KumaAgent,
)

from app.agent.mission_controller import (
    MissionController,
)

from app.agent.mission_state import (
    MissionState,
    MissionStatus,
)

from app.agent.objective_verifier import (
    ObjectiveVerificationResult,
)

from app.agent.recovery_state_verifier import (
    StateVerificationResult,
)

from app.agent.remaining_objective_resolver import (
    RemainingObjectiveResolution,
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


class TestPostContinuationVerification(unittest.TestCase):

    def make_mission(
        self,
    ):

        plan = GoalPlan(
            goal="Complete the original objective."
        )

        step = GoalStep(
            id="recover",
            objective=(
                "Complete the original mission step."
            ),
            success_criteria=[
                "Expected end-state exists."
            ],
            verification_requirements=[
                "Inspect the expected end-state."
            ],
            required_capabilities=[
                "test_capability"
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
            "CONTINUATION_OK"
        )

        mission.continuation_guard_known = True

        mission.continuation_guard_tool = (
            "continuation_test"
        )

        mission.continuation_guard_arguments = {
            "target": "new",
        }

        mission.continuation_guard_capability = (
            "test_capability"
        )

        mission.continuation_verification_pending = True

        mission.action_history = [
            {
                "tool": "continuation_test",
                "arguments": {
                    "target": "new",
                },
                "result": "CONTINUATION_OK",
                "verified": True,
            }
        ]

        return mission

    def make_kuma(
        self,
    ):

        return KumaAgent(
            model="test-model",
            tool_registry={},
        )

    def test_controller_completion_from_verification_does_not_duplicate_action(
        self,
    ):

        mission = self.make_mission()

        controller = (
            MissionController
            .from_mission_state(
                mission
            )
        )

        before = len(
            controller.task_state.action_history
        )

        completed = (
            controller
            .complete_current_step_from_verification(
                result="OBJECTIVE_OK",
                evidence="OBJECTIVE_OK",
                reason="Verified.",
            )
        )

        after = len(
            controller.task_state.action_history
        )

        self.assertTrue(
            completed
        )

        self.assertEqual(
            before,
            after,
        )

        self.assertTrue(
            controller.is_complete()
        )

        self.assertFalse(
            controller.task_state
            .continuation_verification_pending
        )

        self.assertFalse(
            controller.task_state
            .continuation_guard_known
        )

    def test_unknown_state_stays_paused_and_executes_nothing(
        self,
    ):

        persistence = FakePersistence()
        mission = self.make_mission()
        persistence.save(mission)
        kuma = self.make_kuma()

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.RecoveryStateVerifier.verify",
            return_value=StateVerificationResult(
                known=False,
                state_changed=None,
                summary="State unknown.",
                evidence="",
                state="unknown",
            ),
        ), patch(
            "app.agent.mission_service.ObjectiveVerifier.verify",
            side_effect=AssertionError(
                "Objective verifier must not run when current state is unknown."
            ),
        ), patch(
            "app.agent.mission_service.RemainingObjectiveResolver.resolve",
            side_effect=AssertionError(
                "Unknown state must not trigger remaining-objective reasoning."
            ),
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertFalse(result.success)
        self.assertEqual(result.recovery_action, "escalate")
        self.assertEqual(restored.status, MissionStatus.PAUSED)
        self.assertTrue(restored.continuation_verification_pending)
        self.assertEqual(
            restored.plan.get_step("recover").status,
            StepStatus.IN_PROGRESS,
        )

    def test_satisfied_objective_completes_without_duplicate_execution(
        self,
    ):

        persistence = FakePersistence()
        mission = self.make_mission()
        persistence.save(mission)
        kuma = self.make_kuma()

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.RecoveryStateVerifier.verify",
            return_value=StateVerificationResult(
                known=True,
                state_changed=False,
                summary="State observed.",
                evidence="STATE_OK",
                state="present",
            ),
        ), patch(
            "app.agent.mission_service.ObjectiveVerifier.verify",
            return_value=ObjectiveVerificationResult(
                known=True,
                satisfied=True,
                summary="Original objective satisfied.",
                evidence="OBJECTIVE_OK",
            ),
        ), patch(
            "app.agent.mission_service.RemainingObjectiveResolver.resolve",
            side_effect=AssertionError(
                "Satisfied objective must not resolve another remainder."
            ),
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertTrue(result.completed)
        self.assertTrue(result.verified)
        self.assertEqual(restored.status, MissionStatus.COMPLETED)
        self.assertEqual(
            restored.plan.get_step("recover").status,
            StepStatus.COMPLETED,
        )
        self.assertEqual(restored.current_step_id, "")
        self.assertFalse(restored.continuation_verification_pending)
        self.assertFalse(restored.continuation_guard_known)
        self.assertEqual(len(restored.action_history), 1)

    def test_unsatisfied_objective_resolves_new_remainder_without_execution(
        self,
    ):

        persistence = FakePersistence()
        mission = self.make_mission()
        persistence.save(mission)
        kuma = self.make_kuma()

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.RecoveryStateVerifier.verify",
            return_value=StateVerificationResult(
                known=True,
                state_changed=False,
                summary="State observed.",
                evidence="STATE_CURRENT",
                state="present",
            ),
        ), patch(
            "app.agent.mission_service.ObjectiveVerifier.verify",
            return_value=ObjectiveVerificationResult(
                known=True,
                satisfied=False,
                summary="Original objective is still unfinished.",
                evidence="OBJECTIVE_INCOMPLETE",
            ),
        ), patch(
            "app.agent.mission_service.RemainingObjectiveResolver.resolve",
            return_value=RemainingObjectiveResolution(
                known=True,
                remaining_objective="Perform the final unfinished work.",
                reason=(
                    "Independent verification shows one requirement remains."
                ),
                evidence_used="OBJECTIVE_INCOMPLETE",
            ),
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertTrue(result.success)
        self.assertFalse(result.completed)
        self.assertFalse(result.verified)
        self.assertEqual(result.recovery_action, "resume")
        self.assertEqual(restored.status, MissionStatus.PAUSED)
        self.assertEqual(
            restored.plan.get_step("recover").status,
            StepStatus.IN_PROGRESS,
        )
        self.assertFalse(restored.continuation_verification_pending)
        self.assertEqual(
            restored.remaining_objective,
            "Perform the final unfinished work.",
        )
        self.assertTrue(restored.continuation_guard_known)
        self.assertEqual(
            restored.continuation_guard_tool,
            "continuation_test",
        )
        self.assertEqual(len(restored.action_history), 1)

    def test_unknown_objective_does_not_guess_completion_or_remainder(
        self,
    ):

        persistence = FakePersistence()
        mission = self.make_mission()
        persistence.save(mission)
        kuma = self.make_kuma()

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.RecoveryStateVerifier.verify",
            return_value=StateVerificationResult(
                known=True,
                state_changed=False,
                summary="State observed.",
                evidence="STATE_CURRENT",
                state="present",
            ),
        ), patch(
            "app.agent.mission_service.ObjectiveVerifier.verify",
            return_value=ObjectiveVerificationResult(
                known=False,
                satisfied=None,
                summary="No deterministic verifier exists.",
                evidence="STATE_CURRENT",
            ),
        ), patch(
            "app.agent.mission_service.RemainingObjectiveResolver.resolve",
            side_effect=AssertionError(
                "Unknown objective verification must not guess a remainder."
            ),
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertFalse(result.success)
        self.assertEqual(result.recovery_action, "escalate")
        self.assertEqual(restored.status, MissionStatus.PAUSED)
        self.assertEqual(
            restored.plan.get_step("recover").status,
            StepStatus.IN_PROGRESS,
        )
        self.assertTrue(restored.continuation_verification_pending)
        self.assertEqual(restored.remaining_objective, "")


if __name__ == "__main__":
    unittest.main()
