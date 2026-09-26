import unittest

from app.agent.objective_verifier import (
    ObjectiveVerificationResult,
)
from app.agent.recovery_manager import (
    FailureType,
    RecoveryAction,
    RecoveryDecision,
    RecoveryDiagnosis,
)
from app.agent.recovery_state_verifier import (
    StateVerificationResult,
)
from app.agent.recovery_strategy import (
    RecoveryStrategyAdvisor,
)


class TestRecoveryStrategyAdvisor(unittest.TestCase):

    def diagnosis(
        self,
        *,
        failure_type=FailureType.VERIFICATION_FAILURE,
        action=RecoveryAction.RETRY,
        state_may_have_changed=False,
    ):
        return RecoveryDiagnosis(
            failure_type=failure_type,
            summary="Failure.",
            likely_cause="Test failure.",
            confidence=0.9,
            recommended_action=action,
            state_may_have_changed=state_may_have_changed,
            affected_tool="test_tool",
        )

    def decision(
        self,
        *,
        action=RecoveryAction.RETRY,
        retryable=True,
    ):
        return RecoveryDecision(
            failure_type=FailureType.VERIFICATION_FAILURE,
            action=action,
            reason="Policy decision.",
            retryable=retryable,
        )

    def test_safe_policy_retry_remains_retry(self):
        advisor = RecoveryStrategyAdvisor()

        strategy = advisor.assess(
            diagnosis=self.diagnosis(),
            policy_decision=self.decision(),
        )

        self.assertEqual(
            strategy.action,
            RecoveryAction.RETRY,
        )
        self.assertTrue(strategy.automatic)

    def test_dangerous_action_always_escalates(self):
        advisor = RecoveryStrategyAdvisor()

        strategy = advisor.assess(
            diagnosis=self.diagnosis(),
            policy_decision=self.decision(),
            dangerous=True,
        )

        self.assertEqual(
            strategy.action,
            RecoveryAction.ESCALATE,
        )
        self.assertFalse(strategy.automatic)

    def test_unknown_state_after_possible_mutation_escalates(self):
        advisor = RecoveryStrategyAdvisor()

        strategy = advisor.assess(
            diagnosis=self.diagnosis(
                state_may_have_changed=True,
            ),
            policy_decision=self.decision(),
            state_verification=StateVerificationResult(
                known=False,
                state_changed=None,
                summary="Unknown.",
                state="unknown",
            ),
        )

        self.assertEqual(
            strategy.action,
            RecoveryAction.ESCALATE,
        )

    def test_partial_state_and_unsatisfied_objective_recommends_resume(self):
        advisor = RecoveryStrategyAdvisor()

        strategy = advisor.assess(
            diagnosis=self.diagnosis(
                state_may_have_changed=True,
            ),
            policy_decision=self.decision(),
            state_verification=StateVerificationResult(
                known=True,
                state_changed=True,
                summary="Partial change observed.",
                evidence="state evidence",
                state="changed",
            ),
            objective_verification=ObjectiveVerificationResult(
                known=True,
                satisfied=False,
                summary="Objective remains incomplete.",
                evidence="objective evidence",
            ),
        )

        self.assertEqual(
            strategy.action,
            RecoveryAction.RESUME,
        )
        self.assertFalse(strategy.automatic)

    def test_satisfied_objective_requires_no_recovery(self):
        advisor = RecoveryStrategyAdvisor()

        strategy = advisor.assess(
            diagnosis=self.diagnosis(
                state_may_have_changed=True,
            ),
            policy_decision=self.decision(),
            state_verification=StateVerificationResult(
                known=True,
                state_changed=True,
                summary="Changed.",
                state="changed",
            ),
            objective_verification=ObjectiveVerificationResult(
                known=True,
                satisfied=True,
                summary="Objective satisfied.",
                evidence="verified",
            ),
        )

        self.assertEqual(
            strategy.action,
            RecoveryAction.NONE,
        )

    def test_argument_repair_preserves_existing_policy_boundary(self):
        advisor = RecoveryStrategyAdvisor()

        strategy = advisor.assess(
            diagnosis=self.diagnosis(
                failure_type=FailureType.INVALID_ARGUMENTS,
                action=RecoveryAction.REPAIR_ARGUMENTS,
            ),
            policy_decision=self.decision(
                action=RecoveryAction.REPAIR_ARGUMENTS,
                retryable=False,
            ),
        )

        self.assertEqual(
            strategy.action,
            RecoveryAction.REPAIR_ARGUMENTS,
        )
        self.assertFalse(strategy.automatic)

    def test_alternative_capability_is_not_automatic(self):
        advisor = RecoveryStrategyAdvisor()

        strategy = advisor.assess(
            diagnosis=self.diagnosis(
                failure_type=FailureType.CAPABILITY_UNAVAILABLE,
                action=RecoveryAction.ALTERNATIVE_CAPABILITY,
            ),
            policy_decision=self.decision(
                action=RecoveryAction.ALTERNATIVE_CAPABILITY,
                retryable=False,
            ),
        )

        self.assertEqual(
            strategy.action,
            RecoveryAction.ALTERNATIVE_CAPABILITY,
        )
        self.assertFalse(strategy.automatic)


if __name__ == "__main__":
    unittest.main()
