import unittest

from app.agent.kuma_mission_executor import (
    KumaMissionExecutor,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)
from app.agent.objective_verifier import (
    ObjectiveVerificationResult,
)
from app.agent.permissions import (
    PermissionLevel,
    get_recovery_permission_level,
)
from app.agent.recovery_state_verifier import (
    StateVerificationResult,
)


class FakeStep:
    id = "dangerous"
    objective = "Perform the requested action."
    success_criteria = [
        "Requested end-state is observable."
    ]
    verification_requirements = [
        "Inspect the end-state independently."
    ]


class FakeKuma:

    def __init__(
        self,
        results,
        *,
        tool_registry_marker=False,
    ):
        self.results = list(results)
        self.calls = 0

        if tool_registry_marker:
            self.tool_registry = {}

    def execute_mission_step(self, step):
        self.calls += 1

        if not self.results:
            raise AssertionError(
                "Unexpected recovery execution."
            )

        return self.results.pop(0)


class FixedStateVerifier:

    def __init__(self, *, changed):
        self.changed = changed

    def verify(self, **kwargs):
        return StateVerificationResult(
            known=True,
            state_changed=self.changed,
            summary="State independently observed.",
            evidence="STATE_EVIDENCE",
            state=(
                "changed"
                if self.changed
                else "unchanged"
            ),
        )


class FixedObjectiveVerifier:

    def __init__(self, *, satisfied):
        self.satisfied = satisfied

    def verify(self, **kwargs):
        return ObjectiveVerificationResult(
            known=True,
            satisfied=self.satisfied,
            summary="Objective independently observed.",
            evidence="OBJECTIVE_EVIDENCE",
        )


class TestDangerousRecoveryAmbiguity(unittest.TestCase):

    @staticmethod
    def failure(*, tool_name, error="timeout"):
        return MissionExecutionResult(
            success=False,
            step_id="dangerous",
            tool_name=tool_name,
            arguments={},
            error=error,
            verified=False,
        )

    @staticmethod
    def success(*, tool_name):
        return MissionExecutionResult(
            success=True,
            step_id="dangerous",
            tool_name=tool_name,
            arguments={},
            result="SUCCESS",
            verified=True,
        )

    def test_execute_command_is_dangerous_for_recovery(self):
        self.assertEqual(
            get_recovery_permission_level(
                "execute_command"
            ),
            PermissionLevel.DANGEROUS,
        )

    def test_known_safe_tool_keeps_safe_recovery_classification(self):
        self.assertEqual(
            get_recovery_permission_level(
                "list_files"
            ),
            PermissionLevel.SAFE,
        )

    def test_runtime_explicitly_unknown_tool_fails_closed(self):
        self.assertEqual(
            get_recovery_permission_level(
                "mystery_tool",
                tool_known=False,
            ),
            PermissionLevel.DANGEROUS,
        )

    def test_missing_or_malformed_tool_identity_fails_closed(self):
        self.assertEqual(
            get_recovery_permission_level(""),
            PermissionLevel.DANGEROUS,
        )
        self.assertEqual(
            get_recovery_permission_level(None),
            PermissionLevel.DANGEROUS,
        )

    def test_dangerous_transient_failure_never_retries(self):
        kuma = FakeKuma(
            [
                self.failure(
                    tool_name="execute_command"
                ),
                self.success(
                    tool_name="execute_command"
                ),
            ]
        )

        result = KumaMissionExecutor(
            kuma
        ).execute(
            FakeStep()
        )

        self.assertEqual(kuma.calls, 1)
        self.assertFalse(result.success)
        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

    def test_live_runtime_unknown_tool_never_becomes_automatic_retry(self):
        kuma = FakeKuma(
            [
                self.failure(
                    tool_name="mystery_tool"
                ),
                self.success(
                    tool_name="mystery_tool"
                ),
            ],
            tool_registry_marker=True,
        )

        result = KumaMissionExecutor(
            kuma
        ).execute(
            FakeStep()
        )

        self.assertEqual(kuma.calls, 1)
        self.assertFalse(result.success)
        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

    def test_dangerous_changed_unsatisfied_state_never_resumes(self):
        kuma = FakeKuma(
            [
                self.failure(
                    tool_name="execute_command"
                ),
            ]
        )

        executor = KumaMissionExecutor(kuma)
        executor.state_verifier = FixedStateVerifier(
            changed=True
        )
        executor.objective_verifier = FixedObjectiveVerifier(
            satisfied=False
        )

        result = executor.execute(
            FakeStep()
        )

        self.assertEqual(kuma.calls, 1)
        self.assertFalse(result.success)
        self.assertEqual(
            result.recovery_action,
            "escalate",
        )
        self.assertNotEqual(
            result.recovery_action,
            "resume",
        )

    def test_dangerous_known_unchanged_state_still_does_not_retry(self):
        kuma = FakeKuma(
            [
                self.failure(
                    tool_name="execute_command"
                ),
                self.success(
                    tool_name="execute_command"
                ),
            ]
        )

        executor = KumaMissionExecutor(kuma)
        executor.state_verifier = FixedStateVerifier(
            changed=False
        )
        executor.objective_verifier = FixedObjectiveVerifier(
            satisfied=False
        )

        result = executor.execute(
            FakeStep()
        )

        self.assertEqual(kuma.calls, 1)
        self.assertFalse(result.success)
        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

    def test_independently_satisfied_dangerous_objective_is_accepted_without_reexecution(
        self,
    ):
        kuma = FakeKuma(
            [
                self.failure(
                    tool_name="execute_command"
                ),
                self.success(
                    tool_name="execute_command"
                ),
            ]
        )

        executor = KumaMissionExecutor(kuma)
        executor.state_verifier = FixedStateVerifier(
            changed=True
        )
        executor.objective_verifier = FixedObjectiveVerifier(
            satisfied=True
        )

        result = executor.execute(
            FakeStep()
        )

        self.assertEqual(kuma.calls, 1)
        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertTrue(result.completed)
        self.assertEqual(
            result.recovery_action,
            "",
        )


if __name__ == "__main__":
    unittest.main()
