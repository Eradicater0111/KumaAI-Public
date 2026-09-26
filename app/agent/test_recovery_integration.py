import unittest
from unittest.mock import Mock

from app.agent.kuma_mission_executor import KumaMissionExecutor
from app.agent.mission_result import MissionExecutionResult

from app.agent.recovery_manager import (
    FailureType,
    RecoveryAction,
    RecoveryDiagnosis,
)
from app.agent.objective_verifier import (
    ObjectiveVerificationResult,
)

from app.agent.recovery_state_verifier import (
    RecoveryStateVerifier,
    StateVerificationResult,
)


class FakeStep:
    id = "step_1"
    objective = "Complete the test mission step."
    success_criteria = [
        "The expected end-state is satisfied.",
    ]
    verification_requirements = [
        "Verify the end-state independently.",
    ]


class FakeKuma:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def execute_mission_step(self, step):
        self.calls += 1
        return self.results.pop(0)


class FakeStateVerifier:
    """
    Deterministic read-only state verifier used by recovery tests.
    """

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def verify(
        self,
        *,
        tool_name,
        arguments=None,
        result=None,
    ):
        self.calls += 1
        return self.result


class FakeObjectiveVerifier:
    """
    Deterministic objective verifier used only by integration tests.
    """

    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.last_call = None

    def verify(
        self,
        *,
        objective,
        success_criteria=None,
        verification_requirements=None,
        tool_name="",
        arguments=None,
        state=None,
    ):
        self.calls += 1

        self.last_call = {
            "objective": objective,
            "success_criteria": list(
                success_criteria or []
            ),
            "verification_requirements": list(
                verification_requirements or []
            ),
            "tool_name": tool_name,
            "arguments": arguments,
            "state": state,
        }

        return self.result


