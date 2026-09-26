import unittest

from app.agent.goal_decision import (
    GoalDecision,
    GoalStatus,
    parse_goal_decision,
)

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
)


class TestGoalDecision(unittest.TestCase):

    def test_continue_decision(self):
        decision, error = parse_goal_decision(
            """
            {
                "status": "continue",
                "remaining_objective": "Inspect the screen.",
                "next_action": "analyze_screen",
                "reason": "The user's request is not complete."
            }
            """
        )

        self.assertIsNone(error)
        self.assertIsNotNone(decision)
        self.assertEqual(
            decision.status,
            GoalStatus.CONTINUE,
        )
        self.assertTrue(
            decision.should_continue
        )

    def test_complete_decision(self):
        decision, error = parse_goal_decision(
            """
            {
                "status": "complete",
                "remaining_objective": "",
                "next_action": "",
                "reason": "The entire goal has been satisfied."
            }
            """
        )

        self.assertIsNone(error)
        self.assertIsNotNone(decision)
        self.assertEqual(
            decision.status,
            GoalStatus.COMPLETE,
        )
        self.assertTrue(
            decision.is_complete
        )

    def test_blocked_decision(self):
        decision, error = parse_goal_decision(
            """
            {
                "status": "blocked",
                "remaining_objective": "",
                "next_action": "",
                "reason": "Required capability is unavailable."
            }
            """
        )

        self.assertIsNone(error)
        self.assertIsNotNone(decision)
        self.assertEqual(
            decision.status,
            GoalStatus.BLOCKED,
        )
        self.assertTrue(
            decision.is_blocked
        )

    def test_invalid_status_is_rejected(self):
        decision, error = parse_goal_decision(
            """
            {
                "status": "banana",
                "remaining_objective": "",
                "next_action": "",
                "reason": "Invalid."
            }
            """
        )

        self.assertIsNone(decision)
        self.assertIsNotNone(error)

    def test_missing_remaining_objective_is_rejected(self):
        decision, error = parse_goal_decision(
            """
            {
                "status": "continue",
                "remaining_objective": "",
                "next_action": "something",
                "reason": "More work remains."
            }
            """
        )

        self.assertIsNone(decision)
        self.assertIsNotNone(error)

    def test_non_json_is_rejected(self):
        decision, error = parse_goal_decision(
            "not json"
        )

        self.assertIsNone(decision)
        self.assertIsNotNone(error)

    def test_complete_has_no_remaining_objective(self):
        decision, error = parse_goal_decision(
            """
            {
                "status": "complete",
                "remaining_objective": "Still do something.",
                "next_action": "",
                "reason": "Incorrect completion."
            }
            """
        )

        self.assertIsNone(decision)
        self.assertIsNotNone(error)

    def test_continue_updates_remaining_objective(self):
        decision, error = parse_goal_decision(
            """
            {
                "status": "continue",
                "remaining_objective": "Build the backend.",
                "next_action": "implement_backend",
                "reason": "Backend work remains."
            }
            """
        )

        self.assertIsNone(error)
        self.assertEqual(
            decision.remaining_objective,
            "Build the backend.",
        )
        self.assertEqual(
            decision.next_action,
            "implement_backend",
        )

    def test_rich_step_metadata(self):
        step = GoalStep(
            id="backend",
            objective="Implement the backend service.",
            success_criteria=[
                "API starts successfully.",
                "Core endpoints pass tests.",
            ],
            required_capabilities=[
                "filesystem",
                "terminal",
            ],
            risk_level="high",
            artifacts=[
                "backend source",
                "automated tests",
            ],
            verification_requirements=[
                "Run automated tests.",
                "Start the application.",
            ],
        )

        plan = GoalPlan(
            goal="Build an advanced application."
        )

        plan.add_step(step)

        valid, error = plan.validate()

        self.assertTrue(valid)
        self.assertIsNone(error)

        self.assertIn(
            "API starts successfully.",
            plan.summary(),
        )

        self.assertIn(
            "filesystem",
            plan.summary(),
        )

        self.assertIn(
            "Risk: high",
            plan.summary(),
        )

        self.assertIn(
            "Run automated tests.",
            plan.summary(),
        )


if __name__ == "__main__":
    unittest.main()
