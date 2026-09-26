import unittest
from unittest.mock import patch

from app.agent.goal_plan import GoalPlan, GoalStep, StepStatus
from app.agent.kuma_agent import KumaAgent
from app.agent.mission_state import MissionState, MissionStatus
from app.agent.objective_verifier import (
    ObjectiveVerificationResult,
    safe_verify_objective,
)
from app.agent.recovery_manager import (
    FailureType,
    RecoveryAction,
    RecoveryDecision,
    RecoveryDiagnosis,
)
from app.agent.recovery_state_verifier import (
    StateVerificationResult,
    safe_verify_state,
)
from app.agent.recovery_strategy import RecoveryStrategyAdvisor


class RaisingStateVerifier:
    def verify(self, **kwargs):
        raise RuntimeError("state verifier exploded")


class WrongStateVerifier:
    def verify(self, **kwargs):
        return {"known": True}


class RaisingObjectiveVerifier:
    def verify(self, **kwargs):
        raise RuntimeError("objective verifier exploded")


class WrongObjectiveVerifier:
    def verify(self, **kwargs):
        return {"known": True, "satisfied": True}


class FakePersistence:
    def __init__(self):
        self.items = {}

    def save(self, mission):
        self.items[mission.mission_id] = MissionState.from_json(
            mission.to_json()
        )

    def load(self, mission_id):
        mission = self.items.get(mission_id)
        if mission is None:
            return None
        return MissionState.from_json(mission.to_json())