class TestRecoveryIntegration(unittest.TestCase):

    def result(
        self,
        *,
        success=False,
        verified=False,
        error="",
        tool_name="",
        arguments=None,
        result=None,
        verification="",
    ):
        return MissionExecutionResult(
            success=success,
            step_id="step_1",
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            error=error,
            verified=verified,
            verification=verification,
        )

    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------

    def test_success_does_not_retry(self):
        kuma = FakeKuma([
            self.result(
                success=True,
                verified=True,
                tool_name="list_files",
            )
        ])

        executor = KumaMissionExecutor(kuma)

        result = executor.execute(FakeStep())

        self.assertTrue(result.completed)
        self.assertEqual(kuma.calls, 1)

    # -----------------------------------------------------
    # TRANSIENT RETRY
    # -----------------------------------------------------

    def test_timeout_retries(self):
        kuma = FakeKuma([
            self.result(
                error="Tool execution failed: timeout",
                tool_name="list_files",
            ),
            self.result(
                success=True,
                verified=True,
                tool_name="list_files",
            ),
        ])

        executor = KumaMissionExecutor(kuma)

        result = executor.execute(FakeStep())

        self.assertTrue(result.completed)
        self.assertEqual(kuma.calls, 2)

            # -----------------------------------------------------
    # STATE VERIFICATION — UNCHANGED
    # -----------------------------------------------------

    def test_state_verified_unchanged_allows_recovery(self):
        kuma = FakeKuma([
            self.result(
                success=True,
                verified=False,
                tool_name="unknown_mutating_tool",
            ),
            self.result(
                success=True,
                verified=True,
                tool_name="unknown_mutating_tool",
            ),
        ])

        verifier = FakeStateVerifier(
            StateVerificationResult(
                known=True,
                state_changed=False,
                summary="Verified that system state is unchanged.",
                evidence="No relevant state change detected.",
            )
        )

        executor = KumaMissionExecutor(
            kuma,
            state_verifier=verifier,
        )

        result = executor.execute(FakeStep())

        self.assertTrue(result.completed)
        self.assertEqual(kuma.calls, 2)
        self.assertEqual(verifier.calls, 1)

    # -----------------------------------------------------
    # STATE VERIFICATION — CHANGED
    # -----------------------------------------------------

    def test_state_verified_changed_blocks_recovery(self):
        kuma = FakeKuma([
            self.result(
                success=True,
                verified=False,
                tool_name="unknown_mutating_tool",
            )
        ])

        verifier = FakeStateVerifier(
            StateVerificationResult(
                known=True,
                state_changed=True,
                summary="System state changed.",
                evidence="The target state is already different.",
            )
        )

        executor = KumaMissionExecutor(
            kuma,
            state_verifier=verifier,
        )

        result = executor.execute(FakeStep())

        self.assertFalse(result.completed)
        self.assertEqual(kuma.calls, 1)
        self.assertEqual(verifier.calls, 1)

    # -----------------------------------------------------
    # STATE VERIFICATION — UNKNOWN
    # -----------------------------------------------------

    def test_unknown_state_blocks_recovery(self):
        kuma = FakeKuma([
            self.result(
                success=True,
                verified=False,
                tool_name="unknown_mutating_tool",
            )
        ])

        verifier = FakeStateVerifier(
            StateVerificationResult(
                known=False,
                state_changed=None,
                summary="Unable to determine current state.",
                evidence="",
            )
        )

        executor = KumaMissionExecutor(
            kuma,
            state_verifier=verifier,
        )

        result = executor.execute(FakeStep())

        self.assertFalse(result.completed)
        self.assertEqual(kuma.calls, 1)
        self.assertEqual(verifier.calls, 1)

    # -----------------------------------------------------
    # RETRY LIMIT
    # -----------------------------------------------------

    def test_timeout_eventually_escalates(self):
        kuma = FakeKuma([
            self.result(
                error="Tool execution failed: timeout",
                tool_name="list_files",
            ),
            self.result(
                error="Tool execution failed: timeout",
                tool_name="list_files",
            ),
            self.result(
                error="Tool execution failed: timeout",
                tool_name="list_files",
            ),
        ])

        executor = KumaMissionExecutor(kuma)

        result = executor.execute(FakeStep())

        self.assertFalse(result.success)
        self.assertEqual(kuma.calls, 3)

    # -----------------------------------------------------
    # PERMISSION DENIAL
    # -----------------------------------------------------

    def test_permission_denial_does_not_retry(self):
        kuma = FakeKuma([
            self.result(
                error=(
                    "Confirmation required before "
                    "executing 'delete_file'."
                ),
                tool_name="delete_file",
            )
        ])

        executor = KumaMissionExecutor(kuma)

        result = executor.execute(FakeStep())

        self.assertFalse(result.success)
        self.assertEqual(kuma.calls, 1)

    # -----------------------------------------------------
    # DANGEROUS ACTION
    # -----------------------------------------------------

    def test_dangerous_action_does_not_retry(self):
        kuma = FakeKuma([
            self.result(
                error="timeout",
                tool_name="delete_file",
            )
        ])

        executor = KumaMissionExecutor(kuma)

        result = executor.execute(FakeStep())

        self.assertFalse(result.success)
        self.assertEqual(kuma.calls, 1)

    # -----------------------------------------------------
    # INVALID ARGUMENTS
    # -----------------------------------------------------

    def test_invalid_arguments_do_not_create_retry_loop(self):
        kuma = FakeKuma([
            self.result(
                error="Invalid tool arguments",
                tool_name="list_files",
            )
        ])

        executor = KumaMissionExecutor(kuma)

        result = executor.execute(FakeStep())

        self.assertFalse(result.success)
        self.assertEqual(kuma.calls, 1)

    # -----------------------------------------------------
    # VERIFICATION FAILURE
    # -----------------------------------------------------

    def test_verification_failure_can_retry(self):
        kuma = FakeKuma([
            self.result(
                success=True,
                verified=False,
                tool_name="list_files",
            ),
            self.result(
                success=True,
                verified=True,
                tool_name="list_files",
            ),
        ])

        executor = KumaMissionExecutor(kuma)

        result = executor.execute(FakeStep())

        self.assertTrue(result.completed)
        self.assertEqual(kuma.calls, 2)

    # -----------------------------------------------------
    # INVALID RESULT
    # -----------------------------------------------------

    def test_invalid_agent_result_fails_safely(self):
        kuma = FakeKuma([
            "not a MissionExecutionResult"
        ])

        executor = KumaMissionExecutor(kuma)

        result = executor.execute(FakeStep())

        self.assertFalse(result.success)
        self.assertEqual(kuma.calls, 1)

    # -----------------------------------------------------
    # GOAL-LEVEL RECOVERY — OBJECTIVE SATISFIED
    # -----------------------------------------------------

    def test_failed_step_becomes_success_when_objective_verified(self):
        kuma = FakeKuma([
            self.result(
                success=True,
                verified=False,
                tool_name="test_mutating_tool",
                arguments={
                    "target": "example",
                },
                result="Operation may have executed.",
            )
        ])

        state_verifier = FakeStateVerifier(
            StateVerificationResult(
                known=True,
                state_changed=True,
                summary="A state change was observed.",
                evidence="trusted-state-evidence",
                state="changed",
            )
        )

        objective_verifier = FakeObjectiveVerifier(
            ObjectiveVerificationResult(
                known=True,
                satisfied=True,
                summary=(
                    "The expected mission end-state "
                    "was independently verified."
                ),
                evidence="trusted-objective-evidence",
            )
        )

        executor = KumaMissionExecutor(
            kuma,
            state_verifier=state_verifier,
            objective_verifier=objective_verifier,
        )

        result = executor.execute(
            FakeStep()
        )

        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertTrue(result.completed)

        self.assertEqual(
            kuma.calls,
            1,
        )

        self.assertEqual(
            state_verifier.calls,
            1,
        )

        self.assertEqual(
            objective_verifier.calls,
            1,
        )

        self.assertEqual(
            objective_verifier.last_call[
                "success_criteria"
            ],
            FakeStep.success_criteria,
        )

        self.assertEqual(
            objective_verifier.last_call[
                "verification_requirements"
            ],
            FakeStep.verification_requirements,
        )

        self.assertIn(
            "objective verification",
            result.verification.lower(),
        )

    # -----------------------------------------------------
    # GOAL-LEVEL RECOVERY — OBJECTIVE NOT SATISFIED
    # -----------------------------------------------------

    def test_failed_step_does_not_recover_when_objective_unsatisfied(self):
        kuma = FakeKuma([
            self.result(
                success=True,
                verified=False,
                tool_name="test_mutating_tool",
                arguments={
                    "target": "example",
                },
                result="Operation may have executed.",
            )
        ])

        state_verifier = FakeStateVerifier(
            StateVerificationResult(
                known=True,
                state_changed=True,
                summary="A state change was observed.",
                evidence="trusted-state-evidence",
                state="changed",
            )
        )

        objective_verifier = FakeObjectiveVerifier(
            ObjectiveVerificationResult(
                known=True,
                satisfied=False,
                summary=(
                    "The expected mission end-state "
                    "was not satisfied."
                ),
                evidence="trusted-objective-evidence",
            )
        )

        executor = KumaMissionExecutor(
            kuma,
            state_verifier=state_verifier,
            objective_verifier=objective_verifier,
        )

        result = executor.execute(
            FakeStep()
        )

        self.assertFalse(result.completed)

        self.assertEqual(
            kuma.calls,
            1,
        )

        self.assertEqual(
            state_verifier.calls,
            1,
        )

        self.assertEqual(
            objective_verifier.calls,
            1,
        )

        # Verified partial state must become a mission-level
        # RESUME recommendation rather than another tool call.
        self.assertEqual(
            result.recovery_action,
            RecoveryAction.RESUME.value,
        )

        self.assertIn(
            "partial state",
            result.recovery_reason.lower(),
        )

        self.assertIn(
            "trusted-state-evidence",
            result.recovery_evidence,
        )

        self.assertEqual(
            kuma.calls,
            1,
        )


if __name__ == "__main__":
    unittest.main()
