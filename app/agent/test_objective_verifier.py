import unittest

from app.agent.objective_verifier import (
    ObjectiveVerificationResult,
    ObjectiveVerifier,
)

from app.agent.recovery_state_verifier import (
    StateVerificationResult,
)


class TestObjectiveVerifier(unittest.TestCase):

    def test_unknown_state_is_conservative(self):
        verifier = ObjectiveVerifier()

        state = StateVerificationResult(
            known=False,
            state_changed=None,
            summary="State unknown.",
            evidence="",
            state="unknown",
        )

        result = verifier.verify(
            objective="Complete the mission step.",
            success_criteria=[
                "The expected end-state is observable.",
            ],
            verification_requirements=[
                "Inspect the end-state independently.",
            ],
            tool_name="test_tool",
            arguments={},
            state=state,
        )

        self.assertIsInstance(
            result,
            ObjectiveVerificationResult,
        )
        self.assertFalse(result.known)
        self.assertIsNone(result.satisfied)

    def test_known_state_is_not_automatically_success(self):
        verifier = ObjectiveVerifier()

        state = StateVerificationResult(
            known=True,
            state_changed=True,
            summary="A state was observed.",
            evidence="observed-state",
            state="changed",
        )

        result = verifier.verify(
            objective="Complete the mission step.",
            success_criteria=[
                "Expected result exists.",
            ],
            verification_requirements=[
                "Verify expected result.",
            ],
            tool_name="test_tool",
            arguments={},
            state=state,
        )

        self.assertFalse(result.known)
        self.assertIsNone(result.satisfied)
        self.assertIn(
            "No deterministic objective verifier",
            result.summary,
        )

    def test_missing_objective_is_unknown(self):
        verifier = ObjectiveVerifier()

        state = StateVerificationResult(
            known=True,
            state_changed=False,
            summary="Observed.",
            evidence="evidence",
            state="present",
        )

        result = verifier.verify(
            objective="",
            state=state,
        )

        self.assertFalse(result.known)
        self.assertIsNone(result.satisfied)

    def test_verifier_does_not_modify_inputs(self):
        verifier = ObjectiveVerifier()

        arguments = {
            "target": "example",
        }

        criteria = [
            "Expected end-state.",
        ]

        requirements = [
            "Independent verification.",
        ]

        arguments_before = dict(arguments)
        criteria_before = list(criteria)
        requirements_before = list(requirements)

        state = StateVerificationResult(
            known=True,
            state_changed=False,
            summary="Observed.",
            evidence="evidence",
            state="present",
        )

        verifier.verify(
            objective="Complete the step.",
            success_criteria=criteria,
            verification_requirements=requirements,
            tool_name="test_tool",
            arguments=arguments,
            state=state,
        )

        self.assertEqual(
            arguments,
            arguments_before,
        )
        self.assertEqual(
            criteria,
            criteria_before,
        )
        self.assertEqual(
            requirements,
            requirements_before,
        )

    def test_unknown_result_preserves_state_evidence(self):
        verifier = ObjectiveVerifier()

        state = StateVerificationResult(
            known=True,
            state_changed=True,
            summary="Observed.",
            evidence="trusted-state-evidence",
            state="changed",
        )

        result = verifier.verify(
            objective="Complete the step.",
            tool_name="test_tool",
            state=state,
        )

        self.assertEqual(
            result.evidence,
            "trusted-state-evidence",
        )


if __name__ == "__main__":
    unittest.main()