class TestVerifierContractHardening(unittest.TestCase):
    def make_state(self):
        return StateVerificationResult(
            known=True,
            state_changed=False,
            summary="State observed.",
            evidence="STATE_EVIDENCE",
            state="present",
        )

    def make_mission(self):
        plan = GoalPlan(goal="Recover safely.")
        step = GoalStep(
            id="recover",
            objective="Finish the original objective.",
            status=StepStatus.IN_PROGRESS,
            success_criteria=["Expected end-state exists."],
            verification_requirements=["Inspect the expected end-state."],
        )
        plan.add_step(step)
        plan.current_step_id = step.id

        mission = MissionState.create(plan.goal)
        mission.plan = plan
        mission.status = MissionStatus.PAUSED
        mission.current_step_id = step.id
        mission.last_evidence = "CONTINUATION_OK"
        mission.continuation_guard_known = True
        mission.continuation_guard_tool = "open_file"
        mission.continuation_guard_arguments = {
            "path": "/tmp/kuma-contract-test"
        }
        mission.continuation_guard_capability = "filesystem"
        mission.continuation_verification_pending = True
        mission.action_history = [
            {
                "tool": "open_file",
                "arguments": {"path": "/tmp/kuma-contract-test"},
                "result": "CONTINUATION_OK",
                "verified": True,
            }
        ]
        return mission

    def test_objective_known_requires_satisfied(self):
        with self.assertRaises(ValueError):
            ObjectiveVerificationResult(
                known=True,
                satisfied=None,
                summary="Contradictory.",
            )

    def test_objective_unknown_cannot_claim_satisfaction(self):
        with self.assertRaises(ValueError):
            ObjectiveVerificationResult(
                known=False,
                satisfied=True,
                summary="Contradictory.",
            )

    def test_objective_known_must_be_boolean(self):
        with self.assertRaises(ValueError):
            ObjectiveVerificationResult(
                known="true",
                satisfied=True,
                summary="Malformed.",
            )

    def test_state_known_requires_state_changed(self):
        with self.assertRaises(ValueError):
            StateVerificationResult(
                known=True,
                state_changed=None,
                summary="Contradictory.",
                state="present",
            )

    def test_state_unknown_cannot_claim_unchanged(self):
        with self.assertRaises(ValueError):
            StateVerificationResult(
                known=False,
                state_changed=False,
                summary="Contradictory.",
                state="unknown",
            )

    def test_state_known_must_be_boolean(self):
        with self.assertRaises(ValueError):
            StateVerificationResult(
                known=1,
                state_changed=False,
                summary="Malformed.",
                state="present",
            )

    def test_safe_state_exception_fails_closed(self):
        result = safe_verify_state(
            RaisingStateVerifier(),
            tool_name="open_file",
            arguments={},
        )
        self.assertFalse(result.known)
        self.assertTrue(result.contract_failure)
        self.assertIsNone(result.state_changed)

    def test_safe_state_wrong_type_fails_closed(self):
        result = safe_verify_state(
            WrongStateVerifier(),
            tool_name="open_file",
            arguments={},
        )
        self.assertFalse(result.known)
        self.assertTrue(result.contract_failure)

    def test_safe_objective_exception_fails_closed(self):
        result = safe_verify_objective(
            RaisingObjectiveVerifier(),
            objective="Finish the step.",
            state=self.make_state(),
        )
        self.assertFalse(result.known)
        self.assertIsNone(result.satisfied)
        self.assertTrue(result.contract_failure)
        self.assertEqual(result.evidence, "STATE_EVIDENCE")

    def test_safe_objective_wrong_type_fails_closed(self):
        result = safe_verify_objective(
            WrongObjectiveVerifier(),
            objective="Finish the step.",
            state=self.make_state(),
        )
        self.assertFalse(result.known)
        self.assertTrue(result.contract_failure)

    def make_diagnosis_and_policy(self):
        diagnosis = RecoveryDiagnosis(
            failure_type=FailureType.TRANSIENT,
            summary="Temporary failure.",
            likely_cause="Temporary issue.",
            confidence=0.9,
            recommended_action=RecoveryAction.RETRY,
            state_may_have_changed=False,
            affected_tool="test_tool",
        )
        policy = RecoveryDecision(
            failure_type=FailureType.TRANSIENT,
            action=RecoveryAction.RETRY,
            reason="Retry.",
            retryable=True,
        )
        return diagnosis, policy

    def test_strategy_escalates_state_contract_failure(self):
        diagnosis, policy = self.make_diagnosis_and_policy()
        state = StateVerificationResult(
            known=False,
            state_changed=None,
            summary="Contract failure.",
            state="unknown",
            contract_failure=True,
        )
        result = RecoveryStrategyAdvisor().assess(
            diagnosis=diagnosis,
            policy_decision=policy,
            state_verification=state,
        )
        self.assertEqual(result.action, RecoveryAction.ESCALATE)
        self.assertFalse(result.automatic)

    def test_strategy_escalates_objective_contract_failure(self):
        diagnosis, policy = self.make_diagnosis_and_policy()
        objective = ObjectiveVerificationResult(
            known=False,
            satisfied=None,
            summary="Contract failure.",
            contract_failure=True,
        )
        result = RecoveryStrategyAdvisor().assess(
            diagnosis=diagnosis,
            policy_decision=policy,
            objective_verification=objective,
        )
        self.assertEqual(result.action, RecoveryAction.ESCALATE)
        self.assertFalse(result.automatic)

    def test_post_continuation_state_exception_fails_closed(self):
        persistence = FakePersistence()
        mission = self.make_mission()
        persistence.save(mission)
        kuma = KumaAgent(model="test-model", tool_registry={})

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.RecoveryStateVerifier.verify",
            side_effect=RuntimeError("state verifier exploded"),
        ), patch(
            "app.agent.mission_service.ObjectiveVerifier.verify",
            side_effect=AssertionError("objective verifier must not run"),
        ):
            result = kuma.resume_mission(mission.mission_id)

        restored = persistence.load(mission.mission_id)
        self.assertFalse(result.success)
        self.assertEqual(result.recovery_action, "escalate")
        self.assertEqual(restored.status, MissionStatus.PAUSED)
        self.assertTrue(restored.continuation_verification_pending)
        self.assertEqual(len(restored.action_history), 1)

    def test_post_continuation_objective_wrong_type_fails_closed(self):
        persistence = FakePersistence()
        mission = self.make_mission()
        persistence.save(mission)
        kuma = KumaAgent(model="test-model", tool_registry={})

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
            return_value={"known": True, "satisfied": True},
        ):
            result = kuma.resume_mission(mission.mission_id)

        restored = persistence.load(mission.mission_id)
        self.assertFalse(result.success)
        self.assertEqual(result.recovery_action, "escalate")
        self.assertEqual(restored.status, MissionStatus.PAUSED)
        self.assertEqual(
            restored.plan.get_step("recover").status,
            StepStatus.IN_PROGRESS,
        )
        self.assertTrue(restored.continuation_verification_pending)
        self.assertEqual(len(restored.action_history), 1)


if __name__ == "__main__":
    unittest.main()
