import unittest

from app.agent.recovery_manager import (
    FailureType,
    RecoveryAction,
    RecoveryDiagnosis,
)


class TestRecoveryDiagnosis(unittest.TestCase):

    def test_stores_structured_details(self):
        diagnosis = RecoveryDiagnosis(
            failure_type=FailureType.INVALID_ARGUMENTS,
            summary="The tool received invalid arguments.",
            likely_cause="The supplied path is malformed.",
            confidence=0.96,
            recommended_action=RecoveryAction.REPAIR_ARGUMENTS,
            state_may_have_changed=False,
            affected_tool="open_file",
        )

        self.assertEqual(
            diagnosis.failure_type,
            FailureType.INVALID_ARGUMENTS,
        )
        self.assertEqual(
            diagnosis.summary,
            "The tool received invalid arguments.",
        )
        self.assertEqual(
            diagnosis.likely_cause,
            "The supplied path is malformed.",
        )
        self.assertEqual(
            diagnosis.confidence,
            0.96,
        )
        self.assertEqual(
            diagnosis.recommended_action,
            RecoveryAction.REPAIR_ARGUMENTS,
        )
        self.assertFalse(
            diagnosis.state_may_have_changed,
        )
        self.assertEqual(
            diagnosis.affected_tool,
            "open_file",
        )

    def test_read_only_verification_failure_is_not_state_changing(self):
        from app.agent.recovery_manager import RecoveryManager

        manager = RecoveryManager()

        diagnosis = manager.diagnose(
            error="",
            verified=False,
            tool_name="list_files",
            result="listing unavailable",
        )

        self.assertEqual(
            diagnosis.failure_type,
            FailureType.VERIFICATION_FAILURE,
        )
        self.assertFalse(
            diagnosis.state_may_have_changed,
        )
        self.assertEqual(
            diagnosis.affected_tool,
            "list_files",
        )

    def test_unknown_tool_verification_failure_fails_closed_on_state_change(self):
        from app.agent.recovery_manager import RecoveryManager

        manager = RecoveryManager()

        diagnosis = manager.diagnose(
            error="",
            verified=False,
            tool_name="unknown_mutating_tool",
            result="operation may have executed",
        )

        self.assertEqual(
            diagnosis.failure_type,
            FailureType.VERIFICATION_FAILURE,
        )
        self.assertTrue(
            diagnosis.state_may_have_changed,
        )
        self.assertEqual(
            diagnosis.affected_tool,
            "unknown_mutating_tool",
        )

    def test_rejects_confidence_above_one(self):
        with self.assertRaises(ValueError):
            RecoveryDiagnosis(
                failure_type=FailureType.UNKNOWN,
                summary="Unknown failure.",
                likely_cause="Insufficient evidence.",
                confidence=1.5,
                recommended_action=RecoveryAction.ESCALATE,
                state_may_have_changed=True,
            )

    def test_rejects_confidence_below_zero(self):
        with self.assertRaises(ValueError):
            RecoveryDiagnosis(
                failure_type=FailureType.UNKNOWN,
                summary="Unknown failure.",
                likely_cause="Insufficient evidence.",
                confidence=-0.1,
                recommended_action=RecoveryAction.ESCALATE,
                state_may_have_changed=True,
            )

    def test_transient_read_only_failure_is_classified_before_verification_failure(self):
        from app.agent.recovery_manager import RecoveryManager

        manager = RecoveryManager()

        diagnosis = manager.diagnose(
            error="Operation timed out.",
            verified=False,
            tool_name="list_files",
            result=None,
        )

        self.assertEqual(
            diagnosis.failure_type,
            FailureType.TRANSIENT,
        )
        self.assertEqual(
            diagnosis.recommended_action,
            RecoveryAction.RETRY,
        )
        self.assertFalse(
            diagnosis.state_may_have_changed,
        )

    def test_transient_unknown_mutating_failure_preserves_state_risk(self):
        from app.agent.recovery_manager import RecoveryManager

        manager = RecoveryManager()

        diagnosis = manager.diagnose(
            error="Operation timed out.",
            verified=False,
            tool_name="unknown_mutating_tool",
            result=None,
        )

        self.assertEqual(
            diagnosis.failure_type,
            FailureType.TRANSIENT,
        )
        self.assertEqual(
            diagnosis.recommended_action,
            RecoveryAction.RETRY,
        )
        self.assertTrue(
            diagnosis.state_may_have_changed,
        )

    def test_read_only_tool_failure_does_not_claim_state_change(self):
        from app.agent.recovery_manager import RecoveryManager

        manager = RecoveryManager()

        diagnosis = manager.diagnose(
            error="Unexpected filesystem inspection failure.",
            verified=True,
            tool_name="list_files",
            result=None,
        )

        self.assertEqual(
            diagnosis.failure_type,
            FailureType.TOOL_FAILURE,
        )
        self.assertFalse(
            diagnosis.state_may_have_changed,
        )



if __name__ == "__main__":
    unittest.main()