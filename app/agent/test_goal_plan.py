import unittest

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)


class TestGoalPlan(unittest.TestCase):

    def test_valid_plan(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="requirements",
                objective="Define requirements.",
            )
        )

        plan.add_step(
            GoalStep(
                id="architecture",
                objective="Design architecture.",
                dependencies=["requirements"],
            )
        )

        valid, error = plan.validate()

        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_dependency_controls_next_step(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="requirements",
                objective="Define requirements.",
            )
        )

        plan.add_step(
            GoalStep(
                id="architecture",
                objective="Design architecture.",
                dependencies=["requirements"],
            )
        )

        next_step = plan.next_pending_step()

        self.assertIsNotNone(next_step)
        self.assertEqual(
            next_step.id,
            "requirements",
        )

        next_step.status = (
            StepStatus.COMPLETED
        )

        next_step = plan.next_pending_step()

        self.assertIsNotNone(next_step)
        self.assertEqual(
            next_step.id,
            "architecture",
        )

    def test_unknown_dependency_is_rejected(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="frontend",
                objective="Build the frontend.",
                dependencies=["database"],
            )
        )

        valid, error = plan.validate()

        self.assertFalse(valid)
        self.assertIn(
            "unknown dependency",
            error.lower(),
        )

    def test_plan_json_round_trip(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="requirements",
                objective="Define requirements.",
                status=StepStatus.COMPLETED,
                result="Requirements complete.",
                dependencies=[],
                success_criteria=[
                    "Requirements are documented."
                ],
                required_capabilities=[
                    "filesystem"
                ],
                risk_level="normal",
                artifacts=[
                    "requirements.md"
                ],
                verification_requirements=[
                    "Review the requirements."
                ],
            )
        )

        plan.add_step(
            GoalStep(
                id="implementation",
                objective="Implement the application.",
                dependencies=[
                    "requirements"
                ],
                success_criteria=[
                    "Application starts."
                ],
                required_capabilities=[
                    "terminal"
                ],
                risk_level="normal",
                artifacts=[
                    "app.py"
                ],
                verification_requirements=[
                    "Run the application."
                ],
            )
        )

        plan.current_step_id = "implementation"

        restored = GoalPlan.from_json(
            plan.to_json()
        )

        self.assertEqual(
            restored.goal,
            plan.goal,
        )

        self.assertEqual(
            restored.current_step_id,
            "implementation",
        )

        self.assertEqual(
            restored.steps[0].status,
            StepStatus.COMPLETED,
        )

        self.assertEqual(
            restored.steps[0].result,
            "Requirements complete.",
        )

        self.assertEqual(
            restored.steps[1].dependencies,
            ["requirements"],
        )

        self.assertEqual(
            restored.steps[0].required_capabilities,
            ["filesystem"],
        )

    def test_duplicate_ids_are_rejected(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="build",
                objective="Build it.",
            )
        )

        plan.add_step(
            GoalStep(
                id="build",
                objective="Build it again.",
            )
        )

        valid, error = plan.validate()

        self.assertFalse(valid)
        self.assertIn(
            "duplicate",
            error.lower(),
        )

    def test_invalid_restored_step_status_is_rejected(self):

        raw = {
            "goal": "Build an application.",
            "steps": [
                {
                    "id": "build",
                    "objective": "Build it.",
                    "status": "banana",
                }
            ],
        }

        with self.assertRaises(ValueError):
            GoalPlan.from_dict(raw)


    def test_invalid_current_step_is_rejected(self):

        raw = {
            "goal": "Build an application.",
            "current_step_id": "missing",
            "steps": [
                {
                    "id": "build",
                    "objective": "Build it.",
                }
            ],
        }

        with self.assertRaises(ValueError):
            GoalPlan.from_dict(raw)

    def test_plan_is_not_complete_with_pending_steps(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="build",
                objective="Build it.",
            )
        )

        self.assertFalse(
            plan.is_complete()
        )

    def test_plan_becomes_complete(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="build",
                objective="Build it.",
            )
        )

        plan.steps[0].status = (
            StepStatus.COMPLETED
        )

        self.assertTrue(
            plan.is_complete()
        )


if __name__ == "__main__":
    unittest.main()